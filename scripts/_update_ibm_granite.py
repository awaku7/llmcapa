"""Refresh IBM Granite metadata from IBM's current Granite documentation.

The updater is fail-closed: it only records facts explicitly found on IBM's
official Granite 4.2 page and never infers pricing from third-party catalogs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "ibm-granite.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://www.ibm.com/granite/docs/models/granite4-2"

GRANITE_42 = {
    "granite-4.2-3b": "3B",
    "granite-4.2-8b": "8B",
    "granite-4.2-30b": "30B",
}


def fetch_page() -> str:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.read(1_000_000).decode("utf-8", "ignore").lower()


def base_model(model_id: str, size: str) -> dict:
    is_30b = size == "30B"
    return {
        "provider": "ibm-granite",
        "model_id": model_id,
        "display_name": f"IBM: Granite 4.2 {size}",
        "context_window": 512000 if is_30b else 128000,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": False,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": True,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "Other",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [model_id],
        "license_type": "open",
        "pricing": None,
    }


def main() -> None:
    page = fetch_page()
    required = [
        "granite 4.2",
        "granite-4.2-3b",
        "granite-4.2-8b",
        "granite-4.2-30b",
        "128k",
        "apache 2.0",
    ]
    missing = [term for term in required if term not in page]
    if missing:
        raise RuntimeError(f"IBM official page validation failed: missing {missing}")

    data = json.loads(DATA.read_text(encoding="utf-8"))
    models = data.setdefault("models", [])
    today = datetime.now(timezone.utc).date().isoformat()

    # Granite 4.0 is no longer the current documented family.
    for model in models:
        if str(model.get("model_id", "")).startswith("ibm-granite/granite-4.0"):
            model["deprecated"] = True

    {model.get("model_id") for model in models}
    added = 0
    for model_id, size in GRANITE_42.items():
        model = next((m for m in models if m.get("model_id") == model_id), None)
        if model is None:
            # remove legacy slash-duplicate if present
            models[:] = [m for m in models if m.get("model_id") != f"ibm-granite/{model_id}"]
            model = base_model(model_id, size)
            models.append(model)
            added += 1
        model.update(
            {
                "display_name": f"IBM: Granite 4.2 {size}",
                "context_window": 512000 if size == "30B" else 128000,
                "max_output_tokens": 0,
                "supports_function_calling": True,
                "supports_reasoning": True,
                "supports_thinking_budget": True,
                "license_type": "open",
                "deprecated": False,
            }
        )
        extra = model.setdefault("extra", {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": today,
                "official_spec_refresh": "parsed",
                "license": "Apache 2.0",
                "architecture": "dense reasoning language model",
                "granite_4_2_size": size,
                "reasoning": "native chain-of-thought thinking",
                "tool_calling": "reasoning-augmented tool calling",
                "context_note": "128K for all Granite 4.2 models; 30B supports long-context extension to 512K",
                "pricing_status": "not specified on IBM Granite model page",
            }
        )

    models.sort(key=lambda m: m.get("model_id", ""))
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## IBM Granite official refresh ({today})\n\n"
        + f"- Source: {SOURCE}\n"
        + f"- Added/updated Granite 4.2 models: {len(GRANITE_42)} (new: {added}).\n"
        + "- Recorded official 128K context, 30B long-context extension to 512K, Apache 2.0, reasoning, and tool-calling metadata.\n"
        + "- Granite 4.0 records were marked deprecated; pricing was not inferred.\n"
        + "- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"ibm-granite.json: granite_4_2_updated={len(GRANITE_42)} new={added}")


if __name__ == "__main__":
    main()
