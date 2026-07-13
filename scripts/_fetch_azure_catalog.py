"""Fetch all models from Azure AI Catalog (API + SSR page 1).

Usage:
    python scripts/_fetch_azure_catalog.py

This script connects to the Azure AI Catalog via Playwright and collects
ALL models including those on page 1 (which are SSR-only and not available
via the asset-gallery API).

Output:
    - Prints model count and sample data
    - Optionally saves to JSON (--save)

Limitation:
    Page 1 models are SSR'd and NOT accessible via the asset-gallery API.
    This script handles that by scraping the DOM for page 1 and using
    the API for pages 2+.

Requires:
    playwright
"""

import asyncio
import json
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Install playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


AZURE_API_BASE = "https://ai.azure.com/api/japanwest/asset-gallery/v1.0/models"


def _build_request_body(token=None):
    """Build the standard API request body."""
    body = {
        "filters": [
            {"field": "type", "operator": "eq", "values": ["models"]},
            {"field": "kind", "operator": "eq", "values": ["Versioned"]},
            {"field": "properties/isAnonymous", "operator": "ne", "values": ["true"]},
            {"field": "annotations/archived", "operator": "ne", "values": ["true"]},
            {"field": "properties/userProperties/is-promptflow", "operator": "notexists"},
            {"field": "labels", "operator": "eq", "values": ["latest"]},
        ],
        "searchParameters": {
            "freeTextSearch": "",
            "freeTextSearchColumns": [
                {"name": "annotations/systemCatalogData/publisher"},
                {"name": "properties/name"},
                {"name": "annotations/systemCatalogData/inferenceTasks"},
            ],
        },
        "order": [{"field": "usage/popularity", "direction": "Desc"}],
        "pageSize": 200,
        "facets": [],
        "includeTotalResultCount": True,
        "searchBuilder": "AppendPrefix",
    }
    if token:
        body["continuationToken"] = token
    return body


async def fetch_all_models(page) -> list:
    """Fetch ALL models from Azure AI Catalog.

    Combines SSR page 1 (DOM scraping) with API data (pages 2+).
    Returns list of API response items (value[] objects).
    """
    # ---- Step 1: Get SSR page 1 models from the DOM ----
    ssr_links = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll('a[class*="_cardLink"]');
            return Array.from(cards).map(el => el.href).filter(h => h);
        }
    """)
    ssr_names = set()
    for link in ssr_links:
        name = link.rstrip("/").split("/")[-1]
        if name:
            ssr_names.add(name.lower())

    print(f"[SSR] Page 1 models: {len(ssr_names)}")

    # ---- Step 2: Get API data (pages 2+) ----
    api_values = []
    token = None
    page_num = 0

    while True:
        page_num += 1
        body = _build_request_body(token)

        result = await page.evaluate(f"""
            async () => {{
                const resp = await fetch('{AZURE_API_BASE}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({json.dumps(body)})
                }});
                return await resp.json();
            }}
        """)

        values = result.get("value", [])
        api_values.extend(values)

        token = result.get("continuationToken")
        if not token:
            break
        await asyncio.sleep(0.3)

    print(f"[API] Pages 2+: {len(api_values)} models across {page_num} pages")

    # ---- Step 3: Get SSR models' detail data ----
    # SSR models are not in API data, so we need to visit each detail page
    api_names = set()
    for v in api_values:
        name = v.get("properties", {}).get("name", "")
        if name:
            api_names.add(name.lower())

    # SSR-only models = in SSR but not in API
    ssr_only = ssr_names - api_names
    print(f"[SSR] Models NOT in API: {len(ssr_only)}")

    # For SSR-only models, extract from detail pages
    for i, model_name in enumerate(sorted(ssr_only)):
        detail_url = f"https://ai.azure.com/catalog/models/{model_name}"
        try:
            await page.goto(detail_url, timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            # Click accordions
            for section in ["Technical specs"]:
                btn = page.locator(f'button:has-text("{section}")')
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_timeout(300)

            # Extract from Quick facts
            info = await page.evaluate("""
                () => {
                    const text = document.body.innerText || '';
                    const r = {};
                    const ctxM = text.match(/Context window[^\\n]*?([\\d.,]+)\\s*k/i);
                    if (ctxM) r.context_window = ctxM[1];
                    const typeM = text.match(/Type[^\\n]*?([^\\n]+)/);
                    if (typeM) r.type = typeM[1].trim();
                    const provM = text.match(/Model provider[^\\n]*?([^\\n]+)/);
                    if (provM) r.provider = provM[1].trim();
                    const tokenM = text.match(/Token limits[^\\n]*?([^\\n]+)/);
                    if (tokenM) r.token_limits = tokenM[1].trim();
                    const inputM = text.match(/Input type[^\\n]*?([^\\n]+)/);
                    if (inputM) r.input_type = inputM[1].trim();
                    const outputM = text.match(/Output type[^\\n]*?([^\\n]+)/);
                    if (outputM) r.output_type = outputM[1].trim();
                    return r;
                }
            """)
            print(f"  [{i+1}/{len(ssr_only)}] {model_name}: ctx={info.get('context_window','?')}")
        except Exception as e:
            print(f"  [{i+1}/{len(ssr_only)}] {model_name}: ERROR {e}")

    return {
        "ssr_names": sorted(ssr_names),
        "api_values": api_values,
        "ssr_only": sorted(ssr_only),
        "total_unique": len(ssr_names | api_names),
    }


async def main():
    save = "--save" in sys.argv

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Loading Azure AI Catalog...")
        await page.goto("https://ai.azure.com/catalog/models", timeout=30000)
        await page.wait_for_timeout(5000)

        result = await fetch_all_models(page)

        print(f"\n=== Summary ===")
        print(f"SSR page 1 models:  {len(result['ssr_names'])}")
        print(f"API models (2+):    {len(result['api_values'])}")
        print(f"SSR-only models:    {len(result['ssr_only'])}")
        print(f"Total unique:       {result['total_unique']}")

        if save:
            out_path = Path(__file__).parent.parent / "azure_catalog_full.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Saved to {out_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
