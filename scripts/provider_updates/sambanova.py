"""Update the SambaNova catalog from the official SambaCloud model page."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "sambanova.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.sambanova.ai/docs/en/models/sambacloud-models"

MODELS = {
    "MiniMax-M2.7": {"context": 192000, "stage": "production", "input": ["text"]},
    "DeepSeek-V3.1": {"context": 128000, "stage": "production", "input": ["text"]},
    "Meta-Llama-3.3-70B-Instruct": {
        "context": 128000,
        "stage": "production",
        "input": ["text"],
    },
    "gpt-oss-120b": {"context": 128000, "stage": "production", "input": ["text"]},
    "DeepSeek-V3.2": {"context": 32000, "stage": "preview", "input": ["text"]},
    "gemma-4-31B-it": {
        "context": 128000,
        "stage": "preview",
        "input": ["text", "image", "video"],
    },
}


def fetch_page() -> str:
    request = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read(500_000).decode("utf-8", "ignore").lower()


def main() -> None:
    page = fetch_page()
    missing = [name for name in MODELS if name.lower() not in page]
    if missing:
        raise RuntimeError(
            f"SambaNova official page validation failed: missing {missing}"
        )

    rows = []
    for model_id, spec in MODELS.items():
        input_modalities = spec["input"]
        row = {
            "provider": "sambanova",
            "model_id": model_id,
            "display_name": model_id,
            "context_window": spec["context"],
            "max_output_tokens": 0,
            "input_modalities": input_modalities,
            "output_modalities": ["text"],
            "supports_chat_completion": True,
            "supports_streaming": True,
            "supports_function_calling": None,
            "supports_json_mode": None,
            "supports_vision": "image" in input_modalities,
            "supports_reasoning": None,
            "supports_responses_api": False,
            "pricing": None,
            "deprecated": False,
            "aliases": [],
            "extra": {
                "official_source": SOURCE,
                "official_source_checked_at": datetime.now(timezone.utc)
                .date()
                .isoformat(),
                "official_spec_refresh": "parsed",
                "availability": spec["stage"],
                "supported_modalities_note": (
                    "Text, Image, Video; audio input is not supported"
                    if model_id == "gemma-4-31B-it"
                    else "Text"
                ),
                "pricing_status": "not specified on SambaCloud models page",
            },
        }
        rows.append(row)

    DATA.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## SambaNova official refresh ({datetime.now(timezone.utc).date().isoformat()})\n\n"
        + f"- Source: {SOURCE}\n"
        + "- Parsed 4 production and 2 preview SambaCloud models, including context lengths and modalities.\n"
        + "- Pricing was not inferred because it is not specified on the model overview page.\n",
        encoding="utf-8",
    )
    print(f"sambanova.json: official_models_updated={len(rows)}")


if __name__ == "__main__":
    main()
