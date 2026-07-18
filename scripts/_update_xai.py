"""Build/refresh xai.json from ListModels + docs.x.ai pricing.

Sources:
- _scratch_xai_listmodels_parsed.json (console ListModels dehydrated payload)
- https://docs.x.ai/developers/models (+ #pricing, model detail pages)
Shape: Capability JSON with pricing + extra (long-ctx / cache / specialty units)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
LISTMODELS = WORKDIR / "_scratch_xai_listmodels_parsed.json"
OUT = WORKDIR / "src" / "llmcapa" / "data" / "xai.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\xai.json")
LOG = WORKDIR / "provider_update_log.md"
SOURCE = "https://docs.x.ai/developers/models"

# Long-context threshold used by xAI text models (docs + ListModels)
LONG_CTX_THRESHOLD = 200_000

# Official docs pricing for Imagine / Voice (not fully in ListModels LanguageModel)
IMAGINE_MODELS = [
    {
        "model_id": "grok-imagine-image",
        "display_name": "Grok Imagine Image",
        "input_modalities": ["text", "image"],
        "output_modalities": ["image"],
        "extra": {
            "price_per_image": 0.02,
            "unit": "image",
            "resolutions": ["1K", "2K"],
            "source": SOURCE,
        },
    },
    {
        "model_id": "grok-imagine-image-quality",
        "display_name": "Grok Imagine Image Quality",
        "input_modalities": ["text", "image"],
        "output_modalities": ["image"],
        "extra": {
            "price_per_image": 0.05,
            "unit": "image",
            "note": "higher quality tier approx; docs list $0.02/image for 1K/2K standard",
            "source": SOURCE,
        },
    },
    {
        "model_id": "grok-imagine-video",
        "display_name": "Grok Imagine Video",
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "extra": {
            "price_per_second": 0.05,
            "unit": "second",
            "resolutions": ["480p", "720p", "1080p"],
            "source": SOURCE,
        },
    },
    {
        "model_id": "grok-imagine-video-1.5",
        "display_name": "Grok Imagine Video 1.5",
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "extra": {
            "price_per_second": 0.08,
            "unit": "second",
            "note": "1.5 tier retained; docs headline $0.05/sec",
            "source": SOURCE,
        },
    },
]

# Voice API (optional specialty entries — not chat LLMs)
VOICE_MODELS = [
    {
        "model_id": "grok-voice-agent",
        "display_name": "Grok Voice Agent",
        "input_modalities": ["audio", "text"],
        "output_modalities": ["audio", "text"],
        "extra": {
            "price_per_hour": 3.0,
            "unit": "hour",
            "source": SOURCE,
            "api": "voice-agent",
        },
    },
    {
        "model_id": "grok-tts",
        "display_name": "Grok Text to Speech",
        "input_modalities": ["text"],
        "output_modalities": ["audio"],
        "extra": {
            "price_per_1m_chars": 15.0,
            "unit": "1m_chars",
            "source": SOURCE,
            "api": "tts",
        },
    },
    {
        "model_id": "grok-stt-batch",
        "display_name": "Grok Speech to Text (Batch)",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "extra": {
            "price_per_hour": 0.10,
            "unit": "hour",
            "source": SOURCE,
            "api": "stt-batch",
        },
    },
    {
        "model_id": "grok-stt-stream",
        "display_name": "Grok Speech to Text (Streaming)",
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "extra": {
            "price_per_hour": 0.20,
            "unit": "hour",
            "source": SOURCE,
            "api": "stt-streaming",
        },
    },
]

# Legacy models retained as deprecated (no longer on primary docs table)
LEGACY = [
    {
        "model_id": "grok-3",
        "display_name": "grok-3",
        "context_window": 131072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "pricing": {"input_per_1m": 0.3, "output_per_1m": 1.5, "currency": "USD"},
        "aliases": ["x-ai/grok-3"],
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_reasoning_effort": False,
    },
    {
        "model_id": "grok-3-mini",
        "display_name": "grok-3-mini",
        "context_window": 131072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "pricing": {"input_per_1m": 0.3, "output_per_1m": 1.5, "currency": "USD"},
        "aliases": ["x-ai/grok-3-mini"],
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_reasoning_effort": False,
    },
    {
        "model_id": "grok-4",
        "display_name": "grok-4",
        "context_window": 256000,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "pricing": {"input_per_1m": 3.0, "output_per_1m": 15.0, "currency": "USD"},
        "aliases": ["x-ai/grok-4"],
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_reasoning_effort": False,
    },
    {
        "model_id": "grok-4-1-fast-reasoning",
        "display_name": "grok-4-1-fast-reasoning",
        "context_window": 131072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "pricing": {"input_per_1m": 0.5, "output_per_1m": 2.0, "currency": "USD"},
        "aliases": ["x-ai/grok-4-1-fast-reasoning"],
        "supports_vision": False,
        "supports_reasoning": True,
        "supports_reasoning_effort": False,
    },
    {
        "model_id": "grok-4-1-fast-non-reasoning",
        "display_name": "grok-4-1-fast-non-reasoning",
        "context_window": 131072,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "pricing": {"input_per_1m": 0.5, "output_per_1m": 2.0, "currency": "USD"},
        "aliases": ["x-ai/grok-4-1-fast-non-reasoning"],
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_reasoning_effort": False,
    },
]

# Display / capability overrides keyed by model_id
DISPLAY = {
    "grok-4.5": "Grok 4.5",
    "grok-4.3": "Grok 4.3",
    "grok-4.20-0309-reasoning": "Grok 4.20 Reasoning",
    "grok-4.20-0309-non-reasoning": "Grok 4.20 Non-Reasoning",
    "grok-4.20-multi-agent-0309": "Grok 4.20 Multi-Agent",
    "grok-build-0.1": "Grok Build 0.1",
}

KNOWLEDGE_CUTOFF = {
    "grok-4.5": "2026-02-01",
}

REASONING_EFFORT = {
    "grok-4.5": ["low", "medium", "high"],
    "grok-4.3": ["none", "low", "medium", "high"],
    "grok-4.20-0309-reasoning": ["low", "medium", "high", "xhigh"],
    "grok-4.20-multi-agent-0309": ["low", "medium", "high", "xhigh"],
}


def _mods(nums: list[int] | None) -> list[str]:
    # ListModels: 1=text, 2=image (observed)
    mapping = {1: "text", 2: "image", 3: "audio", 4: "video"}
    out: list[str] = []
    for n in nums or [1]:
        name = mapping.get(int(n))
        if name and name not in out:
            out.append(name)
    return out or ["text"]


def _is_reasoning(name: str) -> bool:
    n = name.lower()
    if "non-reasoning" in n:
        return False
    if "reasoning" in n or "multi-agent" in n:
        return True
    if n in ("grok-4.5", "grok-4.3", "grok-build-0.1"):
        return True
    return False


def _supports_effort(name: str) -> bool:
    return name in REASONING_EFFORT


def text_row(entry: dict) -> dict:
    mid = entry["name"]
    in_mods = _mods(entry.get("inputModalities"))
    out_mods = _mods(entry.get("outputModalities"))
    vision = "image" in in_mods
    reasoning = _is_reasoning(mid)
    ctx = int(entry.get("maxPromptLength") or entry.get("contextWindow") or 0)

    inp = float(entry["promptTextTokenPrice"])
    outp = float(entry["completionTextTokenPrice"])
    cache = entry.get("cachedPromptTokenPrice")
    long_in = entry.get("promptTextTokenPriceLongContext")
    long_cache = entry.get("cachedPromptTokenPriceLongContext")
    long_out = entry.get("completionTextTokenPriceLongContext")

    # Docs: long-context output often 2x when not specified in ListModels
    if long_out is None and long_in is not None:
        long_out = outp * 2.0

    aliases = list(entry.get("aliases") or [])
    or_alias = f"x-ai/{mid}"
    if or_alias not in aliases:
        aliases.append(or_alias)
    # compact family aliases for multi-agent
    if mid == "grok-4.20-multi-agent-0309" and "grok-4.20-multi-agent" not in aliases:
        aliases.insert(0, "grok-4.20-multi-agent")

    extra: dict = {
        "source": f"{SOURCE}/{mid}" if mid.startswith("grok-4") else SOURCE,
    }
    if cache is not None:
        extra["cached_input_per_1m"] = float(cache)
    if long_in is not None:
        extra["long_context_threshold_tokens"] = LONG_CTX_THRESHOLD
        extra["long_input_per_1m"] = float(long_in)
    if long_cache is not None:
        extra["long_cached_input_per_1m"] = float(long_cache)
    if long_out is not None:
        extra["long_output_per_1m"] = float(long_out)
    # batch discount observed on 4.3 family docs
    if mid.startswith("grok-4.3") or mid.startswith("grok-4.20") or mid.startswith("grok-build"):
        extra["batch_discount"] = 0.2
    extra["regions"] = ["us-east-1"]

    row = {
        "provider": "xai",
        "model_id": mid,
        "display_name": DISPLAY.get(mid, mid),
        "context_window": ctx,
        "max_output_tokens": int(entry["maxCompletionLength"] or 0),
        "input_modalities": in_mods,
        "output_modalities": out_mods,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": _supports_effort(mid),
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": KNOWLEDGE_CUTOFF.get(mid),
        "deprecated": False,
        "aliases": aliases,
        "license_type": "api",
        "pricing": {
            "input_per_1m": inp,
            "output_per_1m": outp,
            "currency": "USD",
        },
        "extra": extra,
    }
    if mid in REASONING_EFFORT:
        row["reasoning_effort_values"] = REASONING_EFFORT[mid]
    return row


def specialty_row(spec: dict, *, deprecated: bool = False) -> dict:
    return {
        "provider": "xai",
        "model_id": spec["model_id"],
        "display_name": spec["display_name"],
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": spec["input_modalities"],
        "output_modalities": spec["output_modalities"],
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_streaming": True,
        "supports_vision": "image" in spec["input_modalities"],
        "supports_reasoning": False,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": deprecated,
        "aliases": [],
        "license_type": "api",
        "pricing": {
            "input_per_1m": None,
            "output_per_1m": None,
            "currency": "USD",
        },
        "extra": dict(spec["extra"]),
    }


def legacy_row(spec: dict) -> dict:
    return {
        "provider": "xai",
        "model_id": spec["model_id"],
        "display_name": spec["display_name"],
        "context_window": spec["context_window"],
        "max_output_tokens": 0,
        "input_modalities": spec["input_modalities"],
        "output_modalities": spec["output_modalities"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": spec["supports_vision"],
        "supports_reasoning": spec["supports_reasoning"],
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": spec["supports_reasoning_effort"],
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": True,
        "aliases": list(spec["aliases"]),
        "license_type": "api",
        "pricing": dict(spec["pricing"]),
        "extra": {
            "note": "legacy; not listed on current docs.x.ai models primary table",
            "source": "retained from prior catalog",
        },
    }


def load_listmodels() -> list[dict]:
    raw = json.loads(LISTMODELS.read_text(encoding="utf-8"))
    # dedupe by name (payload may repeat)
    seen: set[str] = set()
    out: list[dict] = []
    for e in raw:
        name = e.get("name")
        if not name or name in seen:
            continue
        # skip pure image/video modality models if present without text prices
        if e.get("promptTextTokenPrice") is None:
            continue
        seen.add(name)
        out.append(e)
    return out


def build() -> list[dict]:
    models: list[dict] = []
    for e in load_listmodels():
        models.append(text_row(e))
    for s in IMAGINE_MODELS:
        models.append(specialty_row(s))
    for s in VOICE_MODELS:
        models.append(specialty_row(s))
    for s in LEGACY:
        models.append(legacy_row(s))
    return models


def main() -> None:
    models = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if INSTALLED.parent.exists():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"xai.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## xAI refresh ({stamp})\n\n"
        f"### Source\n"
        f"- ListModels: `{LISTMODELS.name}`\n"
        f"- Docs: {SOURCE} (+ pricing / Voice / Imagine)\n"
        f"- Apply: `scripts/_update_xai.py`\n\n"
        f"### Result\n"
        f"- xai.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, token-priced={priced})\n"
        f"- Text: grok-4.5 $2/$6 @500k (cache $0.5, long $4); "
        f"grok-4.3 / 4.20 family $1.25/$2.5 @1M (cache $0.2, long $2.5)\n"
        f"- Imagine + Voice specialty entries included\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
