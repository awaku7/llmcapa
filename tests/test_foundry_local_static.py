"""Tests for the bundled Microsoft Foundry Local catalog."""

import llmcapa
from scripts._capability_normalizers import normalize_record, preserve_capability_blocks


def test_foundry_local_catalog_is_bundled_and_offline() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    assert models
    assert all(model.provider == "foundry-local" for model in models)
    assert all(
        model.extra.get("source_type") == "official_foundry_local_catalog_api"
        for model in models
    )


def test_foundry_local_aliases_and_capabilities_are_queryable() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    model = next((item for item in models if item.aliases), models[0])
    resolved = llmcapa.get(model.model_id, provider="foundry_local")
    assert resolved.model_id == model.model_id
    assert resolved.extra.get("source_type") == "official_foundry_local_catalog_api"


def test_foundry_local_is_not_a_runtime_fetch_api() -> None:
    assert not hasattr(llmcapa, "fetch_foundry_local")


def test_foundry_local_catalog_contains_only_runnable_variants() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    for model in models:
        variants = model.extra.get("variants", [])
        assert variants
        assert all(variant.get("device") for variant in variants)
        assert all(variant.get("execution_provider") for variant in variants)


def test_foundry_local_exposes_catalog_context_windows_and_licenses() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    with_context = [model for model in models if model.context_window > 0]
    assert with_context
    assert llmcapa.find(provider="foundry-local", min_context_window=1)

    licensed = [model for model in models if model.extra.get("licenses")]
    assert licensed
    for model in licensed:
        licenses = {
            str(value).strip().lower()
            for value in model.extra["licenses"]
            if str(value).strip()
        }
        if len(licenses) == 1:
            assert model.license_type.lower() == next(iter(licenses))


def test_foundry_local_specialized_capabilities_are_normalized() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    audio_models = [
        model
        for model in models
        if "audio" in model.input_modalities or "audio" in model.output_modalities
    ]
    embedding_models = [
        model
        for model in models
        if "embedding" in model.output_modalities
        or "embeddings" in model.output_modalities
    ]
    assert audio_models
    assert embedding_models
    assert all(model.audio is not None for model in audio_models)
    assert all(model.embedding is not None for model in embedding_models)


def test_integrated_normalizer_preserves_curated_capability_details() -> None:
    previous = {
        "provider": "foundry-local",
        "model_id": "sample-audio",
        "audio": {
            "accepts_audio_input": True,
            "curated_detail": "keep-me",
            "extra": {"curated": True},
        },
    }
    refreshed = {
        "provider": "foundry-local",
        "model_id": "sample-audio",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "supports_streaming": False,
        "extra": {},
    }

    assert preserve_capability_blocks(refreshed, previous)
    assert normalize_record(refreshed, checked_at="2026-09-29")
    assert refreshed["audio"]["curated_detail"] == "keep-me"
    assert refreshed["audio"]["extra"]["curated"] is True
    assert refreshed["audio"]["speech_understanding"] is True


def test_foundry_local_generic_image_blocks_remain_refreshable() -> None:
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "llmcapa"
        / "data"
        / "foundry_local.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    checked = 0
    for record in data.get("models", []):
        image = record.get("image")
        extra = record.get("extra") or {}
        if not isinstance(image, dict):
            continue
        if image.get("source_url") != extra.get("source"):
            continue
        checked += 1
        assert image.get("status") == "inferred"
    assert checked == 9
