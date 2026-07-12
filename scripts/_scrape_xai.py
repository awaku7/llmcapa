"""Playwright: scrape xAI Grok pricing (with stealth)."""
import sys, json, traceback
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()
        
        # Try xAI API docs
        page.goto("https://docs.x.ai/docs/models", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        t = page.inner_text("body")
        
        if "blocked" in t.lower()[:500] or len(t) < 500:
            # Try console.x.ai pricing
            page.goto("https://console.x.ai/", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            t = page.inner_text("body")
        
        browser.close()
        result = {"xai_scraped": True, "text_len": len(t), "text": t[:15000]}
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
