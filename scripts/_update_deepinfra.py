"""Refresh DeepInfra's public LLM catalog from the official models API.

Source: https://api.deepinfra.com/models/list
The endpoint is public and does not require an API key. The bundled catalog
includes public text-generation and embedding models; other model types are
outside this LLM catalog updater's scope.
"""

from __future__ import annotations

import json
import math
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "deepinfra.json"
SOURCE = "https://api.deepinfra.com/models/list"
SUPPORTED_TYPES = {"text-generation", "text-embedding", "embedding", "embeddings"}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_catalog() -> Any:
    request = urllib.request.Request(
        SOURCE,
        headers={"User-Agent": "llmcapa provider catalog updater"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("DeepInfra model catalog must be a JSON list")
    return payload


def _is_deprecated(value: Any) -> bool:
    # DeepInfra publishes deprecation timestamps as Unix seconds.
    timestamp = _number(value)
    return timestamp is not None and timestamp <= time.time()


def model_to_entry(model: dict[str, Any]) -> dict[str, Any] | None:
    model_type = str(model.get("type", "")).lower()
    if model_type not in SUPPORTED_TYPES:
        return None
    model_id = str(model.get("model_name", "")).strip()
    if not model_id or model.get("private", 0):
        return None
    if _is_deprecated(model.get("deprecated")):
        return None

    tags = {str(tag).strip().lower().replace("_", "-") for tag in (model.get("tags") or [])}
    is_embedding = model_type in {"text-embedding", "embedding", "embeddings"}
    input_modalities = ["text"]
    if not is_embedding and ({"vision", "multimodal", "image-input"} & tags):
        input_modalities.append("image")
    if not is_embedding and "input-audio" in tags:
        input_modalities.append("audio")
    if not is_embedding and "input-video" in tags:
        input_modalities.append("video")
    output_modalities = ["embedding"] if is_embedding else ["text"]

    pricing_source = model.get("pricing") or {}
    pricing = None
    if str(pricing_source.get("type", "")).lower() in {"tokens", "token"}:
        input_cents = _number(pricing_source.get("cents_per_input_token"))
        output_cents = _number(pricing_source.get("cents_per_output_token"))
        if input_cents is not None:
            pricing = {
                "input_per_1m": round(input_cents * 10_000, 8),
                "currency": "USD",
            }
            if output_cents is not None:
                pricing["output_per_1m"] = round(output_cents * 10_000, 8)

    max_tokens = model.get("max_tokens")
    context_window = max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else 0
    reasoning = True if "reasoning" in tags else False if "non-reasoning" in tags else None
    function_calling = True if "tools" in tags or "tool-calling" in tags else None
    json_mode = True if {"json", "structured-output"} & tags else None

    return {
        "provider": "deepinfra",
        "model_id": model_id,
        "display_name": model_id,
        "context_window": context_window,
        # DeepInfra's public model list exposes the maximum context size, not a
        # distinct generation limit.
        "max_output_tokens": 0,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_chat_completion": not is_embedding,
        "supports_streaming": True if not is_embedding else None,
        "supports_function_calling": function_calling,
        "supports_json_mode": json_mode,
        "supports_vision": "image" in input_modalities,
        "supports_reasoning": reasoning,
        "supports_responses_api": True if {"responses", "responses-api", "responses_api"} & tags else None,
        "pricing": pricing,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
        "extra": {
            "source": SOURCE,
            "model_type": model_type,
            "reported_type": model.get("reported_type"),
            "description": model.get("description", ""),
            "tags": sorted(tags),
            "quantization": model.get("quantization"),
            "replaced_by": model.get("replaced_by"),
            "is_partner": bool(model.get("is_partner", False)),
        },
    }


def catalog_to_models(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for model in payload:
        if not isinstance(model, dict):
            continue
        entry = model_to_entry(model)
        if entry is not None:
            by_id[entry["model_id"].casefold()] = entry
    return [by_id[key] for key in sorted(by_id)]


def main() -> None:
    models = catalog_to_models(fetch_catalog())
    if not models:
        raise RuntimeError("DeepInfra API returned no supported public LLM models")
    DATA.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"deepinfra.json: {len(models)} public LLM models refreshed")


if __name__ == "__main__":
    main()
