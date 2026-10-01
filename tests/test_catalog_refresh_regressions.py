from __future__ import annotations

import importlib
import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")


def _script_module(name: str):
    sys.path.insert(0, SCRIPTS)
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(SCRIPTS)


def test_novita_api_mapper_tracks_responses_and_cached_input_pricing():
    updater = _script_module("_update_novita_from_api")
    entry = updater.api_to_entry(
        {
            "id": "moonshotai/kimi-k3-p",
            "context_size": 1_048_576,
            "max_output_tokens": 1_048_576,
            "input_token_price_per_m": 30_000,
            "output_token_price_per_m": 150_000,
            "pricing": {"input_cache_read": {"price_per_m": 3_000}},
            "features": ["function-calling", "structured-outputs", "reasoning"],
            "endpoints": ["chat/completions", "responses", "anthropic"],
            "input_modalities": ["text", "image", "video"],
            "output_modalities": ["text"],
            "status": 1,
        }
    )

    assert entry is not None
    assert entry["supports_responses_api"] is True
    assert entry["supports_anthropic_api"] is True
    assert entry["supports_vision"] is True
    assert entry["pricing"]["input_per_1m"] == 0.3
    assert entry["extra"]["cache_read_per_1m"] == 0.03


def test_mistral_deprecation_flag_uses_official_card_status():
    updater = _script_module("_update_mistral")
    assert updater.is_deprecated(
        {
            "status": "Deprecated",
            "deprecation_date": "9/29/2026",
            "replacement": "OCR 4.1",
        }
    )
