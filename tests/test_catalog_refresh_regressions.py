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


def test_refresh_safety_retains_models_omitted_by_current_source():
    refresh = _script_module("refresh_catalogs")
    previous = {
        "models": [
            {
                "provider": "example",
                "model_id": "legacy-model",
                "context_window": 32768,
                "max_output_tokens": 4096,
                "image": {"accepts_image_input": True},
                "extra": {"curated": True},
            }
        ]
    }
    updated = {
        "models": [
            {
                "provider": "example",
                "model_id": "new-model",
                "context_window": 8192,
                "max_output_tokens": 2048,
            }
        ]
    }

    retained = refresh.retain_unlisted_models(
        previous, updated, checked_at="2026-10-24"
    )

    assert retained == 1
    old = updated["models"][-1]
    assert old["model_id"] == "legacy-model"
    assert old["image"] == {"accepts_image_input": True}
    assert old["extra"] == {
        "curated": True,
        "not_listed_in_current_provider_refresh": True,
        "provider_refresh_checked_at": "2026-10-24",
    }
    assert previous["models"][0]["extra"] == {"curated": True}
    refresh.validate_refreshed_catalog(previous, updated)


def test_refresh_safety_backfills_omitted_capabilities_with_provenance():
    refresh = _script_module("refresh_catalogs")
    previous = {
        "models": [
            {
                "provider": "example",
                "model_id": "known-model",
                "context_window": 32768,
                "max_output_tokens": 4096,
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
                "image": {"accepts_image_input": True},
            }
        ]
    }
    updated = {
        "models": [
            {
                "provider": "example",
                "model_id": "known-model",
                "context_window": 0,
                "max_output_tokens": 0,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            }
        ]
    }

    changed = refresh.preserve_known_capabilities(
        previous, updated, checked_at="2026-10-24"
    )

    assert changed == 1
    row = updated["models"][0]
    assert row["context_window"] == 32768
    assert row["max_output_tokens"] == 4096
    assert row["input_modalities"] == ["text", "image"]
    assert row["image"] == {"accepts_image_input": True}
    assert row["extra"]["refresh_metadata_fallbacks"] == [
        "context_window",
        "image",
        "input_modalities",
        "max_output_tokens",
    ]
    assert row["extra"]["refresh_metadata_fallback_checked_at"] == "2026-10-24"
    refresh.validate_refreshed_catalog(previous, updated)


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


def test_azure_foundry_retains_and_enriches_microsoft_decision_ssr_card():
    updater = _script_module("_update_azure_foundry")
    card = {
        "name": "Microsoft-Decision-1",
        "displayName": "Microsoft-Decision-1",
        "source": "ssr_card",
    }

    assert updater.is_supported_catalog_item(card)
    row = updater.build_entry(card, {})

    assert row["provider"] == "microsoft"
    assert row["model_id"] == "Microsoft-Decision-1"
    assert row["context_window"] == 32768
    assert row["input_modalities"] == ["text"]
    assert row["output_modalities"] == ["decision"]
    assert row["azure_lifecycle"] == "GA"
    assert row["decision"]["question_kinds"] == ["noul", "choice", "score"]
    assert row["decision"]["endpoints"] == [
        "https://{azure_endpoint}/providers/microsoft/v1/systemone"
    ]


def test_azure_foundry_preserves_missing_curated_specialized_metadata():
    updater = _script_module("_update_azure_foundry")
    previous = {
        "image": {"accepts_image_input": True, "source_url": "official"},
        "video": {"understanding": True},
        "audio": {"input": True, "output": True},
        "computer_use": {"supported": True, "provider": "azure-foundry"},
    }
    row = {}

    updater._preserve_curated_fields(row, previous)

    assert row == previous


def test_azure_foundry_ssr_cards_keep_existing_curated_metadata():
    updater = _script_module("_update_azure_foundry")
    previous = {"image": {"accepts_image_input": True}}
    refreshed = {"image": {"generation": True}}

    updater._preserve_curated_fields(refreshed, previous, prefer_previous=True)

    assert refreshed["image"] == previous["image"]


def test_azure_foundry_retains_models_missing_from_live_catalog():
    updater = _script_module("_update_azure_foundry")
    previous = {
        "old-model": {
            "provider": "microsoft",
            "model_id": "old-model",
            "deprecated": False,
            "extra": {"verified": True},
        }
    }
    current = {"new-model": {"provider": "microsoft", "model_id": "new-model"}}

    retained = updater._retain_unlisted_catalog_rows(current, previous)

    assert retained == 1
    assert current["old-model"]["deprecated"] is False
    assert current["old-model"]["extra"] == {
        "verified": True,
        "not_listed_in_current_docs": True,
    }
    assert previous["old-model"]["extra"] == {"verified": True}
