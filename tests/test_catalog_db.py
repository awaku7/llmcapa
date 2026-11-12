"""SQLite generation must preserve bundled registry contents and precedence."""

import json
import sqlite3
from contextlib import closing

import pytest

from llmcapa import Capability
from llmcapa import registry as registry_module
from llmcapa._catalog_db import build_catalog


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
    for filename, record in (
        ("openai.json", native),
        ("openrouter.json", aggregator),
    ):
        (data / filename).write_text(
            json.dumps({"models": [record]}), encoding="utf-8"
        )
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
    registry = registry_module.Registry()
    registry._load_bundled_files()
    destination = tmp_path / "catalog.sqlite3"
    build_catalog(destination)

    with closing(sqlite3.connect(destination)) as database:
        assert database.execute("PRAGMA user_version").fetchone() == (1,)
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
        for provider, models in registry._by_provider.items():
            rows = database.execute(
                """
                SELECT model_key, payload FROM models
                JOIN capabilities ON capabilities.id = models.capability_id
                WHERE provider = ? ORDER BY ordinal
                """,
                (provider,),
            )
            assert {
                key: Capability.from_dict(json.loads(payload)) for key, payload in rows
            } == models
        rows = database.execute(
            """
            SELECT model_key, payload FROM flat_models
            JOIN capabilities ON capabilities.id = flat_models.capability_id
            ORDER BY ordinal
            """
        )
        assert {
            key: Capability.from_dict(json.loads(payload)) for key, payload in rows
        } == registry._models
        assert dict(database.execute("SELECT * FROM aliases")) == registry._alias_index
        assert database.execute(
            "SELECT model_key FROM scoped_aliases WHERE provider = ? AND alias = ?",
            ("openrouter", "shared"),
        ).fetchone() == ("example",)
        assert set(database.execute("SELECT * FROM provider_files")) == {
            (provider, filename)
            for provider, filenames in registry._catalog_files_by_provider.items()
            for filename in filenames
        }


def test_failed_build_keeps_existing_database(tmp_path, monkeypatch):
    destination = tmp_path / "catalog.sqlite3"
    destination.write_bytes(b"previous snapshot")

    def broken(_self):
        raise ValueError("invalid catalog")

    monkeypatch.setattr(registry_module.Registry, "_load_bundled_files", broken)
    with pytest.raises(ValueError, match="invalid catalog"):
        build_catalog(destination)
    assert destination.read_bytes() == b"previous snapshot"
