"""Refresh qwen.json with Alibaba Model Studio International list prices.

Sources (Playwright 2026-07-18):
- https://www.alibabacloud.com/help/en/model-studio/model-pricing
- https://www.alibabacloud.com/help/en/model-studio/models

Adds bare Model Studio IDs (qwen3.7-max etc.) alongside existing OpenRouter-style
`qwen/...` entries. Primary pricing uses official **list** rates; limited-time
promo rates are recorded in extra.
"""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "qwen.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\qwen.json")
LOG = WORKDIR / "provider_update_log.md"
SOURCE = "https://www.alibabacloud.com/help/en/model-studio/model-pricing"

# Official International list prices (USD / 1M tokens), standard tier ≤ threshold
# promo_* = limited-time effective rates when documented
FLAGSHIP_TEXT: dict[str, dict] = {
    "qwen3.7-max": {
        "display_name": "Qwen3.7 Max",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 2.5,
        "output_per_1m": 7.5,
        "promo_input_per_1m": 1.25,
        "promo_output_per_1m": 3.75,
        "promo_note": "limited-time 50% off list",
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "supports_vision": False,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.7-max"],
    },
    "qwen3.7-plus": {
        "display_name": "Qwen3.7 Plus",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 0.4,
        "output_per_1m": 1.6,
        "promo_input_per_1m": 0.32,
        "promo_output_per_1m": 1.28,
        "promo_note": "limited-time 20% off list ≤256k",
        "long_context_threshold": 256_000,
        "long_context_input_per_1m": 1.2,
        "long_context_output_per_1m": 4.8,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.7-plus"],
    },
    "qwen3.6-flash": {
        "display_name": "Qwen3.6 Flash",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 0.25,
        "output_per_1m": 1.5,
        "long_context_threshold": 256_000,
        "long_context_input_per_1m": 1.0,
        "long_context_output_per_1m": 4.0,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.6-flash"],
    },
    "qwen3.6-plus": {
        "display_name": "Qwen3.6 Plus",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 0.5,
        "output_per_1m": 3.0,
        "long_context_threshold": 256_000,
        "long_context_input_per_1m": 2.0,
        "long_context_output_per_1m": 6.0,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.6-plus"],
    },
    "qwen3.6-max-preview": {
        "display_name": "Qwen3.6 Max Preview",
        "context_window": 262_144,
        "max_output_tokens": 65_536,
        "input_per_1m": 1.3,
        "output_per_1m": 7.8,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.6-max-preview"],
    },
    "qwen3.5-flash": {
        "display_name": "Qwen3.5 Flash",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 0.1,
        "output_per_1m": 0.4,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.5-flash", "qwen/qwen3.5-flash-02-23"],
    },
    "qwen3.5-plus": {
        "display_name": "Qwen3.5 Plus",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 0.4,
        "output_per_1m": 2.4,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3.5-plus", "qwen/qwen3.5-plus-02-15", "qwen/qwen3.5-plus-20260420"],
    },
    "qwen3.5-omni-plus": {
        "display_name": "Qwen3.5 Omni Plus",
        "context_window": 1_000_000,
        "max_output_tokens": 65_536,
        "input_per_1m": 1.4,  # text/image/video input
        "output_per_1m": 8.3,  # text out
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_vision": True,
        "supports_reasoning": True,
        "input_modalities": ["text", "image", "video", "audio"],
        "output_modalities": ["text", "audio"],
        "extra_pricing": {
            "audio_input_per_1m": 11.0,
            "text_audio_output_per_1m": 44.0,
        },
        "aliases": [],
    },
    "qwen-plus": {
        "display_name": "Qwen-Plus",
        "context_window": 1_000_000,
        "max_output_tokens": 32_768,
        "input_per_1m": 0.4,
        "output_per_1m": 1.2,
        "thinking_output_per_1m": 4.0,
        "long_context_threshold": 256_000,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen-plus"],
    },
    "qwen-flash": {
        "display_name": "Qwen-Flash",
        "context_window": 1_000_000,
        "max_output_tokens": 32_768,
        "input_per_1m": 0.05,
        "output_per_1m": 0.4,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "input_modalities": ["text"],
        "aliases": [],
    },
    "qwen-max": {
        "display_name": "Qwen-Max",
        "context_window": 262_144,
        "max_output_tokens": 32_768,
        "input_per_1m": 1.6,
        "output_per_1m": 6.4,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": [],
    },
    "qwen3-max": {
        "display_name": "Qwen3 Max",
        "context_window": 262_144,
        "max_output_tokens": 65_536,
        "input_per_1m": 1.2,
        "output_per_1m": 6.0,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_reasoning": True,
        "input_modalities": ["text"],
        "aliases": ["qwen/qwen3-max", "qwen/qwen3-max-thinking"],
    },
}

