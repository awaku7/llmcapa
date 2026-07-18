"""Scrape Azure AI Foundry catalog (chat-focused) + multi-provider pricing.

Outputs:
  _scratch_azure_catalog_raw.json   - raw API items (deduped by name)
  _scratch_azure_pricing_tables.json - pricing tables from Azure pricing pages

Usage:
  python scripts/_scrape_azure_foundry_full.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_URL = "https://ai.azure.com/catalog/models"
PRICING_URLS = [
    ("aoai", "https://azure.microsoft.com/en-us/pricing/details/azure-openai/"),
    ("aoai_foundry", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/aoai/"),
    ("microsoft", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/microsoft/"),
    ("mistral", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/mistral-ai/"),
    ("llama", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/llama/"),
    ("cohere", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/cohere/"),
    ("deepseek", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/deepseek/"),
    ("grok", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/grok/"),
    ("kimi", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/kimi/"),
    ("fireworks", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/fireworks/"),
    ("bfl", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/black-forest-labs/"),
    ("model_router", "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/model-router/"),
    ("foundry_platform", "https://azure.microsoft.com/en-us/pricing/details/microsoft-foundry/"),
]


def slim_item(item: dict) -> dict:
    """Keep fields useful for llmcapa mapping."""
    ann = item.get("annotations") or {}
    props = item.get("properties") or {}
    scd = ann.get("systemCatalogData") or {}
    tags = ann.get("tags") or {}
    return {
        "entityResourceName": item.get("entityResourceName"),
        "name": props.get("name") or ann.get("name"),
        "displayName": (
            scd.get("displayName")
            or props.get("displayName")
            or tags.get("displayName")
            or ann.get("name")
        ),
        "description": (ann.get("description") or "")[:500],
        "stage": ann.get("stage"),
        "labels": ann.get("labels"),
        "tags": {
            k: tags.get(k)
            for k in (
                "task",
                "author",
                "license",
                "Featured",
                "deploymentOptions",
                "huggingface_model_id",
                "InferenceLegacyDate",
                "InferenceDeprecationDate",
                "InferenceRetirementDate",
                "inputModalities",
                "outputModalities",
                "summary",
            )
            if k in tags
        },
        "systemCatalogData": {
            k: scd.get(k)
            for k in (
                "publisher",
                "deploymentTypes",
                "license",
                "inferenceTasks",
                "fineTuningTasks",
                "languages",
                "summary",
                "displayName",
                "textContextWindow",
                "maxOutputTokens",
                "inputModalities",
                "outputModalities",
                "azureOffers",
                "inferenceRetirementDate",
                "inferenceDeprecationDate",
                "inferenceLegacyDate",
                "finetuneDeprecationDate",
                "finetuneRetirementDate",
                "enableMaap",
                "maasInference",
                "featured",
                "preview",
                "lifecycle",
                "supportsToolCalling",
                "modelCapabilities",
                "keywords",
                "industry",
            )
            if scd.get(k) is not None
        },
        "version": props.get("version") or props.get("alphanumericVersion"),
        "modelFormat": props.get("modelFormat"),
        "limits": props.get("limits"),
        "capabilities": props.get("capabilities"),
    }


EXTRACT_TABLES_JS = """
() => {
  const tables = Array.from(document.querySelectorAll('table'));
  const all = tables.map((tb, i) => {
    // find nearest heading
    let h = null;
    let el = tb;
    for (let n = 0; n < 8 && el; n++) {
      el = el.previousElementSibling || (el.parentElement && el.parentElement.previousElementSibling);
      if (!el) break;
      if (/^H[1-4]$/i.test(el.tagName)) { h = (el.innerText||'').trim(); break; }
      const hh = el.querySelector && el.querySelector('h1,h2,h3,h4');
      if (hh) { h = (hh.innerText||'').trim(); break; }
    }
    const rows = Array.from(tb.querySelectorAll('tr')).map(tr =>
      Array.from(tr.querySelectorAll('th,td')).map(c => (c.innerText||'').trim().replace(/\\s+/g,' '))
    ).filter(r => r.some(c => c));
    return {i, heading: h, rows};
  }).filter(t => t.rows.length > 0);
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4'))
    .map(h => (h.innerText||'').trim()).filter(Boolean);
  return {
    title: document.title,
    url: location.href,
    headings,
    tables: all,
    body_len: (document.body.innerText||'').length,
  };
}
"""


async def scrape_pricing(page) -> dict:
    out = {}
    for key, url in PRICING_URLS:
        print(f"  pricing {key}: {url}")
        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            # dismiss cookie banner if present
            for sel in [
                "button#onetrust-accept-btn-handler",
                "button:has-text('Accept')",
                "button:has-text('Accept all')",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() and await btn.is_visible():
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(500)
                except Exception:
                    pass
            data = await page.evaluate(EXTRACT_TABLES_JS)
            out[key] = data
            ntab = len(data.get("tables") or [])
            print(f"    -> tables={ntab} body_len={data.get('body_len')}")
        except Exception as e:
            print(f"    ERROR {e}")
            out[key] = {"error": str(e), "url": url}
    return out


async def apply_chat_filter(page) -> None:
    """Try to filter catalog to Chat completion inference task."""
    # Expand Inference tasks section if collapsed
    try:
        # Click the Inference tasks filter header
        hdr = page.locator("text=Inference tasks").first
        if await hdr.count():
            await hdr.click(timeout=3000)
            await page.wait_for_timeout(800)
    except Exception as e:
        print(f"  filter expand warn: {e}")

    # Try checkbox / option for Chat completion
    candidates = [
        "label:has-text('Chat completion')",
        "text=Chat completion",
        "[aria-label*='Chat completion']",
        "input[type=checkbox][value*='chat']",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count():
                await loc.click(timeout=3000)
                await page.wait_for_timeout(2500)
                print(f"  applied filter via {sel}")
                return
        except Exception:
            continue
    print("  WARN: could not apply chat filter; scraping unfiltered (will filter in post)")


async def scrape_catalog(page) -> list[dict]:
    """Paginate catalog via Next clicks; capture asset-gallery API responses."""
    items_by_name: dict[str, dict] = {}
    page_num = 0
    max_pages = 200

    # Capture initial SSR/API if any after filter
    async def on_response(response):
        try:
            if "asset-gallery/v1.0/models" in response.url and response.status == 200:
                data = await response.json()
                vals = data.get("value") or []
                for it in vals:
                    slim = slim_item(it)
                    name = slim.get("name")
                    if name:
                        items_by_name[name] = slim
                print(
                    f"    API hit: +{len(vals)} (unique={len(items_by_name)} "
                    f"totalCount={data.get('totalCount')})"
                )
        except Exception as e:
            print(f"    response parse err: {e}")

    page.on("response", on_response)

    await page.goto(CATALOG_URL, timeout=60000, wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)

    # Also collect SSR card names as fallback
    ssr_names = await page.evaluate(
        """() => {
        const links = document.querySelectorAll('a[href*="/catalog/models/"]');
        return Array.from(links).map(a => {
          const href = (a.href||'').replace(/\\/$/, '');
          return href.split('/').pop();
        }).filter(Boolean);
    }"""
    )
    print(f"  SSR cards: {len(ssr_names)}")
    for n in ssr_names:
        if n not in items_by_name:
            items_by_name[n] = {"name": n, "displayName": n, "source": "ssr_card"}

    await apply_chat_filter(page)
    await page.wait_for_timeout(3000)

    # Re-collect after filter
    ssr_names2 = await page.evaluate(
        """() => {
        const links = document.querySelectorAll('a[href*="/catalog/models/"]');
        return Array.from(links).map(a => {
          const href = (a.href||'').replace(/\\/$/, '');
          return href.split('/').pop();
        }).filter(Boolean);
    }"""
    )
    print(f"  SSR cards after filter: {len(ssr_names2)}")
    for n in ssr_names2:
        if n not in items_by_name:
            items_by_name[n] = {"name": n, "displayName": n, "source": "ssr_card"}

    while page_num < max_pages:
        next_btn = page.locator('button:has-text("Next")')
        try:
            await next_btn.wait_for(timeout=5000)
        except Exception:
            print("  No Next button.")
            break
        if await next_btn.is_disabled():
            print("  Next disabled — last page.")
            break

        before = len(items_by_name)
        await next_btn.click()
        page_num += 1
        # wait for either new items or timeout
        for _ in range(20):
            await page.wait_for_timeout(400)
            if len(items_by_name) > before:
                break
        print(f"  page click {page_num}: unique={len(items_by_name)}")

        # safety: if no growth for 3 consecutive pages, stop
        if page_num > 3 and len(items_by_name) == before:
            # try once more with longer wait
            await page.wait_for_timeout(2000)
            if len(items_by_name) == before:
                print("  no growth — stopping pagination")
                # don't break immediately; UI might still advance without API
                # but if Next still enabled keep going a bit
                if page_num > 5 and page_num % 5 == 0:
                    # collect DOM names each 5 pages
                    dom = await page.evaluate(
                        """() => Array.from(document.querySelectorAll('a[href*="/catalog/models/"]'))
                        .map(a => (a.href||'').replace(/\\/$/,'').split('/').pop()).filter(Boolean)"""
                    )
                    for n in dom:
                        if n not in items_by_name:
                            items_by_name[n] = {
                                "name": n,
                                "displayName": n,
                                "source": "ssr_card",
                            }

    page.remove_listener("response", on_response)
    return list(items_by_name.values())


async def main():
    print("=== Azure Foundry full scrape ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        print("\n[1/2] Catalog")
        catalog = await scrape_catalog(page)
        cat_path = ROOT / "_scratch_azure_catalog_raw.json"
        cat_path.write_text(
            json.dumps({"count": len(catalog), "items": catalog}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  saved {len(catalog)} -> {cat_path}")

        print("\n[2/2] Pricing pages")
        pricing = await scrape_pricing(page)
        pr_path = ROOT / "_scratch_azure_pricing_tables.json"
        pr_path.write_text(json.dumps(pricing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  saved pricing keys={list(pricing)} -> {pr_path}")

        await browser.close()
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
