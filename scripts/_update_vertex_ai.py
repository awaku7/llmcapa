"""Refresh the Google Cloud Vertex AI Model Garden catalog via the official SDK.

This catalog is separate from google.json and never reads OpenRouter. Install
with: pip install "google-cloud-aiplatform>=1.84"
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOGLE = ROOT / "src" / "llmcapa" / "data" / "google.json"
OUT = ROOT / "src" / "llmcapa" / "data" / "vertex-ai.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models"
THINKING_SOURCE = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking"
)

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
    "gemini-3-flash-preview": {
        "parameter": "thinking_level",
        "thinking_level_values": ["minimal", "low", "medium", "high"],
    },
}


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
    old = json.loads(OUT.read_text(encoding="utf-8"))["models"] if OUT.exists() else []
    old_by_id = {m["model_id"]: m for m in old}
    google_by_id = {
        m["model_id"]: m
        for m in json.loads(GOOGLE.read_text(encoding="utf-8"))["models"]
    }
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
        rows.append(row)
    OUT.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    entry = f"""
## Vertex AI / Model Garden SDK refresh ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})

- Source: {SOURCE}
- Discovery: `vertexai.model_garden.list_deployable_models(list_hf_models=True)`
- OpenRouter was not used; `google.json` was not modified.
- Result: {len(rows)} SDK-listed deployable Model Garden models. Detailed limits/pricing remain unknown where the SDK does not expose them.
"""
    LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    print(f"vertex-ai.json: {len(rows)} models discovered via Vertex AI SDK")


if __name__ == "__main__":
    main()
