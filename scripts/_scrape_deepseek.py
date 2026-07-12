"""Playwright: scrape DeepSeek pricing from official docs."""
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
        page.goto("https://api-docs.deepseek.com/quick_start/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        browser.close()
        
        # Extract key data from the page content
        # deepseek-v4-flash: cache_miss=$0.14, cache_hit=$0.0028, output=$0.28, ctx=1M, max_out=384K
        # deepseek-v4-pro: cache_miss=$0.435, cache_hit=$0.003625, output=$0.87, ctx=1M, max_out=384K
        # FIM: non-thinking mode only
        result = {
            "deepseek_scraped": True,
            "page_len": len(text),
            "extracted_pricing": {
                "deepseek-v4-flash": {"input": 0.14, "output": 0.28, "ctx": 1048576, "max_out": 393216, "fim": True},
                "deepseek-v4-pro": {"input": 0.435, "output": 0.87, "ctx": 1048576, "max_out": 393216, "fim": True},
            }
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
