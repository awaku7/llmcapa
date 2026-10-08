"""Scrape Azure AI Foundry inference catalog (all tasks) + multi-provider pricing.

Outputs:
  _scratch_azure_catalog_raw.json   - raw API items (deduped by name)
  _scratch_azure_pricing_tables.json - pricing tables from Azure pricing pages

Usage:
  python scripts/_scrape_azure_foundry_full.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Windows consoles may default to CP932; scraper diagnostics can contain Unicode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
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
            # Pricing tables are rendered asynchronously on some pages. Wait
            # for actual table rows instead of sleeping a fixed four seconds.
            try:
                await page.locator("table tr:nth-child(2)").first.wait_for(
                    state="attached", timeout=4000
                )
            except PlaywrightTimeoutError:
                # Some pricing pages have no HTML tables; still preserve their
                # headings/body text in the extracted result.
                pass
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
                except Exception:  # noqa: BLE001, S110
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
    """Legacy UI filter helper; not invoked by the all-task catalog scrape."""
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
        except Exception:  # noqa: BLE001, S112
            continue
    print("  WARN: could not apply chat filter; scraping unfiltered (will filter in post)")


async def scrape_catalog(page, max_pages: int = 500) -> list[dict]:
    """Scrape catalog pages while handling API responses and UI updates separately."""
    items_by_name: dict[str, dict] = {}
    api_pages = 0
    max_clicks = max_pages * 2 + 10
    response_queue = asyncio.Queue()

    def on_response(response):
        if "asset-gallery/v1.0/models" in response.url:
            response_queue.put_nowait(response)

    async def collect_response(response) -> list[str]:
        nonlocal api_pages
        if response.status != 200:
            # On 2026-10-08 the pagination API intermittently returned HTTP 500;
            # a complete rerun later succeeded. No retry/backoff is implemented,
            # so fail rather than silently saving a partial catalog.
            raise RuntimeError(f"Azure catalog API returned HTTP {response.status}")
        data = await response.json()
        values = data.get("value") or []
        model_names = []
        for item in values:
            slim = slim_item(item)
            name = slim.get("name")
            if name:
                items_by_name[name] = slim
                model_names.append(name)
        api_pages += 1
        print(
            f"    API hit: +{len(values)} (unique={len(items_by_name)} "
            f"totalCount={data.get('totalCount')})"
        )
        await asyncio.sleep(0.5)  # keep pagination below the service's request rate
        return model_names

    async def collect_ssr_cards():
        names = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="/catalog/models/"]'))
            .map(a => (a.href || '').split('/').filter(Boolean).pop()).filter(Boolean)"""
        )
        for name in names:
            items_by_name.setdefault(
                name, {"name": name, "displayName": name, "source": "ssr_card"}
            )
        return names

    async def ui_state():
        return await page.evaluate(
            """() => {
                const links = Array.from(document.querySelectorAll('a[href*="/catalog/models/"]'));
                const names = links.map(a => (a.href || '').split('/').filter(Boolean).pop());
                const text = (document.body?.innerText || '').slice(-1000);
                const marker = 'Prev';
                const pos = text.lastIndexOf(marker);
                const rest = pos < 0 ? '' : text.slice(pos + marker.length).trim().split(String.fromCharCode(10)).join(' ');
                const page = Number(rest.split(' ')[0]) || 0;
                return {page, names};
            }"""
        )

    async def wait_for_ui_advance(previous_state):
        await page.wait_for_function(
            """previous => {
                const links = Array.from(document.querySelectorAll('a[href*="/catalog/models/"]'));
                const names = links.map(a => (a.href || '').split('/').filter(Boolean).pop());
                const text = (document.body?.innerText || '').slice(-1000);
                const marker = 'Prev';
                const pos = text.lastIndexOf(marker);
                const rest = pos < 0 ? '' : text.slice(pos + marker.length).trim().split(String.fromCharCode(10)).join(' ');
                const page = Number(rest.split(' ')[0]) || 0;
                return page > previous.page ||
                    (names.length > 0 && JSON.stringify(names) !== JSON.stringify(previous.names));
            }""",
            arg=previous_state,
            timeout=15000,
        )

    page.on("response", on_response)
    response_task = asyncio.create_task(response_queue.get())
    ui_task = None
    clicks = 0
    consecutive_stalls = 0
    try:
        await page.goto(CATALOG_URL, timeout=60000, wait_until="domcontentloaded")
        try:
            await page.locator('a[href*="/catalog/models/"]').first.wait_for(
                state="attached", timeout=5000
            )
        except PlaywrightTimeoutError:
            # Continue: pagination may still be available when SSR cards are absent.
            pass

        ssr_names = await collect_ssr_cards()
        print(f"  SSR cards: {len(ssr_names)}")
        while response_task.done():
            await collect_response(response_task.result())
            response_task = asyncio.create_task(response_queue.get())

        # The catalog showed about 11.9k models in 2026-10 (over 230 pages at
        # 51/page). A full sequential sweep can take several minutes; quiet output
        # during pagination is not by itself evidence that the scraper is stuck.
        while api_pages < max_pages and clicks < max_clicks:
            if response_task.done():
                await collect_response(response_task.result())
                response_task = asyncio.create_task(response_queue.get())
                continue

            next_btn = page.locator('button:has-text("Next")')
            try:
                await next_btn.wait_for(timeout=5000)
            except PlaywrightTimeoutError:
                print("  No Next button.")
                break
            if await next_btn.is_disabled():
                print("  Next disabled — last page.")
                break

            previous_state = await ui_state()
            ui_task = asyncio.create_task(wait_for_ui_advance(previous_state))
            await next_btn.click()
            clicks += 1
            done, _ = await asyncio.wait(
                (response_task, ui_task), timeout=16,
                return_when=asyncio.FIRST_COMPLETED,
            )

            progressed = False
            if response_task in done:
                await collect_response(response_task.result())
                response_task = asyncio.create_task(response_queue.get())
                progressed = True
            if ui_task in done:
                try:
                    ui_task.result()
                    progressed = True
                except PlaywrightTimeoutError:
                    pass
            else:
                ui_task.cancel()
                await asyncio.gather(ui_task, return_exceptions=True)

            if not progressed:
                consecutive_stalls += 1
                print(
                    f"  No API or UI progress after click {clicks} "
                    f"({consecutive_stalls}/3 retries)"
                )
                if consecutive_stalls < 3:
                    await asyncio.sleep(1)
                    continue
                raise RuntimeError(
                    "Azure catalog made no API or UI progress after clicking Next; "
                    "refusing partial results"
                )
            consecutive_stalls = 0
    finally:
        page.remove_listener("response", on_response)
        for task in (response_task, ui_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (response_task, ui_task) if task is not None),
            return_exceptions=True,
        )

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
