from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import update_catalog_from_openrouter as updater
finally:
    sys.path.remove(SCRIPTS)


def test_openrouter_routes_use_gateway_provider_and_keep_short_aliases() -> None:
    base = {
        "name": "fixture",
        "context_length": 1000,
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "supported_parameters": [],
        "top_provider": {},
        "pricing": {},
    }

    gemini = updater.map_record({**base, "id": "google/gemini-2.5-flash"})
    grok = updater.map_record({**base, "id": "x-ai/grok-4.7"})

    assert gemini["provider"] == "openrouter"
    assert "gemini-2.5-flash" in gemini["aliases"]
    assert grok["provider"] == "openrouter"
    assert "grok-4.7" in grok["aliases"]
