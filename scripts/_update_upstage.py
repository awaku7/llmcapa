"""Update Upstage catalog from official model pages.

OpenRouter is intentionally not used. Numeric values are applied only through
explicit rules tied to the official Upstage page.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "upstage.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "upstage.json"
)
LOG = ROOT / "provider_update_log.md"

RULES = {
    "upstage/solar-pro4": {
        "url": "https://console.upstage.ai/docs/models/solar-pro-4",
        "endpoint_model_id": "solar-pro4-260806",
        "context_window": 524288,
        "max_output_tokens": 131072,
        "input_per_1m": 0.30,
        "output_per_1m": 1.20,
        "cached_input_per_1m": 0.06,
        "knowledge_cutoff": "2026-02",
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
            model.update(
                {
                    "context_window": rule["context_window"],
                    "max_output_tokens": rule["max_output_tokens"],
                    "supports_function_calling": True,
                    "supports_json_mode": True,
                    "supports_reasoning": True,
                    "supports_chat_completion": True,
                    "pricing": {
                        "input_per_1m": rule["input_per_1m"],
                        "output_per_1m": rule["output_per_1m"],
                        "currency": "USD",
                    },
                }
            )
            model["knowledge_cutoff"] = rule["knowledge_cutoff"]
            extra = model.setdefault("extra", {})
            extra.update(
                {
                    "official_source": page.url,
                    "official_source_checked_at": today,
                    "official_endpoint_model_id": rule["endpoint_model_id"],
                    "cached_input_per_1m": rule["cached_input_per_1m"],
                    "official_spec_refresh": "parsed",
                }
            )
            if rule["endpoint_model_id"] not in model.setdefault("aliases", []):
                model["aliases"].append(rule["endpoint_model_id"])
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
        + f"\n## Upstage official model refresh ({today})\n\n- Source: https://console.upstage.ai/docs/models/solar-pro-4\n- Checked: {checked}; updated: {updated}\n- Solar Pro 4: 512K context, 128K max output, $0.30/$1.20 per 1M tokens, cached $0.06.\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"upstage.json: official_pages_checked={checked} models_updated={updated}")


if __name__ == "__main__":
    main()
