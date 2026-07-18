"""Build/refresh xiaomi.json (MiMo) from official mimo.mi.com docs.

Sources (Playwright live 2026-07-18):
- https://mimo.mi.com/docs/en-US/price/pay-as-you-go
- https://mimo.mi.com/docs/en-US/quick-start/summary/model
- V2 series deprecated 2026-06-30; V2.5 is current.
- Overseas (USD) pricing used for pricing fields; CNY kept in extra.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "xiaomi.json"
INSTALLED_DIR = Path(r"F:\Python314\Lib\site-packages\llmcapa\data")
LOG = WORKDIR / "provider_update_log.md"
SOURCE_PRICE = "https://mimo.mi.com/docs/en-US/price/pay-as-you-go"
SOURCE_MODELS = "https://mimo.mi.com/docs/en-US/quick-start/summary/model"


def base(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    input_modalities: list[str],
    output_modalities: list[str],
    pricing: dict | None = None,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    reasoning: bool = False,
    vision: bool = False,
    fc: bool = False,
    json_mode: bool = False,
    chat: bool = True,
    license_type: str = "api",
    knowledge_cutoff: str | None = None,
    extra: dict | None = None,
) -> dict:
    aliases = list(aliases or [])
    bare = model_id.split("/")[-1]
    for a in (bare, f"xiaomi/{bare}", f"mimo/{bare}"):
        if a not in aliases and a != model_id:
            aliases.append(a)
    row = {
        "provider": "xiaomi",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_function_calling": fc,
        "supports_json_mode": json_mode,
        "supports_streaming": True,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": True,  # Responses API is live
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": knowledge_cutoff,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": license_type,
        "extra": {
            "source_pricing": SOURCE_PRICE,
            "source_models": SOURCE_MODELS,
            **(extra or {}),
        },
    }
    if pricing is not None:
        row["pricing"] = pricing
    return row


def build() -> list[dict]:
    models: list[dict] = []

    # Text generation — official model IDs are bare (mimo-v2.5-pro / mimo-v2.5)
    models.append(
        base(
            model_id="mimo-v2.5-pro",
            display="Xiaomi MiMo-V2.5-Pro",
            ctx=1_000_000,
            max_out=128_000,
            input_modalities=["text"],
            output_modalities=["text"],
            pricing={
                "input_per_1m": 0.435,
                "output_per_1m": 0.87,
                "currency": "USD",
            },
            aliases=["xiaomi/mimo-v2.5-pro"],
            reasoning=True,
            fc=True,
            json_mode=True,
            chat=True,
            extra={
                "region": "overseas",
                "cached_input_per_1m": 0.0036,
                "cache_miss_input_per_1m": 0.435,
                "cny_pricing": {
                    "cache_hit_per_1m": 0.025,
                    "cache_miss_per_1m": 3.0,
                    "output_per_1m": 6.0,
                    "currency": "CNY",
                },
                "rpm": 100,
                "tpm": 10_000_000,
                "capabilities": [
                    "text_generation",
                    "deep_thinking",
                    "streaming",
                    "function_call",
                    "structured_output",
                    "web_search",
                ],
                "web_search_overseas_per_1000": 5.0,
                "web_search_cny_per_1000": 34.0,
                "official_table": "cache_hit=$0.0036 cache_miss=$0.435 output=$0.87",
            },
        )
    )
    models.append(
        base(
            model_id="mimo-v2.5",
            display="Xiaomi MiMo-V2.5",
            ctx=1_000_000,
            max_out=128_000,
            input_modalities=["text", "image", "audio", "video"],
            output_modalities=["text"],
            pricing={
                "input_per_1m": 0.14,
                "output_per_1m": 0.28,
                "currency": "USD",
            },
            aliases=["xiaomi/mimo-v2.5"],
            reasoning=True,
            vision=True,
            fc=True,
            json_mode=True,
            chat=True,
            extra={
                "region": "overseas",
                "cached_input_per_1m": 0.0028,
                "cache_miss_input_per_1m": 0.14,
                "cny_pricing": {
                    "cache_hit_per_1m": 0.02,
                    "cache_miss_per_1m": 1.0,
                    "output_per_1m": 2.0,
                    "currency": "CNY",
                },
                "rpm": 100,
                "tpm": 10_000_000,
                "capabilities": [
                    "text_generation",
                    "full_modal_understanding",
                    "deep_thinking",
                    "streaming",
                    "function_call",
                    "structured_output",
                    "web_search",
                ],
                "web_search_overseas_per_1000": 5.0,
                "web_search_cny_per_1000": 34.0,
                "official_table": "cache_hit=$0.0028 cache_miss=$0.14 output=$0.28",
            },
        )
    )

    # Closed beta high-speed variant (retain; deprecation TBD)
    models.append(
        base(
            model_id="mimo-v2.5-pro-ultraspeed",
            display="Xiaomi MiMo-V2.5-Pro-UltraSpeed",
            ctx=1_000_000,
            max_out=128_000,
            input_modalities=["text"],
            output_modalities=["text"],
            pricing={
                "input_per_1m": 1.305,
                "output_per_1m": 2.61,
                "currency": "USD",
            },
            aliases=["xiaomi/mimo-v2.5-pro-ultraspeed"],
            reasoning=True,
            fc=True,
            json_mode=True,
            chat=True,
            knowledge_cutoff="2024-12",
            extra={
                "status": "closed_beta",
                "approx_output_tps": 1000,
                "note": "Closed beta extended; deprecation dates announced per resource",
            },
        )
    )

    # ASR — overseas $0.074 / hour
    models.append(
        base(
            model_id="mimo-v2.5-asr",
            display="Xiaomi MiMo-V2.5-ASR",
            ctx=8192,
            max_out=2000,
            input_modalities=["audio"],
            output_modalities=["text"],
            pricing={
                "input_per_1m": 0.0,
                "output_per_1m": 0.0,
                "currency": "USD",
            },
            aliases=["xiaomi/mimo-v2.5-asr"],
            chat=False,
            license_type="api",
            extra={
                "region": "overseas",
                "price_per_hour": 0.074,
                "price_unit": "hour",
                "cny_pricing": {"per_hour": 0.5, "currency": "CNY"},
                "rpm": 100,
                "tpm": 10_000,
                "official_table": "overseas $0.074/h; mainland ¥0.5/h",
            },
        )
    )

    # TTS series — free for limited time (both regions)
    for mid, disp, caps in [
        ("mimo-v2.5-tts", "Xiaomi MiMo-V2.5-TTS", ["speech_synthesis"]),
        (
            "mimo-v2.5-tts-voiceclone",
            "Xiaomi MiMo-V2.5-TTS VoiceClone",
            ["speech_synthesis", "timbre_cloning"],
        ),
        (
            "mimo-v2.5-tts-voicedesign",
            "Xiaomi MiMo-V2.5-TTS VoiceDesign",
            ["speech_synthesis", "timbre_design"],
        ),
    ]:
        models.append(
            base(
                model_id=mid,
                display=disp,
                ctx=8192,
                max_out=8192,
                input_modalities=["text"],
                output_modalities=["speech", "audio"],
                pricing={
                    "input_per_1m": 0.0,
                    "output_per_1m": 0.0,
                    "currency": "USD",
                },
                aliases=[f"xiaomi/{mid}"],
                chat=False,
                license_type="free",
                extra={
                    "pricing_status": "free_limited_time",
                    "capabilities": caps,
                    "rpm": 100,
                    "tpm": 10_000_000,
                    "note": "Official pay-as-you-go: free for a limited time (CN + overseas)",
                },
            )
        )

    # Deprecated V2 series (official 2026-06-30)
    for mid, disp, modalities, vision in [
        ("mimo-v2-pro", "Xiaomi MiMo-V2-Pro", ["text"], False),
        ("mimo-v2-omni", "Xiaomi MiMo-V2-Omni", ["text", "image", "audio", "video"], True),
        ("mimo-v2-flash", "Xiaomi MiMo-V2-Flash", ["text"], False),
        ("mimo-v2-tts", "Xiaomi MiMo-V2-TTS", ["text"], False),
    ]:
        out_mod = ["speech", "audio"] if mid.endswith("tts") else ["text"]
        models.append(
            base(
                model_id=mid,
                display=disp,
                ctx=1_000_000 if not mid.endswith("tts") else 8192,
                max_out=128_000 if not mid.endswith("tts") else 8192,
                input_modalities=modalities,
                output_modalities=out_mod,
                pricing=None,
                aliases=[f"xiaomi/{mid}"],
                deprecated=True,
                vision=vision,
                chat=not mid.endswith("tts"),
                extra={
                    "deprecated_on": "2026-06-30",
                    "migration": "mimo-v2.5 series",
                },
            )
        )

    return models


def main() -> None:
    models = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if INSTALLED_DIR.exists():
        shutil.copy2(OUT, INSTALLED_DIR / OUT.name)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"xiaomi.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        if m.get("deprecated"):
            continue
        p = m.get("pricing") or {}
        print(
            f"  {m['model_id']:32} in={p.get('input_per_1m')} out={p.get('output_per_1m')} "
            f"ctx={m['context_window']}",
            flush=True,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Xiaomi MiMo refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Models: {SOURCE_MODELS}\n"
        f"- Pricing: {SOURCE_PRICE} (Playwright live)\n"
        f"- Apply: `scripts/_update_xiaomi.py`\n\n"
        f"### Result\n"
        f"- xiaomi.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- **mimo-v2.5-pro**: $0.435/$0.87; cache hit $0.0036; 1M/128k\n"
        f"- **mimo-v2.5**: $0.14/$0.28 (was $0.105/$0.28); cache hit $0.0028; multimodal\n"
        f"- **mimo-v2.5-asr**: $0.074/hour overseas\n"
        f"- TTS series free limited-time; voiceclone/voicedesign added\n"
        f"- V2 series marked deprecated 2026-06-30\n"
        f"- Model IDs normalized to bare official IDs\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
