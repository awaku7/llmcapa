"""Regression tests for shared record-level capability normalization."""

from scripts._capability_normalizers import (
    apply_audio,
    apply_structured,
    apply_video,
    normalize_audio_record,
    normalize_decision_record,
    normalize_image_record,
    normalize_record,
    normalize_video_record,
    preserve_capability_blocks,
)


def test_image_input_does_not_imply_generation():
    record = {
        "provider": "test",
        "model_id": "vision-chat",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_vision": False,
    }

    assert normalize_image_record(record, checked_at="2026-09-29") is True
    assert record["image"]["accepts_image_input"] is True
    assert record["image"].get("generation") is not True
    assert record["supports_vision"] is True


def test_recognized_image_output_is_generation():
    record = {
        "provider": "test",
        "model_id": "flux-image-generator",
        "input_modalities": ["text"],
        "output_modalities": ["image"],
    }

    assert normalize_image_record(record, checked_at="2026-09-29") is True
    assert record["image"]["generation"] is True
    assert record["image"]["accepts_text_prompt"] is True
    assert record["image"]["accepts_image_input"] is False


def test_video_input_and_generation_are_distinct():
    understanding = {
        "provider": "test",
        "model_id": "video-understanding",
        "input_modalities": ["text", "video"],
        "output_modalities": ["text"],
    }
    generation = {
        "provider": "test",
        "model_id": "demo-text-to-video",
        "input_modalities": ["text"],
        "output_modalities": ["video"],
    }

    assert normalize_video_record(understanding, checked_at="2026-09-29") is True
    assert understanding["video"]["accepts_video_input"] is True
    assert understanding["video"]["understanding"] is True
    assert understanding["video"]["generation"] is False

    assert normalize_video_record(generation, checked_at="2026-09-29") is True
    assert generation["video"]["accepts_video_input"] is False
    assert generation["video"]["generation"] is True
    assert generation["video"]["text_to_video"] is True


def test_decision_requires_explicit_output_modality():
    named_only = {
        "provider": "test",
        "model_id": "decision-maker",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
    }
    explicit = {
        "provider": "test",
        "model_id": "typed-decision",
        "input_modalities": ["text"],
        "output_modalities": ["decision"],
        "supports_chat_completion": True,
    }

    assert normalize_decision_record(named_only, checked_at="2026-09-29") is False
    assert "decision" not in named_only

    assert normalize_decision_record(explicit, checked_at="2026-09-29") is True
    assert explicit["decision"]["decision"] is True
    assert explicit["decision"]["free_form_text"] is False
    assert explicit["supports_chat_completion"] is False


def test_curated_capability_values_beat_generic_inference():
    record = {
        "provider": "test",
        "model_id": "audio-model",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "supports_streaming": True,
        "audio": {
            "accepts_audio_input": True,
            "supports_streaming": False,
            "status": "documented",
            "extra": {"curated": True},
        },
    }

    assert normalize_audio_record(record, checked_at="2026-09-29") is True
    assert record["audio"]["supports_streaming"] is False
    assert record["audio"]["status"] == "documented"
    assert record["audio"]["extra"]["curated"] is True


def test_decision_block_is_preserved_before_normalization():
    previous = {
        "provider": "typesafe",
        "model_id": "jev",
        "decision": {
            "decision": True,
            "returns_probabilities": True,
            "calibrated_confidence": True,
            "question_kinds": ["choice", "score"],
            "status": "documented",
        },
    }
    record = {
        "provider": "typesafe",
        "model_id": "jev",
        "input_modalities": ["text"],
        "output_modalities": ["decision"],
        "supports_chat_completion": True,
    }

    assert preserve_capability_blocks(record, previous) is True
    assert normalize_record(record, checked_at="2026-09-29") is True
    assert record["decision"]["returns_probabilities"] is True
    assert record["decision"]["calibrated_confidence"] is True
    assert record["decision"]["question_kinds"] == ["choice", "score"]
    assert record["decision"]["free_form_text"] is False
    assert record["supports_chat_completion"] is False


def test_image_top_level_flag_change_is_reported():
    record = {
        "provider": "test",
        "model_id": "vision-chat",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_vision": False,
        "image": {
            "accepts_image_input": True,
            "status": "inferred",
            "checked_at": "2026-09-29",
        },
    }

    assert normalize_image_record(record, checked_at="2026-09-29") is True
    assert record["supports_vision"] is True


def test_decision_top_level_flag_change_is_reported():
    record = {
        "provider": "test",
        "model_id": "typed-decision",
        "input_modalities": ["text"],
        "output_modalities": ["decision"],
        "supports_chat_completion": True,
        "decision": {
            "decision": True,
            "free_form_text": False,
            "status": "inferred",
            "checked_at": "2026-09-29",
        },
    }

    assert normalize_decision_record(record, checked_at="2026-09-29") is True
    assert record["supports_chat_completion"] is False


