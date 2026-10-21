"""Protect Gemini thinking controls against subsequent catalog refreshes."""

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _update_google as updater  # noqa: E402


def test_official_thinking_levels_survive_google_update():
    data_path = Path(__file__).resolve().parents[1] / "src/llmcapa/data/google.json"
    models = json.loads(data_path.read_text(encoding="utf-8"))["models"]
    ids = (
        "gemini-3.8-flash",
        "gemini-3.8-live-extended-thinking",
        "gemini-4-argon",
        "gemini-3.8-live",
        "gemini-3.8-flash-tts",
        "gemini-3.8-flash-lite-tts",
    )
    indexed = {m["model_id"]: m for m in models if m["model_id"] in ids}
    assert len(indexed) == len(ids)
    for model_id in ids:
        model = indexed[model_id]
        expected = updater.template_for(model_id)
        for field in (
            "supports_thinking_level",
            "thinking_level_values",
            "thinking_control",
        ):
            assert expected[field] == model.get(field), (model_id, field)


def test_gemini_3_thinking_levels_not_regressed():
    older = updater.template_for("gemini-3-pro-preview")
    assert older["thinking_level_values"] == ["minimal", "low", "medium", "high"]
    modern = updater.template_for("gemini-4-argon")
    assert modern["thinking_level_values"] == ["low", "medium", "high"]
    assert modern["supports_thinking_level"] is True
    standard_live = updater.template_for("gemini-3.8-live")
    assert standard_live["supports_thinking_level"] is False
    assert standard_live["thinking_control"] is None
