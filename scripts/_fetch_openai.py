"""Fetch OpenAI models from official docs using Playwright."""
import sys, json, traceback, re
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error": "playwright not installed"}', flush=True)
    sys.exit(1)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        results = {}
        
        # === Models page ===
        page.goto("https://developers.openai.com/api/docs/models", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        
        text = page.inner_text("body")
        results["models_text"] = text[:20000]
        results["models_url"] = page.url
        results["models_title"] = page.title()
        
        # Try to extract table data
        tables = page.evaluate("""
            () => {
                const tables = document.querySelectorAll('table');
                return Array.from(tables).map(t => {
                    const rows = t.querySelectorAll('tr');
                    return Array.from(rows).map(r => {
                        const cells = r.querySelectorAll('td, th');
                        return Array.from(cells).map(c => c.innerText.trim());
                    });
                });
            }
        """)
        results["tables"] = tables
        
        # === Pricing page ===
        page.goto("https://developers.openai.com/api/docs/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        
        pricing_text = page.inner_text("body")
        results["pricing_text"] = pricing_text[:20000]
        results["pricing_url"] = page.url
        
        browser.close()
        
        print(json.dumps(results, ensure_ascii=False), flush=True)
        
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False), flush=True)
