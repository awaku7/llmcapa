"""Runtime SQLite parity and fallback tests using a small authoritative catalog."""

import json
import os
import sqlite3
import zlib
from contextlib import closing

import pytest

from llmcapa import registry as registry_module
from llmcapa._catalog_db import build_catalog
from llmcapa.models import Capability, RegionCapability
from llmcapa.registry import ModelNotFoundError, Registry


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
                "aliases": ["collision"],
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
                "aliases": ["route", "collision"],
            },
            {
                "provider": "openrouter",
                "model_id": "router-second",
                "aliases": ["collision"],
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


def test_persistent_github_catalogs_are_ignored(catalog, tmp_path):
    directory = tmp_path / "home" / ".llmcapa" / "catalogs" / "github"
    directory.mkdir(parents=True)
    path = directory / "override.json"
    path.write_text(
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
    assert registry.get("gpt-demo-1.2", "openai").context_window == 1000
    assert registry._catalog_index is not None
    assert registry.get("gpt-demo-1.2").context_window == 1000
    assert registry.get("gpt-demo-1.2", "openrouter").context_window == 2000
    assert path.exists()


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


def test_startup_ignores_github_catalog_cache_but_keeps_additive_openrouter_cache(
    catalog, tmp_path
):
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
    # Even a recent downloaded GitHub snapshot is never auto-applied at startup.
    bundled = registry_module.Path(registry_module.__file__).parent / "data"
    future = (bundled / "openai.json").stat().st_mtime + 1
    os.utime(cache / "main.json", (future, future))
    (home / "openrouter_cache.json").write_text(
        json.dumps([{"id": "cache-only", "context_length": 8192}]),
        encoding="utf-8",
    )

    baseline = json_registry()
    baseline._load_openrouter_cache()

    registry = Registry()
    with pytest.raises(ModelNotFoundError):
        registry.get("new-alias", "openai")
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


def test_unknown_model_does_not_decode_unrelated_records(catalog):
    registry = Registry()
    for provider in (None, "openai", "openrouter"):
        for model in ("not-a-model", "gpt-99.1-unknown"):
            with pytest.raises(ModelNotFoundError):
                registry.get(model, provider)
        assert registry.search("not-a-model", provider) == []
    assert registry._catalog_index is not None
    assert not registry._catalog_index._objects


def test_indexed_numeric_and_prefix_candidates(catalog):
    registry = Registry()
    baseline = json_registry()
    assert registry.get("gpt-demo-1.3", "openai") == baseline.get(
        "gpt-demo-1.3", "openai"
    )
    index = registry._catalog_index
    assert index is not None
    assert len(index._objects) == 2
    for prefix in ("demo model", "route", "collision", "gpt"):
        for provider in (None, "openai", "openrouter"):
            for deprecated in (True, False):
                assert registry.search(prefix, provider, deprecated) == baseline.search(
                    prefix, provider, deprecated
                )


def test_scoped_alias_and_prefix_follow_overlays_and_mutations(catalog):
    registry = Registry()
    baseline = json_registry()
    for current in (registry, baseline):
        assert current.get("collision", "openrouter").model_id == "router-only"
        current.register(
            Capability(provider="openrouter", model_id="router-only"),
            overwrite=True,
        )
        assert current.get("collision", "openrouter").model_id == "router-second"
        cap = current.get("gpt-demo-1.2", "openai")
        cap.aliases.append("runtime-alias")
        assert current.get("runtime-alias", "openai") is cap
    for prefix in ("collision", "runtime", "demo model"):
        assert registry.search(prefix) == baseline.search(prefix)


def test_legacy_database_keeps_lookup_compatibility(catalog):
    _, database = catalog
    with closing(sqlite3.connect(database)) as conn, conn:
        # Materialize the original text-keyed logical tables to exercise v1.
        for table in ("models", "flat_models", "aliases"):
            conn.execute(f"CREATE TABLE legacy_{table} AS SELECT * FROM {table}")
            conn.execute(f"DROP VIEW {table}")
            conn.execute(f"ALTER TABLE legacy_{table} RENAME TO {table}")
        conn.execute("DROP TABLE lookup_blocks")
        conn.execute("PRAGMA user_version = 1")
    registry = Registry()
    assert registry.get("demo", "openai") == json_registry().get("demo", "openai")
    assert registry.search("demo model") == json_registry().search("demo model")
    assert registry._catalog_index is not None


def test_full_catalog_parity(catalog):
    from llmcapa._catalog_parity import verify_catalog

    counts = verify_catalog()
    assert counts["providers"] == 2
    assert counts["scoped_models"] == 5
    assert counts["flat_models"] == 4
    assert counts["lookup_postings"] > 0


@pytest.mark.parametrize("kind", ["payload", "alias", "order", "postings"])
def test_catalog_parity_detects_valid_sqlite_mismatch(catalog, kind):
    from llmcapa._catalog_parity import CatalogParityError, verify_catalog

    _, database = catalog
    with closing(sqlite3.connect(database)) as conn, conn:
        if kind == "payload":
            payload = conn.execute(
                "SELECT payload FROM capability_blocks WHERE id = 1"
            ).fetchone()[0]
            records = json.loads(zlib.decompress(payload))
            records[0]["context_window"] = 123456
            conn.execute(
                "UPDATE capability_blocks SET payload = ? WHERE id = 1",
                (zlib.compress(json.dumps(records).encode()),),
            )
        elif kind == "alias":
            conn.execute(
                "UPDATE alias_entries SET model_key_id = "
                "(SELECT id FROM strings WHERE value = 'router-only') "
                "WHERE alias_id = (SELECT id FROM strings WHERE value = 'demo')"
            )
        elif kind == "order":
            conn.execute("UPDATE model_entries SET ordinal = -ordinal")
        else:
            conn.execute("DELETE FROM lookup_blocks WHERE kind = 'shape'")
    with pytest.raises(CatalogParityError):
        verify_catalog()


def test_catalog_parity_with_warm_registry(catalog):
    from llmcapa._catalog_parity import compare_registries

    expected = json_registry()
    actual = Registry()
    actual._ensure_loaded()
    compare_registries(expected, actual)


def test_catalog_parity_rejects_candidate_query_fallback(catalog, monkeypatch):
    from llmcapa import _catalog_index
    from llmcapa._catalog_parity import CatalogParityError, verify_catalog

    def failed_candidates(conn, kind, term):
        raise sqlite3.OperationalError("candidate index read failed")

    monkeypatch.setattr(_catalog_index, "candidate_ids", failed_candidates)
    with pytest.raises(CatalogParityError, match="candidate lookup fell back"):
        verify_catalog()


def test_open_stamp_skips_source_rehash(catalog, monkeypatch):
    from llmcapa import _catalog_db

    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None

    def unexpected_hash():
        pytest.fail("stamp hit must not re-read the source files")

    monkeypatch.setattr(_catalog_db, "_catalog_sources", unexpected_hash)
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None


def test_stamp_detects_source_edit_with_preserved_mtime(catalog):
    data, _ = catalog
    registry = Registry()
    assert registry.get("demo").context_window == 1000
    assert registry._catalog_index is not None

    source = data / "openai.json"
    original = source.stat()
    records = json.loads(source.read_text(encoding="utf-8"))
    records[0]["context_window"] = 2000
    source.write_text(json.dumps(records), encoding="utf-8")
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))

    registry = Registry()
    assert registry.get("demo").context_window == 2000
    assert registry._catalog_index is None


