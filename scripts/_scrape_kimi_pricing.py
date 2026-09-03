"""Playwright: scrape Kimi AI pricing page."""
import json
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

def parse_model_names(text: str) -> list[str]:
    """Extract model card names from the live Kimi pricing page."""
    names = []
    section = text.split("See detailed pricing for each model:", 1)[-1]
    section = section.split("Was this page helpful", 1)[0]
    for line in section.splitlines():
        line = " ".join(line.split())
        if re.fullmatch(r"Kimi\s+K[0-9]+(?:\.[0-9]+)?(?:\s+[A-Za-z0-9-]+)*", line):
            if line not in names:
                names.append(line)
    return names


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://platform.kimi.ai/docs/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        browser.close()
        model_names = parse_model_names(text)
        result = {
            "kimi_pricing": bool(model_names),
            "text_len": len(text),
            "model_names": model_names,
            "text": text[:15000],
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
