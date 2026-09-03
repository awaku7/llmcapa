"""Playwright: scrape Alibaba Cloud Qwen pricing."""
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

def parse_model_ids(text: str) -> list[str]:
    """Extract Qwen model identifiers from the live pricing text."""
    pattern = r"(?i)\bqwen(?:[0-9][a-z0-9]*(?:[-._][a-z0-9]+)*|[-_][a-z0-9]+(?:[-._][a-z0-9]+)*)\b"
    return list(dict.fromkeys(match.lower() for match in re.findall(pattern, text)))


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Try the English page first, then the Chinese page if necessary.
        t1 = ""
        for url in (
            "https://www.alibabacloud.com/help/en/model-studio/getting-started/billing",
            "https://help.aliyun.com/zh/model-studio/getting-started/billing",
        ):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                candidate = page.inner_text("body")
            except Exception:
                continue
            if len(candidate) > len(t1):
                t1 = candidate
            if "pricing" in candidate.lower()[:1000] or "price" in candidate.lower()[:1000]:
                break
        if not t1:
            raise RuntimeError("Qwen billing pages could not be loaded")
        
        browser.close()
        
        # Extract pricing table from text
        idx = t1.lower().find("pricing")
        if idx == -1:
            idx = t1.lower().find("price")
        if idx == -1:
            idx = t1.lower().find("billing")
        
        text = t1[max(0, idx-200):idx+15000] if idx >= 0 else t1[:15000]
        
        model_ids = parse_model_ids(t1)
        result = {
            "qwen_scraped": bool(model_ids),
            "text_len": len(t1),
            "model_ids": model_ids,
            "pricing_section": text[:20000],
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
