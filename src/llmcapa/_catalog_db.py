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

from ._catalog_index import parse_numeric_name
from .models import Capability
from .registry import Registry

_BLOCK_SIZE = 256

_SCHEMA = """
PRAGMA user_version = 2;
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
CREATE TABLE lookup_names (
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    shape TEXT,
    PRIMARY KEY (capability_id, kind, name)
) WITHOUT ROWID;
CREATE INDEX lookup_names_prefix ON lookup_names(name);
CREATE INDEX lookup_names_shape ON lookup_names(shape) WHERE shape IS NOT NULL;
CREATE TABLE providers (
    provider TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE models (
    provider TEXT NOT NULL REFERENCES providers(provider),
    model_key TEXT NOT NULL,
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (provider, model_key)
) WITHOUT ROWID;
CREATE TABLE flat_models (
    model_key TEXT PRIMARY KEY,
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    ordinal INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE aliases (
    alias TEXT PRIMARY KEY,
    model_key TEXT NOT NULL REFERENCES flat_models(model_key)
) WITHOUT ROWID;
CREATE TABLE scoped_aliases (
    provider TEXT NOT NULL,
    alias TEXT NOT NULL,
    model_key TEXT NOT NULL,
    PRIMARY KEY (provider, alias),
    FOREIGN KEY (provider, model_key) REFERENCES models(provider, model_key)
) WITHOUT ROWID;
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
        if conn.execute("PRAGMA user_version").fetchone() != (2,):
            raise RuntimeError(
                "Unsupported SQLite catalog schema; run scripts/build_catalog_db.py"
            )
        conn.execute("SELECT capability_id, kind, name, shape FROM lookup_names LIMIT 0")
        if dict(conn.execute("SELECT * FROM catalog_sources")) != _catalog_sources():
            raise RuntimeError("Stale SQLite catalog; run scripts/build_catalog_db.py")
        if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("Invalid SQLite catalog")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Invalid SQLite catalog references")
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
            connection.executescript(_SCHEMA)
            connection.executemany(
                "INSERT INTO catalog_sources VALUES (?, ?)", sources.items()
            )
            ids: dict[int, int] = {}
            pending: list[dict] = []
            block_id = 1

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
                    names = [("model", capability.model_id)]
                    if capability.display_name:
                        names.append(("display", capability.display_name))
                    for alias in capability.aliases or []:
                        names.append(("alias", alias))
                        if alias.strip() != alias:
                            names.append(("alias_exact", alias.strip()))
                    rows = []
                    for kind, name in names:
                        parsed = (
                            parse_numeric_name(name)
                            if kind in ("model", "alias")
                            else None
                        )
                        rows.append(
                            (record_id, kind, name.lower(), parsed[0] if parsed else None)
                        )
                    connection.executemany(
                        "INSERT OR IGNORE INTO lookup_names VALUES (?, ?, ?, ?)", rows
                    )
                    pending.append(capability.to_dict())
                    if len(pending) == _BLOCK_SIZE:
                        flush_block()
                return ids[key]

            for provider_order, (provider, models) in enumerate(
                registry._by_provider.items()
            ):
                connection.execute(
                    "INSERT INTO providers VALUES (?, ?)", (provider, provider_order)
                )
                for order, (key, cap) in enumerate(models.items()):
                    connection.execute(
                        "INSERT INTO models VALUES (?, ?, ?, ?)",
                        (provider, key, capability_id(cap), order),
                    )
                    connection.executemany(
                        "INSERT OR IGNORE INTO scoped_aliases VALUES (?, ?, ?)",
                        [
                            (provider, str(alias).strip().lower(), key)
                            for alias in cap.aliases or []
                        ],
                    )

            for order, (key, cap) in enumerate(registry._models.items()):
                connection.execute(
                    "INSERT INTO flat_models VALUES (?, ?, ?)",
                    (key, capability_id(cap), order),
                )
            flush_block()
            connection.executemany(
                "INSERT INTO aliases VALUES (?, ?)", registry._alias_index.items()
            )
            connection.executemany(
                "INSERT INTO provider_files VALUES (?, ?)",
                (
                    (provider, filename)
                    for provider, filenames in registry._catalog_files_by_provider.items()
                    for filename in sorted(filenames)
                ),
            )
        check_catalog(temporary)
        if temporary.stat().st_size > 100 * 1024 * 1024:
            raise RuntimeError("SQLite catalog exceeds GitHub's 100 MiB file limit")
        temporary.replace(destination)
