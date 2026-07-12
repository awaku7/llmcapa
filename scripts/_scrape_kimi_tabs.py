"""Playwright: click Kimi pricing tabs to reveal prices."""
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
        page.goto("https://platform.kimi.ai/docs/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        
        results = {}
        
        # Click each pricing tab to reveal data
        tabs = ["Kimi K2.7 Code", "Kimi K2.6", "Kimi K2.5", "Moonshot V1"]
        for tab_name in tabs:
            try:
                # Try clicking the tab button
                btn = page.query_selector(f"button:has-text('{tab_name}')")
                if btn:
                    btn.click()
                    page.wait_for_timeout(1000)
                # Get the visible pricing content
                section = page.query_selector(".kimi-pricing-content, .pricing-content, [class*='pricing']")
                if section:
                    results[tab_name] = section.inner_text()
                else:
                    # Get all visible text after clicking
                    results[tab_name] = page.inner_text("body")[:3000]
            except Exception as e:
                results[tab_name] = f"error: {e}"
        
        browser.close()
        print(json.dumps(results, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
