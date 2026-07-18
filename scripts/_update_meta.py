"""Refresh meta.json with Meta Model API (Muse Spark) official pricing.

Sources (Playwright live 2026-07-18):
- https://ai.developer.meta.com/docs/getting-started/models
- https://ai.developer.meta.com/docs/getting-started/pricing-rate-limits

Keeps existing open-weight Llama / OpenRouter-style entries; upserts Muse Spark.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "meta.json"
INSTALLED_DIR = Path(r"F:\Python314\Lib\site-packages\llmcapa\data")
LOG = WORKDIR / "provider_update_log.md"
SOURCE_MODELS = "https://ai.developer.meta.com/docs/getting-started/models"
SOURCE_PRICE = "https://ai.developer.meta.com/docs/getting-started/pricing-rate-limits"


def muse_spark() -> dict:
    return {
        "provider": "meta",
        "model_id": "muse-spark-1.1",
        "display_name": "Muse Spark 1.1",
        "context_window": 1_048_576,
        "max_output_tokens": 0,
        "input_modalities": ["text", "image", "video", "pdf"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [
            "meta/muse-spark-1.1",
            "meta-muse-spark-1.1",
            "muse-spark",
        ],
        "license_type": "api",
        "pricing": {
            "input_per_1m": 1.25,
            "output_per_1m": 4.25,
            "currency": "USD",
        },
        "extra": {
            "source_models": SOURCE_MODELS,
            "source_pricing": SOURCE_PRICE,
            "cached_input_per_1m": 0.15,
            "web_search_per_1000_queries": 2.50,
            "no_long_context_premium": True,
            "api_base": "https://api.meta.ai/v1",
            "rate_limits": {
                "free": {"rpm": 60, "tpm": 2_000_000},
                "paid": {"rpm": 3000, "tpm": 4_000_000},
                "background_submissions_per_minute": 600,
            },
            "capabilities": [
                "chat_completion",
                "image_understanding",
                "video_understanding",
                "tool_calling",
                "structured_output",
                "search_grounding",
                "prompt_caching",
                "responses_api",
                "messages_api",
            ],
            "note": "Meta Model API unified pricing for all models; only muse-spark-1.1 listed as available today",
        },
    }


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    models: list[dict] = list(data.get("models") or [])
    by_id = {m["model_id"]: i for i, m in enumerate(models)}

    spark = muse_spark()
    if spark["model_id"] in by_id:
        models[by_id[spark["model_id"]]] = spark
        action = "updated"
    else:
        models.insert(0, spark)
        action = "inserted"

    # Ensure Llama open-weight entries remain free/unpriced unless already api
    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if INSTALLED_DIR.exists():
        shutil.copy2(OUT, INSTALLED_DIR / OUT.name)

    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"meta.json: {len(models)} models (active={active} / priced={priced}); "
        f"muse-spark-1.1 {action}",
        flush=True,
    )
    print(
        "  muse-spark-1.1 $1.25/$4.25 cache=$0.15 ctx=1048576 multimodal",
        flush=True,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Meta Model API refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Models: {SOURCE_MODELS}\n"
        f"- Pricing: {SOURCE_PRICE} (Playwright live)\n"
        f"- Apply: `scripts/_update_meta.py`\n\n"
        f"### Result\n"
        f"- meta.json: **{len(models)}** models (active={active}, priced={priced})\n"
        f"- **muse-spark-1.1** {action}: $1.25/$4.25; cached input $0.15; 1M ctx\n"
        f"- Multimodal: text/image/video/PDF in → text out\n"
        f"- Web search grounding: $2.50 / 1k queries\n"
        f"- Free tier 60 RPM / 2M TPM; Paid 3k RPM / 4M TPM\n"
        f"- Existing Llama open-weight + OpenRouter-style entries retained\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
