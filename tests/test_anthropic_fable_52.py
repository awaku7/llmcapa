from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _update_anthropic


@pytest.mark.parametrize(
    ("model_id", "display_name", "availability"),
    [
        ("claude-fable-5-2", "Claude Fable 5.2", None),
        (
            "claude-mythos-5-2",
            "Claude Mythos 5.2",
            "verification_required",
        ),
    ],
)
def test_anthropic_52_templates_use_official_model_specs(
    model_id: str, display_name: str, availability: str | None
) -> None:
    model = _update_anthropic._template(
        {
            "name": display_name,
            "input": 8.0,
            "output": 40.0,
            "cache_5m": 10.0,
            "cache_1h": 16.0,
            "cache_hit": 0.2,
            "deprecated": False,
        }
    )

    assert model["model_id"] == model_id
    assert model["context_window"] == 1_000_000
    assert model["max_output_tokens"] == 128_000
    assert model["knowledge_cutoff"] == "2026-06"
    assert model["supports_thinking_budget"] is False
    assert "thinking_budget_values" not in model
    assert model["supports_reasoning_effort"] is True
    assert model["reasoning_effort_values"] == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert model["thinking_control"] == {
        "kind": "effort",
        "parameter": "output_config.effort",
        "values": ["low", "medium", "high", "xhigh", "max"],
        "default": "high",
        "thinking_type": "adaptive",
    }
    assert model["extra"]["context_window_source"].endswith(
        f"/models/{'mythos' if 'mythos' in model_id else 'fable'}-5-2/overview"
    )
    if availability is not None:
        assert model["extra"]["availability"] == availability


def test_legacy_price_snapshot_cannot_overwrite_52_model_specs() -> None:
    model = {
        "model_id": "claude-fable-5-2",
        "context_window": 200_000,
        "max_output_tokens": 64_000,
        "supports_thinking_budget": True,
        "thinking_budget_values": {"min": 1024, "max": 64_000},
    }

    updated = _update_anthropic.apply_legacy_price_snapshot(
        [model], {"claude-fable-5-2": (8.0, 40.0, 200_000, 64_000)}
    )

    assert updated == 1
    assert model["context_window"] == 1_000_000
    assert model["max_output_tokens"] == 128_000
    assert model["supports_thinking_budget"] is False
    assert "thinking_budget_values" not in model
    assert model["thinking_control"]["default"] == "high"


def test_anthropic_refresh_repairs_stale_52_records_and_adds_computer_use(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "anthropic.json"
    stale_models = []
    for model_id, display_name in (
        ("claude-fable-5-2", "Claude Fable 5.2"),
        ("claude-mythos-5-2", "Claude Mythos 5.2"),
    ):
        stale_models.append(
            {
                "provider": "anthropic",
                "model_id": model_id,
                "display_name": display_name,
                "context_window": 0,
                "max_output_tokens": 64_000,
                "supports_thinking_budget": True,
                "thinking_budget_values": {"min": 1024, "max": 64_000},
                "extra": {"curated_note": "preserve"},
            }
        )
    path.write_text(json.dumps({"models": stale_models}), encoding="utf-8")
    monkeypatch.setattr(_update_anthropic, "OUT", path)
    monkeypatch.setattr(_update_anthropic, "fetch", lambda _: "official pricing")
    monkeypatch.setattr(
        _update_anthropic,
        "discover_pricing",
        lambda _: [
            {
                "name": "Claude Fable 5.2",
                "input": 8.0,
                "output": 40.0,
                "cache_5m": 10.0,
                "cache_1h": 16.0,
                "cache_hit": 0.2,
                "deprecated": False,
            },
            {
                "name": "Claude Mythos 5.2",
                "input": 8.0,
                "output": 40.0,
                "cache_5m": 10.0,
                "cache_1h": 16.0,
                "cache_hit": 0.2,
                "deprecated": False,
            },
        ],
    )

    refreshed = {model["model_id"]: model for model in _update_anthropic.build()}

    assert set(refreshed) == {"claude-fable-5-2", "claude-mythos-5-2"}
    for model in refreshed.values():
        assert model["context_window"] == 1_000_000
        assert model["max_output_tokens"] == 128_000
        assert model["supports_thinking_budget"] is False
        assert "thinking_budget_values" not in model
        assert model["computer_use"]["tool_type"] == "computer_toolset_20260801"
        assert model["extra"]["curated_note"] == "preserve"
    assert refreshed["claude-mythos-5-2"]["extra"]["availability"] == (
        "verification_required"
    )
