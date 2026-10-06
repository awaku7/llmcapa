"""Tests for the official mdx.MaaS catalog updater's conservative mapping."""

import importlib.util
from io import BytesIO
from pathlib import Path

UPDATER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "_update_mdx_maas.py"
_SPEC = importlib.util.spec_from_file_location("mdx_maas_updater", UPDATER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_UPDATER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_UPDATER)


def test_fetch_model_rows_parses_official_sheet_csv(monkeypatch):
    csv_bytes = (
        ",,,,,\n"
        ",モデル名,説明,即時応答API,Batch API,起動待ち時間あり※\n"
        ",openai/gpt-oss-20b,reasoning model with max context 128k,〇,〇,\n"
        ",Qwen/Qwen3.6-27B-FP8,video model,〇,〇,あり\n"
    ).encode()

    class FakeResponse(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        _UPDATER, "urlopen", lambda request, timeout: FakeResponse(csv_bytes)
    )

    rows = _UPDATER._fetch_model_rows()
    assert [row["model_id"] for row in rows] == [
        "openai/gpt-oss-20b",
        "Qwen/Qwen3.6-27B-FP8",
    ]
    assert rows[1]["cold_start"] == "あり"


def test_record_uses_published_mdx_maas_capabilities():
    record = _UPDATER._record(
        {
            "model_id": "google/gemma-4-31B-it-qat-w4a16-ct",
            "description": "Multimodal model: text/image input and tool calling supported.",
            "immediate": "〇",
            "batch": "〇",
            "cold_start": "",
        },
        "2026-10-06",
    )

    assert record["provider"] == "mdx-maas"
    assert record["supports_chat_completion"] is True
    assert record["supports_responses_api"] is False
    assert record["supports_function_calling"] is True
    assert record["input_modalities"] == ["text", "image"]
    assert record["context_window"] == 0
    assert record["extra"]["api_availability"] == {
        "immediate": True,
        "batch": True,
    }


def test_record_keeps_unpublished_limits_unknown_and_maps_video():
    record = _UPDATER._record(
        {
            "model_id": "Qwen/Qwen3.6-27B-FP8",
            "description": "Multimodal language model; text, image, and video input; Thinking mode.",
            "immediate": "〇",
            "batch": "〇",
            "cold_start": "あり",
        },
        "2026-10-06",
    )

    assert record["context_window"] == 0
    assert record["max_output_tokens"] == 0
    assert record["pricing"] is None
    assert record["supports_reasoning"] is True
    assert record["input_modalities"] == ["text", "image", "video"]
    assert record["extra"]["api_availability"]["may_require_cold_start"] is True


def test_record_extracts_published_128k_context():
    record = _UPDATER._record(
        {
            "model_id": "openai/gpt-oss-20b",
            "description": "Reasoning model with a maximum context window of 128k.",
            "immediate": "〇",
            "batch": "〇",
            "cold_start": "",
        },
        "2026-10-06",
    )

    assert record["context_window"] == 128000
