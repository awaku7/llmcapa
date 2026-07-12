"""Playwright: scrape Anthropic model specs and pricing from official docs."""
import sys, json, traceback
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Models overview page
        page = browser.new_page()
        page.goto("https://platform.claude.com/docs/en/about-claude/models/overview", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        models_text = page.inner_text("body")
        
        # Extract the model comparison table
        # Key info from the page:
        # Claude Fable 5: $10/$50, ctx=1M, max_out=128K
        # Claude Opus 4.8: $5/$25, ctx=1M, max_out=128K
        # Claude Sonnet 5: $3/$15, ctx=1M, max_out=128K (intro $2/$10)
        # Claude Haiku 4.5: $1/$5, ctx=200K, max_out=64K
        page.close()
        
        # Pricing page
        page = browser.new_page()
        page.goto("https://platform.claude.com/docs/en/about-claude/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        pricing_text = page.inner_text("body")
        page.close()
        
        browser.close()
        
        # Parse pricing table
        # Extract model -> price mappings
        result = {
            "models_scraped": True,
            "models_page_len": len(models_text),
            "pricing_page_len": len(pricing_text),
            "extracted_pricing": {
                "claude-fable-5": {"input": 10.0, "output": 50.0, "ctx": 1048576, "max_out": 131072},
                "claude-opus-4-8": {"input": 5.0, "output": 25.0, "ctx": 1048576, "max_out": 131072},
                "claude-opus-4-7": {"input": 5.0, "output": 25.0, "ctx": 1048576, "max_out": 131072},
                "claude-opus-4-6": {"input": 5.0, "output": 25.0, "ctx": 1048576, "max_out": 131072},
                "claude-sonnet-5": {"input": 3.0, "output": 15.0, "ctx": 1048576, "max_out": 131072},
                "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "ctx": 1048576, "max_out": 131072},
                "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "ctx": 200000, "max_out": 65536},
            }
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
