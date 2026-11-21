"""Refresh the Google Cloud Vertex AI Model Garden catalog via the official SDK.

This catalog is separate from google.json and never reads OpenRouter. Install
with: pip install "google-cloud-aiplatform>=1.84"
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from _computer_use_metadata import (
    GOOGLE_COMPUTER_USE_MODELS,
    google_computer_use_capability,
)

ROOT = Path(__file__).resolve().parents[1]
GOOGLE = ROOT / "src" / "llmcapa" / "data" / "google.json"
OUT = ROOT / "src" / "llmcapa" / "data" / "vertex-ai.json"
SOURCE = "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models"
THINKING_SOURCE = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking"
)
COMPUTER_USE_SOURCE = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/computer-use"
)
VERTEX_COMPUTER_USE_MODELS = GOOGLE_COMPUTER_USE_MODELS - {"gemini-3.5-flash-lite"}

# First-party Vertex Gemini controls. These are model-specific and deliberately
# kept separate from OpenAI-compatible reasoning_effort.
VERTEX_GEMINI_SPECS = {
    "gemini-2.5-pro": {
        "parameter": "thinking_budget",
        "supports_thinking_budget": True,
        "thinking_budget_values": {"type": "token_range", "min": 0, "max": 32768},
    },
    "gemini-2.5-flash": {
        "parameter": "thinking_budget",
        "supports_thinking_budget": True,
        "thinking_budget_values": {"type": "token_range", "min": 0, "max": 24576},
    },
    "gemini-2.5-flash-lite": {
        "parameter": "thinking_budget",
        "supports_thinking_budget": True,
        "thinking_budget_values": {"type": "token_range", "min": 512, "max": 24576},
    },
    "gemini-3-pro-preview": {
        "parameter": "thinking_level",
        "thinking_level_values": ["low", "high"],
    },
    "gemini-3.8-flash": {
        "parameter": "thinking_level",
        "thinking_level_values": ["low", "medium", "high"],
    },
    "gemini-3-flash-preview": {
        "parameter": "thinking_level",
        "thinking_level_values": ["minimal", "low", "medium", "high"],
    },
    "gemini-4-argon": {
        "parameter": "thinking_level",
        "thinking_level_values": ["low", "medium", "high"],
    },
    "gemini-4-carbon": {
        "parameter": "thinking_level",
        "thinking_level_values": ["low", "medium", "high"],
    },
    "gemini-4-hydrogen": {
        "parameter": "thinking_level",
        "thinking_level_values": ["low", "medium", "high", "xhigh"],
    },
    "gemini-4-neon": {
        "parameter": "thinking_level",
        "thinking_level_values": ["low", "medium", "high", "xhigh"],
    },
}


def _vertex_model_page_spec(
    display_name: str,
    page: str,
    context_window: int,
    max_output_tokens: int,
    input_modalities: list[str],
    output_modalities: list[str],
    **flags,
) -> dict:
    return {
        "display_name": display_name,
        "source": f"https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/{page}",
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        **flags,
    }


# Model Garden SDK discovery can lag the official first-party model index.
# Keep the linked model-page IDs explicit and use their pages as the source of
# truth for token limits and modalities.
VERTEX_GEMINI_MODEL_PAGE_SPECS = {
    "gemini-3.1-pro-preview": _vertex_model_page_spec(
        "Gemini 3.1 Pro", "3-1-pro", 1_048_576, 65_536,
        ["text", "image", "audio", "video", "file"], ["text"],
    ),
    "gemini-3.6-flash": _vertex_model_page_spec(
        "Gemini 3.6 Flash", "3-6-flash", 1_048_576, 65_536,
        ["text", "image", "audio", "video", "file"], ["text"],
    ),
    "gemini-live-2.5-flash-native-audio": _vertex_model_page_spec(
        "Gemini 2.5 Flash with Gemini Live API", "2-5-flash-live-api",
        131_072, 65_536, ["text", "image", "audio", "video"],
        ["text", "audio"], supports_chat_completion=False,
        supports_function_calling=True, supports_json_mode=False,
        supports_reasoning=False, supports_realtime=True,
        supports_streaming=True,
    ),
    "gemini-3.5-flash-lite": _vertex_model_page_spec(
        "Gemini 3.5 Flash-Lite", "3-5-flash-lite", 1_048_576, 65_536,
        ["text", "image", "audio", "video", "file"], ["text"],
    ),
    "gemini-3.1-flash-lite": _vertex_model_page_spec(
        "Gemini 3.1 Flash-Lite", "3-1-flash-lite", 1_048_576, 65_536,
        ["text", "image", "audio", "video", "file"], ["text"],
    ),
    "gemini-nano-banana-2.1": _vertex_model_page_spec(
        "Gemini Nano Banana 2.1", "nano-banana-2-1", 131_072, 32_768,
        ["text", "image", "video", "file"], ["text", "image"],
    ),
    "gemini-3.1-flash-image": _vertex_model_page_spec(
        "Gemini 3.1 Flash Image (Nano Banana 2)", "3-1-flash-image",
        131_072, 32_768, ["text", "image", "video", "file"], ["text", "image"],
    ),
    "gemini-3.1-flash-lite-image": _vertex_model_page_spec(
        "Gemini 3.1 Flash-Lite Image (Nano Banana 2 Lite)",
        "3-1-flash-lite-image", 65_536, 4_096,
        ["text", "image", "video", "file"], ["text", "image"],
    ),
    "gemini-3-pro-image": _vertex_model_page_spec(
        "Gemini 3 Pro Image (Nano Banana Pro)", "3-pro-image", 65_536,
        32_768, ["text", "image", "file"], ["text", "image"],
    ),
    "gemini-2.5-flash-image": _vertex_model_page_spec(
        "Gemini 2.5 Flash Image", "2-5-flash-image", 32_768, 32_768,
        ["text", "image", "file"], ["text", "image"],
    ),
    "gemini-omni-1.2-flash": _vertex_model_page_spec(
        "Gemini Omni 1.2 Flash", "omni-1-2-flash", 131_072, 260_640,
        ["text", "image", "video"], ["text", "video"],
    ),
    "gemini-omni-1.1-flash-preview": _vertex_model_page_spec(
        "Gemini Omni 1.1 Flash Preview", "omni-1-1-flash", 131_072,
        57_920, ["text", "image", "video"], ["text", "video"],
    ),
    "gemini-omni-flash-preview": _vertex_model_page_spec(
        "Gemini Omni Flash Preview", "omni-flash-preview", 131_072,
        57_920, ["text", "image", "video"], ["text", "video"],
    ),
    "gemini-3.8-flash": _vertex_model_page_spec(
        "Gemini 3.8 Flash", "3-8-flash", 1_048_576, 65_536,
        ["text", "image", "audio", "video", "file"], ["text"],
        supports_reasoning=True,
    ),
    "gemini-3.8-flash-cyber": _vertex_model_page_spec(
        "Gemini 3.8 Flash Cyber", "3-8-flash-cyber", 1_048_576,
        65_536, ["text", "image", "audio", "video", "file"], ["text"],
        supports_chat_completion=True, supports_function_calling=True,
        supports_json_mode=True, supports_reasoning=True,
    ),
    "gemini-3.8-live": _vertex_model_page_spec(
        "Gemini 3.8 Live", "3-8-live", 131_072, 65_536,
        ["text", "image", "audio", "video"], ["text", "audio", "video"],
        supports_chat_completion=False, supports_function_calling=True,
        supports_json_mode=False, supports_reasoning=False,
        supports_realtime=True, supports_streaming=True,
    ),
    "gemini-3.8-flash-tts": _vertex_model_page_spec(
        "Gemini 3.8 Flash TTS", "3-8-flash-tts", 8_192, 16_384,
        ["text"], ["audio"], supports_chat_completion=False,
        supports_function_calling=False, supports_json_mode=False,
        supports_reasoning=False, supports_streaming=True,
    ),
    "gemini-3.8-flash-lite-tts": _vertex_model_page_spec(
        "Gemini 3.8 Flash-Lite TTS", "3-8-flash-lite-tts", 8_192,
        16_384, ["text"], ["audio"], supports_chat_completion=False,
        supports_function_calling=False, supports_json_mode=False,
        supports_reasoning=False, supports_streaming=True,
    ),
    "gemini-3.5-transcribe": _vertex_model_page_spec(
        "Gemini 3.5 Transcribe", "3-5-transcribe", 0, 0,
        ["audio"], ["text"], supports_chat_completion=False,
        supports_function_calling=False, supports_json_mode=False,
        supports_reasoning=False, supports_streaming=False,
    ),
    "gemini-3.5-transcribe-live": _vertex_model_page_spec(
        "Gemini 3.5 Transcribe Live", "3-5-transcribe", 0, 0,
        ["audio"], ["text"], supports_chat_completion=False,
        supports_function_calling=False, supports_json_mode=False,
        supports_reasoning=False, supports_realtime=True,
        supports_streaming=True,
    ),
    "gemini-3.5-live-translate-preview": _vertex_model_page_spec(
        "Gemini 3.5 Live Translate", "3-5-live-translate", 131_072,
        65_536, ["audio"], ["text", "audio"],
        supports_chat_completion=False, supports_function_calling=False,
        supports_json_mode=False, supports_reasoning=False,
        supports_realtime=True, supports_streaming=True,
    ),
    "gemini-embedding-2": _vertex_model_page_spec(
        "Gemini Embedding 2", "embedding-2", 8_192, 0,
        ["text", "image", "audio", "video", "file"], ["embedding"],
        supports_chat_completion=False, supports_function_calling=False,
        supports_json_mode=False, supports_reasoning=False,
    ),
    "gemini-robotics-er-2-preview": _vertex_model_page_spec(
        "Gemini Robotics ER 2", "robotics-er-2", 131_072, 65_536,
        ["text", "image", "audio", "video"], ["text"],
        supports_reasoning=True,
    ),
}

VERTEX_GEMINI_MODALITY_OVERRIDES = {
    "gemini-3.8-flash": {
        "input_modalities": ["image", "audio", "video", "file"],
        "source": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash",
    },
    "gemini-4-argon": {
        "input_modalities": ["image", "audio", "video", "file"],
        "source": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/4-argon",
    },
    "gemini-4-carbon": {
        "input_modalities": ["image", "audio", "video", "file"],
        "source": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/4-carbon",
    },
    "gemini-4-hydrogen": {
        "input_modalities": ["image", "audio", "video", "file"],
        "source": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/4-hydrogen",
    },
    "gemini-4-neon": {
        "input_modalities": ["image", "audio", "video", "file"],
        "source": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/4-neon",
    },
}

_VERTEX_GEMINI_4_VIDEO_MIME_TYPES = [
    "video/x-flv",
    "video/quicktime",
    "video/mpeg",
    "video/mpegs",
    "video/mpg",
    "video/mp4",
    "video/webm",
    "video/wmv",
    "video/3gpp",
]


def discover_models() -> list[tuple[str, str]]:
    """Return SDK-discoverable Model Garden models as (id, display_name)."""
    try:
        from vertexai import model_garden
    except ImportError as exc:
        raise RuntimeError(
            "Install the maintenance dependency first: "
            'pip install "google-cloud-aiplatform>=1.84"'
        ) from exc

    models = model_garden.list_deployable_models(list_hf_models=True)
    result: dict[str, str] = {}
    for item in models or []:
        if isinstance(item, str):
            model_id, label = item, item
        elif isinstance(item, dict):
            model_id = (
                item.get("model_id")
                or item.get("modelId")
                or item.get("name")
                or item.get("id")
            )
            label = (
                item.get("display_name")
                or item.get("displayName")
                or item.get("name")
                or model_id
            )
        else:
            model_id = next(
                (
                    getattr(item, key, None)
                    for key in ("model_id", "modelId", "name", "id")
                    if getattr(item, key, None)
                ),
                None,
            )
            label = next(
                (
                    getattr(item, key, None)
                    for key in ("display_name", "displayName", "name")
                    if getattr(item, key, None)
                ),
                model_id,
            )
        if model_id:
            result[str(model_id)] = str(label or model_id)
    if len(result) < 20:
        raise RuntimeError(
            f"Vertex AI SDK returned too few deployable models: {len(result)}"
        )
    # The SDK Model Garden listing may omit first-party Gemini IDs even though
    # they are supported by Vertex AI. Keep the official Gemini set explicit
    # so their model-specific thinking controls are not lost.
    for model_id in VERTEX_GEMINI_SPECS:
        result.setdefault(model_id, model_id.replace("-", " ").title())
    # The official model index also documents first-party models that can lag
    # the SDK listing. Add those exact page IDs to keep the catalog complete.
    for model_id, spec in VERTEX_GEMINI_MODEL_PAGE_SPECS.items():
        result.setdefault(model_id, spec["display_name"])
    return sorted(result.items())


def minimal(model_id: str, label: str) -> dict:
    return {
        "provider": "vertex-ai",
        "model_id": model_id,
        "display_name": label,
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_chat_completion": True,
        "supports_streaming": True,
        "supports_function_calling": None,
        "supports_json_mode": None,
        "supports_vision": None,
        "supports_reasoning": None,
        "supports_responses_api": False,
        "pricing": None,
        "deprecated": False,
        "aliases": [],
        "extra": {
            "source": SOURCE,
            "platform": "Google Cloud Vertex AI / Model Garden",
            "spec_status": "sdk_listed_only",
        },
    }


def enrich_thinking(row: dict) -> None:
    """Attach first-party Vertex Gemini thinking controls by model family."""
    model_id = row.get("model_id", "").lower()
    spec = next(
        (
            value
            for key, value in sorted(
                VERTEX_GEMINI_SPECS.items(), key=lambda item: len(item[0]), reverse=True
            )
            if model_id.startswith(key)
        ),
        None,
    )
    if not spec:
        return
    row["supports_reasoning"] = True
    row["supports_reasoning_effort"] = False
    row["reasoning_effort_values"] = None
    row["supports_thinking_level"] = bool(spec.get("thinking_level_values"))
    row["thinking_level_values"] = list(spec.get("thinking_level_values", [])) or None
    if spec.get("supports_thinking_budget"):
        row["supports_thinking_budget"] = True
        row["thinking_budget_values"] = dict(spec["thinking_budget_values"])
    if spec["parameter"] == "thinking_budget":
        row["thinking_control"] = {
            "kind": "budget",
            "parameter": "thinking_budget",
            **row["thinking_budget_values"],
        }
    else:
        row["thinking_control"] = {
            "kind": "level",
            "parameter": "thinking_level",
            "values": list(spec["thinking_level_values"]),
        }
    extra = row.setdefault("extra", {})
    extra["thinking_parameter"] = spec["parameter"]
    if "thinking_level_values" in spec:
        extra["thinking_level_values"] = list(spec["thinking_level_values"])
    extra["thinking_source"] = THINKING_SOURCE


def enrich_vertex_gemini_modalities(row: dict) -> None:
    """Add modality support explicitly documented by Vertex Gemini 4 guides."""
    override = VERTEX_GEMINI_MODALITY_OVERRIDES.get(row.get("model_id", "").lower())
    if not override:
        return
    current = row.get("input_modalities")
    current = current if isinstance(current, list) else []
    row["input_modalities"] = list(
        dict.fromkeys([*current, *override["input_modalities"]])
    )
    if "image" in row["input_modalities"]:
        row["supports_vision"] = True
    if "audio" in override["input_modalities"]:
        row["supports_audio_input"] = True
        row["supports_audio_output"] = bool(override.get("supports_audio_output", False))
        row["audio"] = {
            "accepts_audio_input": True,
            "speech_generation": False,
            "speech_understanding": True,
            "supports_streaming": None,
            "supports_realtime": None,
            "source_url": override["source"],
            "status": "documented",
            "endpoints": {"speech_understanding": True},
            "extra": {},
        }
    if "video" in override["input_modalities"]:
        row["video"] = {
            "accepts_video_input": True,
            "generation": False,
            "understanding": True,
            "text_to_video": False,
            "image_to_video": False,
            "video_to_video": False,
            "supports_streaming": None,
            "supports_realtime": None,
            "source_url": override["source"],
            "status": "documented",
            "endpoints": {"understanding": True},
            "input_mime_types": list(_VERTEX_GEMINI_4_VIDEO_MIME_TYPES),
            "extra": {},
        }
    extra = row.setdefault("extra", {})
    extra["vertex_modality_source"] = override["source"]
    if row.get("model_id", "").startswith("gemini-4-"):
        # Vertex model cards document a 65,536-token foreground segment and
        # long decodes up to the unified 1,048,576-token limit.
        extra["long_decode_max_output_tokens"] = 1_048_576
        extra["long_decode_requires_opt_in"] = True


def apply_vertex_gemini_model_page_spec(row: dict) -> None:
    """Apply token and modality facts from a model's official Vertex page."""
    spec = VERTEX_GEMINI_MODEL_PAGE_SPECS.get(row.get("model_id", "").lower())
    if not spec:
        return

    inputs = list(spec["input_modalities"])
    outputs = list(spec["output_modalities"])
    audio_input = "audio" in inputs
    audio_output = "audio" in outputs
    video_input = "video" in inputs
    video_output = "video" in outputs
    row["display_name"] = spec["display_name"]
    row["context_window"] = spec["context_window"]
    row["max_output_tokens"] = spec["max_output_tokens"]
    row["input_modalities"] = inputs
    row["output_modalities"] = outputs
    row["supports_vision"] = "image" in inputs
    row["supports_audio_input"] = audio_input
    row["supports_audio_output"] = audio_output
    row.pop("supports_realtime", None)
    row["supports_google_api"] = True
    row["supports_fim"] = False
    for field in (
        "supports_chat_completion",
        "supports_function_calling",
        "supports_json_mode",
        "supports_reasoning",
        "supports_streaming",
    ):
        if field in spec:
            row[field] = spec[field]

    if audio_input or audio_output:
        endpoints = {}
        if audio_input:
            endpoints["speech_understanding"] = True
        if audio_output:
            endpoints["speech_generation"] = True
        if spec.get("supports_streaming"):
            endpoints["streaming"] = True
        row["audio"] = {
            "accepts_audio_input": audio_input,
            "speech_generation": audio_output,
            "speech_understanding": audio_input,
            "supports_streaming": spec.get("supports_streaming"),
            "supports_realtime": bool(spec.get("supports_realtime", False)),
            "source_url": spec["source"],
            "status": "documented",
            "endpoints": endpoints,
            "extra": {},
        }
    else:
        row.pop("audio", None)

    if video_input or video_output:
        endpoints = {}
        if video_input:
            endpoints["understanding"] = True
        if video_output:
            endpoints["generation"] = True
        if spec.get("supports_streaming"):
            endpoints["streaming"] = True
        row["video"] = {
            "accepts_video_input": video_input,
            "generation": video_output,
            "understanding": video_input,
            "text_to_video": False,
            "image_to_video": False,
            "video_to_video": False,
            "supports_streaming": spec.get("supports_streaming"),
            "supports_realtime": bool(spec.get("supports_realtime", False)),
            "source_url": spec["source"],
            "status": "documented",
            "endpoints": endpoints,
            "input_mime_types": (
                list(_VERTEX_GEMINI_4_VIDEO_MIME_TYPES) if video_input else []
            ),
            "extra": {},
        }
    else:
        row.pop("video", None)

    if spec.get("supports_reasoning") is False:
        row["supports_thinking_level"] = False
        row["thinking_level_values"] = None
        row["supports_thinking_budget"] = False
        row["thinking_budget_values"] = None
        row["thinking_control"] = None

    extra = row.setdefault("extra", {})
    extra["source"] = spec["source"]
    extra["vertex_model_page_source"] = spec["source"]


