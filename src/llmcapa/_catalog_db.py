"""Build the bundled SQLite lookup index from the authoritative JSON files."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zlib
from contextlib import closing
from importlib import resources
from pathlib import Path

from ._catalog_index import LOOKUP_SCHEMA, LookupBuilder, _decode_lookup_block
from .models import Capability
from .registry import Registry

_BLOCK_SIZE = 256

_SCHEMA = """
PRAGMA user_version = 3;
CREATE TABLE catalog_sources (
    filename TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE capability_blocks (
    id INTEGER PRIMARY KEY,
    payload BLOB NOT NULL,
    record_count INTEGER NOT NULL
);
CREATE TABLE capabilities (
    id INTEGER PRIMARY KEY,
    block_id INTEGER NOT NULL REFERENCES capability_blocks(id)
        DEFERRABLE INITIALLY DEFERRED,
    position INTEGER NOT NULL
);
CREATE TABLE strings (
    id INTEGER PRIMARY KEY,
    value TEXT NOT NULL UNIQUE
);
CREATE TABLE providers (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL UNIQUE,
    ordinal INTEGER NOT NULL
);
CREATE TABLE model_entries (
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    model_key_id INTEGER NOT NULL REFERENCES strings(id),
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (provider_id, model_key_id)
) WITHOUT ROWID;
CREATE TABLE flat_entries (
    model_key_id INTEGER PRIMARY KEY REFERENCES strings(id),
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    ordinal INTEGER NOT NULL
);
CREATE TABLE alias_entries (
    alias_id INTEGER PRIMARY KEY REFERENCES strings(id),
    model_key_id INTEGER NOT NULL REFERENCES flat_entries(model_key_id)
);
-- Keep the reader's logical schema stable across database versions.
CREATE VIEW models AS
    SELECT p.provider, s.value AS model_key, m.capability_id, m.ordinal
    FROM model_entries AS m
    JOIN providers AS p ON p.id = m.provider_id
    JOIN strings AS s ON s.id = m.model_key_id;
CREATE VIEW flat_models AS
    SELECT s.value AS model_key, f.capability_id, f.ordinal
    FROM flat_entries AS f
    JOIN strings AS s ON s.id = f.model_key_id;
CREATE VIEW aliases AS
    SELECT a.value AS alias, s.value AS model_key
    FROM alias_entries AS e
    JOIN strings AS a ON a.id = e.alias_id
    JOIN strings AS s ON s.id = e.model_key_id;
CREATE TABLE provider_files (
    provider TEXT NOT NULL,
    filename TEXT NOT NULL,
    PRIMARY KEY (provider, filename)
) WITHOUT ROWID;
"""


def _catalog_sources() -> dict[str, str]:
    """Fingerprint source files independently of Git's Windows newline conversion."""
    return {
        entry.name: hashlib.sha256(
            entry.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for entry in sorted(
            resources.files("llmcapa.data").iterdir(), key=lambda e: e.name
        )
        if entry.name.endswith((".json", ".meta")) and entry.is_file()
    }


def check_catalog(database: Path) -> None:
    """Validate the committed database without generating or changing it."""
    database = Path(database).resolve()
    if not database.is_file():
        raise RuntimeError("Missing SQLite catalog; run scripts/build_catalog_db.py")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA user_version").fetchone() != (3,):
            raise RuntimeError(
                "Unsupported SQLite catalog schema; run scripts/build_catalog_db.py"
            )
        conn.execute("SELECT kind, bucket, ordinal, payload FROM lookup_blocks LIMIT 0")
        if dict(conn.execute("SELECT * FROM catalog_sources")) != _catalog_sources():
            raise RuntimeError("Stale SQLite catalog; run scripts/build_catalog_db.py")
        if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("Invalid SQLite catalog")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Invalid SQLite catalog references")
        max_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM capabilities"
        ).fetchone()[0]
        for (payload,) in conn.execute("SELECT payload FROM lookup_blocks"):
            for _, record_id, _ in _decode_lookup_block(payload):
                if not 1 <= record_id <= max_id:
                    raise RuntimeError("Invalid SQLite lookup record reference")
        if conn.execute("""
            SELECT 1 FROM capabilities AS c
            JOIN capability_blocks AS b ON b.id = c.block_id
            WHERE c.position < 0 OR c.position >= b.record_count
            LIMIT 1
            """).fetchone():
            raise RuntimeError("Invalid SQLite catalog block positions")


def build_catalog(destination: Path) -> None:
    """Build a clean snapshot, preserving the registry's lookup precedence."""
    sources = _catalog_sources()
    registry = Registry()
    registry._load_bundled_files()
    if sources != _catalog_sources():
        raise RuntimeError("Source catalogs changed during SQLite generation")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Build off to the side; never publish a partial or invalid database.
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        temporary = Path(directory) / destination.name
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(_SCHEMA + LOOKUP_SCHEMA)
            lookup = LookupBuilder(connection)
            connection.executemany(
                "INSERT INTO catalog_sources VALUES (?, ?)", sources.items()
            )
            ids: dict[int, int] = {}
            string_ids: dict[str, int] = {}
            pending: list[dict] = []
            block_id = 1

            def string_id(value: str) -> int:
                if value not in string_ids:
                    key = len(string_ids) + 1
                    connection.execute(
                        "INSERT INTO strings VALUES (?, ?)", (key, value)
                    )
                    string_ids[value] = key
                return string_ids[value]

            def flush_block() -> None:
                nonlocal block_id
                if not pending:
                    return
                payload = zlib.compress(
                    json.dumps(
                        pending, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8"),
                    level=9,
                )
                connection.execute(
                    "INSERT INTO capability_blocks VALUES (?, ?, ?)",
                    (block_id, payload, len(pending)),
                )
                pending.clear()
                block_id += 1

            def capability_id(capability: Capability) -> int:
                key = id(capability)
                if key not in ids:
                    record_id = len(ids) + 1
                    connection.execute(
                        "INSERT INTO capabilities VALUES (?, ?, ?)",
                        (record_id, block_id, len(pending)),
                    )
                    ids[key] = record_id
                    lookup.add(record_id, capability)
                    pending.append(capability.to_dict())
                    if len(pending) == _BLOCK_SIZE:
                        flush_block()
                return ids[key]

            for provider_order, (provider, models) in enumerate(
                registry._by_provider.items()
            ):
                provider_id = provider_order + 1
                connection.execute(
                    "INSERT INTO providers VALUES (?, ?, ?)",
                    (provider_id, provider, provider_order),
                )
                for order, (key, cap) in enumerate(models.items()):
                    connection.execute(
                        "INSERT INTO model_entries VALUES (?, ?, ?, ?)",
                        (provider_id, string_id(key), capability_id(cap), order),
                    )

            for order, (key, cap) in enumerate(registry._models.items()):
                connection.execute(
                    "INSERT INTO flat_entries VALUES (?, ?, ?)",
                    (string_id(key), capability_id(cap), order),
                )
            flush_block()
            lookup.finish()
            connection.executemany(
                "INSERT INTO alias_entries VALUES (?, ?)",
                (
                    (string_id(alias), string_id(model_key))
                    for alias, model_key in registry._alias_index.items()
                ),
            )
            connection.executemany(
                "INSERT INTO provider_files VALUES (?, ?)",
                (
                    (provider, filename)
                    for provider, filenames in registry._catalog_files_by_provider.items()
                    for filename in sorted(filenames)
                ),
            )
            connection.commit()
            connection.execute("VACUUM")
        check_catalog(temporary)
        size = temporary.stat().st_size
        if size > 100 * 1024 * 1024:
            raise RuntimeError(
                f"SQLite catalog is {size / (1024 * 1024):.1f} MiB; "
                "exceeds GitHub's 100 MiB file limit"
            )
        temporary.replace(destination)
