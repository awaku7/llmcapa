"""Playwright: scrape official pricing for remaining providers."""
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
        
        # 1. Mistral - try API reference pricing
        page = browser.new_page()
        page.goto("https://mistral.ai/technology/#models", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        # Try clicking through to pricing
        try:
            links = page.query_selector_all('a')
            for link in links:
                href = link.get_attribute('href') or ''
                if 'pricing' in href.lower() or 'Pricing' in link.inner_text():
                    page.goto(href if href.startswith('http') else 'https://mistral.ai' + href, wait_until='networkidle', timeout=30000)
                    page.wait_for_timeout(2000)
                    break
        except:
            pass
        results["mistral"] = page.inner_text("body")[:15000]
        page.close()
        
        # 2. NVIDIA pricing
        page = browser.new_page()
        page.goto("https://build.nvidia.com/meta/llama-3.3-70b-instruct", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["nvidia"] = page.inner_text("body")[:10000]
        page.close()
        
        # 3. Qwen / Alibaba Cloud pricing (English)
        page = browser.new_page()
        page.goto("https://www.alibabacloud.com/help/en/model-studio/developer-mode-on-a-shared-model", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["qwen"] = page.inner_text("body")[:15000]
        page.close()
        
        # 4. AWS Bedrock pricing
        page = browser.new_page()
        page.goto("https://aws.amazon.com/bedrock/pricing/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["bedrock"] = page.inner_text("body")[:15000]
        page.close()
        
        # 5. Meta Llama pricing
        page = browser.new_page()
        page.goto("https://llama.meta.com/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        results["meta"] = page.inner_text("body")[:10000]
        page.close()
        
        browser.close()
        print(json.dumps(results, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