def enrich_modalities(row: dict) -> None:
    """Add conservative modality hints for SDK records lacking metadata.

    The Model Garden SDK lists deployable IDs but does not expose a modality
    schema for every entry. Existing explicit metadata wins; only obvious
    model-family markers are used for the remainder.
    """
    if row.get("extra", {}).get("spec_status") != "sdk_listed_only":
        return
    name = row["model_id"].lower()
    inputs = {"text"}
    outputs = {"text"}
    if any(k in name for k in ("vision", "image", "paligemma", "pix2struct", "clip")):
        inputs.add("image")
    if any(k in name for k in ("audio", "speech", "whisper", "transcribe")):
        inputs.add("audio")
    if "video" in name:
        inputs.add("video")
    if any(k in name for k in ("embedding", "embed")):
        outputs = {"embedding"}
    if any(k in name for k in ("tts", "text-to-speech", "speech-generation")):
        outputs.add("audio")
    if any(k in name for k in ("image-generation", "text-to-image", "diffusion")):
        outputs.add("image")
    row["input_modalities"] = sorted(inputs)
    row["output_modalities"] = sorted(outputs)
    if row.get("supports_vision") is None and "image" in inputs:
        row["supports_vision"] = True
    row["extra"]["modality_source"] = "conservative_model_id_heuristic"


