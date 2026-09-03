"""Refresh the Meta/Llama catalog using a Playwright-backed official check.

Meta's developer pages are JavaScript applications. Playwright is therefore used
for the official-site check (including the rendered document and API response),
then the shared live provider feed supplies the normalized catalog when Meta's
API does not expose an authenticated machine-readable catalog.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts" / "openrouter_providers") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "openrouter_providers"))

from _common import update_provider

LOG = ROOT / "provider_update_log.md"
DATA = ROOT / "src" / "llmcapa" / "data" / "meta.json"
OFFICIAL_HOME = "https://dev.meta.ai/"
OFFICIAL_DOCS = "https://dev.meta.ai/docs/getting-started/models"
OFFICIAL_MODELS = "https://api.meta.ai/v1/models"


def _visit(page, url: str, *, wait_for_body: bool = False):
    """Navigate with Playwright and return the response and rendered text."""
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        response = None
    try:
        if wait_for_body:
            page.locator("body").wait_for(state="visible", timeout=10_000)
        # Allow client-side documentation content to settle without sleeping blindly.
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        pass
    try:
        text = page.locator("body").inner_text(timeout=5_000)
    except PlaywrightTimeoutError:
        text = ""
    return response, text


def official_meta_status() -> str:
    """Check the official Meta pages/API through a real browser context."""
    api_key = os.getenv("META_API_KEY") or os.getenv("LLAMA_API_KEY") or ""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="llmcapa-provider-updater/1.0",
            extra_http_headers={"Accept": "application/json,text/html"},
        )
        page = context.new_page()
        home_response, _ = _visit(page, OFFICIAL_HOME, wait_for_body=True)
        docs_response, docs_text = _visit(page, OFFICIAL_DOCS, wait_for_body=True)

        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        api_response = context.request.get(
            OFFICIAL_MODELS, headers=headers, timeout=30_000
        )
        api_status = api_response.status
        api_body = api_response.text() if api_status == 200 else ""
        browser.close()

    docs_lower = docs_text.lower()
    docs_client_rendered = not any(
        marker in docs_lower
        for marker in ("model_id", '"models"', "input_per_1m", "pricing")
    )
    if api_status == 200 and api_body:
        api_note = "official model endpoint reachable"
    elif api_status in (401, 403):
        api_note = "official model endpoint requires authentication"
    else:
        api_note = f"official model endpoint status={api_status}"
    docs_note = (
        "client-rendered"
        if docs_client_rendered
        else "machine-readable content detected"
    )
    return (
        f"official dev.meta.ai checked with Playwright "
        f"(home={home_response.status if home_response else 'unreachable'}, "
        f"docs={docs_response.status if docs_response else 'unreachable'}, "
        f"docs={docs_note}; {api_note})"
    )


def main() -> int:
    official_status = official_meta_status()
    result = update_provider("meta-llama", "meta.json")
    if result != 0:
        return result

    data = json.loads(DATA.read_text(encoding="utf-8"))
    models = data.get("models", [])
    active = sum(not m.get("deprecated", False) for m in models)
    priced = sum(
        (m.get("pricing") or {}).get("input_per_1m") is not None for m in models
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Meta/Llama catalog refresh ({stamp})\n\n"
        "### Source\n"
        f"- {official_status}\n"
        "- OpenRouter live provider API fallback (`meta-llama`)\n"
        "- Apply: `scripts/_update_meta.py`\n\n"
        "### Result\n"
        f"- meta.json: **{len(models)}** models (active={active}, priced={priced})\n"
        "- Model IDs, capabilities, context windows, and pricing obtained from the live feed\n"
        "- Existing deprecated records retained\n"
    )
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
