"""Build/refresh microsoft.json from Azure Foundry Microsoft pricing + lifecycle.

Sources (Playwright):
- https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/microsoft/
- https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/model-lifecycle-retirement
  (Retired Foundry Models; last updated ~2026-04-25)
- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai
- https://ai.azure.com/catalog/publishers/microsoft
- https://microsoft.ai/news/today-were-announcing-3-new-world-class-mai-models-available-in-foundry/
- OpenRouter microsoft/* (cross-check only)
- azure_foundry.json context windows for Microsoft-owned slice
- Scratch: _scratch_ms_pricing_live2.html, _scratch_ms_retired_text.txt,
  _scratch_ms_mai_docs.html, _scratch_ms_catalog_publisher.html

Canonical PAYG (USD / 1M tokens, Global unless noted):
  Phi-3-mini* $0.13/$0.52; Phi-3-small* $0.15/$0.60; Phi-3-medium* $0.17/$0.68
  Phi-3.5-mini $0.13/$0.52; Phi-3.5-MoE $0.16/$0.64
  Phi-4 $0.125/$0.50; Phi-4-mini* $0.075/$0.30; Phi-4-multimodal text+image $0.08/$0.32
  Phi-4-multimodal audio $4/$0.32; Phi-4-reasoning* $0.125/$0.50
  MAI-DS-R1 Global $1.35/$5.40 (Regional $1.485/$5.94); PTU min 100 @ $1/hr
  MAI-Image-2 Global $5/$33; MAI-Image-2-Efficient Global $5/$19.50
Fine-tune (subset): train $3/1M tokens, host $0.80/hr, same usage rates.

Context notes:
  Foundry pricing table lists Phi-4 as 128K but model card / catalog / OpenRouter
  are 16K — use 16384. Phi-4-reasoning / plus pricing table = 32K.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "microsoft.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\microsoft.json")
LOG = WORKDIR / "provider_update_log.md"

SOURCE_PRICING = (
    "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/microsoft/"
)
SOURCE_RETIRED = (
    "https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/"
    "model-lifecycle-retirement"
)
SOURCE_MAI_DOCS = (
    "https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/"
    "use-foundry-models-mai"
)
SOURCE_CATALOG = "https://ai.azure.com/catalog/publishers/microsoft"
SOURCE_MAI_NEWS = (
    "https://microsoft.ai/news/"
    "today-were-announcing-3-new-world-class-mai-models-available-in-foundry/"
)

# Fine-tune rates shared by Phi subset on Foundry pricing page
FT_TRAIN = 3.0
FT_HOST_HR = 0.80


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
    json_mode: bool = False,
    chat: bool = True,
    license_type: str = "api",
) -> dict:
    aliases = list(aliases or [])
    bare = model_id
    # OpenRouter-style microsoft/<kebab>
    kebab = bare.replace("_", "-")
    # lower-kebab for common API ids
    lower = kebab
    # if PascalCase Foundry id, also add lower-kebab form
    if any(c.isupper() for c in bare):
        # Phi-4-mini-instruct -> phi-4-mini-instruct
        parts = []
        buf = ""
        for ch in bare:
            if ch == "-":
                if buf:
                    parts.append(buf.lower())
                    buf = ""
                parts.append("-")
            else:
                buf += ch
        if buf:
            parts.append(buf.lower())
        lower = "".join(parts)
        # collapse accidental double handling
        lower = lower.replace("--", "-")

    for a in (f"microsoft/{lower}", lower, bare):
        if a and a not in aliases and a != model_id:
            aliases.append(a)
    # de-dupe preserve order
    seen: set[str] = set()
    aliases = [a for a in aliases if not (a in seen or seen.add(a))]

    in_mod = list(input_modalities or (["text", "image"] if vision else ["text"]))
    out_mod = list(output_modalities or ["text"])

    row: dict = {
        "provider": "microsoft",
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
    }
    if pricing is not None:
        row["pricing"] = {
            "input_per_1m": pricing.get("input"),
            "output_per_1m": pricing.get("output"),
            "currency": "USD",
        }
    else:
        row["pricing"] = None

    row["extra"] = {
        "source": SOURCE_PRICING,
        "retired_docs": SOURCE_RETIRED,
        "catalog": SOURCE_CATALOG,
        **(extra or {}),
    }
    return row


def ft_extra(
    *,
    replacement: str | None = None,
    retired: str | None = None,
    notes: dict | None = None,
    include_ft: bool = True,
) -> dict:
    e: dict = {
        "deployment": "foundry_serverless_payg",
        "currency": "USD",
    }
    if include_ft:
        e["finetune_train_per_1m"] = FT_TRAIN
        e["finetune_host_per_hour"] = FT_HOST_HR
    if replacement:
        e["replacement"] = replacement
    if retired:
        e["retirement_date"] = retired
    if notes:
        e.update(notes)
    return e


def service(
    model_id: str,
    display: str,
    *,
    ctx: int = 128_000,
    max_out: int = 16_384,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
    vision: bool = False,
    chat: bool = False,
    extra: dict | None = None,
) -> dict:
    return base(
        model_id=model_id,
        display=display,
        ctx=ctx,
        max_out=max_out,
        pricing=None,
        input_modalities=input_modalities or ["text"],
        output_modalities=output_modalities or ["text"],
        vision=vision,
        reasoning=False,
        function_calling=False,
        streaming=True,
        json_mode=False,
        chat=chat,
        license_type="license",
        extra={
            "category": "azure_ai_service",
            "pricing_note": "metered Azure AI service; not Foundry token PAYG",
            **(extra or {}),
        },
    )


def free_weight(
    model_id: str,
    display: str,
    *,
    ctx: int = 128_000,
    max_out: int = 16_384,
    vision: bool = False,
    reasoning: bool = False,
    chat: bool = False,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
    aliases: list[str] | None = None,
    extra: dict | None = None,
) -> dict:
    return base(
        model_id=model_id,
        display=display,
        ctx=ctx,
        max_out=max_out,
        pricing=None,
        aliases=aliases,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        vision=vision,
        reasoning=reasoning,
        function_calling=False,
        chat=chat,
        license_type="free",
        extra={
            "category": "open_weight_or_community",
            "pricing_note": "weights / community; host-dependent pricing",
            **(extra or {}),
        },
    )


def build() -> list[dict]:
    models: list[dict] = []

    # =====================================================================
    # Active Phi-4 family (Foundry PAYG)
    # =====================================================================
    models.append(
        base(
            model_id="Phi-4",
            display="Phi-4",
            ctx=16_384,  # catalog/OpenRouter; pricing table incorrectly lists 128K
            max_out=16_384,
            pricing={"input": 0.125, "output": 0.50},
            knowledge_cutoff="2024-06",
            function_calling=True,
            json_mode=True,
            chat=True,
            aliases=["phi-4", "microsoft/phi-4"],
            extra=ft_extra(
                notes={
                    "foundry_pricing_context_listed": "128K",
                    "context_note": (
                        "Use 16K from model card/catalog; Foundry pricing "
                        "table lists 128K incorrectly"
                    ),
                    "params": "14B",
                }
            ),
        )
    )
    models.append(
        base(
            model_id="Phi-4-mini-instruct",
            display="Phi-4 mini instruct",
            ctx=128_000,
            max_out=4_096,
            pricing={"input": 0.075, "output": 0.30},
            function_calling=True,
            json_mode=True,
            chat=True,
            aliases=["phi-4-mini-instruct", "phi-4-mini", "Phi-4-mini"],
            extra=ft_extra(
                notes={
                    "foundry_row": "Phi-4-mini",
                    "params": "3.8B",
                }
            ),
        )
    )
    models.append(
        base(
            model_id="Phi-4-multimodal-instruct",
            display="Phi-4 multimodal instruct",
            ctx=128_000,
            max_out=4_096,
            pricing={"input": 0.08, "output": 0.32},
            input_modalities=["text", "image", "audio"],
            output_modalities=["text"],
            vision=True,
            function_calling=True,
            chat=True,
            aliases=["phi-4-multimodal-instruct", "phi-4-multimodal"],
            extra={
                **ft_extra(include_ft=False),
                "audio_input_per_1m": 4.0,
                "audio_output_per_1m": 0.32,
                "text_image_input_per_1m": 0.08,
                "text_image_output_per_1m": 0.32,
                "primary_pricing": "text+image tokens; audio rates in extra",
                "foundry_rows": [
                    "Phi-4-multimodal, text and image",
                    "Phi-4-multimodal, audio",
                ],
            },
        )
    )
    models.append(
        base(
            model_id="Phi-4-mini-reasoning",
            display="Phi-4 mini reasoning",
            ctx=128_000,
            max_out=4_096,
            pricing={"input": 0.075, "output": 0.30},
            reasoning=True,
            function_calling=True,
            chat=True,
            aliases=["phi-4-mini-reasoning"],
            extra=ft_extra(include_ft=False, notes={"foundry_row": "Phi-4-mini-reasoning"}),
        )
    )
    models.append(
        base(
            model_id="Phi-4-reasoning",
            display="Phi-4 reasoning",
            ctx=32_768,
            max_out=4_096,
            pricing={"input": 0.125, "output": 0.50},
            reasoning=True,
            function_calling=True,
            chat=True,
            aliases=["phi-4-reasoning"],
            extra=ft_extra(
                include_ft=False,
                notes={"foundry_row": "Phi-4-reasoning", "foundry_context": "32K"},
            ),
        )
    )
    models.append(
        base(
            model_id="Phi-4-reasoning-plus",
            display="Phi-4 reasoning plus",
            ctx=32_768,  # Foundry pricing table; some catalog rows show 128K
            max_out=4_096,
            pricing={"input": 0.125, "output": 0.50},
            reasoning=True,
            function_calling=True,
            chat=True,
            aliases=[
                "phi-4-reasoning-plus",
                "microsoft-phi-4-reasoning-plus",
            ],
            extra=ft_extra(
                include_ft=False,
                notes={
                    "foundry_row": "Phi-4-reasoning-plus",
                    "foundry_context": "32K",
                    "catalog_context_alt": 128_000,
                    "params": "14B",
                },
            ),
        )
    )
    # Catalog-only Phi-4 variants (no separate Foundry PAYG row)
    models.append(
        free_weight(
            "Phi-4-mini-flash-reasoning",
            "Phi-4 mini flash reasoning",
            ctx=128_000,
            reasoning=True,
            chat=True,
            extra={"foundry_payg": False, "family": "phi-4"},
        )
    )
    models.append(
        free_weight(
            "Phi-4-Reasoning-Vision-15B",
            "Phi-4 Reasoning Vision 15B",
            ctx=128_000,
            vision=True,
            reasoning=True,
            chat=True,
            input_modalities=["text", "image"],
            extra={"foundry_payg": False, "family": "phi-4", "params": "15B"},
        )
    )
    models.append(
        free_weight(
            "Phi-4-mini-reasoning-onnx",
            "Phi-4 mini reasoning (ONNX)",
            ctx=128_000,
            reasoning=True,
            chat=True,
            extra={"foundry_payg": False, "runtime": "onnx", "family": "phi-4"},
        )
    )
    models.append(
        free_weight(
            "Phi-4-reasoning-plus-onnx",
            "Phi-4 reasoning plus (ONNX)",
            ctx=128_000,
            reasoning=True,
            chat=True,
            extra={"foundry_payg": False, "runtime": "onnx", "family": "phi-4"},
        )
    )

    # =====================================================================
    # Retired Phi-3 / Phi-3.5 (still listed on pricing; mark deprecated)
    # Retirement: 2025-08-30 (Learn retired models)
    # =====================================================================
    retired_phi = "2025-08-30"
    for mid, display, ctx, pin, pout, repl, ft in [
        (
            "Phi-3-mini-4k-instruct",
            "Phi-3 mini 4k instruct",
            4_096,
            0.13,
            0.52,
            "Phi-4-mini-instruct",
            True,
        ),
        (
            "Phi-3-mini-128k-instruct",
            "Phi-3 mini 128k instruct",
            128_000,
            0.13,
            0.52,
            "Phi-4-mini-instruct",
            True,
        ),
        (
            "Phi-3-small-8k-instruct",
            "Phi-3 small 8k instruct",
            8_192,
            0.15,
            0.60,
            "Phi-4-mini-instruct",
            False,
        ),
        (
            "Phi-3-small-128k-instruct",
            "Phi-3 small 128k instruct",
            128_000,
            0.15,
            0.60,
            "Phi-4-mini-instruct",
            False,
        ),
        (
            "Phi-3-medium-4k-instruct",
            "Phi-3 medium 4k instruct",
            4_096,
            0.17,
            0.68,
            "Phi-4",
            True,
        ),
        (
            "Phi-3-medium-128k-instruct",
            "Phi-3 medium 128k instruct",
            128_000,
            0.17,
            0.68,
            "Phi-4",
            True,
        ),
        (
            "Phi-3.5-mini-instruct",
            "Phi-3.5 mini instruct",
            131_072,
            0.13,
            0.52,
            "Phi-4-mini-instruct",
            True,
        ),
        (
            "Phi-3.5-MoE-instruct",
            "Phi-3.5 MoE instruct",
            128_000,
            0.16,
            0.64,
            "Phi-4-mini-instruct",
            True,
        ),
    ]:
        models.append(
            base(
                model_id=mid,
                display=display,
                ctx=ctx,
                max_out=min(ctx, 4_096) if ctx <= 8_192 else 4_096,
                pricing={"input": pin, "output": pout},
                deprecated=True,
                function_calling=True,
                chat=True,
                aliases=[mid.lower()],
                extra=ft_extra(
                    replacement=repl,
                    retired=retired_phi,
                    include_ft=ft,
                ),
            )
        )

    # Vision variants (Phi-3.5-vision retired; Phi-3-vision treated as legacy)
    models.append(
        base(
            model_id="Phi-3.5-vision-instruct",
            display="Phi-3.5 vision instruct",
            ctx=131_072,
            max_out=4_096,
            pricing={"input": 0.13, "output": 0.52},  # same class as mini when listed
            deprecated=True,
            input_modalities=["text", "image"],
            vision=True,
            function_calling=True,
            chat=True,
            aliases=["phi-3.5-vision-instruct"],
            extra=ft_extra(
                replacement="Phi-4-mini-instruct",
                retired=retired_phi,
                include_ft=False,
                notes={
                    "pricing_note": (
                        "No separate vision row on Foundry Microsoft table; "
                        "aligned to Phi-3.5-mini PAYG when historically sold"
                    )
                },
            ),
        )
    )
    models.append(
        base(
            model_id="Phi-3-vision-128k-instruct",
            display="Phi-3 vision 128k instruct",
            ctx=128_000,
            max_out=4_096,
            pricing=None,
            deprecated=True,
            input_modalities=["text", "image"],
            vision=True,
            function_calling=True,
            chat=True,
            license_type="free",
            aliases=["phi-3-vision-128k-instruct"],
            extra=ft_extra(
                replacement="Phi-4-multimodal-instruct",
                retired=retired_phi,
                include_ft=False,
                notes={"pricing_note": "open-weight / catalog; no current PAYG row"},
            ),
        )
    )

    # Legacy simplified ids that existed in prior microsoft.json
    models.append(
        base(
            model_id="phi-3-mini-instruct",
            display="Phi-3 mini instruct (legacy id)",
            ctx=128_000,
            max_out=4_096,
            pricing={"input": 0.13, "output": 0.52},
            deprecated=True,
            chat=True,
            aliases=["Phi-3-mini-instruct"],
            extra=ft_extra(
                replacement="Phi-4-mini-instruct",
                retired=retired_phi,
                include_ft=True,
                notes={"maps_to": "Phi-3-mini-128k-instruct"},
            ),
        )
    )

    # =====================================================================
    # MAI family
    # =====================================================================
    models.append(
        base(
            model_id="MAI-DS-R1",
            display="MAI-DS-R1",
            ctx=163_840,  # OpenRouter 164K class
            max_out=16_384,
            pricing={"input": 1.35, "output": 5.40},
            deprecated=True,
            reasoning=True,
            function_calling=True,
            chat=True,
            knowledge_cutoff="2024-07",
            aliases=["mai-ds-r1", "microsoft/mai-ds-r1"],
            extra={
                "source": SOURCE_PRICING,
                "retired_docs": SOURCE_RETIRED,
                "deployment": "foundry_serverless_payg",
                "global_input_per_1m": 1.35,
                "global_output_per_1m": 5.40,
                "regional_input_per_1m": 1.485,
                "regional_output_per_1m": 5.94,
                "ptu_min": 100,
                "ptu_hourly": 1.0,
                "retirement_date": "2026-02-27",
                "replacement": "Any DeepSeek model available in the Model catalog",
                "primary_pricing": "Global PAYG",
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Image-2",
            display="MAI Image 2",
            ctx=128_000,
            max_out=16_384,
            pricing={"input": 5.0, "output": 33.0},
            input_modalities=["text"],
            output_modalities=["image"],
            vision=True,
            function_calling=False,
            chat=False,
            aliases=["mai-image-2", "microsoft/mai-image-2"],
            extra={
                "source": SOURCE_PRICING,
                "mai_docs": SOURCE_MAI_DOCS,
                "foundry_row": "MAI-Image-2 Global",
                "prompt_context_tokens_max": 32_000,
                "availability": "preview",
                "apis": ["mai/v1/images/generations"],
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Image-2e",
            display="MAI Image 2e (Efficient)",
            ctx=128_000,
            max_out=16_384,
            pricing={"input": 5.0, "output": 19.50},
            input_modalities=["text"],
            output_modalities=["image"],
            vision=True,
            function_calling=False,
            chat=False,
            aliases=[
                "mai-image-2e",
                "MAI-Image-2-Efficient",
                "mai-image-2-efficient",
            ],
            extra={
                "source": SOURCE_PRICING,
                "mai_docs": SOURCE_MAI_DOCS,
                "foundry_row": "MAI-Image-2-Efficient Global",
                "prompt_context_tokens_max": 32_000,
                "availability": "preview",
                "apis": ["mai/v1/images/generations"],
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Image-2.5",
            display="MAI Image 2.5",
            ctx=128_000,
            max_out=16_384,
            pricing={"input": 5.0, "output": 33.0},
            input_modalities=["text", "image"],
            output_modalities=["image"],
            vision=True,
            function_calling=False,
            chat=False,
            aliases=["mai-image-2.5", "microsoft/mai-image-2.5"],
            extra={
                "source": SOURCE_PRICING,
                "mai_docs": SOURCE_MAI_DOCS,
                "mai_news": SOURCE_MAI_NEWS,
                "pricing_note": (
                    "Foundry Microsoft table lists MAI-Image-2 Global $5/$33; "
                    "2.5 not yet a separate row — primary aligned to Image-2. "
                    "OpenRouter Azure effective ~$5/$47 observed."
                ),
                "openrouter_list_input_per_1m": 5.0,
                "prompt_context_tokens_max": 32_000,
                "availability": "preview",
                "apis": [
                    "mai/v1/images/generations",
                    "mai/v1/images/edits",
                ],
                "model_version_example": "2026-06-02",
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Image-2.5-Flash",
            display="MAI Image 2.5 Flash",
            ctx=128_000,
            max_out=16_384,
            pricing={"input": 5.0, "output": 19.50},
            input_modalities=["text", "image"],
            output_modalities=["image"],
            vision=True,
            function_calling=False,
            chat=False,
            aliases=["mai-image-2.5-flash"],
            extra={
                "source": SOURCE_PRICING,
                "mai_docs": SOURCE_MAI_DOCS,
                "pricing_note": (
                    "No separate Foundry row; aligned to MAI-Image-2-Efficient "
                    "Global $5/$19.50 as flash/efficient tier proxy"
                ),
                "prompt_context_tokens_max": 32_000,
                "availability": "preview",
                "apis": [
                    "mai/v1/images/generations",
                    "mai/v1/images/edits",
                ],
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Voice-1",
            display="MAI Voice 1",
            ctx=25_000,
            max_out=16_384,
            pricing=None,
            input_modalities=["text", "audio"],
            output_modalities=["text", "audio"],
            function_calling=False,
            chat=False,
            aliases=["mai-voice-1"],
            extra={
                "source": SOURCE_CATALOG,
                "mai_news": SOURCE_MAI_NEWS,
                "category": "speech_tts",
                "pricing_note": "not on Foundry Microsoft token table; Azure Speech metered",
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Voice-2",
            display="MAI Voice 2",
            ctx=25_000,
            max_out=16_384,
            pricing=None,
            input_modalities=["text", "audio"],
            output_modalities=["text", "audio"],
            function_calling=False,
            chat=False,
            aliases=["mai-voice-2", "microsoft/mai-voice-2"],
            extra={
                "source": SOURCE_CATALOG,
                "mai_news": SOURCE_MAI_NEWS,
                "category": "speech_tts",
                "pricing_note": (
                    "not on Foundry Microsoft token table; OpenRouter lists "
                    "~$22/M characters (Azure Speech)"
                ),
                "openrouter_approx_per_1m_chars": 22.0,
                "output_formats": ["mp3", "pcm_24khz"],
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Transcribe-1",
            display="MAI Transcribe 1",
            ctx=25_000,
            max_out=16_384,
            pricing=None,
            input_modalities=["audio"],
            output_modalities=["text"],
            function_calling=False,
            chat=False,
            aliases=["mai-transcribe-1"],
            extra={
                "source": SOURCE_CATALOG,
                "mai_news": SOURCE_MAI_NEWS,
                "category": "speech_stt",
                "pricing_note": "not on Foundry Microsoft token table; duration-based",
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Transcribe-1.5",
            display="MAI Transcribe 1.5",
            ctx=25_000,
            max_out=16_384,
            pricing=None,
            input_modalities=["audio"],
            output_modalities=["text"],
            function_calling=False,
            chat=False,
            aliases=["mai-transcribe-1.5", "microsoft/mai-transcribe-1.5"],
            extra={
                "source": SOURCE_CATALOG,
                "mai_news": SOURCE_MAI_NEWS,
                "category": "speech_stt",
                "pricing_note": (
                    "not on Foundry Microsoft token table; OpenRouter ~$0.36/hour "
                    "duration billing (Azure Speech fast transcription)"
                ),
                "openrouter_approx_per_hour": 0.36,
                "locales": "100+ BCP-47",
            },
        )
    )
    # Announced product surface (catalog / microsoft.ai) — no Foundry PAYG row yet
    models.append(
        base(
            model_id="MAI-Thinking-1",
            display="MAI Thinking 1",
            ctx=256_000,
            max_out=16_384,
            pricing=None,
            reasoning=True,
            function_calling=True,
            chat=True,
            aliases=["mai-thinking-1"],
            extra={
                "source": SOURCE_CATALOG,
                "mai_news": SOURCE_MAI_NEWS,
                "params": "35B",
                "pricing_note": "announced; no Foundry Microsoft PAYG row yet",
                "availability": "product_surface",
            },
        )
    )
    models.append(
        base(
            model_id="MAI-Code-1-Flash",
            display="MAI Code 1 Flash",
            ctx=128_000,
            max_out=16_384,
            pricing=None,
            function_calling=True,
            chat=True,
            aliases=["mai-code-1-flash"],
            extra={
                "source": SOURCE_MAI_NEWS,
                "pricing_note": "announced for Copilot/VS Code; no Foundry PAYG row yet",
                "availability": "product_surface",
                "use_case": "coding_agent",
            },
        )
    )

    # =====================================================================
    # Model router
    # =====================================================================
    models.append(
        base(
            model_id="model-router",
            display="Model Router",
            ctx=128_000,
            max_out=16_384,
            pricing=None,
            function_calling=True,
            chat=True,
            aliases=["Model-Router", "microsoft/model-router"],
            extra={
                "source": SOURCE_CATALOG,
                "category": "router",
                "pricing_note": (
                    "routes to underlying Foundry models; billed at target model rates"
                ),
            },
        )
    )

    # =====================================================================
    # Azure AI services (unpriced service meters)
    # =====================================================================
    models.append(
        service(
            "Azure-AI-Content-Safety",
            "Azure AI Content Safety",
            extra={"family": "ai_services"},
        )
    )
    models.append(
        service(
            "Azure-AI-Content-Understanding",
            "Azure AI Content Understanding",
            ctx=25_000,
            input_modalities=["text", "image", "audio"],
            vision=True,
            extra={"family": "ai_services"},
        )
    )
    models.append(
        service(
            "Azure-AI-Document-Intelligence",
            "Azure AI Document Intelligence",
            extra={"family": "ai_services"},
        )
    )
    models.append(
        service(
            "Azure-AI-Vision",
            "Azure AI Vision",
            input_modalities=["text", "image"],
            vision=True,
            extra={"family": "ai_services"},
        )
    )
    models.append(
        service(
            "Azure-Content-Understanding-Layout",
            "Azure Content Understanding Layout",
            extra={"family": "ai_services"},
        )
    )
    models.append(
        service(
            "Azure-Content-Understanding-Read",
            "Azure Content Understanding Read",
            extra={"family": "ai_services"},
        )
    )
    for mid, disp in [
        (
            "Azure-Language-Conversational-PII-redaction",
            "Azure Language Conversational PII redaction",
        ),
        (
            "Azure-Language-Document-PII-redaction",
            "Azure Language Document PII redaction",
        ),
        ("Azure-Language-Language-detection", "Azure Language detection"),
        (
            "Azure-Language-Text-Analytics-for-Health",
            "Azure Language Text Analytics for Health",
        ),
        ("Azure-Language-Text-PII-redaction", "Azure Language Text PII redaction"),
    ]:
        models.append(service(mid, disp, extra={"family": "language"}))

    models.append(
        service(
            "Azure-Speech-Speech-Translation",
            "Azure Speech Translation",
            input_modalities=["text", "audio"],
            extra={"family": "speech"},
        )
    )
    models.append(
        service(
            "Azure-Speech-Speech-to-text",
            "Azure Speech to text",
            ctx=25_000,
            input_modalities=["audio"],
            extra={"family": "speech"},
        )
    )
    models.append(
        service(
            "Azure-Speech-Text-to-speech",
            "Azure Text to speech",
            ctx=25_000,
            input_modalities=["text"],
            output_modalities=["audio"],
            extra={"family": "speech"},
        )
    )
    models.append(
        service(
            "Azure-Speech-Text-to-speech-Avatar",
            "Azure Text to speech Avatar",
            ctx=25_000,
            input_modalities=["text"],
            output_modalities=["video"],
            extra={"family": "speech"},
        )
    )
    models.append(
        service(
            "Azure-Speech-Voice-Live",
            "Azure Speech Voice Live",
            ctx=25_000,
            input_modalities=["text", "audio"],
            output_modalities=["text", "audio"],
            extra={"family": "speech"},
        )
    )
    models.append(
        service(
            "Azure-Translator-Document-translation",
            "Azure Translator Document translation",
            extra={"family": "translator"},
        )
    )
    models.append(
        service(
            "Azure-Translator-Text-translation",
            "Azure Translator Text translation",
            extra={"family": "translator"},
        )
    )

    # =====================================================================
    # Community / open-weight forks (catalog pollution kept as free)
    # =====================================================================
    for mid, disp, kwargs in [
        ("unsloth-phi-4", "Unsloth Phi-4", {"ctx": 16_384}),
        ("unsloth-phi-4-unsloth-bnb-4bit", "Unsloth Phi-4 bnb 4bit", {"ctx": 16_384}),
        ("unsloth-phi-3.5-mini-instruct", "Unsloth Phi-3.5 mini instruct", {}),
        ("unsloth-phi-3-medium-4k-instruct", "Unsloth Phi-3 medium 4k instruct", {"ctx": 4_096}),
        (
            "sreenington-phi-3-mini-4k-instruct-awq",
            "sreenington Phi-3 mini 4k AWQ",
            {"ctx": 4_096},
        ),
        (
            "vonjack-phi-3-mini-4k-instruct-llamafied",
            "vonjack Phi-3 mini 4k llamafied",
            {"ctx": 4_096},
        ),
        ("ba2han-llama-phi-3-dora", "ba2han llama phi-3 dora", {}),
        (
            "third-intellect-phi-3-mini-4k-instruct-orca-math-word-problems-200k-model-16bit",
            "third-intellect Phi-3 mini orca-math 16bit",
            {"ctx": 4_096},
        ),
        (
            "localai-io-localai-functioncall-phi-4-v0.3",
            "LocalAI functioncall Phi-4 v0.3",
            {"ctx": 16_384, "chat": True},
        ),
    ]:
        models.append(
            free_weight(
                mid,
                disp,
                ctx=kwargs.get("ctx", 128_000),
                chat=kwargs.get("chat", False),
                extra={"upstream_family": "phi"},
            )
        )

    # Managed GPU reference (not a model, but listed on pricing page)
    # Skip as model row — store only in log / not as model_id.

    # Stable sort: active priced Phi/MAI first already; ensure unique ids
    seen_ids: set[str] = set()
    out: list[dict] = []
    for m in models:
        mid = m["model_id"]
        if mid in seen_ids:
            raise ValueError(f"duplicate model_id: {mid}")
        seen_ids.add(mid)
        out.append(m)
    return out


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
        1 for m in models if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    with_extra = sum(1 for m in models if m.get("extra"))
    print(
        f"microsoft.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced} / extra={with_extra})",
        flush=True,
    )
    for m in models:
        p = m.get("pricing") or {}
        pin, pout = p.get("input_per_1m"), p.get("output_per_1m")
        flag = " [deprecated]" if m.get("deprecated") else ""
        if pin is not None:
            print(
                f"  {m['model_id']:42} ${pin}/${pout} "
                f"ctx={m['context_window']}{flag}",
                flush=True,
            )
        else:
            print(
                f"  {m['model_id']:42} (no token price) "
                f"ctx={m['context_window']}{flag}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Microsoft refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Pricing: {SOURCE_PRICING}\n"
        f"- Retired: {SOURCE_RETIRED}\n"
        f"- MAI docs: {SOURCE_MAI_DOCS}\n"
        f"- Catalog: {SOURCE_CATALOG}\n"
        f"- MAI news: {SOURCE_MAI_NEWS}\n"
        f"- Scratch: `_scratch_ms_pricing_live2.html`, `_scratch_ms_retired_text.txt`, "
        f"`_scratch_ms_mai_docs.html`, `_scratch_ms_catalog_publisher.html`\n"
        f"- Apply: `scripts/_update_microsoft.py`\n\n"
        f"### Result\n"
        f"- microsoft.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced}, extra={with_extra})\n"
        f"- Phi PAYG corrected: Phi-4 $0.125/$0.50 ctx **16384**; "
        f"Phi-4-mini $0.075/$0.30; multimodal text+image $0.08/$0.32 (audio $4/$0.32); "
        f"reasoning $0.125/$0.50 @ 32K\n"
        f"- Phi-3/3.5 family marked deprecated (retired 2025-08-30) with Foundry rates kept\n"
        f"- MAI-DS-R1 Global $1.35/$5.40 deprecated (retired 2026-02-27); "
        f"MAI-Image-2 $5/$33, Efficient/2e $5/$19.50; Voice/Transcribe unpriced meters\n"
        f"- Added MAI-Thinking-1 (256K) + MAI-Code-1-Flash product surface (unpriced)\n"
        f"- Deduped phi-4 / microsoft/phi-4; modalities fixed on multimodal/vision\n"
        f"- Azure AI services retained as license/unpriced; community forks free\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
