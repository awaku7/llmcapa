"""Update the SambaNova catalog from the official SambaCloud model page."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

try:
    from scripts.provider_updates._http import fetch_text
except ModuleNotFoundError:  # Running this updater directly from its own directory.
    from _http import fetch_text

ROOT = Path(__file__).resolve().parents[2]
try:
    from scripts._metadata_loader import apply_context_window_overrides
except ModuleNotFoundError:  # Direct execution from scripts/provider_updates
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from _metadata_loader import apply_context_window_overrides


DATA = ROOT / "src" / "llmcapa" / "data" / "sambanova.json"
SOURCE = "https://docs.sambanova.ai/docs/en/models/sambacloud-models"

MODELS = {
    "MiniMax-M3": {
        "stage": "preview",
        "input": ["text"],
        "context_window": 1_000_000,
    },
    "DeepSeek-V3.1": {
        "stage": "production",
        "input": ["text"],
        "context_window": 128_000,
    },
    "Meta-Llama-3.3-70B-Instruct": {
        "stage": "production",
        "input": ["text"],
        "context_window": 128_000,
    },
    "gpt-oss-120b": {
        "stage": "production",
        "input": ["text"],
        "context_window": 128_000,
    },
    "DeepSeek-V3.2": {
        "stage": "preview",
        "input": ["text"],
        "context_window": 32_000,
    },
    "gemma-4-31B-it": {
        "stage": "preview",
        "input": ["text", "image", "video"],
        "context_window": 128_000,
    },
}


def fetch_page() -> str:
    for retry_index in range(4):
        try:
            return fetch_text(
                SOURCE,
                headers={"User-Agent": "llmcapa-official-updater/1.0"},
                timeout=30,
                max_bytes=500_000,
                errors="ignore",
            ).lower()
        except HTTPError as exc:
            if exc.code not in {403, 429, 500, 502, 503, 504} or retry_index == 3:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = max(2.0**retry_index, float(retry_after or 0))
            except ValueError:
                delay = 2.0**retry_index
            print(
                f"Temporary SambaNova docs HTTP {exc.code}; "
                f"retry {retry_index + 1}/3 in {delay:g}s",
                flush=True,
            )
            exc.close()
            time.sleep(delay)
    raise RuntimeError("SambaNova model page retries exhausted")


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
            "context_window": spec["context_window"],
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

    apply_context_window_overrides(rows)
    DATA.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"sambanova.json: official_models_updated={len(rows)}")


if __name__ == "__main__":
    main()