def test_stamp_miss_when_database_file_is_replaced(catalog, monkeypatch):
    import shutil

    from llmcapa import _catalog_db

    _, database = catalog
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None

    calls = []
    original = _catalog_db._catalog_sources

    def counting():
        calls.append(1)
        return original()

    monkeypatch.setattr(_catalog_db, "_catalog_sources", counting)
    replacement = database.with_name("replacement.sqlite3")
    shutil.copyfile(database, replacement)
    os.replace(replacement, database)

    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None
    assert calls, "replacing the database file must re-run the hash check"


def test_windows_change_time_helper_is_unavailable_off_windows(tmp_path):
    if os.name == "nt":
        pytest.skip("the helper reads the real NTFS change time on Windows")
    from llmcapa import _catalog_index

    assert _catalog_index._windows_change_time_ns(tmp_path / "x") is None


def test_file_stat_requires_a_change_time_on_windows(tmp_path, monkeypatch):
    from llmcapa import _catalog_index

    target = tmp_path / "source.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(_catalog_index, "_windows_change_time_ns", lambda path: 4242)
    assert _catalog_index._file_stat(target)[2] == 4242
    monkeypatch.setattr(_catalog_index, "_windows_change_time_ns", lambda path: None)
    with pytest.raises(OSError):
        _catalog_index._file_stat(target)


