"""Lazy, read-only access to the bundled capability index."""

from __future__ import annotations

import json
import re
import sqlite3
import zlib
from collections.abc import Mapping
from contextlib import ExitStack, closing, contextmanager, nullcontext
from importlib import resources
from pathlib import Path
from threading import RLock

from .models import Capability

_READ_ERRORS = (OSError, sqlite3.Error, ValueError, KeyError, TypeError, zlib.error)


_VERSION_RE = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)+|\d+)(?![A-Za-z])")


def parse_numeric_name(value: str):
    text = value.strip().lower()
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    version = tuple(int(part) for part in match.group(1).split("."))
    shape = text[: match.start()] + "<version>" + text[match.end() :]
    return shape, version


def _prefix_end(prefix: str):
    for position in range(len(prefix) - 1, -1, -1):
        if ord(prefix[position]) < 0x10FFFF:
            return prefix[:position] + chr(ord(prefix[position]) + 1)
    return None


class CatalogIndex:
    """Share decoded capabilities across flat and provider-scoped indexes."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self._lock = RLock()
        self._objects: dict[int, Capability] = {}
        self._block_id = None
        self._block = []
        self._fallback = None
        self._batch_stack = None
        self._batch_connection = None

    def _connect(self):
        if self._batch_stack is None:
            return closing(
                sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
            )
        if self._batch_connection is None:
            self._batch_connection = self._batch_stack.enter_context(
                closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True))
            )
        return nullcontext(self._batch_connection)

    @contextmanager
    def batch(self):
        """Reuse a read-only connection during cache registration, then close it."""
        with self._lock:
            if self._batch_stack is not None:
                yield
                return
            with ExitStack() as stack:
                self._batch_stack = stack
                try:
                    yield
                finally:
                    self._batch_connection = None
                    self._batch_stack = None

    @classmethod
    def open(cls):
        """Return a usable snapshot, or None when JSON must remain authoritative."""
        directory = resources.files("llmcapa.data")
        if not isinstance(directory, Path):
            return None
        database = (directory / "catalog.sqlite3").resolve()
        if not database.is_file():
            return None
        reader = cls(database)
        try:
            db_time = database.stat().st_mtime_ns
            marker = directory / ".catalog.sqlite3.stale"
            if marker.exists() and marker.stat().st_mtime_ns >= db_time:
                return None
            # Verify authoritative content once per reader, not on each lookup.
            from ._catalog_db import _catalog_sources

            with reader._connect() as conn:
                version = conn.execute("PRAGMA user_version").fetchone()
                if version not in ((1,), (2,)):
                    return None
                reader._schema_version = version[0]
                if reader._schema_version == 2:
                    conn.execute(
                        "SELECT capability_id, kind, name, shape FROM lookup_names LIMIT 0"
                    )
                expected = dict(
                    conn.execute("SELECT filename, sha256 FROM catalog_sources")
                )
                if expected != _catalog_sources():
                    return None
                reader.providers = [
                    row[0]
                    for row in conn.execute(
                        "SELECT provider FROM providers ORDER BY ordinal"
                    )
                ]
                reader.provider_files = {}
                for provider, filename in conn.execute(
                    "SELECT provider, filename FROM provider_files"
                ):
                    reader.provider_files.setdefault(provider, set()).add(filename)
                # Check the query schema without reading or decoding model data.
                for table, columns in (
                    ("models", "provider, model_key, capability_id, ordinal"),
                    ("flat_models", "model_key, capability_id, ordinal"),
                    ("aliases", "alias, model_key"),
                    ("capabilities", "id, block_id, position"),
                    ("capability_blocks", "id, payload"),
                ):
                    conn.execute(f"SELECT {columns} FROM {table} LIMIT 0")
        except _READ_ERRORS:
            return None
        return reader

    def _capability(self, conn, record_id, block_id, position):
        cap = self._objects.get(record_id)
        if cap is not None:
            return cap
        if block_id != self._block_id:
            row = conn.execute(
                "SELECT payload FROM capability_blocks WHERE id = ?", (block_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Missing capability block")
            block = json.loads(zlib.decompress(row[0]))
            if not isinstance(block, list):
                raise ValueError("Invalid capability block")
            self._block = block
            self._block_id = block_id
        if not 0 <= position < len(self._block):
            raise ValueError("Invalid capability position")
        record = self._block[position]
        if not isinstance(record, dict):
            raise TypeError("Invalid capability record")
        try:
            cap = Capability.from_dict(record)
        except AttributeError as exc:
            raise ValueError("Invalid nested capability record") from exc
        self._objects[record_id] = cap
        return cap

    def _json_index(self, table, provider):
        if self._fallback is None:
            # Import lazily to keep the JSON-only builder independent.
            from .registry import Registry

            registry = Registry()
            registry._load_bundled_files()
            self._fallback = registry
        if table == "models":
            return self._fallback._by_provider.get(provider, {})
        if table == "aliases":
            return self._fallback._alias_index
        return self._fallback._models

    def read(self, table, provider=None, key=None, keys_only=False):
        """Read an index in registry insertion order."""
        key_column = "alias" if table == "aliases" else "model_key"
        columns = f"i.{key_column}"
        join = ""
        if not keys_only:
            if table == "aliases":
                columns += ", i.model_key"
            else:
                columns += ", c.id, c.block_id, c.position"
                join = " JOIN capabilities AS c ON c.id = i.capability_id"
        conditions = []
        args = []
        if provider is not None:
            conditions.append("i.provider = ?")
            args.append(provider)
        if key is not None:
            conditions.append(f"i.{key_column} = ?")
            args.append(key)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        order = "" if table == "aliases" else " ORDER BY i.ordinal"
        with self._lock:
            if self._fallback is None:
                try:
                    with self._connect() as conn:
                        rows = conn.execute(
                            f"SELECT {columns} FROM {table} AS i{join}{where}{order}",
                            args,
                        )
                        if keys_only or table == "aliases":
                            return list(rows)
                        return [
                            (row[0], self._capability(conn, *row[1:])) for row in rows
                        ]
                except _READ_ERRORS:
                    pass
            fallback = self._json_index(table, provider)
            if key is not None:
                items = [(key, fallback[key])] if key in fallback else []
            else:
                items = fallback.items()
            if keys_only:
                return [(name,) for name, _ in items]
            return list(items)

    def candidate_ids(self, kind, term):
        """Find potential matches without decompressing capability payloads."""
        if self._schema_version < 2 or self._fallback is not None:
            return None
        if kind == "alias":
            where = "kind IN ('alias', 'alias_exact') AND name = ?"
            args = [term]
        elif kind == "numeric":
            where = "shape = ?"
            args = [term]
        else:
            end = _prefix_end(term)
            where = "name >= ?"
            args = [term]
            if end is not None:
                where += " AND name < ?"
                args.append(end)
        with self._lock:
            try:
                with self._connect() as conn:
                    return {
                        row[0]
                        for row in conn.execute(
                            f"SELECT DISTINCT capability_id FROM lookup_names WHERE {where}",
                            args,
                        )
                    }
            except _READ_ERRORS:
                return None

    def matching_items(self, table, provider, candidate_ids, updates):
        """Read candidates in base order, then append new overlay keys."""
        if candidate_ids is None:
            combined = dict(self.read(table, provider))
            combined.update(updates)
            return combined.items()
        where = " WHERE i.provider = ?" if provider is not None else ""
        args = [provider] if provider is not None else []
        with self._lock:
            if self._fallback is None:
                try:
                    with self._connect() as conn:
                        result = {}
                        for key, record_id, block_id, position in conn.execute(
                            f"SELECT i.model_key, c.id, c.block_id, c.position "
                            f"FROM {table} AS i JOIN capabilities AS c "
                            f"ON c.id = i.capability_id{where} ORDER BY i.ordinal",
                            args,
                        ):
                            if key in updates:
                                result[key] = updates[key]
                            elif (
                                record_id in candidate_ids
                                or record_id in self._objects
                            ):
                                # Already decoded objects may have been mutated by callers.
                                result[key] = self._capability(
                                    conn, record_id, block_id, position
                                )
                        result.update(updates)
                        return result.items()
                except _READ_ERRORS:
                    pass
            combined = dict(self._json_index(table, provider))
            combined.update(updates)
            return combined.items()

    def index(self, table, provider=None):
        return CatalogMapping(self, table, provider)


class CatalogMapping(Mapping):
    """SQLite-backed mapping with in-memory additions and replacements."""

    def __init__(self, reader, table, provider):
        self.reader = reader
        self.table = table
        self.provider = provider
        self._updates = {}

    def __getitem__(self, key):
        if key in self._updates:
            return self._updates[key]
        rows = self.reader.read(self.table, self.provider, key=key)
        if not rows:
            raise KeyError(key)
        return rows[0][1]

    def __setitem__(self, key, value):
        self._updates[key] = value

    def __contains__(self, key):
        return key in self._updates or bool(
            self.reader.read(self.table, self.provider, key=key, keys_only=True)
        )

    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    def __iter__(self):
        rows = self.reader.read(self.table, self.provider, keys_only=True)
        keys = dict.fromkeys(row[0] for row in rows)
        keys.update(dict.fromkeys(self._updates))
        return iter(keys)

    def __len__(self):
        return sum(1 for _ in self)

    def items(self):
        combined = dict(self.reader.read(self.table, self.provider))
        combined.update(self._updates)
        return combined.items()

    def values(self):
        return [value for _, value in self.items()]

    def matching_values(self, candidate_ids):
        return [
            value
            for _, value in self.reader.matching_items(
                self.table, self.provider, candidate_ids, self._updates
            )
        ]
