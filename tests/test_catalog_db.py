"""SQLite generation must preserve bundled registry contents and precedence."""

import json
import sqlite3
import zlib
from contextlib import closing

import pytest

from llmcapa import Capability, _catalog_db
from llmcapa import registry as registry_module
from llmcapa._catalog_db import build_catalog, check_catalog
from llmcapa._catalog_index import candidate_ids


def test_catalog_database_preserves_lookup_indexes(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    native = {
        "provider": "openai",
        "model_id": "example",
        "aliases": ["shared", "native"],
        "context_window": 1000,
        "max_output_tokens": 100,
    }
    aggregator = {
        **native,
        "provider": "openrouter",
        "aliases": ["shared", "router"],
        "context_window": 2000,
    }
    for filename, records in (
        ("openai.json", [native, {**native, "model_id": "second", "aliases": []}]),
        ("openrouter.json", [aggregator]),
    ):
        (data / filename).write_text(json.dumps({"models": records}), encoding="utf-8")
    monkeypatch.setattr(registry_module.resources, "files", lambda _: data)

    def unexpected_cache(_self):
        pytest.fail("build must not read local user caches")

    monkeypatch.setattr(
        registry_module.Registry, "_load_github_catalog_caches", unexpected_cache
    )
    monkeypatch.setattr(
        registry_module.Registry, "_load_persistent_github_catalogs", unexpected_cache
    )
    monkeypatch.setattr(
        registry_module.Registry, "_load_openrouter_cache", unexpected_cache
    )
    monkeypatch.setattr(_catalog_db, "_BLOCK_SIZE", 2)
    registry = registry_module.Registry()
    registry._load_bundled_files()
    destination = tmp_path / "catalog.sqlite3"
    build_catalog(destination)
    check_catalog(destination)

    with closing(sqlite3.connect(destination)) as database:
        assert database.execute("PRAGMA user_version").fetchone() == (3,)
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
        blocks = {
            key: json.loads(zlib.decompress(payload))
            for key, payload in database.execute(
                "SELECT id, payload FROM capability_blocks"
            )
        }
        assert [len(records) for records in blocks.values()] == [2, 1]
        for provider, models in registry._by_provider.items():
            rows = database.execute(
                """
                SELECT model_key, block_id, position FROM models
                JOIN capabilities ON capabilities.id = models.capability_id
                WHERE provider = ? ORDER BY ordinal
                """,
                (provider,),
            )
            assert {
                key: Capability.from_dict(blocks[block_id][position])
                for key, block_id, position in rows
            } == models
        rows = database.execute("""
            SELECT model_key, block_id, position FROM flat_models
            JOIN capabilities ON capabilities.id = flat_models.capability_id
            ORDER BY ordinal
            """)
        assert {
            key: Capability.from_dict(blocks[block_id][position])
            for key, block_id, position in rows
        } == registry._models
        assert dict(database.execute("SELECT * FROM aliases")) == registry._alias_index
        assert len(candidate_ids(database, "alias", "shared")) == 2
        assert database.execute(
            "SELECT COUNT(*) FROM strings WHERE value = ?", ("example",)
        ).fetchone() == (1,)
        assert database.execute(
            "SELECT COUNT(*) FROM model_entries WHERE model_key_id = "
            "(SELECT id FROM strings WHERE value = ?)",
            ("example",),
        ).fetchone() == (2,)
        assert (
            database.execute(
                "SELECT name FROM sqlite_master WHERE name = 'scoped_aliases'"
            ).fetchone()
            is None
        )
        assert set(database.execute("SELECT * FROM provider_files")) == {
            (provider, filename)
            for provider, filenames in registry._catalog_files_by_provider.items()
            for filename in filenames
        }

    source = data / "openai.json"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="Stale SQLite catalog"):
        check_catalog(destination)


def test_missing_catalog_is_not_generated_by_check(tmp_path):
    destination = tmp_path / "missing.sqlite3"
    with pytest.raises(RuntimeError, match="Missing SQLite catalog"):
        check_catalog(destination)
    assert not destination.exists()


def test_failed_build_keeps_existing_database(tmp_path, monkeypatch):
    destination = tmp_path / "catalog.sqlite3"
    destination.write_bytes(b"previous snapshot")

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(registry_module.resources, "files", lambda _: data)

    def broken(_self):
        raise ValueError("invalid catalog")

    monkeypatch.setattr(registry_module.Registry, "_load_bundled_files", broken)
    with pytest.raises(ValueError, match="invalid catalog"):
        build_catalog(destination)
    assert destination.read_bytes() == b"previous snapshot"


def test_compact_lookup_blocks_preserve_candidates(monkeypatch):
    from llmcapa import _catalog_index

    monkeypatch.setattr(_catalog_index, "_LOOKUP_BLOCK_SIZE", 2)
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.executescript(_catalog_index.LOOKUP_SCHEMA)
        builder = _catalog_index.LookupBuilder(conn)
        for record_id, cap in enumerate(
            (
                Capability(
                    provider="openai",
                    model_id="model-long-1.1",
                    display_name="模型Ａ",
                    aliases=[" shared ", "family-2.1"],
                ),
                Capability(
                    provider="openai",
                    model_id="model-long-1.2",
                    aliases=["shared"],
                ),
                Capability(provider="openai", model_id="model-long-1.3"),
            ),
            start=1,
        ):
            builder.add(record_id, cap)
        builder.finish()
        assert candidate_ids(conn, "alias", "shared") == {1, 2}
        assert candidate_ids(conn, "prefix", "m") == {1, 2, 3}
        assert candidate_ids(conn, "prefix", "model-long-1.2") == {2}
        assert candidate_ids(conn, "prefix", "模型") == {1}
        assert candidate_ids(conn, "numeric", "model-long-<version>") == {1, 2, 3}
        assert candidate_ids(conn, "numeric", "family-<version>") == {1}
        assert candidate_ids(conn, "prefix", "model-long-9") == set()
