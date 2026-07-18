"""Update google.json with official Gemini API pricing + insert missing models.

Sources (Playwright 2026-07-18):
- https://ai.google.dev/gemini-api/docs/pricing
Only updates/inserts known official IDs; preserves unrelated entries.
"""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "google.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\google.json")
LOG = WORKDIR / "provider_update_log.md"
SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"

# model_id -> (input_per_1m, output_per_1m, context_window)
GOOGLE_PRICES: dict[str, tuple[float, float, int]] = {
    "gemini-3.5-flash": (1.5, 9.0, 1_048_576),
    "gemini-3.5-live-translate-preview": (3.5, 21.0, 1_048_576),
    "gemini-3.1-flash-lite": (0.25, 1.5, 1_048_576),
    "gemini-3.1-flash-lite-preview": (0.25, 1.5, 1_048_576),
    "gemini-omni-flash-preview": (1.5, 9.0, 1_048_576),
    "gemini-3.1-pro-preview": (2.0, 12.0, 1_048_576),
    "gemini-3.1-pro-preview-customtools": (2.0, 12.0, 1_048_576),
    "gemini-3.1-flash-live-preview": (0.75, 4.5, 131_072),
    "gemini-3.1-flash-image": (0.5, 3.0, 131_072),
    "gemini-3.1-flash-image-preview": (0.5, 3.0, 131_072),
    "gemini-3.1-flash-lite-image": (0.25, 1.5, 65_536),
    "gemini-3.1-flash-tts-preview": (1.0, 20.0, 131_072),
    "gemini-3-flash-preview": (0.5, 3.0, 1_048_576),
    "gemini-3-pro-image": (2.0, 12.0, 65_536),
    "gemini-3-pro-image-preview": (2.0, 12.0, 65_536),
    "gemini-2.5-pro": (1.25, 10.0, 1_048_576),
    "gemini-2.5-flash": (0.3, 2.5, 1_048_576),
    "gemini-2.5-flash-lite": (0.1, 0.4, 1_048_576),
    "gemini-2.5-flash-lite-preview-09-2025": (0.1, 0.4, 1_048_576),
    "gemini-2.5-flash-native-audio-preview-12-2025": (0.5, 2.0, 1_048_576),
    "gemini-2.5-flash-image": (0.3, 2.5, 32_768),
    "gemini-2.5-flash-preview-tts": (0.5, 10.0, 32_768),
    "gemini-2.5-pro-preview-tts": (1.0, 20.0, 32_768),
    "gemini-2.0-flash": (0.1, 0.4, 1_048_576),
    "gemini-2.0-flash-lite": (0.075, 0.3, 1_048_576),
    "gemini-1.5-pro": (1.25, 10.0, 2_097_152),
    "gemini-1.5-flash": (0.075, 0.3, 1_048_576),
}

# Long-context tier for Pro models (≤200k vs >200k) stored in extra
LONG_CTX_PRO = {
    "gemini-3.1-pro-preview": {
        "long_context_threshold": 200_000,
        "long_context_input_per_1m": 4.0,
        "long_context_output_per_1m": 18.0,
        "note": "≤200k $2/$12; >200k $4/$18",
    },
    "gemini-3.1-pro-preview-customtools": {
        "long_context_threshold": 200_000,
        "long_context_input_per_1m": 4.0,
        "long_context_output_per_1m": 18.0,
    },
}

# Specialty unit pricing (not token-based)
SPECIALTY_EXTRA = {
    "lyria-3-clip-preview": {
        "price_per_song": 0.04,
        "unit": "song",
        "source": SOURCE,
    },
    "lyria-3-pro-preview": {
        "price_per_song": 0.08,
        "unit": "song",
        "source": SOURCE,
    },
    "google/lyria-3-clip-preview": {
        "price_per_song": 0.04,
        "unit": "song",
        "source": SOURCE,
    },
    "google/lyria-3-pro-preview": {
        "price_per_song": 0.08,
        "unit": "song",
        "source": SOURCE,
    },
    "gemini-omni-flash-preview": {
        "source": SOURCE,
        "video_output_per_1m": 17.50,
        "note": "text $1.5/$9; video output $17.50/1M",
    },
}

# Deprecations announced on pricing page
DEPRECATIONS = {
    # shut down 2026-06-01
    "gemini-2.0-flash": "2026-06-01",
    "gemini-2.0-flash-lite": "2026-06-01",
    "gemini-2.0-flash-001": "2026-06-01",
    "gemini-2.0-flash-lite-001": "2026-06-01",
    # Imagen 4 shut 2026-08-17
    "imagen-4.0-generate-001": "2026-08-17",
    "imagen-4.0-ultra-generate-001": "2026-08-17",
    "imagen-4.0-fast-generate-001": "2026-08-17",
    # Veo 3/2 shut 2026-06-30
    "veo-3.0-generate-001": "2026-06-30",
    "veo-3.0-fast-generate-001": "2026-06-30",
    "veo-2.0-generate-001": "2026-06-30",
}

