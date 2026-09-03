"""Playwright: scrape Anthropic model specs and pricing from official docs."""
import json
import sys
import traceback
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
        pricing_html = page.content()
        page.close()

        browser.close()

        # Parse the live pricing table.  Keep model IDs and values entirely
        # data-driven so newly added or retired Claude models are reflected
        # without editing this scraper.
        from pathlib import Path

        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from _update_anthropic import _model_id, discover_pricing

        extracted_pricing = {}
        for row in discover_pricing(pricing_html):
            model_id = _model_id(row["name"])
            extracted_pricing[model_id] = {
                "input": row["input"],
                "output": row["output"],
                "cache_5m": row["cache_5m"],
                "cache_1h": row["cache_1h"],
                "cache_hit": row["cache_hit"],
                "deprecated": row["deprecated"],
            }

        result = {
            "models_scraped": bool(extracted_pricing),
            "models_page_len": len(models_text),
            "pricing_page_len": len(pricing_html),
            "extracted_pricing": extracted_pricing,
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
