"""Runtime SQLite parity and fallback tests using a small authoritative catalog."""

import json
import os
import sqlite3
import zlib
from contextlib import closing

import pytest

from llmcapa import registry as registry_module
from llmcapa._catalog_db import build_catalog
from llmcapa.models import Capability
from llmcapa.registry import Registry


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(registry_module.Path, "home", lambda: home)
    monkeypatch.setattr(registry_module.resources, "files", lambda package: data)
    monkeypatch.setattr(
        Registry, "_refresh_provider_catalog_on_miss", lambda self, provider: False
    )

    def write(name, records):
        (data / name).write_text(json.dumps(records), encoding="utf-8")

    write(
        "openai.json",
        [
            {
                "provider": "openai",
                "model_id": "gpt-demo-1.2",
                "display_name": "Demo model",
                "aliases": ["demo", "shared"],
                "context_window": 1000,
                "supports_vision": True,
            },
            {
                "provider": "openai",
                "model_id": "gpt-demo-1.4",
                "deprecated": True,
            },
        ],
    )
    write(
        "openrouter.json",
        [
            {
                "provider": "openrouter",
                "model_id": "gpt-demo-1.2",
                "aliases": ["shared"],
                "context_window": 2000,
            },
            {
                "provider": "openrouter",
                "model_id": "router-only",
                "aliases": ["route"],
            },
        ],
    )
    database = data / "catalog.sqlite3"
    build_catalog(database)
    return data, database


def json_registry():
    registry = Registry()
    registry._load_bundled_files()
    registry._loaded = True
    return registry


def test_sqlite_lookup_is_lazy_and_matches_json(catalog, monkeypatch):
    baseline = json_registry()

    def unexpected_json(self):
        pytest.fail("SQLite lookup must not load the JSON catalog")

    monkeypatch.setattr(Registry, "_load_bundled_files", unexpected_json)
    registry = Registry()
    result = registry.get("gpt-demo-1.2", "open-ai")
    assert result == baseline.get("gpt-demo-1.2", "open-ai")
    assert registry._catalog_index is not None
    assert len(registry._catalog_index._objects) == 1
    assert registry.get("demo") is result
    for model, provider in (
        ("shared", None),
        ("shared", "openrouter"),
        ("route", "openrouter"),
        ("gpt-demo-1.3", "openai"),
    ):
        assert registry.get(model, provider) == baseline.get(model, provider)
    assert registry.providers() == baseline.providers()
    for provider in (None, "open-ai", "openrouter"):
        for deprecated in (False, True):
            assert registry.list_models(provider, deprecated) == baseline.list_models(
                provider, deprecated
            )
            assert registry.search(
                "gpt", provider, deprecated, limit=2
            ) == baseline.search("gpt", provider, deprecated, limit=2)
            assert registry.find(
                provider=provider, include_deprecated=deprecated, vision=True
            ) == baseline.find(
                provider=provider, include_deprecated=deprecated, vision=True
            )
    assert registry.find_by_model_id("gpt-demo-1.2") == baseline.find_by_model_id(
        "gpt-demo-1.2"
    )


def test_overlay_preserves_identity_and_user_registration(catalog):
    registry = Registry()
    original = registry.get("demo")
    assert registry._catalog_index is not None
    registry.register(Capability(provider="custom", model_id="user-model"))
    assert registry._catalog_index is not None
    assert len(registry._catalog_index._objects) == 1
    assert registry.get("demo") is original
    assert registry.get("user-model").provider == "custom"
    registry.register(
        Capability(provider="openai", model_id="gpt-demo-1.2", context_window=9999),
        overwrite=True,
    )
    assert registry.get("gpt-demo-1.2", "openai").context_window == 9999


def test_load_extra_after_sqlite_lookup(catalog, tmp_path):
    registry = Registry()
    registry.get("demo")
    extra = tmp_path / "extra.json"
    extra.write_text(
        json.dumps([{"provider": "custom", "model_id": "extra"}]),
        encoding="utf-8",
    )
    assert registry.load_extra(extra) == 1
    assert registry.get("extra").provider == "custom"
    assert registry._catalog_index is not None


