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
