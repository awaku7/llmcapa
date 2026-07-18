"""Scrape official model docs for major providers via Playwright. Saves raw text + structured hints."""
from __future__ import annotations
import json, re, traceback
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "_scratch_provider_scrape_latest.json"

TARGETS = [
    {
        "provider": "openai",
        "pages": [
            ("models", "https://platform.openai.com/docs/models"),
            ("pricing", "https://platform.openai.com/docs/pricing"),
            ("models_alt", "https://developers.openai.com/api/docs/models"),
        ],
    },
    {
        "provider": "anthropic",
        "pages": [
            ("models", "https://platform.claude.com/docs/en/about-claude/models/overview"),
            ("pricing", "https://platform.claude.com/docs/en/about-claude/pricing"),
            ("models_docs", "https://docs.anthropic.com/en/docs/about-claude/models"),
        ],
    },
    {
        "provider": "google",
        "pages": [
            ("models", "https://ai.google.dev/gemini-api/docs/models"),
            ("pricing", "https://ai.google.dev/gemini-api/docs/pricing"),
        ],
    },
    {
        "provider": "xai",
        "pages": [
            ("models", "https://docs.x.ai/docs/models"),
            ("console", "https://console.x.ai/"),
        ],
    },
    {
        "provider": "deepseek",
        "pages": [
            ("pricing", "https://api-docs.deepseek.com/quick_start/pricing"),
            ("models", "https://api-docs.deepseek.com/quick_start/pricing"),
        ],
    },
    {
        "provider": "moonshot",
        "pages": [
            ("models", "https://platform.moonshot.ai/docs/pricing/chat"),
            ("pricing", "https://platform.moonshot.ai/docs/pricing"),
        ],
    },
    {
        "provider": "minimax",
        "pages": [
            ("models", "https://platform.minimax.io/docs/guides/models-intro"),
            ("pricing", "https://platform.minimax.io/docs/pricing"),
        ],
    },
    {
        "provider": "qwen",
        "pages": [
            ("models", "https://www.alibabacloud.com/help/en/model-studio/models"),
            ("dashscope", "https://help.aliyun.com/zh/model-studio/models"),
        ],
    },
]


def scrape_page(page, url: str, wait_ms: int = 4000) -> dict:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)
        # scroll to load lazy content
        for _ in range(4):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)
        text = page.inner_text("body")
        title = page.title()
        # collect links that look like model pages
        links = page.eval_on_selector_all(
            "a[href]",
            """els => els.map(e => ({href: e.href, text: (e.innerText||'').trim().slice(0,120)}))
               .filter(x => x.href && x.text)
               .slice(0, 400)""",
        )
        # tables text
        tables = page.eval_on_selector_all(
            "table",
            """els => els.slice(0, 20).map(t => (t.innerText||'').slice(0, 8000))""",
        )
        return {
            "ok": True,
            "url": url,
            "title": title,
            "text_len": len(text),
            "text": text[:50000],
            "links": links[:200],
            "tables": tables,
        }
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e), "traceback": traceback.format_exc()[:2000]}


def main() -> None:
    result = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "providers": {},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1100},
            locale="en-US",
        )
        page = context.new_page()
        for t in TARGETS:
            prov = t["provider"]
            print(f"=== {prov} ===", flush=True)
            pages = {}
            for key, url in t["pages"]:
                print(f"  goto {key}: {url}", flush=True)
                pages[key] = scrape_page(page, url)
                print(
                    f"    ok={pages[key].get('ok')} len={pages[key].get('text_len')} "
                    f"err={pages[key].get('error')}",
                    flush=True,
                )
            result["providers"][prov] = pages
        browser.close()

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}", flush=True)
    # summary
    for prov, pages in result["providers"].items():
        for k, v in pages.items():
            print(f"SUMMARY {prov}/{k}: ok={v.get('ok')} len={v.get('text_len')} title={v.get('title')}", flush=True)


if __name__ == "__main__":
    main()