def main() -> None:
    discovered = discover_models()
    if not discovered:
        raise RuntimeError(
            "Vertex AI SDK returned no models; refusing to overwrite catalog"
        )
    old = json.loads(OUT.read_text(encoding="utf-8"))["models"] if OUT.exists() else []
    old_by_id = {m["model_id"]: m for m in old}
    google_by_id = {
        m["model_id"]: m
        for m in json.loads(GOOGLE.read_text(encoding="utf-8"))["models"]
    }
    # Vertex's official Computer Use guide documents these Gemini model
    # families even when the SDK discovery list has not caught up yet.
    discovered_ids = {model_id for model_id, _ in discovered}
    for model_id in sorted(VERTEX_COMPUTER_USE_MODELS & google_by_id.keys()):
        if model_id not in discovered_ids:
            discovered.append(
                (model_id, google_by_id[model_id].get("display_name", model_id))
            )
            discovered_ids.add(model_id)
    rows = []
    for model_id, label in discovered:
        row = deepcopy(
            old_by_id.get(model_id)
            or google_by_id.get(model_id)
            or minimal(model_id, label)
        )
        row["provider"] = "vertex-ai"
        row.setdefault("extra", {})["source"] = SOURCE
        row["extra"]["platform"] = "Google Cloud Vertex AI / Model Garden"
        enrich_modalities(row)
        enrich_thinking(row)
        enrich_vertex_gemini_modalities(row)
        apply_vertex_gemini_model_page_spec(row)
        computer_use = google_computer_use_capability(model_id, "vertex-ai")
        if computer_use is not None and model_id in VERTEX_COMPUTER_USE_MODELS:
            computer_use["source_url"] = COMPUTER_USE_SOURCE
            row["computer_use"] = computer_use
        elif (row.get("computer_use") or {}).get("provider") in {
            "google",
            "vertex-ai",
        }:
            row.pop("computer_use", None)
        rows.append(row)
    OUT.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"vertex-ai.json: {len(rows)} models discovered via Vertex AI SDK")


if __name__ == "__main__":
    main()
