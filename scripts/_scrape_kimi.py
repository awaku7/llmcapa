"""Playwright: scrape Kimi/Moonshot AI official pricing."""
import json
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_model_names(text: str) -> list[str]:
    """Extract model entries from the live Model List section."""
    section = text.split("Model List", 1)[-1]
    section = section.split("Model Capabilities", 1)[0]
    pattern = r"Kimi\s+K[0-9]+(?:\.[0-9]+)?(?:\s+Code)?(?:\s+Model)?"
    return list(dict.fromkeys(match.strip() for match in re.findall(pattern, section)))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://platform.kimi.ai/docs/models", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        browser.close()
        model_names = parse_model_names(text)
        result = {
            "kimi_scraped": bool(model_names),
            "text_len": len(text),
            "model_names": model_names,
            "text": text[:20000],
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
