"""Playwright: scrape NVIDIA AI models pricing."""
import json
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_model_cards(text: str) -> list[str]:
    """Extract titles that follow the page's generic ``Model`` markers."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    names = []
    for index, line in enumerate(lines[:-1]):
        if line == "Model":
            candidate = lines[index + 1]
            if candidate and not re.fullmatch(r"(?:Link|Docs|Explore|Model)", candidate):
                if candidate not in names:
                    names.append(candidate)
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
        page.goto("https://developer.nvidia.com/ai-models", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        browser.close()
        
        model_names = parse_model_cards(text)
        result = {
            "nvidia_scraped": bool(model_names),
            "text_len": len(text),
            "model_names": model_names,
            "text": text[:20000],
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
