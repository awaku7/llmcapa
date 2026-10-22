"""Regression tests for preserving published Mistral specialty model prices."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "_update_mistral.py"
SPEC = importlib.util.spec_from_file_location("mistral_catalog_updater", PATH)
assert SPEC is not None and SPEC.loader is not None
UPDATER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATER)


def test_mistral_preserves_known_zero_tts_input_price():
    before = {"extra": {"tts_input_price": 0.0, "tts_price": 16.0}}
    refreshed = {"extra": {"supports_tts": True, "tts_price": 17.0}}
    row = UPDATER.preserve_specialty_pricing(refreshed, before)
    assert row["extra"]["tts_input_price"] == 0.0
    assert row["extra"]["tts_price"] == 17.0


def test_mistral_keeps_documented_tts_input_rate_in_bundle():
    catalog = ROOT / "src" / "llmcapa" / "data" / "mistral.json"
    models = json.loads(catalog.read_text(encoding="utf-8"))["models"]
    row = next(m for m in models if m["model_id"] == "voxtral-mini-tts-2603")
    assert row["extra"]["tts_input_price"] == 0.0
def test_mistral_voxtral_three_published_specialty_rates():
    minute_rates = {
        "voxtral-mini-transcribe-3-0": 0.0035,
        "voxtral-mini-transcribe-realtime-3-0": 0.008,
        "voxtral-small-transcribe-3-0": 0.004,
    }
    for model_id, price in minute_rates.items():
        row = UPDATER.build_row(
            model_id,
            {
                "h1": model_id,
                "primaryCode": model_id,
                "input_price": 0.0,
                "head_text": f"Price $ {price} /Min Features",
                "features": {"Transcriptions": True},
            },
        )
        assert row["extra"]["price_per_min"] == price
    tts_id = "voxtral-mini-tts-3-0"
    tts = UPDATER.build_row(
        tts_id,
        {
            "h1": "Voxtral TTS 3",
            "primaryCode": tts_id,
            "head_text": "Price $13 /M Chars Features",
            "features": {"Text to Speech": True},
        },
    )
    assert tts["extra"]["price_per_1m_chars"] == 13.0
    assert tts["extra"]["tts_price"] == 13.0
    assert "tts_input_price" not in tts["extra"]


def test_mistral_voxtral_three_rates_are_in_bundled_catalog():
    catalog = ROOT / "src" / "llmcapa" / "data" / "mistral.json"
    models = {
        m["model_id"]: m
        for m in json.loads(catalog.read_text(encoding="utf-8"))["models"]
    }
    assert models["voxtral-mini-transcribe-3-0"]["extra"]["price_per_min"] == 0.0035
    assert (
        models["voxtral-mini-transcribe-realtime-3-0"]["extra"]["price_per_min"]
        == 0.008
    )
    assert models["voxtral-small-transcribe-3-0"]["extra"]["price_per_min"] == 0.004
    assert models["voxtral-mini-tts-3-0"]["extra"]["price_per_1m_chars"] == 13.0
