"""Scrape the ThaiLLM official site for its published foundation models.

Uses Playwright because the landing page is client-rendered. No API key and no
OpenRouter data are required.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "llmcapa" / "data" / "thaillm.json"
SOURCE = "https://thaillm.or.th/"


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SOURCE, wait_until="networkidle", timeout=90_000)
        text = page.locator("body").inner_text()
        browser.close()

    names = []
    for line in text.splitlines():
        line = re.sub(r"\s*\(Research Preview\)$", "", line.strip())
        if (
            line.startswith(("OpenThaiGPT-", "Typhoon-S-", "Pathumma-", "THaLLE-"))
            and "ThaiLLM" in line
            and len(line) < 140
            and line not in names
        ):
            names.append(line)
    if not names:
        raise RuntimeError("no ThaiLLM foundation models found on official page")

    rows = []
    for name in names:
        rows.append(
            {
                "provider": "thaillm",
                "model_id": name,
                "display_name": name,
                "context_window": 0,
                "max_output_tokens": 0,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supports_chat_completion": True,
                "supports_streaming": True,
                "supports_function_calling": None,
                "supports_json_mode": None,
                "supports_vision": False,
                "supports_reasoning": None,
                "supports_responses_api": False,
                "pricing": None,
                "deprecated": False,
                "aliases": [],
                "extra": {
                    "source": SOURCE,
                    "source_type": "official_rendered_page",
                    "spec_status": "listed_only",
                },
            }
        )
    OUT.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"thaillm.json: {len(rows)} models scraped via Playwright")


if __name__ == "__main__":
    main()
