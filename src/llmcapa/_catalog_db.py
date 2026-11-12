"""Build the bundled SQLite lookup index from the authoritative JSON files."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .models import Capability
from .registry import Registry

_SCHEMA = """
PRAGMA user_version = 1;
CREATE TABLE capabilities (
    id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE providers (
    provider TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL
);
CREATE TABLE models (
    provider TEXT NOT NULL REFERENCES providers(provider),
    model_key TEXT NOT NULL,
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (provider, model_key)
);
CREATE TABLE flat_models (
    model_key TEXT PRIMARY KEY,
    capability_id INTEGER NOT NULL REFERENCES capabilities(id),
    ordinal INTEGER NOT NULL
);
CREATE TABLE aliases (
    alias TEXT PRIMARY KEY,
    model_key TEXT NOT NULL REFERENCES flat_models(model_key)
);
CREATE TABLE scoped_aliases (
    provider TEXT NOT NULL,
    alias TEXT NOT NULL,
    model_key TEXT NOT NULL,
    PRIMARY KEY (provider, alias),
    FOREIGN KEY (provider, model_key) REFERENCES models(provider, model_key)
);
CREATE TABLE provider_files (
    provider TEXT NOT NULL,
    filename TEXT NOT NULL,
    PRIMARY KEY (provider, filename)
);
"""


def build_catalog(destination: Path) -> None:
    """Build a clean snapshot, preserving the registry's lookup precedence."""
    registry = Registry()
    registry._load_bundled_files()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Build off to the side; never publish a partial or invalid database.
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        temporary = Path(directory) / destination.name
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(_SCHEMA)
            ids: dict[int, int] = {}

            def capability_id(capability: Capability) -> int:
                key = id(capability)
                if key not in ids:
                    payload = json.dumps(
                        capability.to_dict(), ensure_ascii=False, separators=(",", ":")
                    )
                    cursor = connection.execute(
                        "INSERT INTO capabilities(payload) VALUES (?)", (payload,)
                    )
                    ids[key] = cursor.lastrowid
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
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("Invalid SQLite catalog")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("Invalid SQLite catalog references")

        temporary.replace(destination)
