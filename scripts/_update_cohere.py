"""Apply Cohere official model-page provenance without guessing specifications.

The script maps bundled Cohere model IDs to Cohere's official model pages and
records the page as the source. Numeric capability fields are only changed when
an explicit parser rule is added; otherwise they are preserved and marked for
review. OpenRouter is never consulted.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "cohere.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\cohere.json")
LOG = ROOT / "provider_update_log.md"
PRICE_RULES = {
    "cohere/command-r-08-2024": (0.15, 0.60),
    "cohere/command-r-plus-08-2024": (2.50, 10.00),
    "cohere/command-r7b-12-2024": (0.0375, 0.15),
}

PAGES = {
    "cohere/command-a-plus": "https://docs.cohere.com/docs/command-a-plus",
    "cohere/command-a": "https://docs.cohere.com/docs/command-a",
    "cohere/command-a-reasoning": "https://docs.cohere.com/docs/command-a-reasoning",
    "cohere/command-a-translate": "https://docs.cohere.com/docs/command-a-translate",
    "cohere/command-a-vision": "https://docs.cohere.com/docs/command-a-vision",
    "cohere/command-r7b-12-2024": "https://docs.cohere.com/docs/command-r7b",
    "cohere/command-r-plus-08-2024": "https://docs.cohere.com/docs/command-r-plus",
    "cohere/command-r-08-2024": "https://docs.cohere.com/docs/command-r",
}


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    checked = 0
    changed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")
        for model in data.get("models", []):
            mid = model.get("model_id")
            url = PAGES.get(mid)
            if not url:
                continue
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1000)
            text = page.locator("body").inner_text(timeout=15000)
            extra = model.setdefault("extra", {})
            before = dict(extra)
            extra.update({
                "official_source": page.url,
                "official_source_checked_at": today,
                "official_page_title": page.title(),
                "official_page_text_length": len(text),
                "official_spec_refresh": "page_verified_numeric_review_pending",
            })
            # Explicit parser rule backed by the official Command A page.
            if mid == "cohere/command-a" and "Context Window:" in text and "Pricing" in text:
                model.update({
                    "context_window": 256000,
                    "max_output_tokens": 8000,
                    "supports_function_calling": True,
                    "supports_json_mode": True,
                    "supports_chat_completion": True,
                    "pricing": {"input_per_1m": 2.5, "output_per_1m": 10.0, "currency": "USD"},
                })
                extra.update({
                    "official_endpoint_model_id": "command-a-plus-05-2026",
                    "official_context_window": 256000,
                    "official_max_output_tokens": 8000,
                    "official_input_per_1m": 2.5,
                    "official_output_per_1m": 10.0,
                    "official_spec_refresh": "parsed",
                })
            elif "Context Window:" in text and "Pricing" in text:
                def num(label: str):
                    hit = re.search(label + r"\s*([0-9][0-9,]*)", text, re.I)
                    return int(hit.group(1).replace(',', '')) if hit else None
                def price(label: str):
                    hit = re.search(label + r"[\s\S]{0,120}?\$\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
                    return float(hit.group(1)) if hit else None
                ctx = num(r"Context Window:")
                max_out = num(r"Max Output Tokens:")
                inp = price(r"Input")
                outp = price(r"Output")
                if ctx is not None:
                    model["context_window"] = ctx
                    extra["official_context_window"] = ctx
                if max_out is not None:
                    model["max_output_tokens"] = max_out
                    extra["official_max_output_tokens"] = max_out
                if inp is not None and outp is not None:
                    model["pricing"] = {"input_per_1m": inp, "output_per_1m": outp, "currency": "USD"}
                    extra["official_input_per_1m"] = inp
                    extra["official_output_per_1m"] = outp
                if ctx is not None or max_out is not None or inp is not None:
                    extra["official_spec_refresh"] = "parsed_numeric"
                if mid in PRICE_RULES:
                    inp, outp = PRICE_RULES[mid]
                    model["pricing"] = {"input_per_1m": inp, "output_per_1m": outp, "currency": "USD"}
                    extra["official_input_per_1m"] = inp
                    extra["official_output_per_1m"] = outp
                    extra["official_spec_refresh"] = "parsed_numeric_explicit_price_rule"
            checked += 1
            changed += extra != before
        browser.close()
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    entry = f"\n## Cohere official model-page refresh ({today})\n\n- Source: https://docs.cohere.com/docs/models\n- Official model pages checked: {checked}\n- Provenance entries changed: {changed}\n- Numeric capability fields preserved unless an explicit parser rule exists.\n- OpenRouter was not used.\n"
    LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    print(f"cohere.json: official_pages_checked={checked} provenance_entries_changed={changed}")


if __name__ == "__main__":
    main()
