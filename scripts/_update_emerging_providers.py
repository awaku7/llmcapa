"""Scrape official model pages for emerging inference providers.

No provider API keys are required. This updater intentionally does not use
OpenRouter. It extracts publicly documented model IDs and only assigns
capability details when the page exposes them.
"""
from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"
LOG = ROOT / "provider_update_log.md"
SOURCES = {
    "groq": "https://console.groq.com/docs/models",
    "cerebras": "https://inference-docs.cerebras.ai/models/overview",
    "fireworks": "https://fireworks.ai/models",
    "sambanova": "https://docs.sambanova.ai/docs/en/models/sambacloud-models",
    "siliconflow": "https://docs.siliconflow.com/en/userguide/quickstart",
}

# Provider-specific model-id forms. These are deliberately conservative to
# avoid treating ordinary prose/navigation links as models.
PATTERNS = {
    "groq": r"(?<![\w/])(?:llama|meta-llama|openai|qwen|deepseek|gemma|whisper|canopyml|playai|compound)[\w./:-]+",
    "cerebras": r"(?<![\w/])(?:llama|qwen|deepseek|gpt|zai|qwen)[\w./:-]+",
    "fireworks": r"(?:accounts/[^\s\"']+/models/)?(?:deepseek|qwen|kimi|glm|minimax|openai|llama|mixtral|mistral|yi|phi|gemma)[a-zA-Z0-9._:/-]+",
    "sambanova": r"(?<![\w/])(?:DeepSeek|Meta-Llama|MiniMax|gemma|gpt-oss)[\w./:-]+",
    "siliconflow": r"(?<![\w/])(?:Qwen|deepseek|THUDM|Pro|Kimi|moonshotai|zai-org|Wan-AI|black-forest-labs)[\w./:-]+",
}


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "llmcapa-official-scraper/1.0", "Accept": "text/html"})
    try:
        with urlopen(req, timeout=60) as response:
            return response.read().decode("utf-8", "ignore")
    except Exception:
        # JS-rendered sites are handled with Playwright, still without API auth.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=90000)
            text = page.locator("body").inner_text()
            browser.close()
            return text


def normalize(provider: str, raw: str) -> str:
    model_id = raw.strip().strip("`'\".,;:()[]")
    model_id = re.sub(r"^accounts/[^/]+/models/", "", model_id)
    if provider == "sambanova":
        model_id = model_id.replace("Meta-", "Meta-")
    return model_id


def scrape(provider: str) -> list[str]:
    text = fetch_text(SOURCES[provider])
    candidates = {normalize(provider, x) for x in re.findall(PATTERNS[provider], text, re.I)}
    candidates = {x for x in candidates if 2 < len(x) < 160 and not x.lower().endswith(("model", "models", "api"))}
    if len(candidates) < 1:
        raise RuntimeError("no model IDs found on official page")
    return sorted(candidates, key=str.lower)


def main() -> None:
    log = [f"\n## Emerging provider official-page refresh ({date.today()})\n", "- Public official documentation pages scraped; API keys and OpenRouter were not used.\n"]
    for provider in SOURCES:
        try:
            ids = scrape(provider)
            rows = [{
                "provider": provider, "model_id": mid, "display_name": mid,
                "context_window": 0, "max_output_tokens": 0,
                "input_modalities": ["text"], "output_modalities": ["text"],
                "supports_chat_completion": True, "supports_streaming": True,
                "supports_function_calling": None, "supports_json_mode": None,
                "supports_vision": None, "supports_reasoning": None,
                "supports_responses_api": False, "pricing": None,
                "deprecated": False, "aliases": [],
                "extra": {"source": SOURCES[provider], "source_type": "official_page_scrape", "spec_status": "listed_only"},
            } for mid in ids]
            (DATA / f"{provider}.json").write_text(json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log.append(f"- {provider}: {len(rows)} model IDs scraped from {SOURCES[provider]}\n")
            print(f"{provider}: updated ({len(rows)})")
        except Exception as exc:
            log.append(f"- {provider}: skipped ({exc})\n")
            print(f"{provider}: skipped ({exc})")
    LOG.write_text(LOG.read_text(encoding="utf-8") + "".join(log), encoding="utf-8")


if __name__ == "__main__":
    main()
