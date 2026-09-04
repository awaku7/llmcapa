"""Refresh meta.json from Meta's official developer documentation.

Sources (Playwright live):
- Models: https://dev.meta.ai/docs/getting-started/models
- Pricing: https://dev.meta.ai/docs/pricing-rate-limits
- Top: https://dev.meta.ai/ (model lineup)
- Glimmer: https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model

This catalog covers Meta's own Model API (Muse family) only and never reads
OpenRouter. Llama weight distribution (Hugging Face etc.) and Azure-hosted
Llama records belong to other catalogs, not here.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "provider_update_log.md"
DATA = ROOT / "src" / "llmcapa" / "data" / "meta.json"
OFFICIAL_HOME = "https://dev.meta.ai/"
OFFICIAL_MODELS = "https://dev.meta.ai/docs/getting-started/models"
OFFICIAL_PRICING = "https://dev.meta.ai/docs/pricing-rate-limits"
OFFICIAL_GLIMMER = (
    "https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model"
)

# Official Standard / Contributor token pricing (USD / 1M tokens).
# Source: OFFICIAL_PRICING.
STANDARD = {"input": 1.25, "output": 4.25, "cached_input": 0.15}
CONTRIBUTOR = {"input": 0.10, "output": 0.20, "cached_input": 0.002}

BASE_URL = "https://api.meta.ai/v1"


def _visit(page, url: str):
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        response = None
    try:
        page.locator("body").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        pass
    try:
        text = page.locator("body").inner_text(timeout=8_000)
    except PlaywrightTimeoutError:
        text = ""
    return (response.status if response else None), text


def parse_pricing(text: str) -> dict:
    """Extract Standard / Contributor / Voice / Image pricing from the page."""
    out: dict = {}
    std = re.search(
        r"Standard pricing.*?Cached input \| \$([0-9.]+).*?Input \| \$([0-9.]+).*?Output \| \$([0-9.]+)",
        text,
        re.DOTALL,
    )
    if std:
        out["standard"] = {
            "cached_input": float(std.group(1)),
            "input": float(std.group(2)),
            "output": float(std.group(3)),
        }
    con = re.search(
        r"Contributor tier.*?Cached input \| \$([0-9.]+).*?Input \| \$([0-9.]+).*?Output \| \$([0-9.]+)",
        text,
        re.DOTALL,
    )
    if con:
        out["contributor"] = {
            "cached_input": float(con.group(1)),
            "input": float(con.group(2)),
            "output": float(con.group(3)),
        }
    voice = re.search(r"Audio processed \| \$([0-9.]+) per hour", text)
    if voice:
        out["voice_per_hour"] = float(voice.group(1))
    image = re.search(
        r"billed at a flat \$([0-9.]+) per generated image", text
    )
    if image:
        out["image_per_image"] = float(image.group(1))
    return out


def parse_models_page(text: str) -> dict:
    """Extract the Available-models table from the official models page."""
    out: dict = {}
    # e.g. "muse-spark-1.1 | Text, image, video, PDF | Text | 1,048,576 tokens"
    for m in re.finditer(
        r"(muse-[\w.\-]+)\s*\|\s*([^|]+?)\|\s*([^|]+?)\|\s*([\d,]+)\s*tokens",
        text,
    ):
        mid, inp, outp, ctx = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
        )
        out[mid] = {
            "input": inp.strip(),
            "output": outp.strip(),
            "context": int(ctx.replace(",", "")),
        }
    return out


def spark_row(*, model_id: str, display: str, tier: str, table: dict) -> dict:
    pricing = STANDARD if tier == "standard" else CONTRIBUTOR
    row = {
        "provider": "meta",
        "model_id": model_id,
        "display_name": display,
        "context_window": table.get("context", 1_048_576),
        "max_output_tokens": 0,
        "input_modalities": ["text", "image", "video", "file", "audio"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "supports_reasoning_effort": True,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "license_type": "api",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": {
            "input_per_1m": pricing["input"],
            "output_per_1m": pricing["output"],
            "currency": "USD",
        },
        "deprecated": False,
        "aliases": [],
        "supports_realtime": False,
        "supports_json_schema": True,
        "extra": {
            "source": OFFICIAL_PRICING,
            "models_page": OFFICIAL_MODELS,
            "tier": tier,
            "cached_input_per_1m": pricing["cached_input"],
            "endpoints": [
                {
                    "base_url": BASE_URL,
                    "protocol": "openai-compatible",
                    "auth": "bearer",
                    "source": OFFICIAL_MODELS,
                }
            ],
        },
    }
    return row


def build() -> tuple[list[dict], dict]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent="llmcapa-provider-updater/1.0")
        page = context.new_page()
        home_status, home_text = _visit(page, OFFICIAL_HOME)
        models_status, models_text = _visit(page, OFFICIAL_MODELS)
        pricing_status, pricing_text = _visit(page, OFFICIAL_PRICING)
        _, glimmer_text = _visit(page, OFFICIAL_GLIMMER)
        browser.close()

    if models_status != 200 or "Available models" not in models_text:
        raise RuntimeError("official Meta models page did not render")
    if pricing_status != 200 or "Price per 1M tokens" not in pricing_text:
        raise RuntimeError("official Meta pricing page did not render")

    table = parse_models_page(models_text)
    prices = parse_pricing(pricing_text)
    std = prices.get("standard", STANDARD)
    con = prices.get("contributor", CONTRIBUTOR)

    models: list[dict] = []
    specs = [
        ("muse-spark-1.3", "Meta: Muse Spark 1.3", "standard"),
        ("muse-spark-1.2", "Meta: Muse Spark 1.2", "standard"),
        ("muse-spark-1.1", "Meta: Muse Spark 1.1", "standard"),
        ("muse-spark-1.3-contributor", "Meta: Muse Spark 1.3 Contributor", "contributor"),
        ("muse-spark-1.2-contributor", "Meta: Muse Spark 1.2 Contributor", "contributor"),
    ]
    for mid, display, tier in specs:
        row = spark_row(model_id=mid, display=display, tier=tier, table=table.get(mid, {}))
        # Refresh pricing from the live page (falls back to constants above).
        live = std if tier == "standard" else con
        row["pricing"] = {
            "input_per_1m": live["input"],
            "output_per_1m": live["output"],
            "currency": "USD",
        }
        row["extra"]["cached_input_per_1m"] = live["cached_input"]
        models.append(row)

    # Muse Glimmer 30B: Apache 2.0 open weights for local agents (no API pricing).
    glimmer = {
        "provider": "meta",
        "model_id": "muse-glimmer-30b",
        "display_name": "Meta: Muse Glimmer 30B",
        "context_window": 131072,
        "max_output_tokens": 0,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "license_type": "open",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [],
        "supports_realtime": False,
        "supports_json_schema": True,
        "extra": {
            "source": OFFICIAL_GLIMMER,
            "license": "Apache 2.0",
            "params": "30B",
            "distribution": "open weights (Hugging Face) for local agents",
            "note": "no Meta API token pricing; third-party hosted prices vary",
        },
    }
    models.append(glimmer)

    # Muse Voice Transcribe: billed per audio hour, not per token.
    voice_per_hour = prices.get("voice_per_hour", 0.18)
    models.append(
        {
            "provider": "meta",
            "model_id": "muse-voice-transcribe",
            "display_name": "Meta: Muse Voice Transcribe",
            "context_window": 0,
            "max_output_tokens": 0,
            "input_modalities": ["audio", "speech"],
            "output_modalities": ["text"],
            "supports_function_calling": False,
            "supports_json_mode": False,
            "supports_streaming": True,
            "supports_vision": False,
            "supports_reasoning": False,
            "supports_chat_completion": False,
            "supports_responses_api": False,
            "supports_reasoning_effort": False,
            "supports_thinking_budget": False,
            "supports_anthropic_api": False,
            "supports_google_api": False,
            "supports_fim": False,
            "license_type": "api",
            "tokenizer_name": "",
            "knowledge_cutoff": None,
            "deprecated": False,
            "aliases": [],
            "supports_realtime": False,
            "extra": {
                "source": OFFICIAL_PRICING,
                "price_per_hour": voice_per_hour,
                "unit": "hour",
                "unit_detail": "minutes of audio processed",
                "endpoints": [
                    {
                        "base_url": BASE_URL,
                        "protocol": "openai-compatible",
                        "auth": "bearer",
                        "source": OFFICIAL_MODELS,
                    }
                ],
            },
        }
    )

    # Muse Image: billed per generated image, not per token.
    image_per_image = prices.get("image_per_image", 0.01)
    models.append(
        {
            "provider": "meta",
            "model_id": "muse-image-1.0",
            "display_name": "Meta: Muse Image 1.0",
            "context_window": 0,
            "max_output_tokens": 0,
            "input_modalities": ["text", "image"],
            "output_modalities": ["image"],
            "supports_function_calling": False,
            "supports_json_mode": False,
            "supports_streaming": False,
            "supports_vision": True,
            "supports_reasoning": True,
            "supports_chat_completion": False,
            "supports_responses_api": False,
            "supports_reasoning_effort": False,
            "supports_thinking_budget": False,
            "supports_anthropic_api": False,
            "supports_google_api": False,
            "supports_fim": False,
            "license_type": "api",
            "tokenizer_name": "",
            "knowledge_cutoff": None,
            "deprecated": False,
            "aliases": [],
            "supports_realtime": False,
            "extra": {
                "source": OFFICIAL_PRICING,
                "price_per_image": image_per_image,
                "unit": "image",
                "endpoints": [
                    {
                        "base_url": BASE_URL,
                        "protocol": "openai-compatible",
                        "auth": "bearer",
                        "source": OFFICIAL_MODELS,
                    }
                ],
            },
        }
    )

    meta = {
        "home_status": home_status,
        "models_status": models_status,
        "pricing_status": pricing_status,
        "table_entries": len(table),
        "glimmer_text_len": len(glimmer_text),
        "home_has_spark_13": "Muse Spark 1.3" in home_text,
    }
    return models, meta


def main() -> int:
    models, meta = build()
    models.sort(key=lambda m: m.get("model_id", ""))
    DATA.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(
        1 for m in models if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Meta Model API refresh ({stamp})\n\n"
        "### Source\n"
        f"- Models: {OFFICIAL_MODELS} (status={meta['models_status']}, table={meta['table_entries']})\n"
        f"- Pricing: {OFFICIAL_PRICING} (status={meta['pricing_status']})\n"
        f"- Top: {OFFICIAL_HOME} (status={meta['home_status']}, spark-1.3={meta['home_has_spark_13']})\n"
        f"- Glimmer: {OFFICIAL_GLIMMER} (text_len={meta['glimmer_text_len']})\n"
        "- Apply: `scripts/_update_meta.py`\n"
        "- OpenRouter was not used.\n\n"
        "### Result\n"
        f"- meta.json: **{len(models)}** models (active={active}, token-priced={priced})\n"
        "- Spark Standard $1.25/$4.25 + cached $0.15; Contributor $0.10/$0.20 + cached $0.002\n"
        "- Glimmer 30B recorded as Apache 2.0 open weights (no API pricing)\n"
        "- Voice Transcribe ($/hour) and Image 1.0 ($/image) recorded as specialty units\n"
    )
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    print(
        f"meta.json: {len(models)} models (active={active}, token-priced={priced})",
        flush=True,
    )
    for m in models:
        p = m.get("pricing") or {}
        print(
            f"  {m['model_id']:32} ctx={m['context_window']} "
            f"price={p.get('input_per_1m')}/{p.get('output_per_1m')}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