def test_audio_catalog_task_drives_transcription_without_name_hint():
    record = {
        "provider": "foundry-local",
        "model_id": "parakeet-tdt-0.6b-v2",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "supports_streaming": False,
        "extra": {"tasks": ["automatic-speech-recognition"]},
    }

    assert normalize_audio_record(record, checked_at="2026-09-29") is True
    assert record["audio"]["transcription"] is True
    assert record["audio"]["supports_streaming"] is None


def test_audio_streaming_hint_overrides_chat_only_false_for_inferred_block():
    record = {
        "provider": "foundry-local",
        "model_id": "nemotron-speech-streaming-en-0.6b",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "supports_streaming": False,
        "extra": {"tasks": ["automatic-speech-recognition"]},
        "audio": {
            "accepts_audio_input": True,
            "speech_understanding": True,
            "supports_streaming": False,
            "status": "inferred",
            "checked_at": "2026-09-28",
        },
    }

    assert normalize_audio_record(record, checked_at="2026-09-29") is True
    assert record["audio"]["transcription"] is True
    assert record["audio"]["supports_streaming"] is True


def test_documented_audio_streaming_value_remains_curated():
    record = {
        "provider": "test",
        "model_id": "streaming-audio",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "supports_streaming": True,
        "audio": {
            "accepts_audio_input": True,
            "supports_streaming": False,
            "status": "documented",
            "checked_at": "2026-09-28",
        },
    }

    normalize_audio_record(record, checked_at="2026-09-29")
    assert record["audio"]["supports_streaming"] is False


def test_fresh_video_inference_replaces_preserved_inferred_values():
    record = {
        "provider": "test",
        "model_id": "demo-text-to-video",
        "input_modalities": ["text"],
        "output_modalities": ["video"],
        "video": {
            "accepts_video_input": True,
            "generation": False,
            "understanding": True,
            "status": "inferred",
            "checked_at": "2026-09-28",
        },
    }

    assert normalize_video_record(record, checked_at="2026-09-29") is True
    assert record["video"]["accepts_video_input"] is False
    assert record["video"]["generation"] is True
    assert record["video"]["understanding"] is False


def test_stale_inferred_capability_is_removed_when_modality_disappears():
    record = {
        "provider": "test",
        "model_id": "plain-text",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "audio": {
            "accepts_audio_input": True,
            "speech_understanding": True,
            "status": "inferred",
        },
    }

    assert normalize_audio_record(record, checked_at="2026-09-29") is True
    assert "audio" not in record


def test_documented_capability_survives_when_generic_signal_disappears():
    record = {
        "provider": "test",
        "model_id": "plain-text",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "audio": {
            "accepts_audio_input": True,
            "status": "documented",
            "source_url": "https://example.test/audio",
        },
    }

    assert normalize_audio_record(record, checked_at="2026-09-29") is False
    assert record["audio"]["status"] == "documented"


def test_stale_inferred_decision_block_is_removed():
    record = {
        "provider": "test",
        "model_id": "now-text",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "decision": {
            "decision": True,
            "free_form_text": False,
            "status": "inferred",
        },
    }

    assert normalize_decision_record(record, checked_at="2026-09-29") is True
    assert "decision" not in record


def test_stale_inferred_embedding_block_is_removed():
    record = {
        "provider": "test",
        "model_id": "plain-text",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "embedding": {
            "embedding": True,
            "output_formats": ["float"],
            "status": "inferred",
        },
    }

    assert normalize_record(record, checked_at="2026-09-29") is True
    assert "embedding" not in record


def test_generic_image_source_url_remains_refreshable_inference():
    record = {
        "provider": "foundry-local",
        "model_id": "vision-chat",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "extra": {"source": "https://ai.azure.com/api/catalog"},
    }
    assert normalize_image_record(record, checked_at="2026-09-29") is True
    assert record["image"]["accepts_image_input"] is True
    assert record["image"]["source_url"] == "https://ai.azure.com/api/catalog"
    assert record["image"]["status"] == "inferred"


def test_compatibility_apply_functions_remove_stale_derived_blocks(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text(
        __import__("json").dumps(
            {
                "models": [
                    {
                        "provider": "test",
                        "model_id": "old-audio",
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                        "audio": {"transcription": True, "status": "inferred"},
                    },
                    {
                        "provider": "test",
                        "model_id": "old-video",
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                        "video": {"generation": True, "status": "inferred"},
                    },
                    {
                        "provider": "test",
                        "model_id": "old-vector-model",
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                        "embedding": {"embedding": True, "status": "inferred"},
                    },
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert apply_audio(tmp_path)["records_changed"] == 1
    assert apply_video(tmp_path)["records_changed"] == 1
    assert apply_structured(tmp_path)["records_changed"] == 1
    data = __import__("json").loads(path.read_text(encoding="utf-8"))
    by_id = {record["model_id"]: record for record in data["models"]}
    assert "audio" not in by_id["old-audio"]
    assert "video" not in by_id["old-video"]
    assert "embedding" not in by_id["old-vector-model"]
