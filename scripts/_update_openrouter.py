"""Build/refresh openrouter.json from OpenRouter public Models API.

Sources:
- GET https://openrouter.ai/api/v1/models  (live; scratch _scratch_openrouter_models.json)
- Docs: https://openrouter.ai/docs
- Pricing page: https://openrouter.ai/models

OpenRouter prices are USD **per token** in the API (`prompt`/`completion`).
Catalog stores USD **per 1M tokens** (× 1_000_000).

Special routers with prompt=-1 keep the catalog convention
input_per_1m = -1_000_000 (dynamic / routed pricing).
"""
from __future__ import annotations

import json
import shutil
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKDIR = Path(r"C:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "openrouter.json"
INSTALLED = Path(r"C:\Users\ukawahrf\AppData\Local\Programs\Python\Python314\Lib\site-packages\llmcapa\data\openrouter.json")
LOG = WORKDIR / "provider_update_log.md"
SCRATCH = WORKDIR / "_scratch_openrouter_models.json"
API_URL = "https://openrouter.ai/api/v1/models"
SOURCE_DOCS = "https://openrouter.ai/docs"
SOURCE_MODELS = "https://openrouter.ai/models"
BASE_URL = "https://openrouter.ai/api/v1"

# Catalog convention for dynamic/router pricing (matches prior openrouter.json)
DYNAMIC_PRICE = -1_000_000.0

# Effort values commonly accepted via OpenRouter reasoning_effort
DEFAULT_EFFORT = ["none", "minimal", "low", "medium", "high", "xhigh"]

# Synthetic "~latest" convenience aliases (not in API; keep for clients)
# Prices are approximate shells from prior catalog / flagship rates.
LATEST_ALIASES: list[dict[str, Any]] = [
    {
        "model_id": "~anthropic/claude-opus-latest",
        "display_name": "OpenRouter ~ Claude Opus (latest)",
        "resolves_hint": "anthropic/claude-opus-*",
        "ctx": 200_000,
        "max_out": 32_000,
        "input": 5.0,
        "output": 25.0,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~anthropic/claude-sonnet-latest",
        "display_name": "OpenRouter ~ Claude Sonnet (latest)",
        "resolves_hint": "anthropic/claude-sonnet-*",
        "ctx": 1_000_000,
        "max_out": 64_000,
        "input": 3.0,
        "output": 15.0,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~anthropic/claude-haiku-latest",
        "display_name": "OpenRouter ~ Claude Haiku (latest)",
        "resolves_hint": "anthropic/claude-haiku-*",
        "ctx": 200_000,
        "max_out": 64_000,
        "input": 1.0,
        "output": 5.0,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~anthropic/claude-fable-latest",
        "display_name": "OpenRouter ~ Claude Fable (latest)",
        "resolves_hint": "anthropic/claude-fable-*",
        "ctx": 200_000,
        "max_out": 32_000,
        "input": 10.0,
        "output": 50.0,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~google/gemini-flash-latest",
        "display_name": "OpenRouter ~ Gemini Flash (latest)",
        "resolves_hint": "google/gemini-*-flash*",
        "ctx": 1_048_576,
        "max_out": 65_536,
        "input": 0.3,
        "output": 2.5,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~google/gemini-pro-latest",
        "display_name": "OpenRouter ~ Gemini Pro (latest)",
        "resolves_hint": "google/gemini-*-pro*",
        "ctx": 1_048_576,
        "max_out": 65_536,
        "input": 1.25,
        "output": 10.0,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~openai/gpt-latest",
        "display_name": "OpenRouter ~ OpenAI GPT (latest flagship)",
        "resolves_hint": "openai/gpt-*",
        "ctx": 400_000,
        "max_out": 100_000,
        "input": 5.0,
        "output": 15.0,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~openai/gpt-mini-latest",
        "display_name": "OpenRouter ~ OpenAI GPT mini (latest)",
        "resolves_hint": "openai/gpt-*-mini*",
        "ctx": 400_000,
        "max_out": 100_000,
        "input": 0.4,
        "output": 1.6,
        "vision": True,
        "reasoning": True,
    },
    {
        "model_id": "~x-ai/grok-latest",
        "display_name": "OpenRouter ~ xAI Grok (latest)",
        "resolves_hint": "x-ai/grok-*",
        "ctx": 256_000,
        "max_out": 64_000,
        "input": 2.0,
        "output": 6.0,
        "vision": True,
        "reasoning": True,
    },
]


def fetch_models() -> list[dict]:
    """Fetch live API; fall back to scratch if network fails."""
    try:
        req = urllib.request.Request(
            API_URL,
            headers={
                "User-Agent": "llmcapa-updater/1.0",
                "Accept": "application/json",
            },
        )
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
            data = json.load(resp)
        models = data.get("data") or data
        if not isinstance(models, list) or not models:
            raise RuntimeError("empty models list from API")
        SCRATCH.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        print(f"fetched live API: {len(models)} models → {SCRATCH.name}", flush=True)
        return models
    except Exception as exc:  # noqa: BLE001
        print(f"live fetch failed ({exc}); using scratch if present", flush=True)
        if SCRATCH.exists():
            data = json.loads(SCRATCH.read_text(encoding="utf-8"))
            models = data.get("data") or data
            print(f"scratch: {len(models)} models", flush=True)
            return models
        raise


def per_token_to_1m(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return DYNAMIC_PRICE
    # API is USD per token
    return round(f * 1_000_000.0, 6)


def parse_cutoff(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        # unix seconds
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%Y-%m")
        except (OSError, ValueError, OverflowError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    # already YYYY-MM or YYYY-MM-DD
    if len(s) >= 7 and s[4] == "-":
        return s[:7]
    return s


def ts_to_iso(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def map_model(raw: dict) -> dict:
    mid = raw.get("id") or ""
    arch = raw.get("architecture") or {}
    pricing_raw = raw.get("pricing") or {}
    top = raw.get("top_provider") or {}
    params = list(raw.get("supported_parameters") or [])
    params_set = set(params)

    in_mod = list(arch.get("input_modalities") or ["text"])
    out_mod = list(arch.get("output_modalities") or ["text"])
    # normalize empty
    if not in_mod:
        in_mod = ["text"]
    if not out_mod:
        out_mod = ["text"]

    vision = any(x in in_mod for x in ("image", "video"))
    has_audio_in = "audio" in in_mod
    has_file = "file" in in_mod
    has_image_out = "image" in out_mod
    has_audio_out = "audio" in out_mod
    has_embedding_out = "embedding" in out_mod or "embeddings" in out_mod

    tools = "tools" in params_set or "tool_choice" in params_set
    json_mode = "response_format" in params_set or "structured_outputs" in params_set
    reasoning = (
        "reasoning" in params_set
        or "include_reasoning" in params_set
        or "reasoning_effort" in params_set
        or bool(raw.get("reasoning"))
    )
    effort = "reasoning_effort" in params_set
    streaming = True  # OpenRouter chat always streams-capable
    chat = not has_embedding_out  # embeddings are not chat

    pin = per_token_to_1m(pricing_raw.get("prompt"))
    pout = per_token_to_1m(pricing_raw.get("completion"))
    is_dynamic = pin == DYNAMIC_PRICE or pout == DYNAMIC_PRICE
    is_free = (
        pin == 0.0
        and pout == 0.0
        and not is_dynamic
        and (":free" in mid or mid.endswith("/free") or mid == "openrouter/free")
    ) or (
        pin == 0.0
        and pout == 0.0
        and float(pricing_raw.get("prompt") or 1) == 0
        and float(pricing_raw.get("completion") or 1) == 0
    )

    ctx = int(raw.get("context_length") or top.get("context_length") or 0)
    max_out = top.get("max_completion_tokens")
    if max_out is None:
        max_out = 0
    else:
        try:
            max_out = int(max_out)
        except (TypeError, ValueError):
            max_out = 0

    # license
    if is_dynamic or mid.startswith("openrouter/"):
        license_type = "special"
    elif is_free or (pin == 0.0 and pout == 0.0):
        license_type = "free"
    else:
        license_type = "api"

    # deprecated via expiration_date in the past
    deprecated = False
    exp = raw.get("expiration_date")
    exp_iso = None
    if exp:
        exp_iso = str(exp)[:10] if not isinstance(exp, (int, float)) else ts_to_iso(exp)
        try:
            if exp_iso and exp_iso < datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                deprecated = True
        except Exception:  # noqa: BLE001
            pass

    aliases: list[str] = []
    # short id without org if unique-looking
    if "/" in mid:
        short = mid.split("/", 1)[1]
        aliases.append(short)
    # openrouter/ prefix form
    if not mid.startswith("openrouter/"):
        aliases.append(f"openrouter/{mid}")
    canonical = raw.get("canonical_slug")
    if canonical and canonical != mid and canonical not in aliases:
        aliases.append(canonical)

    # pricing block
    if pin is None and pout is None:
        pricing = None
    else:
        pricing = {
            "input_per_1m": pin if pin is not None else 0.0,
            "output_per_1m": pout if pout is not None else 0.0,
            "currency": "USD",
        }

    # cache / extra pricing from API (per-token → per 1M)
    cache_read = per_token_to_1m(pricing_raw.get("input_cache_read"))
    cache_write = per_token_to_1m(pricing_raw.get("input_cache_write"))
    cache_write_1h = per_token_to_1m(pricing_raw.get("input_cache_write_1h"))
    web_search = None
    if pricing_raw.get("web_search") is not None:
        try:
            # web_search is typically USD per request, not per token
            web_search = float(pricing_raw["web_search"])
        except (TypeError, ValueError):
            web_search = None
    image_price = per_token_to_1m(pricing_raw.get("image"))
    image_out_price = per_token_to_1m(pricing_raw.get("image_output"))
    audio_price = per_token_to_1m(pricing_raw.get("audio"))
    audio_out_price = per_token_to_1m(pricing_raw.get("audio_output"))
    internal_reasoning = per_token_to_1m(pricing_raw.get("internal_reasoning"))

    native_provider = mid.split("/", 1)[0] if "/" in mid else "openrouter"

    extra: dict[str, Any] = {
        "source": API_URL,
        "docs": SOURCE_DOCS,
        "models_page": SOURCE_MODELS,
        "base_url": BASE_URL,
        "native_provider": native_provider,
        "canonical_slug": canonical,
        "hugging_face_id": raw.get("hugging_face_id") or None,
        "modality": arch.get("modality"),
        "tokenizer": arch.get("tokenizer"),
        "instruct_type": arch.get("instruct_type"),
        "top_provider": {
            "context_length": top.get("context_length"),
            "max_completion_tokens": top.get("max_completion_tokens"),
            "is_moderated": top.get("is_moderated"),
        },
        "supported_parameters": params,
        "created": ts_to_iso(raw.get("created")),
        "description": (raw.get("description") or "")[:400] or None,
    }
    if exp_iso:
        extra["expiration_date"] = exp_iso
    if is_dynamic:
        extra["pricing_note"] = (
            "dynamic/router pricing (API prompt=-1); billed at routed model rate"
        )
        extra["dynamic_pricing"] = True
    if is_free or (pin == 0.0 and pout == 0.0 and not is_dynamic):
        extra["free_tier"] = True
    if cache_read is not None:
        extra["cache_read_per_1m"] = cache_read
    if cache_write is not None:
        extra["cache_write_per_1m"] = cache_write
    if cache_write_1h is not None:
        extra["cache_write_1h_per_1m"] = cache_write_1h
    if web_search is not None:
        extra["web_search_per_request_usd"] = web_search
    if image_price is not None:
        extra["image_input_per_1m"] = image_price
    if image_out_price is not None:
        extra["image_output_per_1m"] = image_out_price
    if audio_price is not None:
        extra["audio_input_per_1m"] = audio_price
    if audio_out_price is not None:
        extra["audio_output_per_1m"] = audio_out_price
    if internal_reasoning is not None:
        extra["internal_reasoning_per_1m"] = internal_reasoning
    if pricing_raw.get("overrides"):
        extra["pricing_overrides"] = pricing_raw.get("overrides")
    if raw.get("default_parameters"):
        # strip nulls
        dp = {k: v for k, v in (raw["default_parameters"] or {}).items() if v is not None}
        if dp:
            extra["default_parameters"] = dp
    if raw.get("per_request_limits"):
        extra["per_request_limits"] = raw["per_request_limits"]
    if raw.get("reasoning"):
        extra["reasoning_meta"] = raw["reasoning"]
    if raw.get("links"):
        extra["links"] = raw["links"]
    # keep benchmarks compact (counts only) to avoid huge JSON
    benches = raw.get("benchmarks")
    if isinstance(benches, dict) and benches:
        extra["benchmarks_present"] = {
            k: (len(v) if isinstance(v, list) else 1) for k, v in benches.items()
        }

    features: list[str] = []
    if tools:
        features.append("tools")
    if json_mode:
        features.append("structured_outputs")
    if reasoning:
        features.append("reasoning")
    if effort:
        features.append("reasoning_effort")
    if vision:
        features.append("vision")
    if has_audio_in:
        features.append("audio_input")
    if has_audio_out:
        features.append("audio_output")
    if has_file:
        features.append("file_input")
    if has_image_out:
        features.append("image_output")
    if has_embedding_out:
        features.append("embeddings")
    if "web_search_options" in params_set:
        features.append("web_search")
    if is_dynamic:
        features.append("router")
    if features:
        extra["features"] = features

    # drop None values from extra one level
    extra = {k: v for k, v in extra.items() if v is not None}

    row: dict[str, Any] = {
        "provider": "openrouter",
        "model_id": mid,
        "display_name": raw.get("name") or mid,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": in_mod,
        "output_modalities": out_mod,
        "supports_function_calling": tools and chat,
        "supports_json_mode": json_mode and chat,
        "supports_streaming": streaming,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": False,
        "supports_reasoning_effort": effort,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": arch.get("tokenizer") or "",
        "knowledge_cutoff": parse_cutoff(raw.get("knowledge_cutoff")),
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": license_type,
        "pricing": pricing,
        "extra": extra,
    }
    if effort:
        row["reasoning_effort_values"] = list(DEFAULT_EFFORT)

    return row


def build_latest_aliases() -> list[dict]:
    rows: list[dict] = []
    for a in LATEST_ALIASES:
        mid = a["model_id"]
        rows.append(
            {
                "provider": "openrouter",
                "model_id": mid,
                "display_name": a["display_name"],
                "context_window": a["ctx"],
                "max_output_tokens": a["max_out"],
                "input_modalities": ["text", "image"] if a.get("vision") else ["text"],
                "output_modalities": ["text"],
                "supports_function_calling": True,
                "supports_json_mode": True,
                "supports_streaming": True,
                "supports_vision": bool(a.get("vision")),
                "supports_reasoning": bool(a.get("reasoning")),
                "supports_chat_completion": True,
                "supports_responses_api": False,
                "supports_reasoning_effort": True,
                "supports_thinking_budget": False,
                "supports_anthropic_api": False,
                "supports_google_api": False,
                "supports_fim": False,
                "tokenizer_name": "",
                "knowledge_cutoff": None,
                "deprecated": False,
                "aliases": [mid.lstrip("~"), f"openrouter/{mid}"],
                "license_type": "special",
                "pricing": {
                    "input_per_1m": a["input"],
                    "output_per_1m": a["output"],
                    "currency": "USD",
                },
                "reasoning_effort_values": list(DEFAULT_EFFORT),
                "extra": {
                    "source": API_URL,
                    "docs": SOURCE_DOCS,
                    "base_url": BASE_URL,
                    "tier": "latest_alias",
                    "synthetic": True,
                    "resolves_hint": a["resolves_hint"],
                    "pricing_note": (
                        "approximate shell for ~latest convenience id; "
                        "actual billed rate is the resolved model on OpenRouter"
                    ),
                    "features": ["latest_alias", "router"],
                },
            }
        )
    return rows


def dedupe(models: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for m in models:
        mid = m["model_id"]
        if mid not in by_id:
            by_id[mid] = m
            order.append(mid)
            continue
        # merge aliases
        seen = set(by_id[mid].get("aliases") or [])
        for a in m.get("aliases") or []:
            if a not in seen and a != mid:
                by_id[mid].setdefault("aliases", []).append(a)
                seen.add(a)
    for mid, m in by_id.items():
        aliases: list[str] = []
        seen: set[str] = set()
        for a in m.get("aliases") or []:
            if a == mid or a in seen:
                continue
            aliases.append(a)
            seen.add(a)
        m["aliases"] = aliases
    return [by_id[i] for i in order]


def main() -> None:
    raw_models = fetch_models()
    models = [map_model(r) for r in raw_models if r.get("id")]
    # append synthetic ~latest aliases (not in API)
    models.extend(build_latest_aliases())
    models = dedupe(models)

    # sort: openrouter/* specials first, then ~aliases, then alpha by id
    def sort_key(m: dict) -> tuple:
        mid = m["model_id"]
        if mid.startswith("openrouter/"):
            return (0, mid)
        if mid.startswith("~"):
            return (1, mid)
        return (2, mid)

    models.sort(key=sort_key)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if INSTALLED.parent.exists():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
        and (m.get("pricing") or {}).get("input_per_1m") != DYNAMIC_PRICE
        and (m.get("pricing") or {}).get("input_per_1m") != 0.0
    )
    free_n = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") == 0.0
        and (m.get("pricing") or {}).get("output_per_1m") == 0.0
    )
    dynamic_n = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") == DYNAMIC_PRICE
    )
    extra_n = sum(1 for m in models if m.get("extra"))
    with_cache = sum(
        1 for m in models if (m.get("extra") or {}).get("cache_read_per_1m") is not None
    )
    vision_n = sum(1 for m in models if m.get("supports_vision"))
    reasoning_n = sum(1 for m in models if m.get("supports_reasoning"))
    tools_n = sum(1 for m in models if m.get("supports_function_calling"))

    from collections import Counter

    providers = Counter(
        (m.get("extra") or {}).get("native_provider") or m["model_id"].split("/")[0]
        for m in models
        if not m["model_id"].startswith("~")
    )

    print(
        f"openrouter.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / "
        f"priced={priced} / free={free_n} / dynamic={dynamic_n} / extra={extra_n})",
        flush=True,
    )
    print(
        f"  vision={vision_n} reasoning={reasoning_n} tools={tools_n} "
        f"cache={with_cache} native_providers={len(providers)}",
        flush=True,
    )
    print(f"  top providers: {providers.most_common(12)}", flush=True)
    # sample specials + a few flagships
    show = [
        "openrouter/auto",
        "openrouter/free",
        "openrouter/fusion",
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-v4-pro",
        "~anthropic/claude-sonnet-latest",
    ]
    by = {m["model_id"]: m for m in models}
    for sid in show:
        m = by.get(sid)
        if not m:
            # fuzzy
            hits = [x for x in models if sid in x["model_id"]]
            m = hits[0] if hits else None
        if not m:
            print(f"  (missing) {sid}", flush=True)
            continue
        p = m.get("pricing") or {}
        print(
            f"  {m['model_id'][:48]:48} "
            f"${p.get('input_per_1m')}/{p.get('output_per_1m')} "
            f"ctx={m['context_window']} max_out={m['max_output_tokens']}",
            flush=True,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## OpenRouter refresh ({stamp})\n\n"
        f"### Source\n"
        f"- API: `{API_URL}` (live → `_scratch_openrouter_models.json`)\n"
        f"- Docs: {SOURCE_DOCS}\n"
        f"- Apply: `scripts/_update_openrouter.py`\n\n"
        f"### Result\n"
        f"- openrouter.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced}, "
        f"free={free_n}, dynamic={dynamic_n}, extra={extra_n})\n"
        f"- vision={vision_n}, reasoning={reasoning_n}, tools={tools_n}, "
        f"cache_pricing={with_cache}\n"
        f"- native providers: {len(providers)} "
        f"(top: {providers.most_common(10)})\n"
        f"- Pricing: API per-token ×1e6 → USD/1M; "
        f"router prompt=-1 → catalog {DYNAMIC_PRICE}\n"
        f"- Cache: input_cache_read/write(/1h) in extra when present\n"
        f"- Synthetic `~*/…-latest` aliases retained ({len(LATEST_ALIASES)})\n"
        f"- Replaced thin 14-model placeholder catalog\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
