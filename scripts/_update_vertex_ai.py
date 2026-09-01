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


def discover_models() -> list[tuple[str, str]]:
    """Return SDK-discoverable Model Garden models as (id, display_name)."""
    try:
        from vertexai import model_garden
    except ImportError as exc:
        raise RuntimeError(
            'Install the maintenance dependency first: '
            'pip install "google-cloud-aiplatform>=1.84"'
        ) from exc

    models = model_garden.list_deployable_models(list_hf_models=True)
    result: dict[str, str] = {}
    for item in models or []:
        if isinstance(item, str):
            model_id, label = item, item
        elif isinstance(item, dict):
            model_id = item.get("model_id") or item.get("modelId") or item.get("name") or item.get("id")
            label = item.get("display_name") or item.get("displayName") or item.get("name") or model_id
        else:
            model_id = next((getattr(item, key, None) for key in ("model_id", "modelId", "name", "id") if getattr(item, key, None)), None)
            label = next((getattr(item, key, None) for key in ("display_name", "displayName", "name") if getattr(item, key, None)), model_id)
        if model_id:
            result[str(model_id)] = str(label or model_id)
    if len(result) < 20:
        raise RuntimeError(f"Vertex AI SDK returned too few deployable models: {len(result)}")
    return sorted(result.items())


def minimal(model_id: str, label: str) -> dict:
    return {
        "provider": "vertex-ai", "model_id": model_id,
        "display_name": label, "context_window": 0, "max_output_tokens": 0,
        "input_modalities": ["text"], "output_modalities": ["text"],
        "supports_chat_completion": True, "supports_streaming": True,
        "supports_function_calling": None, "supports_json_mode": None,
        "supports_vision": None, "supports_reasoning": None,
        "supports_responses_api": False, "pricing": None,
        "deprecated": False, "aliases": [],
        "extra": {"source": SOURCE, "platform": "Google Cloud Vertex AI / Model Garden", "spec_status": "sdk_listed_only"},
    }


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
    google_by_id = {m["model_id"]: m for m in json.loads(GOOGLE.read_text(encoding="utf-8"))["models"]}
    rows = []
    for model_id, label in discovered:
        row = deepcopy(old_by_id.get(model_id) or google_by_id.get(model_id) or minimal(model_id, label))
        row["provider"] = "vertex-ai"
        row.setdefault("extra", {})["source"] = SOURCE
        row["extra"]["platform"] = "Google Cloud Vertex AI / Model Garden"
        enrich_modalities(row)
        rows.append(row)
    OUT.write_text(json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
