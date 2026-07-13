"""Scrape Azure AI Foundry model catalog with SSR page 1 support.

Usage:
    python scripts/_scrape_azure_catalog.py [--save] [--output PATH]

This script handles the SSR limitation of Azure AI Catalog:
- Page 1 (top ~51 models by popularity) is server-side rendered into HTML
  and NOT accessible via the asset-gallery/v1.0/models API.
- Pages 2+ use the API for data.

The script:
  1. Reads model names from the SSR page 1 DOM
  2. Fetches pages 2+ via the API
  3. Visits each SSR-only model's detail page for metadata
  4. Outputs combined catalog in our standard format
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)


AZURE_API_BASE = "https://ai.azure.com/api/japanwest/asset-gallery/v1.0/models"
CATALOG_URL = "https://ai.azure.com/catalog/models"
DETAIL_URL = "https://ai.azure.com/catalog/models/{name}"


def _build_api_body(token=None):
    """Build the standard API request body for the catalog API."""
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


def _convert_api_item(item: dict) -> dict:
    """Convert an API response item to our catalog format."""
    props = item.get("properties", {})
    annotations = item.get("annotations", {})
    name = props.get("name", "")
    display = props.get("displayName", "") or name

    # Determine modalities from inference tasks
    tasks = annotations.get("systemCatalogData", {}).get("inferenceTasks", [])
    input_mods = ["text"]
    output_mods = ["text"]
    supports_vision = False
    supports_audio_input = False
    supports_audio_output = False

    for task in tasks:
        tl = task.lower() if task else ""
        if "image" in tl or "vision" in tl:
            if "image" not in input_mods:
                input_mods.append("image")
            supports_vision = True
        if "audio" in tl or "speech" in tl:
            if "audio" not in input_mods:
                input_mods.append("audio")
            supports_audio_input = True
        if "audio" in tl or "speech" in tl:
            if "audio" not in output_mods:
                output_mods.append("audio")
            supports_audio_output = True

    # Context window estimation from limits
    limits = props.get("limits", {})
    ctx = limits.get("maxContextLength", 4096) or 4096
    max_out = limits.get("maxOutputTokens", 2048) or 2048

    return {
        "provider": "azure-openai",
        "model_id": name,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": input_mods,
        "output_modalities": output_mods,
        "supports_function_calling": props.get("capabilities", {}).get("functionCalling", False),
        "supports_vision": supports_vision,
        "supports_audio_input": supports_audio_input,
        "supports_audio_output": supports_audio_output,
    }


def _quick_facts_from_text(text: str) -> dict:
    """Extract quick facts from a detail page's text content."""
    r = {}
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Find labels and take next line as value
    labels = {
        "Model provider": "provider",
        "Type": "type",
        "Lifecycle": "lifecycle",
        "Input type": "input_type",
        "Output type": "output_type",
        "Context window": "context_window",
        "Token limits": "token_limits",
    }

    for i, line in enumerate(lines):
        if line in labels and i + 1 < len(lines):
            r[labels[line]] = lines[i + 1]

    # Parse context window (e.g. "400k" -> 400000)
    ctx_raw = r.get("context_window", "")
    if ctx_raw:
        ctx_match = re.search(r"([\d,.]+)\s*k", ctx_raw, re.I)
        if ctx_match:
            num = float(ctx_match.group(1).replace(",", ""))
            r["context_window_num"] = int(num * 1000)

    # Parse token limits
    tok_raw = r.get("token_limits", "")
    if tok_raw:
        tok_match = re.search(r"([\d,.]+)\s*k", tok_raw, re.I)
        if tok_match:
            num = float(tok_match.group(1).replace(",", ""))
            r["token_limits_num"] = int(num * 1000)

    return r


