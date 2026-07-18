"""Build/refresh sakura.json — さくらインターネット さくらのAI Engine.

Sources (Playwright, 2026-07-18):
- https://ai.sakura.ad.jp/sakura-ai/ai-engine/
- Scratch: _scratch_sakura_ai_engine.html
- Manual closed models: https://manual.sakura.ad.jp/cloud/ai-engine/06-closed-model.html
- Playground: https://playground.aipf.sakura.ad.jp/

Pricing on the official page is tax-included JPY per 10,000 tokens
(or per 60s audio / 10,000 mora TTS / 100 RAG chunks). Catalog stores
USD shell at ~150 JPY/USD with exact JPY in extra.pricing_jpy.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "sakura.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\sakura.json")
LOG = WORKDIR / "provider_update_log.md"

SRC = "https://ai.sakura.ad.jp/sakura-ai/ai-engine/"
SRC_MANUAL_CLOSED = "https://manual.sakura.ad.jp/cloud/ai-engine/06-closed-model.html"
SRC_PLAYGROUND = "https://playground.aipf.sakura.ad.jp/"
SRC_CONTROL = "https://secure.sakura.ad.jp/ai/"
# JPY/USD shell for catalog primary pricing field
FX = 150.0


def jpy10k_to_usd_per_1m(jpy_per_10k: float) -> float:
    """Convert official ¥/10k-tokens → USD/1M tokens at FX."""
    jpy_per_1m = jpy_per_10k * 100.0
    return round(jpy_per_1m / FX, 6)


def jpy10k_to_jpy_per_1m(jpy_per_10k: float) -> float:
    return jpy_per_10k * 100.0


def base(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    pricing: dict | None,
    extra: dict | None = None,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    knowledge_cutoff: str | None = None,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
    vision: bool = False,
    reasoning: bool = False,
    function_calling: bool = True,
    streaming: bool = True,
    json_mode: bool = True,
    chat: bool = True,
    responses_api: bool = True,
    anthropic_api: bool = False,
    license_type: str = "api",
    preview: bool = False,
) -> dict:
    aliases = list(aliases or [])
    for a in (f"sakura/{model_id}", model_id):
        if a not in aliases and a != model_id:
            aliases.append(a)
    # preview/ prefix used on Anthropic Messages for Kimi
    if preview:
        pref = f"preview/{model_id}"
        if pref not in aliases:
            aliases.append(pref)

    in_mod = list(input_modalities or (["text", "image"] if vision else ["text"]))
    out_mod = list(output_modalities or ["text"])

    row: dict = {
        "provider": "sakura",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": in_mod,
        "output_modalities": out_mod,
        "supports_function_calling": function_calling,
        "supports_json_mode": json_mode,
        "supports_streaming": streaming,
        "supports_vision": vision or ("image" in in_mod),
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": responses_api,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": anthropic_api,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": knowledge_cutoff,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": license_type,
    }
    if pricing is not None:
        row["pricing"] = {
            "input_per_1m": pricing.get("input"),
            "output_per_1m": pricing.get("output"),
            "currency": pricing.get("currency", "USD"),
        }
    else:
        row["pricing"] = None

    row["extra"] = {
        "source": SRC,
        "playground": SRC_PLAYGROUND,
        "control_panel": SRC_CONTROL,
        "domestic_jp_cloud": True,
        "openai_compatible": True,
        "tax_included": True,
        "fx_jpy_per_usd_shell": FX,
        **(extra or {}),
    }
    return row


def chat_price(jpy_in_10k: float, jpy_out_10k: float) -> tuple[dict, dict]:
    """Return (pricing USD, jpy extra block) for chat token models."""
    pricing = {
        "input": jpy10k_to_usd_per_1m(jpy_in_10k),
        "output": jpy10k_to_usd_per_1m(jpy_out_10k),
        "currency": "USD",
    }
    jpy = {
        "input_per_10k_tokens": jpy_in_10k,
        "output_per_10k_tokens": jpy_out_10k,
        "input_per_1m": jpy10k_to_jpy_per_1m(jpy_in_10k),
        "output_per_1m": jpy10k_to_jpy_per_1m(jpy_out_10k),
        "currency": "JPY",
        "tax": "included",
    }
    return pricing, jpy


def free_tier_chat(n: int = 3000) -> dict:
    return {
        "free_plan_requests_per_month": n,
        "payg_free_requests_per_month": n,
        "plans": ["base_model_free", "payg"],
        "plan_note": (
            "free plan rate-limits after quota; payg bills per 10k tokens "
            "after free quota; plans do not auto-switch"
        ),
    }


def build() -> list[dict]:
    models: list[dict] = []

    # =====================================================================
    # Standard chat models (通常モデル)
    # =====================================================================
    p, j = chat_price(0.15, 0.75)
    models.append(
        base(
            model_id="gpt-oss-120b",
            display="Sakura gpt-oss-120b",
            ctx=131_072,
            max_out=16_384,
            pricing=p,
            extra={
                **free_tier_chat(3000),
                "pricing_jpy": j,
                "category": "chat_completions",
                "tier": "standard",
                "upstream": "openai_gpt_oss_120b",
                "features": ["chat_completions", "responses_api"],
            },
            aliases=["sakura/gpt-oss-120b", "gpt-oss-120b"],
            knowledge_cutoff="2025-06",
            reasoning=True,
            function_calling=True,
        )
    )

    p, j = chat_price(0.3, 2.5)
    models.append(
        base(
            model_id="Qwen3-Coder-480B-A35B-Instruct-FP8",
            display="Sakura Qwen3-Coder-480B-A35B-Instruct-FP8",
            ctx=262_144,
            max_out=65_536,
            pricing=p,
            extra={
                **free_tier_chat(3000),
                "pricing_jpy": j,
                "category": "chat_completions",
                "tier": "standard",
                "upstream": "qwen3_coder_480b_a35b",
                "features": ["coding", "chat_completions", "tool_use"],
                "quant": "FP8",
            },
            aliases=[
                "sakura/Qwen3-Coder-480B-A35B-Instruct-FP8",
                "Qwen3-Coder-480B-A35B-Instruct-FP8",
                "qwen3-coder-480b",
                "sakura/qwen3-coder-480b",
            ],
            knowledge_cutoff="2025-06",
            reasoning=False,
            function_calling=True,
        )
    )

    p, j = chat_price(0.15, 0.75)
    models.append(
        base(
            model_id="Qwen3-Coder-30B-A3B-Instruct",
            display="Sakura Qwen3-Coder-30B-A3B-Instruct",
            ctx=131_072,
            max_out=32_768,
            pricing=p,
            extra={
                **free_tier_chat(3000),
                "pricing_jpy": j,
                "category": "chat_completions",
                "tier": "standard",
                "upstream": "qwen3_coder_30b_a3b",
                "features": ["coding", "chat_completions", "tool_use"],
            },
            aliases=[
                "sakura/Qwen3-Coder-30B-A3B-Instruct",
                "Qwen3-Coder-30B-A3B-Instruct",
                "qwen3-coder-30b",
                "sakura/qwen3-coder-30b",
            ],
            knowledge_cutoff="2025-06",
            reasoning=False,
            function_calling=True,
        )
    )

    p, j = chat_price(0.15, 0.75)
    models.append(
        base(
            model_id="llm-jp-3.1-8x13b-instruct4",
            display="Sakura llm-jp-3.1-8x13b-instruct4",
            ctx=32_768,
            max_out=8_192,
            pricing=p,
            extra={
                **free_tier_chat(3000),
                "pricing_jpy": j,
                "category": "chat_completions",
                "tier": "standard",
                "upstream": "llm-jp / NII",
                "full_scratch_jp": True,
                "features": ["japanese", "chat_completions"],
                "params_note": "MoE 8x13B class",
            },
            aliases=[
                "sakura/llm-jp-3.1-8x13b-instruct4",
                "llm-jp-3.1-8x13b-instruct4",
                "llm-jp-3.1",
                "sakura/llm-jp-3.1",
            ],
            knowledge_cutoff="2025-03",
            reasoning=False,
            function_calling=True,
        )
    )

    # =====================================================================
    # Audio / Embeddings / TTS / RAG
    # =====================================================================
    # whisper: 0.5 JPY / 60s → $0.003333 / minute at FX=150
    models.append(
        base(
            model_id="whisper-large-v3-turbo",
            display="Sakura whisper-large-v3-turbo",
            ctx=30,  # ~30s chunks typical; not token ctx
            max_out=4_096,
            pricing=None,
            extra={
                "free_plan_requests_per_month": 50,
                "payg_free_requests_per_month": 50,
                "pricing_jpy": {
                    "per_60_seconds": 0.5,
                    "currency": "JPY",
                    "tax": "included",
                },
                "pricing_usd_shell": {
                    "per_minute": round(0.5 / FX, 6),
                    "note": f"0.5 JPY/60s @ {FX} JPY/USD",
                },
                "category": "audio_transcription",
                "tier": "standard",
                "upstream": "openai_whisper_large_v3_turbo",
                "features": ["audio_transcription"],
            },
            aliases=[
                "sakura/whisper-large-v3-turbo",
                "whisper-large-v3-turbo",
            ],
            input_modalities=["audio"],
            output_modalities=["text"],
            chat=False,
            responses_api=False,
            function_calling=False,
            json_mode=False,
            knowledge_cutoff="2024-10",
        )
    )

    p_in = jpy10k_to_usd_per_1m(2.0)
    models.append(
        base(
            model_id="multilingual-e5-large",
            display="Sakura multilingual-e5-large",
            ctx=512,
            max_out=0,
            pricing={"input": p_in, "output": 0.0, "currency": "USD"},
            extra={
                "free_plan_requests_per_month": 10_000,
                "payg_free_requests_per_month": 10_000,
                "pricing_jpy": {
                    "input_per_10k_tokens": 2.0,
                    "output": "free",
                    "input_per_1m": jpy10k_to_jpy_per_1m(2.0),
                    "currency": "JPY",
                    "tax": "included",
                },
                "category": "embeddings",
                "tier": "standard",
                "upstream": "intfloat/multilingual-e5-large",
                "features": ["embeddings"],
            },
            aliases=[
                "sakura/multilingual-e5-large",
                "multilingual-e5-large",
            ],
            output_modalities=["embedding"],
            chat=False,
            responses_api=False,
            function_calling=False,
            json_mode=False,
            knowledge_cutoff="2024-01",
        )
    )

    # VOICEVOX family — one row per speaker, shared pricing
    voicevox_speakers = [
        ("VOICEVOX:ずんだもん", "voicevox-zundamon"),
        ("VOICEVOX:東北ずん子", "voicevox-tohoku-zunko"),
        ("VOICEVOX:東北きりたん", "voicevox-tohoku-kiritan"),
        ("VOICEVOX:東北イタコ", "voicevox-tohoku-itako"),
        ("VOICEVOX:四国めたん", "voicevox-shikoku-metan"),
        ("VOICEVOX:あんこもん", "voicevox-ankomon"),
        ("VOICEVOX:冥鳴ひまり", "voicevox-meimei-himari"),
        ("VOICEVOX:春日部つむぎ", "voicevox-kasukabe-tsumugi"),
    ]
    for official_name, mid in voicevox_speakers:
        models.append(
            base(
                model_id=mid,
                display=f"Sakura {official_name}",
                ctx=1_024,
                max_out=0,
                pricing=None,
                extra={
                    "free_plan_requests_per_month": 50,
                    "payg_free_requests_per_month": 50,
                    "pricing_jpy": {
                        "per_10k_mora": 3.0,
                        "currency": "JPY",
                        "tax": "included",
                        "mora_note": "1 mora ≈ 1 kana length unit",
                    },
                    "pricing_usd_shell": {
                        "per_10k_mora": round(3.0 / FX, 6),
                    },
                    "category": "text_to_speech",
                    "tier": "standard",
                    "upstream": "VOICEVOX",
                    "official_model_name": official_name,
                    "features": ["tts"],
                    "license_manual": (
                        "https://manual.sakura.ad.jp/cloud/ai-engine/05-tts-licenses.html"
                    ),
                },
                aliases=[
                    f"sakura/{mid}",
                    mid,
                    official_name,
                    f"sakura/{official_name}",
                ],
                input_modalities=["text"],
                output_modalities=["audio"],
                chat=False,
                responses_api=False,
                function_calling=False,
                json_mode=False,
                knowledge_cutoff=None,
            )
        )

    # RAG document service (not a model, but metered capability)
    models.append(
        base(
            model_id="rag-document",
            display="Sakura RAG Document Store",
            ctx=0,
            max_out=0,
            pricing=None,
            extra={
                "pricing_jpy": {
                    "per_100_chunks": 3.0,
                    "currency": "JPY",
                    "tax": "included",
                    "free_tier": False,
                },
                "pricing_usd_shell": {
                    "per_100_chunks": round(3.0 / FX, 6),
                },
                "category": "rag",
                "tier": "standard",
                "features": ["document_store", "retrieval"],
                "note": "no free quota; billed per 100 chunks on both plans",
            },
            aliases=["sakura/rag-document", "rag-document", "sakura-rag"],
            chat=False,
            responses_api=False,
            function_calling=False,
            json_mode=False,
            license_type="api",
        )
    )

    # =====================================================================
    # Closed models (申請必須) — PLaMo 2.0-31B, cotomi v3
    # =====================================================================
    models.append(
        base(
            model_id="PLaMo-2.0-31B",
            display="Sakura PLaMo 2.0-31B (closed)",
            ctx=32_768,
            max_out=4_096,
            pricing=None,
            extra={
                "source": SRC,
                "closed_manual": SRC_MANUAL_CLOSED,
                "category": "chat_completions",
                "tier": "closed",
                "upstream_provider": "pfn",
                "upstream_model": "plamo-2.0-prime / PLaMo 2.0-31B",
                "application_required": True,
                "free_plan": "not_eligible",
                "pricing_note": "quote / manual; control-panel application required",
                "related_native": "japanese.json pfn/plamo-2.0-prime (deprecated) / plamo-3.0-prime",
            },
            aliases=[
                "sakura/PLaMo-2.0-31B",
                "PLaMo-2.0-31B",
                "plamo-2.0-31b",
                "sakura/plamo-2.0-31b",
            ],
            knowledge_cutoff="2025-07",
            function_calling=True,
            license_type="api",
        )
    )

    models.append(
        base(
            model_id="cotomi-v3",
            display="Sakura cotomi v3 (closed)",
            ctx=128_000,
            max_out=8_192,
            pricing=None,
            extra={
                "source": SRC,
                "closed_manual": SRC_MANUAL_CLOSED,
                "category": "chat_completions",
                "tier": "closed",
                "upstream_provider": "nec",
                "upstream_model": "cotomi v3",
                "application_required": True,
                "free_plan": "not_eligible",
                "pricing_note": "quote / manual; control-panel application required",
                "related_native": "japanese.json nec/cotomi-v3",
                "trademark": "cotomi is a registered trademark of NEC",
            },
            aliases=[
                "sakura/cotomi-v3",
                "cotomi-v3",
                "sakura/cotomi_v3",
            ],
            knowledge_cutoff="2025-07",
            function_calling=True,
            license_type="api",
        )
    )

    # =====================================================================
    # Public preview models
    # =====================================================================
    previews = [
        # model_id, display, ctx, max_out, jpy_in_10k, jpy_out_10k, since, vision, reasoning, anthropic, notes
        (
            "Qwen3-0.6B-cpu",
            "Sakura Qwen3-0.6B-cpu (preview)",
            32_768,
            8_192,
            0.01,
            0.03,
            "2025-10-09",
            False,
            False,
            False,
            {"upstream": "Qwen3-0.6B", "runtime": "cpu"},
        ),
        (
            "Phi-4-mini-instruct-cpu",
            "Sakura Phi-4-mini-instruct-cpu (preview)",
            128_000,
            4_096,
            0.01,
            0.03,
            "2025-10-09",
            False,
            False,
            False,
            {"upstream": "microsoft/Phi-4-mini-instruct", "runtime": "cpu"},
        ),
        (
            "Qwen3-VL-30B-A3B-Instruct",
            "Sakura Qwen3-VL-30B-A3B-Instruct (preview)",
            131_072,
            32_768,
            0.1,
            0.3,
            "2025-10-21",
            True,
            False,
            False,
            {"upstream": "Qwen3-VL-30B-A3B", "vision": True},
        ),
        (
            "Phi-4-multimodal-instruct",
            "Sakura Phi-4-multimodal-instruct (preview)",
            128_000,
            4_096,
            0.1,
            0.3,
            "2025-10-21",
            True,
            False,
            False,
            {
                "upstream": "microsoft/Phi-4-multimodal-instruct",
                "vision": True,
                "input_modalities_note": "text+image (+audio on upstream)",
            },
        ),
        (
            "Kimi-K2.6",
            "Sakura Kimi-K2.6 (preview)",
            262_144,
            32_768,
            0.6,
            3.0,
            "2026-05-12",
            False,
            True,
            True,  # Anthropic Messages API available for this model only
            {
                "upstream": "moonshotai/Kimi-K2.6",
                "anthropic_messages_api": True,
                "anthropic_model_id": "preview/Kimi-K2.6",
                "claude_code_compatible": True,
            },
        ),
        (
            "Qwen3.6-35B-A3B",
            "Sakura Qwen3.6-35B-A3B (preview)",
            131_072,
            32_768,
            0.3,
            1.5,
            "2026-06-04",
            False,
            True,
            False,
            {"upstream": "Qwen3.6-35B-A3B"},
        ),
        (
            "gemma-4-31B-it",
            "Sakura gemma-4-31B-it (preview)",
            131_072,
            16_384,
            0.24,
            0.96,
            "2026-06-30",
            False,
            False,
            False,
            {
                "upstream": "google/gemma-4-31B-it",
                "news": (
                    "https://cloud.sakura.ad.jp/news/2026/06/30/"
                    "aiengine_gemma-4-31b-it_pubpreview/"
                ),
            },
        ),
    ]
    for mid, disp, ctx, mout, jin, jout, since, vis, rea, anth, notes in previews:
        p, j = chat_price(jin, jout)
        models.append(
            base(
                model_id=mid,
                display=disp,
                ctx=ctx,
                max_out=mout,
                pricing=p,
                extra={
                    **free_tier_chat(3000),
                    "pricing_jpy": j,
                    "category": "chat_completions",
                    "tier": "public_preview",
                    "preview_since": since,
                    "preview_note": (
                        "may end without notice; stability/quality not guaranteed; "
                        "price may change when GA"
                    ),
                    **notes,
                },
                aliases=[f"sakura/{mid}", mid, mid.lower()],
                knowledge_cutoff=since[:7],
                vision=vis,
                reasoning=rea,
                anthropic_api=anth,
                preview=True,
                function_calling=True,
            )
        )

    # Embedding preview
    p_in = jpy10k_to_usd_per_1m(3.0)
    models.append(
        base(
            model_id="Qwen3-Embedding-4B-FP16",
            display="Sakura Qwen3-Embedding-4B (FP16, preview)",
            ctx=8_192,
            max_out=0,
            pricing={"input": p_in, "output": 0.0, "currency": "USD"},
            extra={
                "free_plan_requests_per_month": 10_000,
                "payg_free_requests_per_month": 10_000,
                "pricing_jpy": {
                    "input_per_10k_tokens": 3.0,
                    "output": "free",
                    "input_per_1m": jpy10k_to_jpy_per_1m(3.0),
                    "currency": "JPY",
                    "tax": "included",
                },
                "category": "embeddings",
                "tier": "public_preview",
                "preview_since": "2025-12-16",
                "upstream": "Qwen3-Embedding-4B",
                "quant": "FP16",
                "official_model_name": "Qwen3-Embedding-4B(FP16)",
                "features": ["embeddings"],
            },
            aliases=[
                "sakura/Qwen3-Embedding-4B-FP16",
                "Qwen3-Embedding-4B(FP16)",
                "Qwen3-Embedding-4B",
                "qwen3-embedding-4b",
            ],
            output_modalities=["embedding"],
            chat=False,
            responses_api=False,
            function_calling=False,
            json_mode=False,
            preview=True,
            knowledge_cutoff="2025-12",
        )
    )

    # Keep a soft default alias for older clients expecting sakura-default
    models.append(
        base(
            model_id="sakura-default",
            display="SAKURA AI Engine (default → gpt-oss-120b)",
            ctx=131_072,
            max_out=16_384,
            pricing=chat_price(0.15, 0.75)[0],
            extra={
                **free_tier_chat(3000),
                "pricing_jpy": chat_price(0.15, 0.75)[1],
                "category": "chat_completions",
                "tier": "alias_default",
                "resolves_to": "gpt-oss-120b",
                "note": (
                    "legacy placeholder id; prefer explicit model_id. "
                    "Mapped to gpt-oss-120b standard chat model."
                ),
            },
            aliases=["sakura/sakura-default", "sakura-default", "sakura"],
            knowledge_cutoff="2025-06",
            reasoning=True,
            function_calling=True,
            deprecated=False,
        )
    )

    return dedupe(models)


def dedupe(models: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for m in models:
        mid = m["model_id"]
        if mid not in by_id:
            by_id[mid] = m
            order.append(mid)
            continue
        seen = set(by_id[mid].get("aliases") or [])
        for a in m.get("aliases") or []:
            if a not in seen:
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
    models = build()
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
    )
    extra_n = sum(1 for m in models if m.get("extra"))
    by_tier: dict[str, int] = {}
    for m in models:
        t = (m.get("extra") or {}).get("tier", "?")
        by_tier[t] = by_tier.get(t, 0) + 1

    print(
        f"sakura.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / "
        f"priced={priced} / extra={extra_n})",
        flush=True,
    )
    print(f"  tiers: {by_tier}", flush=True)
    for m in models:
        p = m.get("pricing") or {}
        pin, pout = p.get("input_per_1m"), p.get("output_per_1m")
        flag = " [deprecated]" if m.get("deprecated") else ""
        tier = (m.get("extra") or {}).get("tier", "")
        if pin is not None:
            print(
                f"  {m['model_id'][:42]:42} ${pin}/${pout} "
                f"ctx={m['context_window']} [{tier}]{flag}",
                flush=True,
            )
        else:
            print(
                f"  {m['model_id'][:42]:42} (metered/quote) "
                f"ctx={m['context_window']} [{tier}]{flag}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Sakura (さくらのAI Engine) refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Product: {SRC}\n"
        f"- Closed models manual: {SRC_MANUAL_CLOSED}\n"
        f"- Playground: {SRC_PLAYGROUND}\n"
        f"- Scratch: `_scratch_sakura_ai_engine.html`\n"
        f"- Apply: `scripts/_update_sakura.py`\n\n"
        f"### Result\n"
        f"- sakura.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, "
        f"priced={priced}, extra={extra_n})\n"
        f"- Tiers: {by_tier}\n"
        f"- Standard chat: gpt-oss-120b ¥0.15/0.75 per 10k "
        f"(USD shell $0.10/$0.50); Qwen3-Coder 480B/30B; llm-jp-3.1\n"
        f"- Preview: Kimi-K2.6 (Anthropic Messages), Qwen3.6-35B, "
        f"gemma-4-31B-it (2026-06-30), Phi-4 mini/mm, Qwen3-VL, "
        f"Qwen3-0.6B-cpu, Qwen3-Embedding-4B\n"
        f"- Closed (application): PLaMo 2.0-31B, cotomi v3\n"
        f"- Also: whisper, e5-large, VOICEVOX×8, RAG document meter\n"
        f"- Free tier 3,000 chat req/mo; tax-included JPY official\n"
        f"- Replaced placeholder sakura-default with full catalog "
        f"(default alias → gpt-oss-120b)\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
