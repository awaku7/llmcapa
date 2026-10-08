"""Regression tests for Claude Haiku 5.5's distinct API capabilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import llmcapa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _computer_use_metadata
import _update_anthropic


def test_haiku_55_catalog_has_official_limits_and_controls():
    cap = llmcapa.get("claude-haiku-5-5", provider="anthropic")
    assert cap is not None
    assert cap.context_window == 1_000_000
    assert cap.max_output_tokens == 128_000
    assert cap.knowledge_cutoff == "2026-06"
    assert cap.supports_vision is True
    assert cap.supports_function_calling is True
    assert cap.supports_reasoning_effort is True
    assert cap.supports_thinking_budget is False
    assert cap.get_thinking_budget_values() == {}
    assert cap.get_reasoning_effort_values() == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert cap.get_thinking_control() == {
        "kind": "effort",
        "parameter": "output_config.effort",
        "values": ["low", "medium", "high", "xhigh", "max"],
        "default": "medium",
        "thinking_type": "adaptive",
    }
    assert cap.extra["batch_max_output_tokens"] == 300_000
    assert cap.extra["batch_output_beta_header"] == "output-300k-2026-03-24"
    assert cap.extra["browser_use"]["tool_type"] == "browser_toolset_20260801"
    assert cap.extra["assistant_prefill_supported"] is False


def test_haiku_55_pricing_switches_entire_request_at_100k_input():
    cap = llmcapa.get("claude-haiku-5-5", provider="anthropic")
    assert cap.estimate_cost(100_000, 1_000)["cost"] == pytest.approx(0.0105)
    assert cap.estimate_cost(100_001, 1_000)["cost"] == pytest.approx(
        (100_001 * 0.5 + 1_000 * 2.5) / 1_000_000
    )
    assert cap.extra["cache_write_5m_per_1m"] == 0.125
    assert cap.extra["cache_write_5m_long_per_1m"] == 0.625
    assert cap.extra["cache_hit_per_1m"] == 0.01
    assert cap.extra["cache_hit_long_per_1m"] == 0.05


def test_other_models_keep_flat_cost_estimates_and_old_thinking():
    legacy = llmcapa.get("claude-haiku-4-5", provider="anthropic")
    assert legacy.supports_thinking_budget is True
    assert legacy.supports_reasoning_effort is False
    assert legacy.estimate_cost(100_001, 1_000)["cost"] == pytest.approx(
        (100_001 * 1.0 + 1_000 * 5.0) / 1_000_000
    )


def test_haiku_55_computer_use_is_platform_scoped():
    current = _computer_use_metadata.anthropic_computer_use_capability(
        "claude-haiku-5-5", "anthropic"
    )
    assert current["tool_type"] == "computer_toolset_20260801"
    assert current["requires_beta"] is False
    assert current["enable_zoom"] is True
    google = _computer_use_metadata.anthropic_computer_use_capability(
        "claude-haiku-5-5", "google-cloud"
    )
    assert google["tool_type"] == "computer_toolset_20260801"
    assert (
        _computer_use_metadata.anthropic_computer_use_capability(
            "claude-haiku-5-5", "amazon"
        )
        is None
    )
    old = _computer_use_metadata.anthropic_computer_use_capability(
        "claude-haiku-4-5", "anthropic"
    )
    assert old["tool_type"] == "computer_20250124"
    assert old["requires_beta"] is True


def test_anthropic_refresh_reconciles_stale_haiku_55_data(monkeypatch, tmp_path):
    path = tmp_path / "anthropic.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "anthropic",
                        "model_id": "claude-haiku-5-5",
                        "display_name": "Claude Haiku 5.5",
                        "context_window": 200_000,
                        "max_output_tokens": 64_000,
                        "supports_thinking_budget": True,
                        "thinking_budget_values": {"min": 1024, "max": 64000},
                        "extra": {"curated_note": "preserve"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    row = {
        "name": "Claude Haiku 5.5",
        "input": 0.10,
        "output": 0.50,
        "cache_5m": 0.125,
        "cache_1h": 0.20,
        "cache_hit": 0.01,
        "deprecated": False,
    }
    monkeypatch.setattr(_update_anthropic, "OUT", path)
    monkeypatch.setattr(_update_anthropic, "fetch", lambda _: "offline")
    monkeypatch.setattr(_update_anthropic, "discover_pricing", lambda _: [row])

    refreshed = _update_anthropic.build()
    assert len(refreshed) == 1
    model = refreshed[0]
    assert model["context_window"] == 1_000_000
    assert model["max_output_tokens"] == 128_000
    assert model["supports_thinking_budget"] is False
    assert "thinking_budget_values" not in model
    assert model["supports_reasoning_effort"] is True
    assert model["thinking_control"]["parameter"] == "output_config.effort"
    assert model["pricing"]["prompt_length_threshold_tokens"] == 100_000
    assert model["pricing"]["long_output_per_1m"] == 2.5
    assert model["computer_use"]["tool_type"] == "computer_toolset_20260801"
    assert model["extra"]["curated_note"] == "preserve"


def test_haiku_55_template_can_be_reconciled_without_previous_snapshot():
    row = {
        "name": "Claude Haiku 5.5",
        "input": 0.10,
        "output": 0.50,
        "cache_5m": 0.125,
        "cache_1h": 0.20,
        "cache_hit": 0.01,
        "deprecated": False,
    }
    model = _update_anthropic._template(row)
    assert model["supports_thinking_budget"] is False
    assert model["reasoning_effort_values"][-2:] == ["xhigh", "max"]
