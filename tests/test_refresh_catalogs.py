"""Regression tests for guarded catalog refresh and diff reports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import refresh_catalogs as refresh


def _catalog(*ids: str) -> dict:
    return {
        "models": [{"model_id": model_id, "context_window": 100} for model_id in ids]
    }


def test_model_index_rejects_empty_and_duplicate_catalogs():
    with pytest.raises(ValueError, match="no models"):
        refresh.model_index({"models": []})
    with pytest.raises(ValueError, match="duplicate"):
        refresh.model_index(_catalog("a", "a"))
    with pytest.raises(ValueError, match="model_id"):
        refresh.model_index({"models": [{"model_id": ""}]})


def test_model_diff_lists_added_removed_and_nested_modified_fields():
    previous = _catalog("one", "two")
    previous["models"][0]["pricing"] = {"input_per_1m": 1, "currency": "USD"}
    new = _catalog("one", "three")
    new["models"][0]["pricing"] = {"input_per_1m": 2, "currency": "USD"}
    diff = refresh.compare_catalogs(previous, new)
    assert diff == {
        "added": ["three"],
        "removed": ["two"],
        "modified": {"one": ["pricing.input_per_1m"]},
    }


def test_model_order_does_not_count_as_a_change():
    previous = _catalog("one", "two")
    updated = {"models": list(reversed(previous["models"]))}
    assert refresh.compare_catalogs(previous, updated) == {
        "added": [],
        "removed": [],
        "modified": {},
    }


def test_mass_deletion_is_rejected():
    previous = _catalog(*(f"model-{i}" for i in range(20)))
    updated = _catalog("model-1", "model-2")
    with pytest.raises(ValueError, match="suspicious deletion"):
        refresh.compare_catalogs(previous, updated)


def test_provider_filename_special_cases():
    assert refresh.catalog_filename("azure-foundry") == "azure_foundry.json"
    assert refresh.catalog_filename("foundry-local") == "foundry_local.json"
    assert refresh.catalog_filename("llama-cpp") == "llama_cpp.json"
    assert refresh.catalog_filename("openrouter") == "openrouter.json"


def test_report_lists_all_model_changes_and_failed_provider(tmp_path):
    results = [
        {
            "provider": "google",
            "status": "updated",
            "changes": {
                "added": ["new-model"],
                "removed": ["old-model"],
                "modified": {"known-model": ["pricing.input_per_1m"]},
            },
        },
        {
            "provider": "anthropic",
            "status": "failed",
            "reason": "network unavailable",
        },
        {
            "provider": "sakura",
            "status": "unsupported",
            "reason": "no updater",
        },
    ]
    totals = refresh.write_reports(results, tmp_path)
    assert totals == {
        "updated": 1,
        "unchanged": 0,
        "failed": 1,
        "unsupported": 1,
        "added": 1,
        "modified": 1,
        "removed": 1,
    }
    markdown = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "new-model" in markdown
    assert "old-model" in markdown
    assert "pricing.input_per_1m" in markdown
    assert "network unavailable" in markdown
    assert len(json.loads((tmp_path / "report.json").read_text())["providers"]) == 3


def test_loader_rejects_invalid_json_and_root(tmp_path):
    path = tmp_path / "provider.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        refresh.load_catalog(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="root"):
        refresh.load_catalog(path)


def test_timeout_terminates_provider_process_group_before_restore(
    tmp_path, monkeypatch
):
    if os.name == "nt":
        pytest.skip("POSIX process-group test")

    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    data_dir = tmp_path / "src" / "llmcapa" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "google.json").write_text(
        json.dumps(_catalog("model-1")), encoding="utf-8"
    )
    monkeypatch.setattr(refresh, "DATA_DIR", data_dir)
    calls = []

    class FakeProcess:
        pid = 54321

        def __init__(self):
            self.wait_count = 0

        def wait(self, timeout=None):
            self.wait_count += 1
            if self.wait_count == 1:
                raise subprocess.TimeoutExpired("update", timeout)
            calls.append("reaped")
            return 0

    fake_proc = FakeProcess()

    def fake_popen(command, **kwargs):
        assert "--provider" in command
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] == subprocess.DEVNULL
        calls.append("spawned")
        return fake_proc

    monkeypatch.setattr(refresh.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        refresh.os,
        "killpg",
        lambda pid, sig: calls.append(("kill-group", pid, sig)),
    )
    monkeypatch.setattr(refresh, "restore_unstaged", lambda: calls.append("restored"))
    result = refresh.run_provider(
        "google", timeout_seconds=1, log_directory=tmp_path / "logs"
    )
    assert result["status"] == "failed"
    assert "timed out" in result["reason"]
    assert calls[0] == "spawned"
    assert calls[1][0] == "kill-group"
    assert calls[1][1] == fake_proc.pid
    assert calls[2:] == ["reaped", "restored"]



def _complete_catalog() -> dict:
    return {
        "models": [
            {
                "model_id": "model-1",
                "context_window": 1024,
                "max_output_tokens": 256,
                "pricing": {
                    "input_per_1m": 5.0,
                    "output_per_1m": 25.0,
                    "currency": "USD",
                },
                "extra": {"cached_input_per_1m": 0.5},
                "image": {"generation": True, "status": "documented"},
                "audio": {"transcription": True},
                "decision": {"decision": True},
            }
        ]
    }


def test_refresh_guard_accepts_complete_updated_metadata():
    old = _complete_catalog()
    updated = json.loads(json.dumps(old))
    updated["models"][0]["pricing"]["input_per_1m"] = 6.0
    refresh.validate_refreshed_catalog(old, updated)


@pytest.mark.parametrize("key", ["context_window", "max_output_tokens"])
def test_refresh_guard_rejects_incomplete_model_records(key):
    previous = _complete_catalog()
    updated = json.loads(json.dumps(previous))
    del updated["models"][0][key]
    with pytest.raises(ValueError, match="missing or invalid"):
        refresh.validate_refreshed_catalog(previous, updated)


@pytest.mark.parametrize("key", ["image", "audio", "decision"])
def test_refresh_guard_rejects_lost_documented_capabilities(key):
    previous = _complete_catalog()
    updated = json.loads(json.dumps(previous))
    del updated["models"][0][key]
    with pytest.raises(ValueError, match=f"documented {key} was lost"):
        refresh.validate_refreshed_catalog(previous, updated)


def test_refresh_guard_rejects_erased_known_rates():
    previous = _complete_catalog()
    updated = json.loads(json.dumps(previous))
    updated["models"][0]["pricing"]["output_per_1m"] = None
    with pytest.raises(ValueError, match="known output_per_1m was lost"):
        refresh.validate_refreshed_catalog(previous, updated)


def test_refresh_guard_rejects_cached_output_rate_inversion():
    previous = _complete_catalog()
    updated = json.loads(json.dumps(previous))
    updated["models"][0]["pricing"]["output_per_1m"] = 0.5
    updated["models"][0]["extra"]["cached_input_per_1m"] = 25.0
    with pytest.raises(ValueError, match="cached and output prices swapped"):
        refresh.validate_refreshed_catalog(previous, updated)


def test_refresh_guard_rejects_deleting_cited_models():
    previous = _complete_catalog()
    previous["models"][0]["extra"]["context_window_source"] = "https://example.org"
    updated = _complete_catalog()
    updated["models"][0]["model_id"] = "replacement-model"
    with pytest.raises(ValueError, match="documented model disappeared"):
        refresh.validate_refreshed_catalog(previous, updated)


def test_xai_refresh_without_scratch_snapshot(tmp_path, monkeypatch):
    """A clean checkout must fetch xAI models before any scratch file exists."""
    import _scrape_xai
    import _update_xai

    snapshot = tmp_path / "_scratch_xai_listmodels_parsed.json"
    monkeypatch.setattr(_update_xai, "LISTMODELS", snapshot)
    monkeypatch.setattr(_scrape_xai, "fetch", lambda: "official model table")

    def fake_parse(markdown):
        assert markdown == "official model table"
        return [{"name": "grok-test", "promptTextTokenPrice": 1.0}]

    monkeypatch.setattr(_scrape_xai, "parse", fake_parse)
    models = _update_xai.load_listmodels()
    assert models == [{"name": "grok-test", "promptTextTokenPrice": 1.0}]
    assert json.loads(snapshot.read_text(encoding="utf-8")) == models
    assert _update_xai.LISTMODELS_FALLBACK is False
