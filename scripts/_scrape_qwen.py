"""Playwright: scrape Alibaba Cloud Qwen pricing."""
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
        
        # Try billing page
        page.goto("https://www.alibabacloud.com/help/en/model-studio/getting-started/billing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        t1 = page.inner_text("body")
        
        if "pricing" not in t1.lower()[:1000] and "price" not in t1.lower()[:1000]:
            # Try Chinese version
            page.goto("https://help.aliyun.com/zh/model-studio/getting-started/billing", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            t1 = page.inner_text("body")
        
        browser.close()
        
        # Extract pricing table from text
        idx = t1.lower().find("pricing")
        if idx == -1:
            idx = t1.lower().find("price")
        if idx == -1:
            idx = t1.lower().find("billing")
        
        text = t1[max(0, idx-200):idx+15000] if idx >= 0 else t1[:15000]
        
        result = {"qwen_scraped": True, "text_len": len(t1), "pricing_section": text[:20000]}
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
