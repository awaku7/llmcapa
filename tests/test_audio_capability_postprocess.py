from __future__ import annotations

import json

import llmcapa
from scripts._audio_capability_postprocess import apply


MODEL_ID = "MAI-Transcribe-2-Streaming"
MODEL_CARD_URL = (
    "https://microsoft.ai/pdf/MAI-Transcribe-2-Streaming-Model-Card-Memo.pdf"
)


def test_mai_transcribe_streaming_catalog_is_realtime_documented() -> None:
    model = llmcapa.get(MODEL_ID, provider="microsoft")

    assert model.audio is not None
    assert model.audio.transcription is True
    assert model.audio.supports_streaming is True
    assert model.audio.supports_realtime is True
    assert model.audio.source_url == MODEL_CARD_URL
    assert model.audio.status == "documented"
    assert model.audio.endpoints is not None
    assert model.audio.endpoints.realtime is True
    assert model.audio.endpoints.streaming is True


def test_audio_postprocess_keeps_mai_realtime_override(tmp_path) -> None:
    catalog = {
        "models": [
            {
                "provider": "microsoft",
                "model_id": MODEL_ID,
                "input_modalities": ["audio"],
                "output_modalities": ["text"],
                "supports_streaming": True,
            }
        ]
    }
    (tmp_path / "microsoft.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )

    result = apply(tmp_path)

    updated = json.loads((tmp_path / "microsoft.json").read_text(encoding="utf-8"))
    audio = updated["models"][0]["audio"]
    assert result["records_changed"] == 1
    assert audio["supports_realtime"] is True
    assert audio["supports_streaming"] is True
    assert audio["transcription"] is True
    assert audio["source_url"] == MODEL_CARD_URL
    assert audio["status"] == "documented"
    assert audio["endpoints"]["realtime"] is True
    assert audio["endpoints"]["streaming"] is True
