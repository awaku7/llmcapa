"""Reusable SQLite snapshot of the user-owned startup catalog overrides."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import weakref
import zlib
from contextlib import closing
from pathlib import Path
from threading import RLock

from .models import Capability

ERRORS = (OSError, sqlite3.Error, ValueError, TypeError, KeyError, zlib.error)
_FORMAT = 1
_SCHEMA = """
CREATE TABLE metadata (signature TEXT NOT NULL);
CREATE TABLE maps (
    kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    PRIMARY KEY (kind, provider)
) WITHOUT ROWID;
CREATE TABLE records (
    id INTEGER PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE entries (
    kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    record_id INTEGER REFERENCES records(id),
    alias_value TEXT,
    owner TEXT,
    PRIMARY KEY (kind, provider, model_key)
) WITHOUT ROWID;
"""


def startup_signature(registry, home, now):
    """Fingerprint inputs cheaply; include TTL decisions and bundled content."""
    from importlib.metadata import PackageNotFoundError, version

    inputs = []
    for directory, pattern, expires in (
        (home / "catalogs" / "github", "*.json", False),
        (home / "github_catalog_cache", "*.json", True),
        (home, "openrouter_cache.json", True),
    ):
        for path in sorted(directory.glob(pattern)):
            info = path.stat()
            inputs.append(
                (
                    str(path.relative_to(home)),
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                    expires and now - info.st_mtime >= 86400,
                )
            )
    if not any((home / "catalogs" / "github").glob("*.json")):
        return None
    bundle = registry._catalog_index
    sources = bundle.source_fingerprints
    timestamps = []
    for name in sorted(sources):
        timestamps.append((name, (bundle.database.parent / name).stat().st_mtime_ns))
    try:
        package_version = version("llmcapa")
    except PackageNotFoundError:
        package_version = "source-tree"
    payload = [_FORMAT, package_version, sources, timestamps, inputs]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def overlay_maps(registry):
    """Yield only additions/replacements, not bundled capability payloads."""
    from ._catalog_index import CatalogMapping

    for kind, provider, mapping in (
        ("flat_models", "", registry._models),
        ("aliases", "", registry._alias_index),
        *(
            ("models", provider, mapping)
            for provider, mapping in registry._by_provider.items()
        ),
    ):
        yield (
            kind,
            provider,
            mapping._updates if isinstance(mapping, CatalogMapping) else mapping,
        )


def remove_old_generations(directory, keep, before_ns):
    """Remove superseded generations, never ones published during this startup."""
    try:
        paths = list(directory.glob("cache-*.sqlite3"))
    except OSError:
        return
    for path in paths:
        if path == keep:
            continue
        try:
            if path.stat().st_mtime_ns < before_ns:
                path.unlink()
        except OSError:
            # Another process may still have an immutable generation open.
            pass


def write_snapshot(path, signature, registry):
    """Publish an immutable generation atomically, after a successful build."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        with closing(sqlite3.connect(temporary)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_SCHEMA)
            conn.execute("INSERT INTO metadata VALUES (?)", (signature,))
            ids = {}
            for kind, provider, values in overlay_maps(registry):
                if not values and provider in registry._catalog_index.providers:
                    continue
                conn.execute("INSERT INTO maps VALUES (?, ?)", (kind, provider))
                rows = []
                for ordinal, (key, value) in enumerate(values.items()):
                    if kind == "aliases":
                        record_id, alias, owner = None, value, None
                    else:
                        identity = id(value)
                        if identity not in ids:
                            payload = zlib.compress(
                                json.dumps(
                                    value.to_dict(),
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ).encode("utf-8"),
                                level=1,
                            )
                            record_id = conn.execute(
                                "INSERT INTO records(payload) VALUES (?)", (payload,)
                            ).lastrowid
                            ids[identity] = record_id
                        record_id, alias, owner = ids[identity], None, value.provider
                    rows.append((kind, provider, key, ordinal, record_id, alias, owner))
                conn.executemany(
                    "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?)", rows
                )
        temporary.replace(path)


class UserCatalogCache:
    """One immutable snapshot, shared by all registry overlay mappings."""

    def __init__(self, path, signature, fallback):
        self._lock = RLock()
        self._objects = {}
        self._fallback_factory = fallback
        self._fallback = None
        conn = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        try:
            if conn.execute("SELECT signature FROM metadata").fetchone() != (
                signature,
            ):
                raise ValueError("User catalog cache signature mismatch")
            self.maps = list(conn.execute("SELECT kind, provider FROM maps"))
            conn.execute("SELECT * FROM entries LIMIT 0")
            conn.execute("SELECT * FROM records LIMIT 0")
        except BaseException:
            conn.close()
            raise
        self._connection = conn
        self._close = weakref.finalize(self, conn.close)

    def _value(self, record_id, alias):
        if record_id is None:
            return alias
        if record_id not in self._objects:
            row = self._connection.execute(
                "SELECT payload FROM records WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Missing cached capability")
            self._objects[record_id] = Capability.from_dict(
                json.loads(zlib.decompress(row[0]))
            )
        return self._objects[record_id]

    def read(self, kind, provider, key=None, *, keys_only=False, owner_only=False):
        provider = provider or ""
        with self._lock:
            if self._fallback is None:
                try:
                    where = "kind = ? AND provider = ?"
                    args = [kind, provider]
                    if key is not None:
                        where += " AND model_key = ?"
                        args.append(key)
                    rows = self._connection.execute(
                        "SELECT model_key, record_id, alias_value, owner "
                        f"FROM entries WHERE {where} ORDER BY ordinal",
                        args,
                    )
                    return [
                        (
                            name,
                            (
                                None
                                if keys_only
                                else (
                                    owner
                                    if owner_only
                                    else self._value(record_id, alias)
                                )
                            ),
                        )
                        for name, record_id, alias, owner in rows
                    ]
                except ERRORS + (AttributeError,):
                    self._fallback = {
                        (kind, provider): values
                        for kind, provider, values in overlay_maps(
                            self._fallback_factory()
                        )
                    }
                    self._close()
            values = self._fallback.get((kind, provider), {})
            items = (
                [(key, values[key])]
                if key is not None and key in values
                else ([] if key is not None else values.items())
            )
            return [
                (
                    name,
                    None if keys_only else (value.provider if owner_only else value),
                )
                for name, value in items
            ]
