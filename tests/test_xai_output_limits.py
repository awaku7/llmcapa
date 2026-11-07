"""Regression tests for the xAI output-limit source and refresh policy."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"_{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}_output", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(name="grok-new", **overrides):
    entry = {
        "name": name,
        "maxPromptLength": 500_000,
        "inputModalities": [1, 2],
        "outputModalities": [1],
        "promptTextTokenPrice": 2,
        "completionTextTokenPrice": 6,
    }
    return {**entry, **overrides}


def test_pricing_scraper_does_not_fabricate_output_cap():
    scraper = _load("scrape_xai")
    source = (
        "| Model | Context | Input / 1M tokens | "
        "Cached input / 1M tokens | Output / 1M tokens |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| grok-new | 500K | $2 | $0.5 | $6 |\n"
    )
    [record] = scraper.parse(source)
    assert record["maxPromptLength"] == 500_000
    assert "maxCompletionLength" not in record


def test_explicit_published_output_limit_is_recorded():
    updater = _load("update_xai")
    record = updater.text_row(_entry(maxCompletionLength=64_000))
    assert record["max_output_tokens"] == 64_000
    assert record["extra"]["max_output_tokens_status"] == "published"
    assert record["extra"]["max_output_tokens_source"] == updater.SOURCE


def test_missing_output_limit_preserves_previous_positive_value():
    updater = _load("update_xai")
    previous = {
        "max_output_tokens": 16_384,
        "extra": {"max_output_tokens_source": "https://docs.x.ai/example"},
    }
    for value in (None, 0, -100, True, "unknown"):
        entry = _entry()
        if value is not None:
            entry["maxCompletionLength"] = value
        record = updater.text_row(entry, previous=previous)
        assert record["max_output_tokens"] == 16_384
        assert record["extra"]["max_output_tokens_status"] == "retained_previous"
        assert record["extra"]["max_output_tokens_source"] == (
            "https://docs.x.ai/example"
        )


def test_new_unverified_model_does_not_inherit_api_default():
    updater = _load("update_xai")
    record = updater.text_row(_entry())
    assert record["max_output_tokens"] == 0
    assert record["extra"]["max_output_tokens_status"] == "not_published"
    assert "max_output_tokens_source" not in record["extra"]


def test_only_documented_unbounded_models_use_explicit_status():
    updater = _load("update_xai")
    for model_id in ("grok-4.6", "grok-4.7"):
        record = updater.text_row(_entry(model_id))
        assert record["max_output_tokens"] == 0
        assert record["extra"]["max_output_tokens_status"] == "documented_unbounded"
        assert record["extra"]["max_output_tokens_source"].startswith(
            "https://docs.x.ai/"
        )
    other = updater.text_row(_entry("grok-4.5"))
    assert other["extra"]["max_output_tokens_status"] == "not_published"


def test_specialty_and_legacy_limits_preserve_previous_facts():
    updater = _load("update_xai")
    specialty = {
        "model_id": "grok-special",
        "display_name": "Specialty",
        "input_modalities": ["text"],
        "output_modalities": ["image"],
        "extra": {},
    }
    new = updater.specialty_row(specialty)
    assert new["max_output_tokens"] == 0
    assert new["extra"]["max_output_tokens_status"] == "not_applicable"
    previous = {"max_output_tokens": 12_000, "extra": {}}
    old = updater.specialty_row(specialty, previous=previous)
    assert old["max_output_tokens"] == 12_000
    assert old["extra"]["max_output_tokens_status"] == "retained_previous"
    legacy = next(entry for entry in updater.LEGACY if entry["model_id"] == "grok-3")
    old_legacy = updater.legacy_row(legacy, previous=previous)
    assert old_legacy["max_output_tokens"] == 12_000
    assert old_legacy["extra"]["max_output_tokens_status"] == "retained_previous"


def test_build_preserves_previous_limit_after_docs_refresh(tmp_path, monkeypatch):
    updater = _load("update_xai")
    target = tmp_path / "xai.json"
    target.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "model_id": "grok-new",
                        "max_output_tokens": 65_536,
                        "extra": {"max_output_tokens_source": "https://docs.x.ai/spec"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "OUT", target)
    monkeypatch.setattr(updater, "LISTMODELS_FALLBACK", False)
    monkeypatch.setattr(updater, "load_listmodels", lambda: [_entry()])
    monkeypatch.setattr(updater, "IMAGINE_MODELS", [])
    monkeypatch.setattr(updater, "VOICE_MODELS", [])
    monkeypatch.setattr(updater, "LEGACY", [])
    [row] = updater.build()
    assert row["max_output_tokens"] == 65_536
    assert row["extra"]["max_output_tokens_status"] == "retained_previous"
    assert row["extra"]["max_output_tokens_source"] == "https://docs.x.ai/spec"


def test_bundled_xai_catalog_has_explicit_source_status():
    rows = json.loads(
        (ROOT / "src" / "llmcapa" / "data" / "xai.json").read_text(encoding="utf-8")
    )["models"]
    assert len(rows) == 22
    for row in rows:
        assert row["max_output_tokens"] >= 0
        assert row["extra"]["max_output_tokens_status"] in {
            "documented_unbounded",
            "not_published",
            "not_applicable",
            "published",
            "retained_previous",
        }
    no_limit = {
        row["model_id"]
        for row in rows
        if row["extra"]["max_output_tokens_status"] == "documented_unbounded"
    }
    assert no_limit == {"grok-4.6", "grok-4.7"}
