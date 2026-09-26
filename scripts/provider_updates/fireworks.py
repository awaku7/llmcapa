"""Refresh Fireworks' native catalog from its public rendered model library.

The source page exposes structured model-card links and visible metadata. This
scraper deliberately reads those cards instead of regex-scanning all page text,
which previously captured UI labels and JavaScript property names as model IDs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/fireworks.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://fireworks.ai/models"
BASE_URL = "https://api.fireworks.ai/inference/v1"
ENDPOINT_SOURCE = "https://docs.fireworks.ai/"

CATEGORIES = {
    "llm", "vision", "embeddings", "reranks", "image generation",
    "video generation", "speech", "audio", "transcription",
}


def context_tokens(text: str) -> int:
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*([kKmM]?)\s+Context\b", text)
    if not match:
        return 0
    value = float(match.group(1).replace(",", ""))
    suffix = match.group(2).lower()
    return int(value * (1_000 if suffix == "k" else 1_000_000 if suffix == "m" else 1))


def parse_model_cards(cards: list[dict]) -> list[dict]:
    rows: dict[str, dict] = {}
    for card in cards:
        path = urlparse(str(card.get("href") or "")).path.strip("/").split("/")
        if len(path) != 3 or path[:2] != ["models", "fireworks"]:
            continue
        model_id = unquote(path[2]).strip()
        if not model_id or model_id.lower() in {"models", "fireworks"}:
            continue

        text = str(card.get("text") or "")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        category = next((line.lower() for line in reversed(lines) if line.lower() in CATEGORIES), "")
        display = next(
            (
                line for line in lines
                if line.lower() != "new"
                and line.lower() not in CATEGORIES
                and not re.search(r"\$|\bContext\b|\b/M\s+(?:Input|Output|Tokens)", line, re.I)
            ),
            model_id,
        )

        input_modalities = ["text"]
        output_modalities = ["text"]
        chat: bool | None = None
        supports_vision: bool | None = None
        if category in {"llm", "vision"}:
            chat = True
        if category == "vision":
            input_modalities = ["text", "image"]
            supports_vision = True
        elif category == "embeddings":
            output_modalities = ["embedding"]
            chat = False
        elif category == "reranks":
            output_modalities = ["rerank"]
            chat = False
        elif category == "image generation":
            output_modalities = ["image"]
            chat = False
        elif category == "video generation":
            output_modalities = ["video"]
            chat = False
        elif category in {"speech", "audio", "transcription"}:
            input_modalities = ["audio"]
            output_modalities = ["text"] if category == "transcription" else ["audio"]
            chat = False

        input_price = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*/M\s*Input\b", text, re.I)
        cached_price = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*/M\s*Cached\s*Input\b", text, re.I)
        output_price = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*/M\s*Output\b", text, re.I)
        token_price = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*/M\s*Tokens\b", text, re.I)
        pricing = None
        if input_price and output_price:
            pricing = {
                "input_per_1m": float(input_price.group(1)),
                "output_per_1m": float(output_price.group(1)),
                "currency": "USD",
            }
        elif token_price and category in {"embeddings", "reranks"}:
            pricing = {
                "input_per_1m": float(token_price.group(1)),
                "output_per_1m": 0.0,
                "currency": "USD",
            }

        extra = {
            "source": SOURCE,
            "source_type": "official_rendered_model_card",
            "model_path": f"accounts/fireworks/models/{model_id}",
        }
        if category:
            extra["catalog_category"] = category
        if cached_price:
            extra["cached_input_per_1m"] = float(cached_price.group(1))

        row = {
            "provider": "fireworks",
            "model_id": model_id,
            "display_name": display,
            "context_window": context_tokens(text),
            "max_output_tokens": 0,
            "input_modalities": input_modalities,
            "output_modalities": output_modalities,
            "supports_chat_completion": chat,
            "supports_function_calling": None,
            "supports_json_mode": None,
            "supports_streaming": None,
            "supports_vision": supports_vision,
            "supports_reasoning": None,
            "supports_responses_api": None,
            "pricing": pricing,
            "deprecated": False,
            "aliases": [f"accounts/fireworks/models/{model_id}"],
            "license_type": "api",
            "extra": extra,
        }
        rows[model_id.lower()] = row
    if not rows:
        raise RuntimeError("official Fireworks model-card links were not found")
    return list(rows.values())


def fetch_catalog() -> list[dict]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SOURCE, wait_until="domcontentloaded", timeout=90_000)
        page.locator('a[href^="/models/fireworks/"]').first.wait_for(timeout=30_000)
        cards = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href^=\"/models/fireworks/\"]'))
                .map(a => ({href: a.href, text: (a.innerText || '').trim()}))"""
        )
        browser.close()
    return parse_model_cards(cards)


def _merge_existing(fresh: list[dict], previous: list[dict]) -> list[dict]:
    old = {str(model.get("model_id", "")).lower(): model for model in previous}
    merged = []
    for row in fresh:
        prior = old.get(row["model_id"].lower())
        if prior:
            result = dict(prior)
            for key, value in row.items():
                if key == "extra":
                    result["extra"] = {**(result.get("extra") or {}), **value}
                elif key == "pricing" and value is None:
                    continue
                elif key in {"context_window", "max_output_tokens"} and not value:
                    continue
                elif key.startswith("supports_") and value is None:
                    continue
                else:
                    result[key] = value
            row = result
        merged.append(row)
    return merged


def update_catalog() -> list[dict]:
    previous = json.loads(DATA.read_text(encoding="utf-8")).get("models", [])
    models = _merge_existing(fetch_catalog(), previous)
    DATA.write_text(json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Fireworks official catalog refresh ({datetime.now(timezone.utc).date()})\n\n"
        + f"- Source: {SOURCE}\n- Structured model cards: {len(models)}\n- Model specs/pricing only from card fields; unknown values left unset.\n",
        encoding="utf-8",
    )
    print(f"fireworks.json: {len(models)} official model cards")
    return models


def update_endpoints() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for model in data.get("models", []):
        extra = model.setdefault("extra", {})
        extra["endpoints"] = [
            {
                "base_url": BASE_URL,
                "protocol": "openai-compatible",
                "auth": "bearer",
                "source": ENDPOINT_SOURCE,
            }
        ]
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    update_catalog()
    update_endpoints()


if __name__ == "__main__":
    main()