MEDIA_MODELS: dict[str, dict] = {
    "qwen-image-2.0-pro": {
        "display_name": "Qwen Image 2.0 Pro",
        "input_modalities": ["text"],
        "output_modalities": ["image"],
        "supports_chat_completion": False,
        "price_per_image": 0.075,
    },
    "wan2.7-image-pro": {
        "display_name": "Wan 2.7 Image Pro",
        "input_modalities": ["text"],
        "output_modalities": ["image"],
        "supports_chat_completion": False,
        "price_per_image": 0.075,
    },
    "happyhorse-1.1-t2v": {
        "display_name": "HappyHorse 1.1 T2V",
        "input_modalities": ["text"],
        "output_modalities": ["video"],
        "supports_chat_completion": False,
        "price_per_second_720p": 0.14,
        "note": "list ~$0.14/s 720p; promo may apply",
    },
}


def make_text_model(model_id: str, spec: dict) -> dict:
    extra: dict = {"source": SOURCE, "pricing_tier": "international_list"}
    if "promo_input_per_1m" in spec:
        extra["promo_input_per_1m"] = spec["promo_input_per_1m"]
        extra["promo_output_per_1m"] = spec["promo_output_per_1m"]
        extra["promo_note"] = spec.get("promo_note", "limited-time discount")
    for k in (
        "long_context_threshold",
        "long_context_input_per_1m",
        "long_context_output_per_1m",
        "thinking_output_per_1m",
    ):
        if k in spec:
            extra[k] = spec[k]
    if "extra_pricing" in spec:
        extra.update(spec["extra_pricing"])

    return {
        "provider": "qwen",
        "model_id": model_id,
        "display_name": spec["display_name"],
        "context_window": spec.get("context_window", 128_000),
        "max_output_tokens": spec.get("max_output_tokens", 32_768),
        "input_modalities": spec.get("input_modalities", ["text"]),
        "output_modalities": spec.get("output_modalities", ["text"]),
        "supports_function_calling": spec.get("supports_function_calling", True),
        "supports_json_mode": spec.get("supports_json_mode", True),
        "supports_streaming": True,
        "supports_vision": spec.get("supports_vision", False)
        or ("image" in spec.get("input_modalities", [])),
        "supports_reasoning": spec.get("supports_reasoning", False),
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
        "pricing": {
            "input_per_1m": spec["input_per_1m"],
            "output_per_1m": spec["output_per_1m"],
            "currency": "USD",
        },
        "deprecated": False,
        # Do not cross-alias OpenRouter ids (they exist as separate model_id rows)
        "aliases": [],
        "reasoning_effort_values": None,
        "extra": extra,
    }


def make_media_model(model_id: str, spec: dict) -> dict:
    extra = {"source": SOURCE, "unit": "image" if "price_per_image" in spec else "second"}
    if "price_per_image" in spec:
        extra["price_per_image"] = spec["price_per_image"]
    if "price_per_second_720p" in spec:
        extra["price_per_second_720p"] = spec["price_per_second_720p"]
    if "note" in spec:
        extra["note"] = spec["note"]
    return {
        "provider": "qwen",
        "model_id": model_id,
        "display_name": spec["display_name"],
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": spec.get("input_modalities", ["text"]),
        "output_modalities": spec.get("output_modalities", ["image"]),
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_streaming": False,
        "supports_vision": "image" in spec.get("input_modalities", []),
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
        "pricing": None,
        "deprecated": False,
        "aliases": [],
        "reasoning_effort_values": None,
        "extra": extra,
    }


