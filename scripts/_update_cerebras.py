"""Refresh Cerebras public models from the official rendered model catalog.

Uses Playwright because the Cerebras docs page is rendered by JavaScript. No
API key and no OpenRouter data are required.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "llmcapa" / "data" / "cerebras.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://inference-docs.cerebras.ai/models/overview"


def parse_context(value: str) -> int:
    values = re.findall(r"(\d+(?:\.\d+)?)\s*([kKmM])", value)
    if not values:
        return 0
    number, suffix = values[-1]  # paid tier is the second value when present
    multiplier = 1_000 if suffix.lower() == "k" else 1_000_000
    return int(float(number) * multiplier)


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SOURCE, wait_until="networkidle", timeout=90_000)
        rows = page.locator("#content-area table tbody tr")
        models = []
        for i in range(rows.count()):
            cells = rows.nth(i).locator("td")
            if cells.count() < 2:
                continue
            name = cells.nth(0).inner_text().strip()
            model_id = cells.nth(1).inner_text().strip()
            context_text = (
                cells.nth(3).inner_text().strip() if cells.count() > 3 else ""
            )
            if not model_id:
                continue
            multimodal = "gemma" in model_id.lower()
            models.append(
                {
                    "provider": "cerebras",
                    "model_id": model_id,
                    "display_name": name,
                    "context_window": parse_context(context_text),
                    "max_output_tokens": 0,
                    "input_modalities": ["text", "image"] if multimodal else ["text"],
                    "output_modalities": ["text"],
                    "supports_chat_completion": True,
                    "supports_streaming": True,
                    "supports_function_calling": None,
                    "supports_json_mode": None,
                    "supports_vision": bool(multimodal),
                    "supports_reasoning": (
                        True if "gpt-oss" in model_id.lower() else None
                    ),
                    "supports_responses_api": False,
                    "pricing": None,
                    "deprecated": False,
                    "aliases": [],
                    "extra": {
                        "source": SOURCE,
                        "source_type": "official_rendered_page",
                    },
                }
            )
        browser.close()
    if not models:
        raise RuntimeError("no models found in rendered Cerebras catalog table")
    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Cerebras refresh ({datetime.now(timezone.utc).date()})\n\n- Source: {SOURCE}\n- Discovery: Playwright-rendered official catalog table\n- Result: {len(models)} public models\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"cerebras.json: {len(models)} models scraped via Playwright")


if __name__ == "__main__":
    main()