# Templates for models that must be inserted if missing
NEW_MODEL_TEMPLATES: dict[str, dict] = {
    "gemini-3.5-live-translate-preview": {
        "display_name": "Gemini 3.5 Live Translate Preview",
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_chat_completion": True,
        "max_output_tokens": 8192,
        "extra": {"source": SOURCE, "api": "live-translate"},
    },
    "gemini-omni-flash-preview": {
        "display_name": "Gemini Omni Flash Preview",
        "input_modalities": ["text", "image", "video", "audio"],
        "output_modalities": ["text", "video"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "max_output_tokens": 65_536,
        "extra": {
            "source": SOURCE,
            "video_output_per_1m": 17.50,
            "note": "text $1.5/$9; video output $17.50/1M",
        },
    },
    "gemini-3.1-flash-tts-preview": {
        "display_name": "Gemini 3.1 Flash TTS Preview",
        "input_modalities": ["text"],
        "output_modalities": ["audio"],
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_chat_completion": True,
        "max_output_tokens": 16_384,
        "extra": {"source": SOURCE, "api": "tts"},
    },
}


def base_model(model_id: str, template: dict, price_tuple: tuple[float, float, int]) -> dict:
    inp, out, ctx = price_tuple
    return {
        "provider": "google",
        "model_id": model_id,
        "display_name": template.get("display_name", model_id),
        "context_window": ctx,
        "max_output_tokens": template.get("max_output_tokens", 8192),
        "input_modalities": template.get("input_modalities", ["text"]),
        "output_modalities": template.get("output_modalities", ["text"]),
        "supports_function_calling": template.get("supports_function_calling", True),
        "supports_json_mode": template.get("supports_json_mode", True),
        "supports_streaming": True,
        "supports_vision": template.get("supports_vision", False),
        "supports_reasoning": template.get("supports_reasoning", False),
        "supports_chat_completion": template.get("supports_chat_completion", True),
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": True,
        "supports_fim": False,
        "license_type": "api",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"},
        "deprecated": False,
        "aliases": [],
        "reasoning_effort_values": None,
        "extra": deepcopy(template.get("extra") or {}),
    }


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    models: list[dict] = data["models"]
    by_id = {m["model_id"]: m for m in models}

    updated = 0
    inserted = 0
    specialty = 0
    deprecated_n = 0

    # Update existing prices / context
    for mid, (inp, out, ctx) in GOOGLE_PRICES.items():
        if mid not in by_id:
            continue
        m = by_id[mid]
        m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
        m["context_window"] = ctx
        m["supports_google_api"] = True
        m["supports_responses_api"] = False
        m["supports_fim"] = False
        if mid in LONG_CTX_PRO:
            extra = m.get("extra") or {}
            extra.update(LONG_CTX_PRO[mid])
            extra["source"] = SOURCE
            m["extra"] = extra
        updated += 1

    # Insert missing models that have templates
    for mid, tmpl in NEW_MODEL_TEMPLATES.items():
        if mid in by_id:
            # still ensure price applied
            if mid in GOOGLE_PRICES:
                inp, out, ctx = GOOGLE_PRICES[mid]
                by_id[mid]["pricing"] = {
                    "input_per_1m": inp,
                    "output_per_1m": out,
                    "currency": "USD",
                }
                by_id[mid]["context_window"] = ctx
            continue
        if mid not in GOOGLE_PRICES:
            continue
        new_m = base_model(mid, tmpl, GOOGLE_PRICES[mid])
        models.append(new_m)
        by_id[mid] = new_m
        inserted += 1

    # Specialty unit pricing (Lyria etc.)
    for mid, extra_patch in SPECIALTY_EXTRA.items():
        if mid not in by_id:
            continue
        m = by_id[mid]
        extra = m.get("extra") or {}
        extra.update(extra_patch)
        m["extra"] = extra
        # keep token pricing as 0 placeholder for non-token models
        if mid.startswith("lyria") or mid.startswith("google/lyria"):
            m["pricing"] = {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"}
            m["supports_chat_completion"] = False
            m["input_modalities"] = m.get("input_modalities") or ["text"]
            m["output_modalities"] = ["audio"]
        specialty += 1

    # Deprecations
    for m in models:
        mid = m["model_id"]
        # exact or prefix match for versioned ids
        shutdown = DEPRECATIONS.get(mid)
        if shutdown is None:
            for key, date in DEPRECATIONS.items():
                if mid == key or mid.startswith(key + "-") or mid.startswith(key + "@"):
                    shutdown = date
                    break
        if shutdown:
            m["deprecated"] = True
            extra = m.get("extra") or {}
            extra["shutdown_date"] = shutdown
            extra["source"] = SOURCE
            m["extra"] = extra
            deprecated_n += 1

    # Flags for all google models
    for m in models:
        m["supports_google_api"] = True
        m.setdefault("supports_responses_api", False)
        m.setdefault("supports_fim", False)

    models.sort(key=lambda x: x["model_id"])
    data["models"] = models
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if INSTALLED.parent.exists():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(1 for m in models if m.get("pricing") and (m["pricing"].get("input_per_1m") or 0) > 0)
    print(
        f"google.json: updated={updated} inserted={inserted} specialty={specialty} "
        f"deprecated_flagged={deprecated_n} total={len(models)} "
        f"(active={active}, token-priced={priced})",
        flush=True,
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"""
## Google refresh ({ts})

### Source
- Pricing: {SOURCE}
- Apply: `scripts/_update_google.py`

### Result
- google.json: **{len(models)}** models (active={active}, token-priced={priced})
- Inserted: gemini-3.5-live-translate-preview, gemini-omni-flash-preview, gemini-3.1-flash-tts-preview
- Lyria-3 clip/pro: $0.04 / $0.08 per song (extra)
- Deprecations: gemini-2.0-flash* shut 2026-06-01; Imagen 4 2026-08-17; Veo 3/2 2026-06-30
- Install copy synced
"""
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry.lstrip(), encoding="utf-8")


if __name__ == "__main__":
    main()
