"""Lazy, read-only access to the bundled capability index."""

from __future__ import annotations

import json
import sqlite3
import zlib
from collections.abc import Mapping
from contextlib import closing
from importlib import resources
from pathlib import Path
from threading import RLock

from .models import Capability

_READ_ERRORS = (OSError, sqlite3.Error, ValueError, KeyError, TypeError, zlib.error)


class CatalogIndex:
    """Share decoded capabilities across flat and provider-scoped indexes."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self._lock = RLock()
        self._objects: dict[int, Capability] = {}
        self._block_id = None
        self._block = []
        self._fallback = None

    def _connect(self):
        return closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True))

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
                if conn.execute("PRAGMA user_version").fetchone() != (1,):
                    return None
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

    def index(self, table, provider=None):
        return _Index(self, table, provider)


class _Index(Mapping):
    """Read-only mapping implementing the existing registry lookup contract."""

    def __init__(self, reader, table, provider):
        self.reader = reader
        self.table = table
        self.provider = provider

    def __getitem__(self, key):
        rows = self.reader.read(self.table, self.provider, key=key)
        if not rows:
            raise KeyError(key)
        return rows[0][1]

    def __iter__(self):
        rows = self.reader.read(self.table, self.provider, keys_only=True)
        return iter(row[0] for row in rows)

    def __len__(self):
        return len(self.reader.read(self.table, self.provider, keys_only=True))

    def items(self):
        return self.reader.read(self.table, self.provider)

    def values(self):
        return [value for _, value in self.items()]
