"""Playwright: scrape Google Gemini API models and pricing."""
import sys, json, traceback
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://ai.google.dev/gemini-api/docs/models", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        models_text = page.inner_text("body")
        page.goto("https://ai.google.dev/gemini-api/docs/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        pricing_text = page.inner_text("body")
        browser.close()
        result = {"models_len": len(models_text), "pricing_len": len(pricing_text)}
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
