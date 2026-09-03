"""Playwright: scrape Novita AI pricing from official docs."""
import json
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_model_names(text: str) -> list[str]:
    """Extract model names from rows containing a context-size column."""
    names = []
    for raw_line in text.splitlines():
        cells = [cell.strip() for cell in raw_line.split("	")]
        if len(cells) < 2:
            continue
        name, context = cells[0], cells[1]
        if not name or not re.search(r"[A-Za-z]", name):
            continue
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\s*[KM]", context, re.I):
            continue
        if name not in names:
            names.append(name)
    return names
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://novita.ai/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        browser.close()
        
        model_names = parse_model_names(text)
        result = {
            "novita_scraped": bool(model_names),
            "page_len": len(text),
            "model_names": model_names,
            "text": text[:15000],
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
