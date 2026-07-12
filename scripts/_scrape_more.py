"""Scrape remaining providers from correct official URLs."""
import sys, json, traceback
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

results = {}

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 1. Qwen - Alibaba Cloud Model Studio models page
        page = browser.new_page()
        page.goto("https://www.alibabacloud.com/help/en/model-studio/getting-started/models", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["qwen"] = page.inner_text("body")[:15000]
        page.close()
        
        # 2. NVIDIA build.nvidia.com - try catalog page
        page = browser.new_page()
        page.goto("https://build.nvidia.com/explore/discover", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["nvidia_catalog"] = page.inner_text("body")[:10000]
        page.close()
        
        # 3. Microsoft Azure OpenAI pricing
        page = browser.new_page()
        page.goto("https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["azure"] = page.inner_text("body")[:15000]
        page.close()
        
        # 4. xAI/Grok pricing
        page = browser.new_page()
        page.goto("https://x.ai/api", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["xai"] = page.inner_text("body")[:10000]
        page.close()
        
        # 5. Cohere pricing
        page = browser.new_page()
        page.goto("https://cohere.com/pricing", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["cohere"] = page.inner_text("body")[:10000]
        page.close()
        
        browser.close()
        print(json.dumps(results, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
