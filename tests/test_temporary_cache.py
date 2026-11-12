"""Retention tests for regenerable user caches."""

import json
import os
import time

import pytest

from llmcapa._temporary_cache import (
    DAY,
    LEGACY_RETENTION,
    cleanup_temporary_caches,
    write_temporary_cache,
)
from llmcapa.registry import Registry


def _old_file(path, age):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    modified = time.time() - age
    os.utime(path, (modified, modified))
    return path


def test_cleanup_only_recognized_legacy_files(tmp_path):
    expired = [
        _old_file(tmp_path / name, LEGACY_RETENTION + DAY)
        for name in (
            "openrouter_cache.json",
            "huggingface_all_tasks_cache_all.json",
            "huggingface_all_tasks_cache_limit_100.json",
            "github_catalog_cache/" + "a" * 64 + ".json",
        )
    ]
    preserved = [
        _old_file(tmp_path / name, LEGACY_RETENTION + DAY)
        for name in (
            "catalogs/github/tag.json",
            "github_catalog_backups/openai.json.bak",
            "sqlite_cache/cache-old.sqlite3",
            "unrelated.json",
            "github_catalog_cache/manual.json",
            "huggingface_all_tasks_cache_custom.json",
        )
    ]
    preserved.append(
        _old_file(tmp_path / "huggingface_all_tasks_cache_limit_5.json", DAY)
    )
    cleanup_temporary_caches(tmp_path)
    assert not any(path.exists() for path in expired)
    assert all(path.exists() for path in preserved)


@pytest.mark.parametrize("ttl", [DAY, 90 * DAY])
def test_recorded_expiry_preserves_custom_ttl(tmp_path, ttl):
    path = tmp_path / "openrouter_cache.json"
    write_temporary_cache(tmp_path, path, [{"id": "model"}], ttl)
    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "model"}]
    deadline = path.stat().st_mtime + ttl
    cleanup_temporary_caches(tmp_path, deadline - 1)
    assert path.exists()
    cleanup_temporary_caches(tmp_path, deadline + 1)
    assert not path.exists()
    assert not path.with_suffix(".json.expiry").exists()


def test_replaced_cache_does_not_inherit_old_expiry(tmp_path):
    path = tmp_path / "openrouter_cache.json"
    write_temporary_cache(tmp_path, path, [], DAY)
    path.write_text('[{"id":"new"}]', encoding="utf-8")
    cleanup_temporary_caches(tmp_path, time.time() + 2 * DAY)
    assert path.exists()


def test_cleanup_failure_is_nonfatal(tmp_path, monkeypatch):
    path = _old_file(tmp_path / "openrouter_cache.json", LEGACY_RETENTION + DAY)

    def locked(self, *args, **kwargs):
        raise PermissionError("file in use")

    monkeypatch.setattr(type(path), "unlink", locked)
    cleanup_temporary_caches(tmp_path)
    assert path.exists()


def test_cleanup_at_registry_startup(tmp_path, monkeypatch):
    home = tmp_path / ".llmcapa"
    path = _old_file(home / "openrouter_cache.json", LEGACY_RETENTION + DAY)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Registry, "_try_load_sqlite", lambda self: False)
    monkeypatch.setattr(Registry, "_load_bundled_files", lambda self: None)
    Registry()._ensure_loaded()
    assert not path.exists()