def test_corrupt_stamp_is_ignored(catalog, tmp_path):
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None
    stamp = tmp_path / "home" / ".llmcapa" / "catalog_index_stamp.json"
    assert stamp.is_file()
    stamp.write_text("not json", encoding="utf-8")

    registry = Registry()
    assert registry.get("demo").provider == "openai"
    assert registry._catalog_index is not None


def test_diagnostics_reports_healthy_sqlite(catalog):
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    diagnostics = registry.catalog_diagnostics()
    assert diagnostics["mode"] == "sqlite"
    assert diagnostics["schema_version"] >= 2
    assert diagnostics["using_json_fallback"] is False
    assert diagnostics["fallback_reason"] is None
    assert diagnostics["candidate_failures"] == 0
    assert diagnostics["last_candidate_error"] is None


def test_diagnostics_json_mode():
    registry = json_registry()
    assert registry.catalog_diagnostics() == {"mode": "json"}


def test_diagnostics_records_candidate_failure(catalog):
    _, database = catalog
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("DROP TABLE lookup_blocks")
        conn.commit()

    # Lookups still answer through the full scan, but the failure is visible.
    assert registry.search("demo")
    diagnostics = registry.catalog_diagnostics()
    assert diagnostics["candidate_failures"] >= 1
    assert "lookup_blocks" in diagnostics["last_candidate_error"]


def test_diagnostics_records_json_fallback(catalog):
    _, database = catalog
    registry = Registry()
    assert registry.get("demo").provider == "openai"
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("DROP VIEW models")
        conn.commit()

    assert registry.get("demo", "openai").provider == "openai"
    diagnostics = registry.catalog_diagnostics()
    assert diagnostics["using_json_fallback"] is True
    assert "models" in diagnostics["fallback_reason"]


