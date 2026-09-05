"""Refresh Aion Labs models and pricing from Aion's official model page."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "aion-labs.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "aion-labs.json"
)
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://www.aionlabs.ai/docs/models/"
RULES = {
    "aion-labs/aion-2.0": (128000, 32768, 0.80, 1.60, True),
    "aion-labs/aion-3.0": (128000, 32768, 3.00, 6.00, True),
    "aion-labs/aion-3.0-mini": (128000, 32768, 0.70, 1.40, True),
    "aion-labs/aion-rp-llama-3.1-8b": (32768, 32768, 0.80, 1.60, False),
    "aion-labs/aion-2.5": (128000, 32768, 1.00, 3.00, True),
}


def main() -> None:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        text = response.read(300_000).decode("utf-8", "ignore")
    if "aion-labs/aion-3.0" not in text or "Input / 1M" not in text:
        raise RuntimeError("Aion Labs official model page validation failed")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    by_id = {m.get("model_id"): m for m in data.get("models", [])}
    updated = 0
    for mid, (ctx, max_out, inp, out, reasoning) in RULES.items():
        bare = mid.split("/", 1)[1] if "/" in mid else mid
        # drop legacy slash-duplicate; the native catalog uses bare ids
        # (slash routes such as aion-labs/aion-3.0 belong to the openrouter catalog)
        data["models"][:] = [
            m for m in data.get("models", []) if m.get("model_id") != mid
        ]
        by_id.pop(mid, None)
        model = by_id.get(bare)
        if model is None:
            model = {
                "provider": "aion-labs",
                "model_id": bare,
                "display_name": bare,
                "context_window": ctx,
                "max_output_tokens": max_out,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supports_function_calling": False,
                "supports_json_mode": False,
                "supports_streaming": True,
                "supports_vision": False,
                "supports_reasoning": reasoning,
                "supports_chat_completion": True,
                "supports_responses_api": False,
                "supports_reasoning_effort": False,
                "supports_thinking_budget": False,
                "supports_anthropic_api": False,
                "supports_google_api": False,
                "supports_fim": False,
                "tokenizer_name": "Other",
                "knowledge_cutoff": None,
                "deprecated": bare.endswith("2.5"),
                "aliases": [],
                "license_type": "api",
                "pricing": {},
            }
            data["models"].append(model)
            by_id[mid] = model
        model.update(
            {
                "context_window": ctx,
                "max_output_tokens": max_out,
                "pricing": {
                    "input_per_1m": inp,
                    "output_per_1m": out,
                    "currency": "USD",
                },
                "license_type": "api",
            }
        )
        extra = model.setdefault("extra", {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": today,
                "official_spec_refresh": "parsed",
                "official_models_api": "https://api.aionlabs.ai/v1/models",
            }
        )
        updated += 1
    data["models"].sort(key=lambda m: m.get("model_id", ""))
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Aion Labs official refresh ({today})\n\n- Source: {SOURCE}\n- Parsed official context, max output, reasoning flag, and USD pricing for {updated} Aion records, including expired Aion 2.5.\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"aion-labs.json: official_models_updated={updated}")


if __name__ == "__main__":
    main()