async def fetch_ssr_page1_names(page) -> set:
    """Get model names from SSR page 1 DOM."""
    await page.goto(CATALOG_URL, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    names = await page.evaluate("""
        () => {
            const links = document.querySelectorAll('a[class*="_cardLink"]');
            return Array.from(links).map(a => {
                const href = a.href || '';
                return href.replace(/\\/$/, '').split('/').pop();
            }).filter(n => n);
        }
    """)
    return set(names)


async def fetch_api_models(page) -> list:
    """Fetch models from pages 2+ via API. Returns list of catalog-format dicts."""
    page_num = 0
    token = None
    all_items = []

    while True:
        page_num += 1
        body = _build_api_body(token)

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
        for item in values:
            all_items.append(_convert_api_item(item))

        token = result.get("continuationToken")
        if not token:
            break
        await asyncio.sleep(0.3)

    print(f"  API pages 2+: {len(all_items)} models across {page_num} pages")
    return all_items


async def fetch_ssr_detail(page, model_name: str) -> dict:
    """Visit a model's detail page to get metadata."""
    url = DETAIL_URL.format(name=model_name)
    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    # Try to click "Technical specs" accordion
    btn = page.locator('button:has-text("Technical specs")')
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(500)

    text = await page.evaluate("document.body.innerText")
    qf = _quick_facts_from_text(text)

    entry = {
        "provider": "azure-openai",
        "model_id": model_name,
        "display_name": model_name,
        "context_window": qf.get("context_window_num", 4096),
        "max_output_tokens": qf.get("token_limits_num", 2048),
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": False,
        "supports_vision": False,
        "supports_audio_input": False,
        "supports_audio_output": False,
    }

    # Infer modalities from type
    model_type = qf.get("type", "").lower()
    input_type = qf.get("input_type", "").lower()
    output_type = qf.get("output_type", "").lower()

    if "image" in input_type:
        entry["input_modalities"].append("image")
        entry["supports_vision"] = True
    if "audio" in input_type:
        entry["input_modalities"].append("audio")
        entry["supports_audio_input"] = True
    if "audio" in output_type:
        if "audio" not in entry["output_modalities"]:
            entry["output_modalities"].append("audio")
        entry["supports_audio_output"] = True
    if "image" in output_type:
        entry["output_modalities"].append("image")

    if "responses" in model_type:
        entry["supports_function_calling"] = True

    return entry


async def main():
    save = "--save" in sys.argv
    output_path = None
    for arg in sys.argv:
        if arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Step 1: Get SSR page 1 model names
        print("Step 1: Fetching SSR page 1 model names...")
        ssr_names = await fetch_ssr_page1_names(page)
        print(f"  SSR page 1: {len(ssr_names)} models")

        # Step 2: Fetch API models (pages 2+)
        print("Step 2: Fetching API models...")
        api_models = await fetch_api_models(page)
        api_names = {m["model_id"] for m in api_models}

        # Step 3: Identify SSR-only models
        ssr_only = ssr_names - api_names
        both = ssr_names & api_names
        print(f"  API only: {len(api_names - ssr_names)}")
        print(f"  Both: {len(both)}")
        print(f"  SSR only: {len(ssr_only)}")

        # Report duplicates
        for m in sorted(both):
            print(f"    (both) {m}")

        # Step 4: Fetch detail data for SSR-only models
        print("\nStep 3: Fetching detail pages for SSR-only models...")
        ssr_models = []
        for i, model_name in enumerate(sorted(ssr_only)):
            entry = await fetch_ssr_detail(page, model_name)
            ssr_models.append(entry)
            ctx = entry["context_window"]
            print(f"  [{i+1}/{len(ssr_only)}] {model_name}: ctx={ctx}")
            await asyncio.sleep(0.5)

        # Combine: API models + SSR-only models
        combined = api_models + ssr_models

        # Deduplicate (shouldn't happen but just in case)
        seen = set()
        unique = []
        for m in combined:
            if m["model_id"] not in seen:
                seen.add(m["model_id"])
                unique.append(m)

        print(f"\n=== Summary ===")
        print(f"  SSR page 1 models:  {len(ssr_names)}")
        print(f"  API models:         {len(api_models)}")
        print(f"  SSR-only models:    {len(ssr_only)}")
        print(f"  Total unique:       {len(unique)}")

        output = {"models": unique}

        if save:
            if output_path:
                out_path = Path(output_path)
            else:
                proj_root = Path(__file__).resolve().parent.parent
                out_path = proj_root / "src" / "llmcapa" / "data" / "azure_foundry.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"  Saved to {out_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
