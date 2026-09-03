"""Playwright: click Kimi pricing tabs to reveal prices."""
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

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://platform.kimi.ai/docs/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        
        results = {}

        # Discover pricing tabs from the page instead of maintaining a fixed
        # list of model names. The page may add or retire models at any time.
        candidates = page.locator("button, a").all_inner_texts()
        tabs = []
        pattern = r"(?:Kimi\s+K[0-9]+(?:\.[0-9]+)?(?:\s+Code)?|Moonshot\s+V[0-9]+)"
        for label in candidates:
            for match in re.findall(pattern, " ".join(label.split())):
                tab_name = match.strip()
                if tab_name not in tabs:
                    tabs.append(tab_name)

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
