"""Scrape Azure AI Foundry model catalog with SSR page 1 support.

Usage:
    python scripts/_scrape_azure_catalog.py [--save] [--output PATH]

How it works:
    1. Reads model names from the SSR page 1 DOM (top ~51 models).
    2. Clicks "Next" repeatedly via Playwright to trigger the API for pages 2+.
       (Direct API calls via fetch() don't work - they lack auth tokens.)
    3. Captures model data from each API response.
    4. Visits detail pages for any SSR-only models to get their metadata.
    5. Outputs combined catalog in our standard format.

Important:
    The Azure AI Catalog API requires a continuationToken that is generated
    from the SSR page state. The only way to paginate is to click "Next" in
    the browser. Direct fetch() calls to the API will fail with 400 errors.
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


CATALOG_URL = "https://ai.azure.com/catalog/models"
DETAIL_URL = "https://ai.azure.com/catalog/models/{name}"


def _api_item_to_entry(item: dict) -> dict:
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
        tl = (task or "").lower()
        if "image" in tl or "vision" in tl:
            if "image" not in input_mods:
                input_mods.append("image")
            supports_vision = True
        if "audio" in tl or "speech" in tl:
            if "audio" not in input_mods:
                input_mods.append("audio")
            supports_audio_input = True
            if "audio" not in output_mods:
                output_mods.append("audio")
            supports_audio_output = True

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


async def get_ssr_page1_names(page) -> set:
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


async def click_until_no_next(page) -> list:
    """Click 'Next' repeatedly to paginate through all API pages.

    Returns list of catalog-format entries from all API responses.
    """
    all_entries = []
    page_num = 0
    max_pages = 500  # safety limit

    while page_num < max_pages:
        # Wait for the Next button to appear and be clickable
        next_btn = page.locator('button:has-text("Next")')
        try:
            await next_btn.wait_for(timeout=5000)
        except Exception:
            print("  No more Next button found.")
            break

        is_disabled = await next_btn.is_disabled()
        if is_disabled:
            print("  Next button is disabled. Reached last page.")
            break

        # Before clicking, set up a one-shot listener for the API response
        future_response = asyncio.get_event_loop().create_future()

        def capture_response(response):
            if "asset-gallery/v1.0/models" in response.url and response.status == 200:
                if not future_response.done():
                    future_response.set_result(response)

        page.on("response", capture_response)

        # Click Next
        await next_btn.click()
        page_num += 1

        # Wait a moment for the API response
        try:
            resp = await asyncio.wait_for(future_response, timeout=10)
            data = await resp.json()
            values = data.get("value", [])
            for item in values:
                all_entries.append(_api_item_to_entry(item))
            print(f"  Page {page_num}: {len(values)} models (total: {len(all_entries)})")
        except asyncio.TimeoutError:
            print(f"  Page {page_num}: timeout waiting for API response")
            break
        finally:
            page.remove_listener("response", capture_response)

        await asyncio.sleep(0.5)

    return all_entries


async def fetch_ssr_detail(page, model_name: str) -> dict:
    """Visit a model's detail page to get metadata (for SSR-only models)."""
    url = DETAIL_URL.format(name=model_name)
    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    # Try to click "Technical specs" accordion
    btn = page.locator('button:has-text("Technical specs")')
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(500)

    text = await page.evaluate("document.body.innerText")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Extract quick facts
    qf = {}
    labels = ["Model provider", "Type", "Lifecycle", "Input type",
              "Output type", "Context window", "Token limits"]
    for i, line in enumerate(lines):
        if line in labels and i + 1 < len(lines):
            qf[line] = lines[i + 1]

    # Parse context window (e.g. "400k" -> 400000)
    ctx_raw = qf.get("Context window", "")
    ctx_match = re.search(r"([\d,.]+)\s*k", ctx_raw, re.I)
    ctx = int(float(ctx_match.group(1).replace(",", "")) * 1000) if ctx_match else 4096

    # Parse token limits
    tok_raw = qf.get("Token limits", "")
    tok_match = re.search(r"([\d,.]+)\s*k", tok_raw, re.I)
    max_out = int(float(tok_match.group(1).replace(",", "")) * 1000) if tok_match else 2048

    # Modalities
    input_type = qf.get("Input type", "").lower()
    output_type = qf.get("Output type", "").lower()

    input_mods = ["text"]
    output_mods = ["text"]
    supports_vision = "image" in input_type
    supports_audio_input = "audio" in input_type
    supports_audio_output = "audio" in output_type

    if supports_vision and "image" not in input_mods:
        input_mods.append("image")
    if supports_audio_input and "audio" not in input_mods:
        input_mods.append("audio")
    if supports_audio_output and "audio" not in output_mods:
        output_mods.append("audio")
    if "image" in output_type and "image" not in output_mods:
        output_mods.append("image")

    model_type = qf.get("Type", "").lower()
    supports_fc = "responses" in model_type

    return {
        "provider": "azure-openai",
        "model_id": model_name,
        "display_name": model_name,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": input_mods,
        "output_modalities": output_mods,
        "supports_function_calling": supports_fc,
        "supports_vision": supports_vision,
        "supports_audio_input": supports_audio_input,
        "supports_audio_output": supports_audio_output,
    }


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
        ssr_names = await get_ssr_page1_names(page)
        print(f"  SSR page 1: {len(ssr_names)} models")

        # Step 2: Click Next repeatedly to get API models (pages 2+)
        print("\nStep 2: Paginating through API pages via Next clicks...")
        api_entries = await click_until_no_next(page)
        print(f"  Total API models: {len(api_entries)}")

        api_names = {m["model_id"] for m in api_entries}

        # Step 3: Identify SSR-only models
        ssr_only = ssr_names - api_names
        both = ssr_names & api_names
        print(f"\n  SSR only: {len(ssr_only)}")
        print(f"  Both SSR+API: {len(both)}")

        # Step 4: Fetch detail data for SSR-only models
        if ssr_only:
            print("\nStep 3: Fetching detail pages for SSR-only models...")
            ssr_entries = []
            for i, model_name in enumerate(sorted(ssr_only)):
                entry = await fetch_ssr_detail(page, model_name)
                ssr_entries.append(entry)
                ctx = entry["context_window"]
                print(f"  [{i+1}/{len(ssr_only)}] {model_name}: ctx={ctx}")
                await asyncio.sleep(0.5)
        else:
            ssr_entries = []
            print("\nStep 3: No SSR-only models to fetch.")

        # Combine: API entries + SSR-only entries
        combined = api_entries + ssr_entries

        # Deduplicate
        seen = set()
        unique = []
        for m in combined:
            if m["model_id"] not in seen:
                seen.add(m["model_id"])
                unique.append(m)

        print(f"\n=== Summary ===")
        print(f"  SSR page 1 models:  {len(ssr_names)}")
        print(f"  API models:         {len(api_entries)}")
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
