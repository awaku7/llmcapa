"""Tests for the bundled Microsoft Foundry Local catalog."""

import json
from pathlib import Path

import llmcapa
from scripts import _update_foundry_local as updater


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


def test_foundry_local_specialized_capabilities_are_postprocessed() -> None:
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


def test_foundry_local_asr_tasks_expose_transcription() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    asr_models = [
        model
        for model in models
        if "automatic-speech-recognition"
        in {str(task).lower() for task in model.extra.get("tasks", [])}
    ]
    assert asr_models
    assert all(model.audio is not None for model in asr_models)
    assert all(model.audio.transcription is True for model in asr_models)
    assert all(model.audio.endpoints.transcription is True for model in asr_models)


def test_foundry_local_streaming_audio_preserves_streaming_support() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    streaming_models = [
        model
        for model in models
        if "audio" in model.input_modalities and "streaming" in model.model_id.lower()
    ]
    assert streaming_models
    assert all(model.supports_streaming is True for model in streaming_models)
    assert all(model.audio is not None for model in streaming_models)
    assert all(model.audio.supports_streaming is True for model in streaming_models)


def test_foundry_local_updater_applies_postprocessors(tmp_path: Path) -> None:
    output = tmp_path / "foundry_local.json"
    output.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "foundry-local",
                        "model_id": "speech-streaming",
                        "input_modalities": ["audio"],
                        "output_modalities": ["text"],
                        "supports_streaming": True,
                        "extra": {"media_model_type": "asr"},
                    },
                    {
                        "provider": "foundry-local",
                        "model_id": "text-embedding",
                        "input_modalities": ["text"],
                        "output_modalities": ["embedding"],
                        "supports_streaming": False,
                        "extra": {},
                    },
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    updater._postprocess_output(output)
    records = json.loads(output.read_text(encoding="utf-8"))["models"]
    speech, embedding = records
    assert speech["audio"]["transcription"] is True
    assert speech["audio"]["supports_streaming"] is True
    assert speech["audio"]["endpoints"]["transcription"] is True
    assert speech["audio"]["endpoints"]["streaming"] is True
    assert embedding["embedding"]
