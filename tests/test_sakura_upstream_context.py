"""Tests for source-attributed upstream context data in the Sakura catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import _update_sakura

EXPECTED_CONTEXTS = {
    "llm-jp-3.1-8x13b-instruct4": 4096,
    "PLaMo 3.0 Prime": 262144,
    "cotomi v3": 131072,
    "Qwen3-0.6B-cpu": 32768,
    "Phi-4-mini-instruct-cpu": 131072,
    "Qwen3-VL-30B-A3B-Instruct": 262144,
    "Kimi-K2.6": 262144,
    "Qwen3.6-35B-A3B": 262144,
    "gemma-4-31B-it": 262144,
    "Kimi-K2.7-Code": 262144,
    "Qwen3-Embedding-4B(FP16)": 32768,
    "Weblab-MedLLM-gpt-oss-120b": 131072,
}


def test_sakura_catalog_contexts_have_upstream_source_provenance() -> None:
    data_path = ROOT / "src" / "llmcapa" / "data" / "sakura.json"
    records = json.loads(data_path.read_text(encoding="utf-8"))["models"]
    by_id = {row["model_id"]: row for row in records}

    for model_id, expected_context in EXPECTED_CONTEXTS.items():
        row = by_id[model_id]
        assert row["context_window"] == expected_context
        assert row["extra"]["context_window_basis"] == "upstream_base_model"
        assert row["extra"]["context_window_source"].startswith("https://")
        assert "Sakura deployment-specific context limit is not published" in row[
            "extra"]["context_window_note"]


def test_updater_preserves_catalog_context_metadata_without_constants() -> None:
    source = "https://example.invalid/model-card"
    models = [
        {"model_id": "PLaMo 3.0 Prime", "context_window": 0, "extra": {}},
        {"model_id": "unknown-model", "context_window": 0, "extra": {}},
    ]
    previous = [
        {
            "model_id": "PLaMo 3.0 Prime",
            "context_window": 262144,
            "extra": {
                "context_window_basis": "upstream_base_model",
                "context_window_source": source,
                "context_window_note": "upstream value; not the Sakura service limit",
            },
        },
        {"model_id": "unverified-model", "context_window": 65536, "extra": {}},
    ]

    assert _update_sakura.preserve_upstream_context_specs(models, previous) == 1
    assert models[0]["context_window"] == 262144
    assert models[0]["extra"]["context_window_source"] == source
    assert models[1]["context_window"] == 0