@pytest.fixture
def region_catalog(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(registry_module.Path, "home", lambda: home)
    monkeypatch.setattr(registry_module.resources, "files", lambda package: data)
    models = [
        {"provider": "vertex-ai", "model_id": f"model-{letter}"} for letter in "abcdef"
    ]
    models[1]["aliases"] = ["bee"]
    models[1]["regions"] = {"locations": ["us-central1"]}
    models[2]["aliases"] = ["cee"]
    models[2]["regions"] = {"locations": ["europe-west1"]}
    models[3]["regions"] = {"locations": ["own-region"]}
    # A display-name twin of a region-bearing record carries no regions.
    models.append(
        {"provider": "vertex-ai", "model_id": "model-g", "display_name": "model-b"}
    )
    (data / "vertex-ai.json").write_text(json.dumps(models), encoding="utf-8")
    database = data / "catalog.sqlite3"
    build_catalog(database)
    return data, database


def test_record_regions_match_between_sqlite_and_json(region_catalog):
    baseline = json_registry()

    registry = Registry()
    registry._ensure_loaded()
    assert registry._catalog_index is not None

    for model_id in ("model-a", "model-b", "model-c", "model-d", "model-e", "model-g"):
        assert registry.get(model_id, "vertex-ai") == baseline.get(
            model_id, "vertex-ai"
        )
    assert registry.get("model-g", "vertex-ai").regions is None
    assert registry.get("model-b", "vertex-ai").regions.locations == ("us-central1",)
    assert registry.get("model-c", "vertex-ai").regions.locations == ("europe-west1",)
    assert registry.get("model-d", "vertex-ai").regions.locations == ("own-region",)
    assert registry.list_regions() == baseline.list_regions()
    for region in baseline.list_regions():
        assert registry.find_by_region(region) == baseline.find_by_region(region)


def test_object_cache_evicts_oldest_decodes(region_catalog, monkeypatch):
    import llmcapa._catalog_index as index_module

    monkeypatch.setattr(index_module, "_OBJECT_CACHE_LIMIT", 3)
    registry = Registry()
    first = registry.get("model-a", "vertex-ai")
    registry.get("model-b", "vertex-ai")
    registry.get("model-c", "vertex-ai")
    newest = registry.get("model-d", "vertex-ai")

    index = registry._catalog_index
    assert index is not None
    assert len(index._objects) == 3
    # Recent decodes keep their identity; the evicted oldest record is
    # decoded again and compares equal without being the same object.
    assert registry.get("model-d", "vertex-ai") is newest
    assert registry.get("model-a", "vertex-ai") == first
    assert registry.get("model-a", "vertex-ai") is not first


def test_refreshed_record_preserves_bundled_regions(region_catalog):
    registry = Registry()
    registry._ensure_loaded()
    index = registry._catalog_index
    assert index is not None

    # A snapshot fetched before regions moved into the records omits the
    # field; the refresh must not drop the bundled regional availability.
    with index.batch():
        registry._register_refreshed_catalog_record(
            Capability(provider="vertex-ai", model_id="model-b", context_window=123)
        )
    updated = registry.get("model-b", "vertex-ai")
    assert updated.context_window == 123
    assert updated.regions.locations == ("us-central1",)
    # The bundled payload was never decoded to recover the regions.
    assert not index._objects

    # A refreshed record that carries regions replaces them.
    with index.batch():
        registry._register_refreshed_catalog_record(
            Capability(
                provider="vertex-ai",
                model_id="model-b",
                regions=RegionCapability(locations=("new-region",)),
            )
        )
    assert registry.get("model-b", "vertex-ai").regions.locations == ("new-region",)


def test_fetch_github_catalog_preserves_regions_in_written_bundle(
    region_catalog, monkeypatch
):
    from io import BytesIO

    data, _database = region_catalog
    registry = Registry()
    registry._ensure_loaded()

    # The fetched snapshot predates regions in the records.
    stale = [{"provider": "vertex-ai", "model_id": "model-b", "context_window": 999}]
    response_data = json.dumps({"models": stale}).encode("utf-8")
    monkeypatch.setattr(
        "llmcapa.registry.urllib.request.urlopen",
        lambda request, context=None, timeout=None: BytesIO(response_data),
    )
    registered = registry.fetch_github_catalog("vertex-ai", cache_ttl=0)
    assert registered >= 1
    assert registry.get("model-b", "vertex-ai").regions.locations == ("us-central1",)

    # The bundled file written from the download carries the regions too,
    # so a fresh registry still sees them.
    written = json.loads((data / "vertex-ai.json").read_text(encoding="utf-8"))
    record = next(r for r in written["models"] if r["model_id"] == "model-b")
    assert record["regions"]["locations"] == ["us-central1"]
    fresh = Registry()
    assert fresh.get("model-b", "vertex-ai").regions.locations == ("us-central1",)


def test_refreshed_record_preserves_regions_in_json_mode(region_catalog):
    registry = json_registry()
    registry._register_refreshed_catalog_record(
        Capability(provider="vertex-ai", model_id="model-b", context_window=123)
    )
    updated = registry.get("model-b", "vertex-ai")
    assert updated.context_window == 123
    assert updated.regions.locations == ("us-central1",)
