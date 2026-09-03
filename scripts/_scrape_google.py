"""Playwright: scrape Google Gemini API models and pricing."""
import json
import re
import sys
import traceback
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

def parse_model_ids(text: str) -> list[str]:
    """Return model IDs discovered in the live Models page."""
    pattern = r"\b(?:gemini|gemma)-[a-z0-9]+(?:[-.][a-z0-9]+)*\b"
    return list(dict.fromkeys(match.lower() for match in re.findall(pattern, text, re.I)))


def parse_pricing_model_ids(text: str) -> list[str]:
    """Return model IDs exposed by the live Pricing page."""
    return parse_model_ids(text)


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://ai.google.dev/gemini-api/docs/models", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        models_text = page.inner_text("body")
        model_ids = parse_model_ids(models_text)
        page.goto("https://ai.google.dev/gemini-api/docs/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        pricing_text = page.inner_text("body")
        pricing_model_ids = parse_pricing_model_ids(pricing_text)
        browser.close()
        result = {
            "models_scraped": bool(model_ids),
            "models_len": len(models_text),
            "pricing_len": len(pricing_text),
            "model_ids": model_ids,
            "pricing_model_ids": pricing_model_ids,
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