def test_refresh_invalidates_database(catalog, tmp_path):
    registry = Registry()
    registry.get("demo")
    assert registry._catalog_index is not None
    records = [{"provider": "openai", "model_id": "new-model"}]
    assert registry._write_bundled_catalog_files(
        {"openai.json": json.dumps(records)}, backup_dir=tmp_path / "backup"
    )
    fresh = Registry()
    assert fresh.get("new-model", "openai").provider == "openai"
    assert fresh._catalog_index is None


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_corrupt_database_falls_back(catalog, corrupt):
    _, database = catalog
    if corrupt:
        database.write_bytes(b"not a SQLite database")
    else:
        database.unlink()
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is None


@pytest.mark.parametrize("payload", [b"invalid", zlib.compress(b"[null]")])
def test_corrupt_payload_falls_back(catalog, payload):
    _, database = catalog
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("UPDATE capability_blocks SET payload = ?", (payload,))
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None
    assert registry._catalog_index._fallback is not None


def test_persistent_cache_overrides_sqlite(catalog, tmp_path):
    directory = tmp_path / "home" / ".llmcapa" / "catalogs" / "github"
    directory.mkdir(parents=True)
    (directory / "override.json").write_text(
        json.dumps(
            {
                "source": "https://github.com/awaku7/llmcapa",
                "providers": ["openai"],
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-demo-1.2",
                        "context_window": 3456,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = Registry()
    assert registry.get("gpt-demo-1.2", "openai").context_window == 3456
    assert registry._catalog_index is not None
    assert not registry._catalog_index._objects
    assert registry.get("gpt-demo-1.2").context_window == 3456
    assert registry.get("gpt-demo-1.2", "openrouter").context_window == 2000


def test_stale_source_with_preserved_mtime_falls_back(catalog):
    data, _ = catalog
    source = data / "openai.json"
    original = source.stat()
    records = json.loads(source.read_text(encoding="utf-8"))
    records[0]["context_window"] = 2000
    source.write_text(json.dumps(records), encoding="utf-8")
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))

    registry = Registry()
    assert registry.get("demo").context_window == 2000
    assert registry._catalog_index is None


def test_startup_cache_overlays_match_json_without_full_decode(catalog, tmp_path):
    home = tmp_path / "home" / ".llmcapa"
    cache = home / "github_catalog_cache"
    cache.mkdir(parents=True)
    (cache / "main.json").write_text(
        json.dumps(
            {
                "ref": "main",
                "providers": ["openai"],
                "files": {
                    "openai.json": json.dumps(
                        [
                            {
                                "provider": "openai",
                                "model_id": "gpt-demo-1.2",
                                "context_window": 2222,
                                "aliases": ["new-alias"],
                            }
                        ]
                    )
                },
            }
        ),
        encoding="utf-8",
    )
    # The cache loader ignores snapshots older than the installed source.
    bundled = registry_module.Path(registry_module.__file__).parent / "data"
    future = (bundled / "openai.json").stat().st_mtime + 1
    os.utime(cache / "main.json", (future, future))
    (home / "openrouter_cache.json").write_text(
        json.dumps([{"id": "cache-only", "context_length": 8192}]),
        encoding="utf-8",
    )

    baseline = json_registry()
    baseline._load_github_catalog_caches()
    baseline._load_persistent_github_catalogs()
    baseline._load_openrouter_cache()

    registry = Registry()
    assert registry.get("new-alias", "openai") == baseline.get("new-alias", "openai")
    assert registry.get("cache-only", "openrouter") == baseline.get(
        "cache-only", "openrouter"
    )
    index = registry._catalog_index
    assert index is not None
    assert not index._objects
    assert not index._batch_metadata
    assert index._batch_owners is None
    assert index._batch_connection is None
    assert index._batch_stack is None

    for provider in (None, "openai", "openrouter"):
        assert registry.list_models(provider, True) == baseline.list_models(
            provider, True
        )
        assert registry.search("", provider, True) == baseline.search(
            "", provider, True
        )
    assert registry.providers() == baseline.providers()


def test_large_persistent_override_avoids_decoding_bundled_records(
    catalog, tmp_path, monkeypatch
):
    from llmcapa._catalog_index import CatalogIndex

    data, database = catalog
    records = [
        {
            "provider": "openai",
            "model_id": f"large-{n}",
            "aliases": [f"alias-{n}"],
            "context_window": 100,
        }
        for n in range(600)
    ]
    (data / "openai.json").write_text(json.dumps(records), encoding="utf-8")
    build_catalog(database)

    directory = tmp_path / "home" / ".llmcapa" / "catalogs" / "github"
    directory.mkdir(parents=True)
    updated = [{**record, "context_window": 200} for record in reversed(records)]
    (directory / "override.json").write_text(
        json.dumps(
            {
                "source": "https://github.com/awaku7/llmcapa",
                "providers": ["openai"],
                "models": updated,
            }
        ),
        encoding="utf-8",
    )

    def unexpected_decode(self, *args):
        pytest.fail("Persistent overrides must not decode replaced bundled records")

    monkeypatch.setattr(CatalogIndex, "_capability", unexpected_decode)
    registry = Registry()
    assert registry.get("large-0", "openai").context_window == 200
    assert registry.get("alias-599").context_window == 200
    assert registry._catalog_index is not None
    assert not registry._catalog_index._objects


def test_registration_metadata_preserves_flat_owner(catalog):
    registry = Registry()
    original = registry.get("gpt-demo-1.2")
    index = registry._catalog_index
    assert index is not None
    with index.batch():
        registry._register_refreshed_catalog_record(
            Capability(
                provider="openrouter", model_id="gpt-demo-1.2", context_window=789
            )
        )
    assert registry.get("gpt-demo-1.2") is original
    assert registry.get("gpt-demo-1.2", "openrouter").context_window == 789


def test_warm_user_cache_uses_sqlite_without_json_registration(
    catalog, tmp_path, monkeypatch
):
    home = tmp_path / "home" / ".llmcapa"
    directory = home / "catalogs" / "github"
    directory.mkdir(parents=True)
    path = directory / "override.json"
    path.write_text(
        json.dumps(
            {
                "source": "https://github.com/awaku7/llmcapa",
                "ref": "main",
                "providers": ["openai"],
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-demo-1.2",
                        "context_window": 1234,
                        "aliases": ["cached-alias"],
                    },
                    {
                        "provider": "openai",
                        "model_id": "new-cached-model",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    cold = Registry()
    cap = cold.get("cached-alias")
    assert cap.context_window == 1234
    assert list((home / "sqlite_cache").glob("cache-*.sqlite3"))

    def unexpected_load(self):
        pytest.fail("Warm startup must not parse persistent JSON")

    monkeypatch.setattr(Registry, "_load_startup_caches", unexpected_load)
    warm = Registry()
    result = warm.get("cached-alias")
    assert result == cap
    assert warm.get("gpt-demo-1.2", "openai") is result
    assert warm.get("new-cached-model", "openai").provider == "openai"
    assert warm._catalog_index is not None
    assert not warm._catalog_index._objects
    assert warm.list_models("openai") == cold.list_models("openai")
    assert path.exists()


def test_old_persistent_main_cache_is_removed(catalog, tmp_path):
    data, _ = catalog
    directory = tmp_path / "home" / ".llmcapa" / "catalogs" / "github"
    directory.mkdir(parents=True)
    path = directory / "old.json"
    path.write_text(
        json.dumps(
            {
                "source": "https://github.com/awaku7/llmcapa",
                "ref": "main",
                "providers": ["openai"],
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-demo-1.2",
                        "context_window": 9999,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    older = (data / "openai.json").stat().st_mtime - 10
    os.utime(path, (older, older))
    registry = Registry()
    assert registry.get("gpt-demo-1.2", "openai").context_window == 1000
    assert not path.exists()
