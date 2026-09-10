"""Update Upstage catalog from official model pages.

OpenRouter is intentionally not used. Numeric values are applied only through
explicit rules tied to the official Upstage page.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "upstage.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "upstage.json"
)
LOG = ROOT / "provider_update_log.md"

def parse_official_model_page(text: str) -> dict:
    """Extract current Solar model metadata from the rendered official page."""
    normalized = " ".join(text.split())

    def money(label: str) -> float:
        match = re.search(
            rf"{re.escape(label)}\s+Price\s+\$([0-9]+(?:\.[0-9]+)?)",
            normalized,
            re.I,
        )
        if not match:
            raise RuntimeError(f"Upstage page missing {label} price")
        return float(match.group(1))

    context = re.search(r"(\d+)K context length", normalized, re.I)
    max_output = re.search(r"Max output tokens\s+(\d+)K", normalized, re.I)
    version = re.search(r"Versions\s+(solar-[a-z0-9-]+)", normalized, re.I)
    cutoff = re.search(r"([A-Z][a-z]{2},\s*\d{4}) training data cut-off", normalized)
    if not context or not max_output or not version:
        raise RuntimeError("Upstage official model page is missing required metadata")
    page_prices = [
        float(value)
        for value in re.findall(r"\$([0-9]+(?:\.[0-9]+)?)", normalized)
    ]
    if len(page_prices) < 3:
        raise RuntimeError("Upstage official model page is missing pricing values")
    return {
        "context_window": int(context.group(1)) * 1_000,
        "max_output_tokens": int(max_output.group(1)) * 1_000,
        "input_per_1m": money("Input Token"),
        "output_per_1m": money("Output Token"),
        "cached_input_per_1m": page_prices[2],
        "endpoint_model_id": version.group(1),
        "knowledge_cutoff": cutoff.group(1) if cutoff else None,
    }


RULES = {
    "solar-pro4": {
        "url": "https://console.upstage.ai/docs/models/solar-pro-4",
    }
}


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    checked = 0
    updated = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")
        for model in data.get("models", []):
            rule = RULES.get(model.get("model_id"))
            if not rule:
                continue
            page.goto(rule["url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1000)
            text = page.locator("body").inner_text(timeout=15000)
            required = ["512K context length", "Max output tokens", "Tool calling"]
            if not all(item in text for item in required):
                raise RuntimeError(
                    f"official page validation failed for {model['model_id']}"
                )
            live = parse_official_model_page(text)
            model.update(
                {
                    "context_window": live["context_window"],
                    "max_output_tokens": live["max_output_tokens"],
                    "supports_function_calling": True,
                    "supports_json_mode": True,
                    "supports_reasoning": True,
                    "supports_chat_completion": True,
                    "pricing": {
                        "input_per_1m": live["input_per_1m"],
                        "output_per_1m": live["output_per_1m"],
                        "currency": "USD",
                    },
                }
            )
            model["knowledge_cutoff"] = live["knowledge_cutoff"]
            extra = model.setdefault("extra", {})
            extra.update(
                {
                    "official_source": page.url,
                    "official_source_checked_at": today,
                    "official_endpoint_model_id": live["endpoint_model_id"],
                    "cached_input_per_1m": live["cached_input_per_1m"],
                    "official_spec_refresh": "parsed",
                }
            )
            if live["endpoint_model_id"] not in model.setdefault("aliases", []):
                model["aliases"].append(live["endpoint_model_id"])
            checked += 1
            updated += 1
        browser.close()
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Upstage official model refresh ({today})\n\n- Source: https://console.upstage.ai/docs/models/solar-pro-4\n- Checked: {checked}; updated: {updated}\n- Context, output limit, prices, cached price, endpoint version, and cutoff were parsed from the official page.\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"upstage.json: official_pages_checked={checked} models_updated={updated}")


if __name__ == "__main__":
    main()