def sync_openrouter_entry(m: dict, bare_id: str, spec: dict) -> bool:
    """Annotate OpenRouter-style qwen/... entry with official list/promo (no cross-alias)."""
    changed = False
    extra = m.get("extra") or {}
    list_price = {
        "input_per_1m": spec["input_per_1m"],
        "output_per_1m": spec["output_per_1m"],
        "currency": "USD",
    }
    if extra.get("alibaba_list_pricing") != list_price:
        extra["alibaba_list_pricing"] = list_price
        changed = True
    if "promo_input_per_1m" in spec:
        promo = {
            "input_per_1m": spec["promo_input_per_1m"],
            "output_per_1m": spec["promo_output_per_1m"],
        }
        if extra.get("alibaba_promo_pricing") != promo:
            extra["alibaba_promo_pricing"] = promo
            extra["promo_note"] = spec.get("promo_note", "limited-time discount")
            changed = True
    # Keep marketplace price on OR entry; record official source only.
    if extra.get("alibaba_source") != SOURCE:
        extra["alibaba_source"] = SOURCE
        changed = True
    if extra.get("alibaba_model_id") != bare_id:
        extra["alibaba_model_id"] = bare_id
        changed = True
    # Remove accidental cross-aliases from prior runs
    aliases = list(m.get("aliases") or [])
    cleaned = [a for a in aliases if a != bare_id]
    if cleaned != aliases:
        m["aliases"] = cleaned
        changed = True
    m["extra"] = extra
    return changed


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    models: list[dict] = data["models"]
    by_id = {m["model_id"]: m for m in models}

    inserted = 0
    updated_or = 0
    media_n = 0

    for mid, spec in FLAGSHIP_TEXT.items():
        if mid not in by_id:
            new_m = make_text_model(mid, spec)
            models.append(new_m)
            by_id[mid] = new_m
            inserted += 1
        else:
            # refresh bare entry pricing to list
            m = by_id[mid]
            m["pricing"] = {
                "input_per_1m": spec["input_per_1m"],
                "output_per_1m": spec["output_per_1m"],
                "currency": "USD",
            }
            m["context_window"] = spec.get("context_window", m.get("context_window", 0))
            m["display_name"] = spec["display_name"]
            m["aliases"] = []  # no OR cross-alias
            extra = m.get("extra") or {}
            extra["source"] = SOURCE
            extra["pricing_tier"] = "international_list"
            if "promo_input_per_1m" in spec:
                extra["promo_input_per_1m"] = spec["promo_input_per_1m"]
                extra["promo_output_per_1m"] = spec["promo_output_per_1m"]
            m["extra"] = extra
            updated_or += 1

        # sync linked OpenRouter-style ids
        for alias in spec.get("aliases") or []:
            if alias in by_id and alias != mid:
                if sync_openrouter_entry(by_id[alias], mid, spec):
                    updated_or += 1

    for mid, spec in MEDIA_MODELS.items():
        if mid not in by_id:
            models.append(make_media_model(mid, spec))
            by_id[mid] = models[-1]
            inserted += 1
            media_n += 1
        else:
            m = by_id[mid]
            extra = m.get("extra") or {}
            if "price_per_image" in spec:
                extra["price_per_image"] = spec["price_per_image"]
            if "price_per_second_720p" in spec:
                extra["price_per_second_720p"] = spec["price_per_second_720p"]
            extra["source"] = SOURCE
            m["extra"] = extra
            media_n += 1

    models.sort(key=lambda x: x["model_id"])
    data["models"] = models
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if INSTALLED.parent.exists():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if m.get("pricing") and (m["pricing"].get("input_per_1m") or 0) > 0
    )
    print(
        f"qwen.json: inserted={inserted} updated_or_synced={updated_or} media={media_n} "
        f"total={len(models)} (active={active}, token-priced={priced})",
        flush=True,
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"""
## Qwen / Alibaba Model Studio refresh ({ts})

### Source
- Pricing: {SOURCE}
- Apply: `scripts/_update_qwen.py`

### Result
- qwen.json: **{len(models)}** models (active={active}, token-priced={priced})
- Added bare Model Studio IDs: qwen3.7-max/plus, qwen3.6-flash/plus/max-preview, qwen3.5-*, qwen-plus/flash/max, qwen3-max
- List prices (intl): qwen3.7-max $2.5/$7.5 (promo $1.25/$3.75); qwen3.7-plus $0.4/$1.6; qwen3.6-flash $0.25/$1.5
- Media: qwen-image-2.0-pro / wan2.7-image-pro $0.075/image; happyhorse-1.1-t2v ~$0.14/s 720p
- OpenRouter `qwen/...` entries kept; alibaba_list_pricing annotated in extra
- Install copy synced
"""
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry.lstrip(), encoding="utf-8")


if __name__ == "__main__":
    main()
