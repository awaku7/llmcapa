"""Build/refresh minimax.json from official MiniMax PayGO + Chat Completions docs.

Sources (Playwright 2026-07-18):
- https://platform.minimax.io/docs/guides/models-intro
- https://platform.minimax.io/docs/guides/pricing-paygo
- https://platform.minimax.io/docs/api-reference/text-chat
Shape: Capability JSON with pricing + extra (cache / long-ctx / specialty units)
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts._scrape_minimax import fetch_minimax_catalog
except ModuleNotFoundError:  # Direct execution: python scripts/_update_minimax.py
    from _scrape_minimax import fetch_minimax_catalog

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "minimax.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "minimax.json"
)
LOG = WORKDIR / "provider_update_log.md"
SOURCE_PRICING = "https://platform.minimax.io/docs/guides/pricing-paygo"
SOURCE_MODELS = "https://platform.minimax.io/docs/guides/models-intro"
SOURCE_CHAT = "https://platform.minimax.io/docs/api-reference/text-chat"

# Official Chat Completions model enum (docs) + PayGO pricing
# M3 permanent 50% off applied as list effective price for ≤512k tier.
TEXT_MODELS = [
    {
        "model_id": "MiniMax-M3",
        "display_name": "MiniMax M3",
        "context_window": 1_000_000,
        "max_output_tokens": 524_288,
        "input_modalities": ["text", "image", "video"],
        "output_modalities": ["text"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "supports_thinking_budget": False,
        "thinking_control": {
            "kind": "toggle",
            "parameter": "thinking",
            "values": ["enabled", "disabled"],
            "encoding": {
                "enabled": {"type": "enabled"},
                "disabled": {"type": "disabled"},
            },
        },
        "pricing": {"input_per_1m": 0.30, "output_per_1m": 1.20, "currency": "USD"},
        "aliases": ["minimax-m3", "MiniMax-M3"],
        "extra": {
            "source": SOURCE_PRICING,
            "pricing_note": "permanent 50% off ≤512k (list $0.60/$2.40); >512k $0.60/$2.40",
            "cache_read_per_1m": 0.06,
            "long_context_threshold": 512_000,
            "long_context_input_per_1m": 0.60,
            "long_context_output_per_1m": 2.40,
            "priority_tier_multiplier": 1.5,
            "recommended_max_completion_tokens": 131_072,
            "features": [
                "image_understanding",
                "video_understanding",
                "adaptive_thinking",
            ],
        },
    },
    {
        "model_id": "MiniMax-M2.7",
        "display_name": "MiniMax M2.7",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "pricing": {"input_per_1m": 0.30, "output_per_1m": 1.20, "currency": "USD"},
        "aliases": ["minimax-m2.7"],
        "extra": {
            "source": SOURCE_PRICING,
            "cache_read_per_1m": 0.06,
            "cache_write_per_1m": 0.375,
        },
    },
    {
        "model_id": "MiniMax-M2.7-highspeed",
        "display_name": "MiniMax M2.7 Highspeed",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "pricing": {"input_per_1m": 0.60, "output_per_1m": 2.40, "currency": "USD"},
        "aliases": ["minimax-m2.7-highspeed"],
        "extra": {"source": SOURCE_PRICING, "tier": "highspeed"},
    },
    {
        "model_id": "MiniMax-M2.5",
        "display_name": "MiniMax M2.5",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "pricing": {"input_per_1m": 0.30, "output_per_1m": 1.20, "currency": "USD"},
        "aliases": ["minimax-m2.5"],
        "extra": {"source": SOURCE_PRICING},
    },
    {
        "model_id": "MiniMax-M2.5-highspeed",
        "display_name": "MiniMax M2.5 Highspeed",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "pricing": {"input_per_1m": 0.60, "output_per_1m": 2.40, "currency": "USD"},
        "aliases": ["minimax-m2.5-highspeed"],
        "extra": {"source": SOURCE_PRICING, "tier": "highspeed"},
    },
    {
        "model_id": "MiniMax-M2.1",
        "display_name": "MiniMax M2.1",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "pricing": {"input_per_1m": 0.30, "output_per_1m": 1.20, "currency": "USD"},
        "aliases": ["minimax-m2.1"],
        "extra": {"source": SOURCE_PRICING},
    },
    {
        "model_id": "MiniMax-M2.1-highspeed",
        "display_name": "MiniMax M2.1 Highspeed",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "pricing": {"input_per_1m": 0.60, "output_per_1m": 2.40, "currency": "USD"},
        "aliases": ["minimax-m2.1-highspeed"],
        "extra": {"source": SOURCE_PRICING, "tier": "highspeed"},
    },
    {
        "model_id": "MiniMax-M2",
        "display_name": "MiniMax M2",
        "context_window": 1_000_000,
        "max_output_tokens": 131_072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "pricing": {"input_per_1m": 0.30, "output_per_1m": 1.20, "currency": "USD"},
        "aliases": ["minimax-m2"],
        "extra": {"source": SOURCE_PRICING},
    },
    # Legacy / third-party mirror ids retained for lookup
    {
        "model_id": "minimax-m1",
        "display_name": "MiniMax M1",
        "context_window": 1_000_000,
        "max_output_tokens": 100_000,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "pricing": {"input_per_1m": 0.55, "output_per_1m": 2.20, "currency": "USD"},
        "aliases": [],
        "deprecated": False,
        "extra": {
            "source": SOURCE_PRICING,
            "note": "legacy generation; still listed on some mirrors",
        },
    },
    {
        "model_id": "minimax-01",
        "display_name": "MiniMax-01",
        "context_window": 1_000_192,
        "max_output_tokens": 100_000,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_vision": True,
        "supports_function_calling": True,
        "pricing": {"input_per_1m": 0.20, "output_per_1m": 1.10, "currency": "USD"},
        "aliases": [],
        "extra": {"source": SOURCE_PRICING, "note": "legacy multimodal"},
    },
]

AUDIO_MODELS = [
    {
        "model_id": "speech-2.8-hd",
        "display_name": "Speech 2.8 HD",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["audio"],
        "supports_chat_completion": False,
        "supports_streaming": True,
        "pricing": None,
        "extra": {
            "source": SOURCE_PRICING,
            "price_per_1m_chars": 100.0,
            "unit": "1m_chars",
            "api": "tts",
            "quality": "hd",
        },
    },
    {
        "model_id": "speech-2.8-turbo",
        "display_name": "Speech 2.8 Turbo",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["audio"],
        "supports_chat_completion": False,
        "supports_streaming": True,
        "pricing": None,
        "extra": {
            "source": SOURCE_PRICING,
            "price_per_1m_chars": 60.0,
            "unit": "1m_chars",
            "api": "tts",
            "quality": "turbo",
        },
    },
]

VIDEO_MODELS = [
    {
        "model_id": "Hailuo-2.3",
        "display_name": "Hailuo 2.3",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "supports_chat_completion": False,
        "supports_vision": True,
        "pricing": None,
        "extra": {
            "source": SOURCE_PRICING,
            "price_per_clip_range_usd": [0.28, 0.56],
            "unit": "clip",
            "note": "varies by resolution/duration",
            "api": "video",
        },
    },
    {
        "model_id": "Hailuo-2.3-Fast",
        "display_name": "Hailuo 2.3 Fast",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "supports_chat_completion": False,
        "supports_vision": True,
        "pricing": None,
        "extra": {
            "source": SOURCE_PRICING,
            "unit": "clip",
            "note": "faster/cheaper tier vs Hailuo 2.3",
            "api": "video",
        },
    },
]

MUSIC_MODELS = [
    {
        "model_id": "music-3.0",
        "display_name": "Music 3.0",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["audio"],
        "supports_chat_completion": False,
        "pricing": None,
        "extra": {
            "source": SOURCE_PRICING,
            "price_per_track_usd": 0.15,
            "max_duration_min": 5,
            "unit": "track",
            "api": "music",
        },
    },
]

IMAGE_MODELS = [
    {
        "model_id": "image-01",
        "display_name": "Image-01",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["image"],
        "supports_chat_completion": False,
        "pricing": None,
        "extra": {
            "source": SOURCE_PRICING,
            "price_per_image": 0.0035,
            "unit": "image",
            "api": "image",
        },
    },
]


def base_capability(**kwargs) -> dict:
    d = {
        "provider": "minimax",
        "model_id": "",
        "display_name": "",
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "license_type": "api",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": None,
        "deprecated": False,
        "aliases": [],
        "reasoning_effort_values": None,
        "thinking_budget_values": None,
        "thinking_level_values": None,
        "thinking_control": None,
        "extra": {},
    }
    d.update(kwargs)
    # vision flag from modalities
    if "image" in d.get("input_modalities", []) or "video" in d.get(
        "input_modalities", []
    ):
        d["supports_vision"] = True
    return d


def build_models() -> list[dict]:
    models: list[dict] = []
    for group in (TEXT_MODELS, AUDIO_MODELS, VIDEO_MODELS, MUSIC_MODELS, IMAGE_MODELS):
        for spec in group:
            models.append(base_capability(**spec))

    # stable sort: text first by id, then specialty
    def sort_key(m: dict) -> tuple:
        specialty = (
            0 if m.get("supports_chat_completion", True) and m.get("pricing") else 1
        )
        return (specialty, m["model_id"].lower())

    models.sort(key=sort_key)
    return models


def main() -> None:
    live_catalog = fetch_minimax_catalog()
    known_ids = {spec["model_id"] for spec in TEXT_MODELS}
    live_updates = 0
    for spec in TEXT_MODELS:
        live = live_catalog.get(spec["model_id"])
        if live and "input" in live and "output" in live:
            spec["pricing"] = {
                "input_per_1m": live["input"],
                "output_per_1m": live["output"],
                "currency": "USD",
            }
            live_updates += 1
    for model_id, live in live_catalog.items():
        if model_id in known_ids or "input" not in live or "output" not in live:
            continue
        TEXT_MODELS.append(
            {
                "model_id": model_id,
                "display_name": model_id,
                "context_window": 0,
                "max_output_tokens": 0,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supports_function_calling": True,
                "supports_json_mode": True,
                "supports_reasoning": "thinking" in model_id.lower(),
                "pricing": {
                    "input_per_1m": live["input"],
                    "output_per_1m": live["output"],
                    "currency": "USD",
                },
                "aliases": [],
                "extra": {"source": SOURCE_PRICING, "pricing_fetched": True},
            }
        )
        live_updates += 1

    for spec in AUDIO_MODELS + VIDEO_MODELS + MUSIC_MODELS + IMAGE_MODELS:
        live = live_catalog.get(spec["model_id"])
        if not live or "specialty_price" not in live:
            continue
        extra = spec.setdefault("extra", {})
        if "price_per_1m_chars" in extra:
            extra["price_per_1m_chars"] = live["specialty_price"]
        elif "price_per_image" in extra:
            extra["price_per_image"] = live["specialty_price"]
        elif "price_per_track_usd" in extra:
            extra["price_per_track_usd"] = live["specialty_price"]
        elif "price_per_clip_range_usd" in extra:
            extra["price_per_clip_range_usd"] = [
                min(live.get("specialty_prices", [live["specialty_price"]])),
                max(live.get("specialty_prices", [live["specialty_price"]])),
            ]
        live_updates += 1

    models = build_models()
    payload = {"models": models}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if INSTALLED.parent.exists() and OUT.resolve() != INSTALLED.resolve():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(1 for m in models if m.get("pricing"))
    print(
        f"minimax.json: {len(models)} models "
        f"(active={active}, deprecated={len(models)-active}, token-priced={priced})",
        flush=True,
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"""
## MiniMax refresh ({ts})

### Source
- Models: {SOURCE_MODELS}
- PayGO: {SOURCE_PRICING}
- Chat enum: {SOURCE_CHAT}
- Apply: `scripts/_update_minimax.py`

### Result
- minimax.json: **{len(models)}** models (active={active}, token-priced={priced})
- Official MiniMax pricing rows applied to {live_updates} text models
- New official token-priced model IDs are added with generic metadata
- Specialty model metadata remains static until corresponding tables are parsed
"""
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry.lstrip(), encoding="utf-8")


if __name__ == "__main__":
    main()
