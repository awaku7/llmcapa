"""Regression coverage for documented model rates and input modalities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import _update_deepinfra
import _update_hf_official_orgs
import _update_inception

import llmcapa


def test_mercury_3_does_not_treat_free_trial_as_zero_token_price() -> None:
    record = {
        "id": "mercury-3",
        "pricing": {
            "prompt": 0.0,
            "completion": 0.0,
            "input_cache_reads": 0.0,
        },
    }
    model = _update_inception._chat_entry(record, "2026-10-22")
    assert model["pricing"] == {
        "input_per_1m": 0.10,
        "output_per_1m": 0.35,
        "cached_input_per_1m": 0.01,
        "currency": "USD",
    }
    assert model["extra"]["list_pricing"]["input_per_1m"] == 0.20
    assert model["extra"]["free_trial"]["free_tokens"] == 100_000_000

    record["pricing"] = {
        "prompt": 0.33 / 1_000_000,
        "completion": 0.88 / 1_000_000,
        "input_cache_reads": 0.05 / 1_000_000,
    }
    updated = _update_inception._chat_entry(record, "2026-10-22")
    assert updated["pricing"]["input_per_1m"] == 0.33
    assert updated["pricing"]["output_per_1m"] == 0.88
    assert updated["pricing"]["cached_input_per_1m"] == 0.05


def test_ming_audio_modes_survive_hf_inventory_refresh() -> None:
    for suffix in ("flash", "tiny"):
        model_id = f"inclusionAI/Ming-3.0-audio-{suffix}"
        item = {"modelId": model_id, "pipeline_tag": "text-to-speech"}
        model = _update_hf_official_orgs._update_row(
            "inclusionai", "inclusionAI", item, "2026-10-22", None
        )
        assert model["input_modalities"] == ["text", "audio"]
        assert model["output_modalities"] == ["text", "audio"]

    other = _update_hf_official_orgs._update_row(
        "inclusionai",
        "inclusionAI",
        {"modelId": "inclusionAI/ordinary-tts", "pipeline_tag": "text-to-speech"},
        "2026-10-22",
        None,
    )
    assert other["input_modalities"] == ["text"]
    assert other["output_modalities"] == ["audio"]


def test_nemotron_35_embedding_keeps_image_input_and_published_rates() -> None:
    rates = {
        "1B": (0.015, 0.035),
        "8B": (0.035, 0.070),
    }
    for size, (text_rate, image_rate) in rates.items():
        name = f"nvidia/Nemotron-3.5-Embed-{size}-BF16"
        model = _update_deepinfra.model_to_entry(
            {
                "model_name": name,
                "type": "embeddings",
                "tags": ["multimodal"],
                "pricing": {},
            }
        )
        assert model is not None
        assert model["input_modalities"] == ["text", "image"]
        assert model["supports_vision"] is True
        assert model["pricing"]["input_per_1m"] == text_rate
        assert model["extra"]["image_input_per_1m"] == image_rate
        missing_tags = _update_deepinfra.model_to_entry(
            {"model_name": name, "type": "embeddings", "tags": []}
        )
        assert missing_tags is not None
        assert missing_tags["input_modalities"] == ["text", "image"]

    other = _update_deepinfra.model_to_entry(
        {"model_name": "other/embed", "type": "embeddings", "tags": ["multimodal"]}
    )
    assert other is not None
    assert other["input_modalities"] == ["text"]


def test_bundled_review_fixes_are_available_through_registry() -> None:
    inception = json.loads(
        (ROOT / "src/llmcapa/data/inception.json").read_text(encoding="utf-8")
    )
    mercury = next(m for m in inception["models"] if m["model_id"] == "mercury-3")
    assert mercury["pricing"]["input_per_1m"] == 0.10
    assert mercury["extra"]["free_trial"]["free_tokens"] == 100_000_000

    for suffix in ("flash", "tiny"):
        name = f"inclusionAI/Ming-3.0-audio-{suffix}"
        model = llmcapa.get(name, provider="inclusionai")
        assert model is not None
        assert model.supports("audio_input") is True
        assert model.supports("text_output") is True

    for size in ("1B", "8B"):
        name = f"nvidia/Nemotron-3.5-Embed-{size}-BF16"
        model = llmcapa.get(name, provider="deepinfra")
        assert model is not None
        assert model.supports("image_input") is True


def test_hf_image_feature_extraction_maps_modalities() -> None:
    model = _update_hf_official_orgs._new_model(
        "allenai",
        {
            "modelId": "allenai/OlmoEarth-v1_3-Base",
            "pipeline_tag": "image-feature-extraction",
        },
    )
    assert model["input_modalities"] == ["image"]
    assert model["output_modalities"] == ["embedding"]
    assert model["supports_vision"] is True

    other = _update_hf_official_orgs._new_model(
        "allenai",
        {"modelId": "allenai/text-model", "pipeline_tag": "feature-extraction"},
    )
    assert other["input_modalities"] == ["text"]
    assert other["output_modalities"] == ["embedding"]


def test_bundled_olmoearth_image_feature_capabilities() -> None:
    model = llmcapa.get("allenai/OlmoEarth-v1_3-Base", provider="allenai")
    assert model is not None
    assert model.supports("image_input") is True
    assert model.supports("embedding_output") is True
