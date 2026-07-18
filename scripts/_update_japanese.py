"""Build/refresh japanese.json — multi-vendor domestic JP LLM aggregator.

Sources (Playwright + official pages, 2026-07-18):
- PFN PLaMo API: https://plamo.preferredai.jp/api
- PFN PR PLaMo 3.0 Prime GA: https://www.preferred.jp/ja/news/pr20260622/
- PFN tech blog: https://tech.preferred.jp/ja/blog/plamo-3-0-prime-release/
- SoftBank Cloud PF Type A: https://www.softbank.jp/biz/services/ai/cloud-pf-type-a/
- SoftBank Sarashina API (legacy): https://www.softbank.jp/business/service/ai/sarashina-api/
- SB Intuitions Sarashina3 blog: https://www.sbintuitions.co.jp/blog/entry/2026/06/30/sarashina3-mini-nano/
- SB Intuitions press 2026-06-30 Sarashina3 on Cloud PF Type A
- NTT DATA tsuzumi 2: https://www.nttdata.com/jp/ja/lineup/tsuzumi/
- Azure Marketplace tsuzumi 2 Instruct
- GENNAI / 源内 7-model comparison (third-party synthesis of official claims)
- Scratch: _scratch_jp_*.html

japanese.json is a multi-vendor aggregator. Each model keeps its native
``provider`` field (pfn / softbank / ntt / nec / elyza / fujitsu /
customer-cloud). sakura (さくらインターネット AI Engine) is a separate
provider file (sakura.json), not folded here.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "japanese.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\japanese.json")
LOG = WORKDIR / "provider_update_log.md"

# ---- canonical sources -------------------------------------------------
SRC_PLAMO_API = "https://plamo.preferredai.jp/api"
SRC_PLAMO_PR = "https://www.preferred.jp/ja/news/pr20260622/"
SRC_PLAMO_BLOG = "https://tech.preferred.jp/ja/blog/plamo-3-0-prime-release/"
SRC_PLAMO_BASE = "https://api.platform.preferredai.jp/v1"
SRC_CLOUD_PF = "https://www.softbank.jp/biz/services/ai/cloud-pf-type-a/"
SRC_SARASHINA_API = "https://www.softbank.jp/business/service/ai/sarashina-api/"
SRC_SARASHINA3_BLOG = (
    "https://www.sbintuitions.co.jp/blog/entry/2026/06/30/sarashina3-mini-nano/"
)
SRC_SARASHINA3_PRESS = (
    "https://www.sbintuitions.co.jp/news/press/2026/06/30/sarashina3-cloud-pf/"
)
SRC_TSUZUMI = "https://www.nttdata.com/jp/ja/lineup/tsuzumi/"
SRC_TSUZUMI_RD = "https://www.rd.ntt/research/LLM_tsuzumi.html"
SRC_TSUZUMI_AZURE = (
    "https://marketplace.microsoft.com/en-us/product/"
    "1681106214127.nttdata-tsuzumi-2-instruct-offer"
)
SRC_GENNAI = "https://www.digital.go.jp/"  # 源内 / GENAI selection
SRC_LLM7 = "https://ai-revolution.co.jp/media/japan-llm-7-comparison/"

# PLaMo Standard plan (JPY / 1M tokens). Official page 2026-07-18.
# USD mirror uses ~150 JPY/USD → ¥60≈$0.40, ¥250≈$1.67 (catalog keeps
# historical 2.x USD of $0.40/$1.60 for continuity; 3.0 uses same USD shell
# with exact JPY in extra).
PLAMO_JPY_IN = 60.0
PLAMO_JPY_OUT = 250.0
PLAMO_USD_IN = 0.40
PLAMO_USD_OUT = 1.67
# Azure Marketplace secondary token table cited by third-party (per 1M):
TSUZUMI_AZURE_IN = 4.0  # $0.004 / 1K
TSUZUMI_AZURE_OUT = 1100.0  # $1.1 / 1K
TSUZUMI_GPU_HOUR = 0.76  # paygo-surcharge A100/H100 GPU hour (Marketplace)


def base(
    *,
    provider: str,
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
    effort: bool = False,
    effort_values: list[str] | None = None,
    function_calling: bool = True,
    streaming: bool = True,
    json_mode: bool = False,
    chat: bool = True,
    license_type: str = "api",
    currency: str = "USD",
) -> dict:
    aliases = list(aliases or [])
    # dual alias: bare + provider/id
    bare = model_id
    if bare.startswith(f"{provider}/"):
        bare = bare[len(provider) + 1 :]
    prefixed = f"{provider}/{bare}"
    for a in (prefixed, bare):
        if a not in aliases and a != model_id:
            aliases.append(a)

    in_mod = list(input_modalities or (["text", "image"] if vision else ["text"]))
    out_mod = list(output_modalities or ["text"])

    row: dict = {
        "provider": provider,
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
        "supports_responses_api": False,
        "supports_reasoning_effort": effort,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
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
            "currency": pricing.get("currency", currency),
        }
    else:
        row["pricing"] = None
    if effort and effort_values:
        row["reasoning_effort_values"] = effort_values

    row["extra"] = {
        "aggregator": "japanese",
        "native_provider": provider,
        **(extra or {}),
    }
    return row


def build() -> list[dict]:
    models: list[dict] = []

    # =====================================================================
    # PFN / Preferred Networks — PLaMo
    # =====================================================================
    # Flagship GA 2026-06-22. OpenAI-compatible. Reasoning via reasoning_effort.
    models.append(
        base(
            provider="pfn",
            model_id="plamo-3.0-prime",
            display="PFN PLaMo 3.0 Prime",
            ctx=262_144,  # 256K official
            max_out=20_000,  # third-party measured ~20K / request
            pricing={"input": PLAMO_USD_IN, "output": PLAMO_USD_OUT},
            extra={
                "source": SRC_PLAMO_API,
                "press": SRC_PLAMO_PR,
                "tech_blog": SRC_PLAMO_BLOG,
                "base_url": SRC_PLAMO_BASE,
                "model_version": "PLaMo 3.0 Prime",
                "ga_date": "2026-06-22",
                "full_scratch": True,
                "openai_compatible": True,
                "features": [
                    "reasoning_toggle",
                    "non_reasoning",
                    "tool_calling",
                    "structured_output",
                    "json_mode",
                    "zdr_standard_plus",
                    "on_prem",
                    "bedrock_marketplace",
                    "snowflake",
                ],
                "reasoning_effort": ["none", "medium"],
                "reasoning_effort_note": (
                    "only none|medium accepted; high/low → HTTP 422"
                ),
                "reasoning_cost_note": (
                    "third-party: latency ~6–17×, tokens ~12–35× when reasoning"
                ),
                "pricing_jpy_per_1m": {
                    "input": PLAMO_JPY_IN,
                    "output": PLAMO_JPY_OUT,
                    "plan": "standard",
                    "note": (
                        "≤128K Input/Output unit price; "
                        "128K+ same rate during GA campaign period"
                    ),
                },
                "plans": {
                    "free": {
                        "input_jpy": 0,
                        "output_jpy": 0,
                        "status": "preparing",
                        "limits": "rate/volume limited",
                    },
                    "standard": {
                        "input_jpy": PLAMO_JPY_IN,
                        "output_jpy": PLAMO_JPY_OUT,
                        "zdr": True,
                        "no_training_on_inputs": True,
                    },
                    "provider": {
                        "input_jpy": "custom",
                        "output_jpy": "custom",
                        "reasoning_full_text": True,
                        "priority": True,
                    },
                },
                "campaign": {
                    "new_signup_credit_tokens": 10_000_000,
                    "through": "2026-07-31",
                    "credit_valid_days": 30,
                    "io_ratio_assumed": "4:1",
                },
                "currency_note": (
                    f"primary pricing USD shell ≈¥{PLAMO_JPY_IN}/¥{PLAMO_JPY_OUT} "
                    f"at ~150 JPY/USD; exact bill is JPY on Standard plan"
                ),
                "gennai_selected": True,
                "params_note": "flagship closed weights (Prime); base open separately",
            },
            aliases=[
                "pfn/plamo-3.0-prime",
                "plamo-3.0-prime",
                "plamo-3-prime",
                "plamo3-prime",
                "PLaMo-3.0-Prime",
            ],
            knowledge_cutoff="2026-06",
            reasoning=True,
            effort=True,
            effort_values=["none", "medium"],
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    # Legacy 2.2 (reasoning intro) — keep for alias continuity, mark deprecated
    models.append(
        base(
            provider="pfn",
            model_id="plamo-2.2-prime",
            display="PFN PLaMo 2.2 Prime",
            ctx=32_768,
            max_out=8_192,
            pricing={"input": 0.40, "output": 1.60},
            extra={
                "source": SRC_PLAMO_API,
                "status": "superseded_by_plamo_3_0_prime",
                "superseded_by": "plamo-3.0-prime",
                "ga_note": "2026-01-28 class; 3.0 GA 2026-06-22",
                "pricing_jpy_per_1m": {"input": 60.0, "output": 250.0},
                "features": ["reasoning", "openai_compatible"],
            },
            aliases=[
                "pfn/plamo-2.2-prime",
                "plamo-2.2-prime",
            ],
            knowledge_cutoff="2026-03",
            reasoning=True,
            function_calling=True,
            json_mode=True,
            deprecated=True,
            license_type="api",
        )
    )

    # Legacy 2.0 — 源内 selection vintage; superseded
    models.append(
        base(
            provider="pfn",
            model_id="plamo-2.0-prime",
            display="PFN PLaMo 2.0 Prime",
            ctx=32_768,
            max_out=4_096,
            pricing={"input": 0.40, "output": 1.60},
            extra={
                "source": SRC_PLAMO_API,
                "status": "superseded_by_plamo_3_0_prime",
                "superseded_by": "plamo-3.0-prime",
                "params": "31B",
                "gennai_selected_as": "plamo-2.0-prime",
                "nikkei_award": "2025 日経優秀製品・サービス賞 最優秀賞",
                "pricing_jpy_per_1m": {"input": 60.0, "output": 250.0},
            },
            aliases=[
                "pfn/plamo-2.0-prime",
                "plamo-2.0-prime",
            ],
            knowledge_cutoff="2025-07",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            deprecated=True,
            license_type="api",
        )
    )

    # =====================================================================
    # SoftBank / SB Intuitions — Sarashina
    # =====================================================================
    # Sarashina3 on Cloud PF Type A from 2026-06-30. Token rates quote-only.
    models.append(
        base(
            provider="softbank",
            model_id="sarashina3-mini",
            display="SoftBank Sarashina3 mini",
            ctx=128_000,  # not officially restated; keep 源内-era 128K default
            max_out=8_192,
            pricing=None,
            extra={
                "source": SRC_CLOUD_PF,
                "press": SRC_SARASHINA3_PRESS,
                "tech_blog": SRC_SARASHINA3_BLOG,
                "legacy_api": SRC_SARASHINA_API,
                "channel": "cloud_pf_type_a",
                "available_from": "2026-06-30",
                "developer": "SB Intuitions",
                "full_scratch": True,
                "pretrain_tokens": "30T+",
                "model_class": "instruct_non_reasoning",
                "features": [
                    "chat_completions",
                    "tool_use_agent",
                    "math",
                    "coding",
                    "instruction_following",
                ],
                "deployment": {
                    "dedicated": "monthly_fixed_gpu",
                    "on_demand": "payg_shared_gpu",
                },
                "pricing_note": (
                    "Cloud PF Type A: Dedicated monthly fixed / On-Demand payg; "
                    "per-token table not public — contact SoftBank"
                ),
                "gennai_selected": True,
                "series": "Sarashina3",
            },
            aliases=[
                "softbank/sarashina3-mini",
                "sarashina3-mini",
                "sarashina-3-mini",
                "sb-intuitions/sarashina3-mini",
            ],
            knowledge_cutoff="2026-06",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    models.append(
        base(
            provider="softbank",
            model_id="sarashina3-nano",
            display="SoftBank Sarashina3 nano",
            ctx=128_000,
            max_out=8_192,
            pricing=None,
            extra={
                "source": SRC_CLOUD_PF,
                "press": SRC_SARASHINA3_PRESS,
                "tech_blog": SRC_SARASHINA3_BLOG,
                "channel": "cloud_pf_type_a",
                "available_from": "2026-06-30",
                "developer": "SB Intuitions",
                "full_scratch": True,
                "model_class": "instruct_lightweight",
                "features": [
                    "chat_completions",
                    "high_throughput",
                    "extraction",
                    "classification",
                    "summarization",
                ],
                "pricing_note": (
                    "Cloud PF Type A quote; optimized for bulk simple tasks"
                ),
                "series": "Sarashina3",
            },
            aliases=[
                "softbank/sarashina3-nano",
                "sarashina3-nano",
                "sarashina-3-nano",
                "sb-intuitions/sarashina3-nano",
            ],
            knowledge_cutoff="2026-06",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    models.append(
        base(
            provider="softbank",
            model_id="sarashina3-guard",
            display="SoftBank Sarashina3 guard",
            ctx=32_768,
            max_out=1_024,
            pricing=None,
            extra={
                "source": SRC_CLOUD_PF,
                "press": SRC_SARASHINA3_PRESS,
                "channel": "cloud_pf_type_a",
                "available_from": "2026-06-30",
                "developer": "SB Intuitions",
                "model_class": "guardrail",
                "features": [
                    "harmful_category_detection",
                    "input_output_filter",
                    "no_text_generation",
                ],
                "pricing_note": "Cloud PF Type A quote",
                "series": "Sarashina3",
            },
            aliases=[
                "softbank/sarashina3-guard",
                "sarashina3-guard",
            ],
            knowledge_cutoff="2026-06",
            reasoning=False,
            function_calling=False,
            json_mode=True,
            chat=True,
            license_type="api",
        )
    )

    models.append(
        base(
            provider="softbank",
            model_id="sarashina3-embedding",
            display="SoftBank Sarashina3 embedding",
            ctx=8_192,
            max_out=0,
            pricing=None,
            extra={
                "source": SRC_CLOUD_PF,
                "press": SRC_SARASHINA3_PRESS,
                "channel": "cloud_pf_type_a",
                "available_from": "2026-06-30",
                "developer": "SB Intuitions",
                "model_class": "embedding",
                "features": [
                    "embeddings_api",
                    "task_type_switch_7",
                    "dimension_truncation_robust",
                ],
                "pricing_note": "Cloud PF Type A quote",
                "series": "Sarashina3",
            },
            aliases=[
                "softbank/sarashina3-embedding",
                "sarashina3-embedding",
            ],
            knowledge_cutoff="2026-06",
            reasoning=False,
            function_calling=False,
            json_mode=False,
            chat=False,
            output_modalities=["embedding"],
            license_type="api",
        )
    )

    models.append(
        base(
            provider="softbank",
            model_id="sarashina3-rerank",
            display="SoftBank Sarashina3 rerank",
            ctx=8_192,
            max_out=1_024,
            pricing=None,
            extra={
                "source": SRC_CLOUD_PF,
                "press": SRC_SARASHINA3_PRESS,
                "channel": "cloud_pf_type_a",
                "available_from": "2026-06-30",
                "developer": "SB Intuitions",
                "model_class": "reranker",
                "features": [
                    "rerank_api",
                    "rag_precision",
                    "task_type_switch_5",
                    "japanese_instruction",
                ],
                "pricing_note": "Cloud PF Type A quote",
                "series": "Sarashina3",
            },
            aliases=[
                "softbank/sarashina3-rerank",
                "sarashina3-rerank",
            ],
            knowledge_cutoff="2026-06",
            reasoning=False,
            function_calling=False,
            json_mode=True,
            chat=False,
            license_type="api",
        )
    )

    # Legacy Sarashina2 mini — API new-signup closed 2026-06-16 → Cloud PF
    models.append(
        base(
            provider="softbank",
            model_id="sarashina2-mini",
            display="SoftBank Sarashina2 mini",
            ctx=128_000,
            max_out=4_096,
            pricing=None,
            extra={
                "source": SRC_SARASHINA_API,
                "status": "migrating_to_cloud_pf_type_a",
                "superseded_by": "sarashina3-mini",
                "new_signup_closed": "2026-06-16",
                "developer": "SB Intuitions",
                "features": [
                    "chat_completions",
                    "embeddings_api_sarashina2_embedding",
                    "guard_sarashina2_guard",
                ],
                "pricing_note": "legacy quote / annual credit; prefer Sarashina3",
                "gennai_selected_as": "sarashina2-mini",
            },
            aliases=[
                "softbank/sarashina2-mini",
                "sarashina2-mini",
                "sarashina-2-mini",
            ],
            knowledge_cutoff="2025-05",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            deprecated=True,
            license_type="api",
        )
    )

    # =====================================================================
    # NTT / NTT DATA — tsuzumi 2
    # =====================================================================
    models.append(
        base(
            provider="ntt",
            model_id="tsuzumi-2",
            display="NTT tsuzumi 2",
            ctx=128_000,
            max_out=8_192,
            pricing=None,  # primary is GPU-hour / enterprise quote
            extra={
                "source": SRC_TSUZUMI,
                "rd": SRC_TSUZUMI_RD,
                "azure_marketplace": SRC_TSUZUMI_AZURE,
                "params": "~30B",
                "full_scratch": True,
                "single_gpu": True,
                "domains": ["finance", "government", "medical", "rag", "doc_qa"],
                "vision_announced": "2026-05-19",
                "channels": [
                    "on_prem",
                    "private_cloud",
                    "ntt_group_b2b",
                    "azure_marketplace_managed_compute",
                ],
                "azure_pricing": {
                    "model": "managed_compute_not_pure_token",
                    "gpu_hour_usd": TSUZUMI_GPU_HOUR,
                    "meters": [
                        "paygo-surcharge-a100-gpu",
                        "paygo-surcharge-h100-gpu",
                    ],
                    "secondary_token_table_per_1m_usd": {
                        "input": TSUZUMI_AZURE_IN,
                        "output": TSUZUMI_AZURE_OUT,
                        "source": "third_party_summary_of_azure_listing",
                        "note": (
                            "treat as secondary; Marketplace emphasizes "
                            "GPU-hour + 'price varies'"
                        ),
                    },
                },
                "contact": "nttd_tsuzumi@hml.nttdata.co.jp",
                "gennai_selected": True,
                "pricing_note": (
                    "B2B quote / on-prem; Azure = managed GPU-hour "
                    f"(~${TSUZUMI_GPU_HOUR}/GPU-h) not pure token PAYG"
                ),
            },
            aliases=[
                "ntt/tsuzumi-2",
                "tsuzumi-2",
                "tsuzumi2",
                "nttdata/tsuzumi-2",
                "nttdata-tsuzumi-2-instruct",
            ],
            knowledge_cutoff="2025-10",
            vision=True,
            reasoning=False,
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    # =====================================================================
    # NEC — cotomi v3
    # =====================================================================
    models.append(
        base(
            provider="nec",
            model_id="cotomi-v3",
            display="NEC cotomi v3",
            ctx=128_000,
            max_out=8_192,
            pricing=None,
            extra={
                "source": "https://jpn.nec.com/LLM/cotomi.html",
                "source_note": (
                    "official page may return Akamai Access Denied; "
                    "specs from GENNAI materials + sakura AI Engine channel"
                ),
                "params_estimate": "~13B class (series history)",
                "features": [
                    "keigo_specialty",
                    "domain_terminology",
                    "ai_agent",
                    "mcp_native",
                    "webarena_agent_eval",
                ],
                "webarena_score_claimed": 0.804,
                "power_vs_v2": "approx_half",
                "channels": [
                    "nec_enterprise",
                    "on_prem",
                    "sakura_ai_engine",
                ],
                "sakura_ai_engine": {
                    "free_calls_per_month": 3000,
                    "overage": "payg_undisclosed",
                },
                "gennai_selected": True,
                "pricing_note": (
                    "enterprise quote; sakura AI Engine free tier 3,000 calls/mo"
                ),
                # sakura is separate provider file; note channel only
                "related_provider_file": "sakura.json",
            },
            aliases=[
                "nec/cotomi-v3",
                "cotomi-v3",
                "cotomi_v3",
                "cotomi3",
            ],
            knowledge_cutoff="2025-07",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    # =====================================================================
    # ELYZA / KDDI — Llama-3.1-ELYZA-JP-70B
    # =====================================================================
    models.append(
        base(
            provider="elyza",
            model_id="llama-3.1-elyza-jp-70b",
            display="ELYZA Llama-3.1-ELYZA-JP-70B",
            ctx=128_000,
            max_out=8_192,
            pricing=None,
            extra={
                "source": "https://elyza.ai/",
                "base_model": "Meta Llama 3.1 70B",
                "params": "70B",
                "origin": "additional_japanese_sft_on_llama_not_full_scratch",
                "applicant": "KDDI + ELYZA joint (源内)",
                "features": [
                    "long_context_128k",
                    "japanese_instruction_following",
                    "general_purpose_70b",
                ],
                "related_products": [
                    "ELYZA-Shortcut-1.0-Qwen-32B",
                    "ELYZA-LLM-Diffusion",
                    "ELYZA Works",
                ],
                "channels": ["enterprise_api_quote", "demo_free", "elyza_works"],
                "gennai_selected": True,
                "pricing_note": "enterprise inquiry; public demo free",
                "license_base": "Llama 3.1 Community License (base weights)",
            },
            aliases=[
                "elyza/llama-3.1-elyza-jp-70b",
                "llama-3.1-elyza-jp-70b",
                "Llama-3.1-ELYZA-JP-70B",
                "elyza-jp-70b",
            ],
            knowledge_cutoff="2024-07",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    # =====================================================================
    # Fujitsu × Cohere — Takane 32B
    # =====================================================================
    models.append(
        base(
            provider="fujitsu",
            model_id="takane-32b",
            display="Fujitsu Takane 32B",
            ctx=128_000,
            max_out=8_192,
            pricing=None,
            extra={
                "source": "https://www.fujitsu.com/global/about/resources/news/",
                "kozuchi": "Fujitsu Kozuchi / Enterprise AI Factory",
                "partner": "Cohere Inc.",
                "params": "32B",
                "origin": "cohere_based_japanese_enterprise_not_full_scratch",
                "features": [
                    "admin_document_processing",
                    "1bit_quantization",
                    "jglue_strong",
                    "private_deployment",
                ],
                "quantization": {
                    "memory_reduction_claimed": "94%",
                    "speedup_claimed": "3x",
                    "accuracy_retention_claimed": "89%",
                },
                "channels": [
                    "fujitsu_kozuchi",
                    "enterprise_on_prem",
                    "private_cloud",
                ],
                "gennai_selected": True,
                "pricing_note": "enterprise quote only via Fujitsu",
            },
            aliases=[
                "fujitsu/takane-32b",
                "takane-32b",
                "takane",
                "Takane-32B",
            ],
            knowledge_cutoff="2025-10",
            reasoning=True,  # enterprise reasoning / decision-support positioning
            function_calling=True,
            json_mode=True,
            license_type="api",
        )
    )

    # =====================================================================
    # Customer Cloud — CC Gov-LLM
    # =====================================================================
    models.append(
        base(
            provider="customer-cloud",
            model_id="cc-gov-llm",
            display="Customer Cloud CC Gov-LLM",
            ctx=128_000,
            max_out=8_192,
            pricing=None,
            extra={
                "source": "https://customer-cloud.co.jp/",
                "focus": "government_local_llm_security",
                "full_scratch_claimed": True,
                "features": [
                    "air_gapped_local",
                    "no_external_cloud_dependency",
                    "admin_docs",
                    "citizen_response",
                    "policy_support",
                ],
                "channels": ["on_prem_local", "government_contract"],
                "gennai_selected": True,
                "pricing_note": "government / enterprise contract; not public API",
                "license_type_note": "deployed_local_not_public_api",
            },
            aliases=[
                "customer-cloud/cc-gov-llm",
                "cc-gov-llm",
                "cc_gov_llm",
                "gov-llm",
            ],
            knowledge_cutoff="2026-01",
            reasoning=False,
            function_calling=True,
            json_mode=True,
            license_type="api",
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
    by_prov: dict[str, int] = {}
    for m in models:
        by_prov[m["provider"]] = by_prov.get(m["provider"], 0) + 1

    print(
        f"japanese.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / "
        f"priced={priced} / extra={extra_n})",
        flush=True,
    )
    print(f"  providers: {by_prov}", flush=True)
    for m in models:
        p = m.get("pricing") or {}
        pin, pout = p.get("input_per_1m"), p.get("output_per_1m")
        flag = " [deprecated]" if m.get("deprecated") else ""
        prov = m["provider"]
        if pin is not None:
            cur = p.get("currency", "USD")
            print(
                f"  {prov:16} {m['model_id']:28} "
                f"{cur} {pin}/{pout} ctx={m['context_window']}{flag}",
                flush=True,
            )
        else:
            print(
                f"  {prov:16} {m['model_id']:28} "
                f"(quote/free) ctx={m['context_window']}{flag}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Japanese (multi-vendor) refresh ({stamp})\n\n"
        f"### Source\n"
        f"- PLaMo API: {SRC_PLAMO_API}\n"
        f"- PLaMo PR GA: {SRC_PLAMO_PR}\n"
        f"- PLaMo blog: {SRC_PLAMO_BLOG}\n"
        f"- Cloud PF Type A: {SRC_CLOUD_PF}\n"
        f"- Sarashina3 blog: {SRC_SARASHINA3_BLOG}\n"
        f"- tsuzumi 2: {SRC_TSUZUMI}\n"
        f"- Azure tsuzumi: {SRC_TSUZUMI_AZURE}\n"
        f"- GENNAI / 7-model synthesis: {SRC_LLM7}\n"
        f"- Scratch: `_scratch_jp_*.html`, `_scratch_jp_plamo_api3.html`\n"
        f"- Apply: `scripts/_update_japanese.py`\n\n"
        f"### Result\n"
        f"- japanese.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, "
        f"priced={priced}, extra={extra_n})\n"
        f"- Providers: {by_prov}\n"
        f"- PFN: plamo-3.0-prime GA 256K, Standard ¥60/¥250 "
        f"(USD shell ${PLAMO_USD_IN}/${PLAMO_USD_OUT}); "
        f"2.0/2.2 deprecated\n"
        f"- SoftBank: Sarashina3 mini/nano/guard/embedding/rerank "
        f"on Cloud PF Type A (2026-06-30); sarashina2-mini deprecated\n"
        f"- NTT tsuzumi-2: vision + Azure GPU-hour "
        f"(~${TSUZUMI_GPU_HOUR}/h); secondary token $4/$1100\n"
        f"- NEC cotomi-v3 / ELYZA 70B / Fujitsu Takane 32B / "
        f"CC Gov-LLM: enterprise quote, 源内 selected\n"
        f"- sakura kept separate (sakura.json) — next refresh\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
