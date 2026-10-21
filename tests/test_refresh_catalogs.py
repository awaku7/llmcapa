"""Regression tests for guarded catalog refresh and diff reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import refresh_catalogs as refresh  # noqa: E402


def _catalog(*ids: str) -> dict:
    return {"models": [{"model_id": model_id, "context_window": 100} for model_id in ids]}


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
    with pytest.raises(ValueError, match="root"):
        refresh.load_catalog(path)
