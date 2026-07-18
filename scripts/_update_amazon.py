"""Build/refresh amazon.json from AWS Bedrock / Nova official pricing.

Sources (Playwright + meteredUnitMaps):
- https://aws.amazon.com/bedrock/pricing/ (Amazon → Amazon Nova)
- https://aws.amazon.com/nova/pricing/
- https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrock/USD/current/bedrock.json
- _scratch_amazon_nova_pricing_live.html

Primary pricing: US East (N. Virginia) On-Demand Standard.
Nova 2 text models: Global Cross-Region Inference (CRI) as primary;
geo/in-region rates stored in extra.
Cache read = 75% less than on-demand input (official).
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "amazon.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\amazon.json")
LOG = WORKDIR / "provider_update_log.md"
SOURCE_BEDROCK = "https://aws.amazon.com/bedrock/pricing/"
SOURCE_NOVA = "https://aws.amazon.com/nova/pricing/"
SOURCE_API = (
    "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/"
    "bedrock/USD/current/bedrock.json"
)
REGION_NOTE = "US East (N. Virginia) on-demand standard"


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
) -> dict:
    aliases = list(aliases or [])
    # dual alias: OpenRouter-style amazon/<id> + Bedrock amazon.<id>:0
    bare = model_id
    if bare.startswith("amazon/"):
        bare = bare[len("amazon/") :]
    or_id = f"amazon/{bare}"
    br_id = f"amazon.{bare}:0" if not bare.startswith("amazon.") else bare
    # also bare without version suffix variants handled by caller
    for a in (or_id, br_id):
        if a not in aliases and a != model_id:
            aliases.append(a)

    in_mod = list(input_modalities or (["text", "image"] if vision else ["text"]))
    out_mod = list(output_modalities or ["text"])

    row: dict = {
        "provider": "amazon",
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
        "license_type": "api",
    }
    if pricing is not None:
        row["pricing"] = {
            "input_per_1m": pricing.get("input"),
            "output_per_1m": pricing.get("output"),
            "currency": "USD",
        }
        # specialty unit prices (image/sec) may live only in extra
        if pricing.get("input") is None and pricing.get("output") is None:
            # keep currency shell only if specialty
            if "unit" in (extra or {}):
                row["pricing"] = {"currency": "USD"}
    else:
        row["pricing"] = None

    ex = {
        "source": SOURCE_BEDROCK,
        "nova_pricing": SOURCE_NOVA,
        "price_api": SOURCE_API,
        "region": REGION_NOTE,
        **(extra or {}),
    }
    row["extra"] = ex
    return row


def text_extra(
    *,
    cache_hit: float | None = None,
    batch_in: float | None = None,
    batch_out: float | None = None,
    geo_in: float | None = None,
    geo_out: float | None = None,
    latency_opt_in: float | None = None,
    latency_opt_out: float | None = None,
    notes: dict | None = None,
) -> dict:
    e: dict = {}
    if cache_hit is not None:
        e["cache_hit_per_1m"] = cache_hit
        e["cache_hit_note"] = "75% less than on-demand input (official)"
    if batch_in is not None:
        e["batch_input_per_1m"] = batch_in
    if batch_out is not None:
        e["batch_output_per_1m"] = batch_out
    if geo_in is not None:
        e["geo_input_per_1m"] = geo_in
    if geo_out is not None:
        e["geo_output_per_1m"] = geo_out
    if latency_opt_in is not None:
        e["latency_optimized_input_per_1m"] = latency_opt_in
    if latency_opt_out is not None:
        e["latency_optimized_output_per_1m"] = latency_opt_out
    if notes:
        e.update(notes)
    return e


def build() -> list[dict]:
    models: list[dict] = []

    # =====================================================================
    # Nova 2 family (Global CRI primary)
    # =====================================================================
    # Nova 2 Lite — Global $0.30/$2.50; Geo $0.33/$2.75
    models.append(
        base(
            model_id="nova-2-lite-v1",
            display="Amazon Nova 2 Lite",
            ctx=1_000_000,
            max_out=65_535,
            pricing={"input": 0.30, "output": 2.50},
            extra=text_extra(
                cache_hit=0.075,  # 0.30 * 0.25
                batch_in=0.15,
                batch_out=1.25,
                geo_in=0.33,
                geo_out=2.75,
                notes={
                    "inference": "global_cross_region",
                    "modalities_note": "text/image/video/file input; text output",
                },
            ),
            aliases=[
                "amazon/nova-2-lite-v1",
                "amazon.nova-2-lite-v1:0",
                "amazon.nova-2-lite-v1",
            ],
            knowledge_cutoff="2025-10",
            input_modalities=["text", "image", "video", "file"],
            output_modalities=["text"],
            vision=True,
            reasoning=True,
        )
    )

    # Nova 2 Pro (Preview) — Global $1.25/$10; Geo $1.375/$11
    models.append(
        base(
            model_id="nova-2-pro-v1",
            display="Amazon Nova 2 Pro (Preview)",
            ctx=1_000_000,
            max_out=65_535,
            pricing={"input": 1.25, "output": 10.0},
            extra=text_extra(
                cache_hit=0.3125,
                batch_in=0.625,
                batch_out=5.0,
                geo_in=1.375,
                geo_out=11.0,
                notes={
                    "inference": "global_cross_region",
                    "availability": "preview",
                },
            ),
            aliases=[
                "amazon/nova-2-pro-v1",
                "amazon.nova-2-pro-v1:0",
                "amazon.nova-2-pro-v1",
            ],
            knowledge_cutoff="2025-10",
            input_modalities=["text", "image", "video", "file"],
            output_modalities=["text"],
            vision=True,
            reasoning=True,
        )
    )

    # Nova 2 Omni (Preview) — Global text $0.30/$2.50; Geo text out $2.80
    models.append(
        base(
            model_id="nova-2-omni-v1",
            display="Amazon Nova 2 Omni (Preview)",
            ctx=1_000_000,
            max_out=65_535,
            pricing={"input": 0.30, "output": 2.50},
            extra=text_extra(
                cache_hit=0.075,
                batch_in=0.15,
                batch_out=1.25,
                geo_in=0.30,
                geo_out=2.80,
                notes={
                    "inference": "global_cross_region",
                    "availability": "preview",
                    "modalities_note": "omni multimodal; primary pricing is text tokens",
                },
            ),
            aliases=[
                "amazon/nova-2-omni-v1",
                "amazon.nova-2-omni-v1:0",
                "amazon.nova-2-omni-v1",
            ],
            knowledge_cutoff="2025-10",
            input_modalities=["text", "image", "video", "audio", "speech"],
            output_modalities=["text", "image", "video", "speech"],
            vision=True,
            reasoning=True,
        )
    )

    # Nova 2 Sonic — speech $3/$12, text $0.33/$2.75 (geo text as primary catalog)
    models.append(
        base(
            model_id="nova-2-sonic-v1",
            display="Amazon Nova 2 Sonic",
            ctx=1_000_000,
            max_out=64_000,
            pricing={"input": 0.33, "output": 2.75},
            extra={
                **text_extra(
                    cache_hit=0.0825,
                    notes={
                        "speech_input_per_1m": 3.0,
                        "speech_output_per_1m": 12.0,
                        "text_input_per_1m": 0.33,
                        "text_output_per_1m": 2.75,
                        "primary_pricing": "text tokens; speech rates in extra",
                    },
                ),
            },
            aliases=[
                "amazon/nova-2-sonic-v1",
                "amazon.nova-2-sonic-v1:0",
                "amazon.nova-2-sonic-v1",
            ],
            knowledge_cutoff="2025-10",
            input_modalities=["text", "audio", "speech"],
            output_modalities=["text", "speech"],
            vision=False,
            reasoning=True,
        )
    )

    # =====================================================================
    # Nova 1.0 family
    # =====================================================================
    models.append(
        base(
            model_id="nova-micro-v1",
            display="Amazon Nova Micro",
            ctx=128_000,
            max_out=5_120,
            pricing={"input": 0.035, "output": 0.14},
            extra=text_extra(
                cache_hit=0.00875,
                batch_in=0.0175,
                batch_out=0.07,
            ),
            aliases=[
                "amazon/nova-micro-v1",
                "amazon.nova-micro-v1:0",
                "amazon.nova-micro-v1",
            ],
            knowledge_cutoff="2024-10-31",
            input_modalities=["text"],
            output_modalities=["text"],
            vision=False,
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="nova-lite-v1",
            display="Amazon Nova Lite",
            ctx=300_000,
            max_out=5_120,
            pricing={"input": 0.06, "output": 0.24},
            extra=text_extra(
                cache_hit=0.015,
                batch_in=0.03,
                batch_out=0.12,
            ),
            aliases=[
                "amazon/nova-lite-v1",
                "amazon.nova-lite-v1:0",
                "amazon.nova-lite-v1",
            ],
            knowledge_cutoff="2024-10-31",
            input_modalities=["text", "image", "video"],
            output_modalities=["text"],
            vision=True,
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="nova-pro-v1",
            display="Amazon Nova Pro",
            ctx=300_000,
            max_out=5_120,
            pricing={"input": 0.80, "output": 3.20},
            extra=text_extra(
                cache_hit=0.20,
                batch_in=0.40,
                batch_out=1.60,
                latency_opt_in=1.00,
                latency_opt_out=4.00,
            ),
            aliases=[
                "amazon/nova-pro-v1",
                "amazon.nova-pro-v1:0",
                "amazon.nova-pro-v1",
            ],
            knowledge_cutoff="2024-10-31",
            input_modalities=["text", "image", "video"],
            output_modalities=["text"],
            vision=True,
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="nova-premier-v1",
            display="Amazon Nova Premier",
            ctx=1_000_000,
            max_out=32_000,
            pricing={"input": 2.50, "output": 12.50},
            extra=text_extra(
                cache_hit=0.625,
                batch_in=1.25,
                batch_out=6.25,
            ),
            aliases=[
                "amazon/nova-premier-v1",
                "amazon.nova-premier-v1:0",
                "amazon.nova-premier-v1",
            ],
            knowledge_cutoff="2024-10",
            input_modalities=["text", "image", "video"],
            output_modalities=["text"],
            vision=True,
            reasoning=True,
        )
    )

    # Nova Sonic 1.0 — speech $3.40/$13.60, text $0.06/$0.24
    models.append(
        base(
            model_id="nova-sonic-v1",
            display="Amazon Nova Sonic",
            ctx=128_000,
            max_out=5_000,
            pricing={"input": 0.06, "output": 0.24},
            extra={
                **text_extra(
                    cache_hit=0.015,
                    notes={
                        "speech_input_per_1m": 3.40,
                        "speech_output_per_1m": 13.60,
                        "text_input_per_1m": 0.06,
                        "text_output_per_1m": 0.24,
                        "primary_pricing": "text tokens; speech rates in extra",
                    },
                ),
            },
            aliases=[
                "amazon/nova-sonic-v1",
                "amazon.nova-sonic-v1:0",
                "amazon.nova-sonic-v1",
            ],
            knowledge_cutoff="2025-01",
            input_modalities=["text", "audio", "speech"],
            output_modalities=["text", "speech"],
            vision=False,
            reasoning=False,
        )
    )

    # =====================================================================
    # Creative / embeddings (specialty units)
    # =====================================================================
    models.append(
        base(
            model_id="nova-canvas-v1",
            display="Amazon Nova Canvas",
            ctx=1,
            max_out=0,
            pricing=None,
            extra={
                "unit": "image",
                "price_per_image_std_le_1024": 0.04,
                "price_per_image_premium_le_1024": 0.06,
                "note": "≤1024 standard $0.04 / premium $0.06 per image (US East)",
            },
            aliases=[
                "amazon/nova-canvas-v1",
                "amazon.nova-canvas-v1:0",
                "amazon.nova-canvas-v1",
            ],
            input_modalities=["text", "image"],
            output_modalities=["image"],
            vision=True,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )
    models.append(
        base(
            model_id="nova-reel-v1",
            display="Amazon Nova Reel",
            ctx=1,
            max_out=0,
            pricing=None,
            extra={
                "unit": "second",
                "price_per_second_720p": 0.08,
                "note": "720p $0.08/sec (US East)",
            },
            aliases=[
                "amazon/nova-reel-v1",
                "amazon.nova-reel-v1:0",
                "amazon.nova-reel-v1",
            ],
            input_modalities=["text", "image"],
            output_modalities=["video"],
            vision=True,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )
    models.append(
        base(
            model_id="nova-multimodal-embeddings-v1",
            display="Amazon Nova Multimodal Embeddings",
            ctx=8_192,
            max_out=0,
            pricing={"input": 0.135, "output": None},
            extra={
                "unit": "token_and_image",
                "text_input_per_1m": 0.135,
                "price_per_image": 0.06,
                "note": "text $0.135/1M tokens; image $0.06/image (US East)",
            },
            aliases=[
                "amazon/nova-multimodal-embeddings-v1",
                "amazon.nova-multimodal-embeddings-v1:0",
                "amazon.nova-multimodal-embeddings-v1",
            ],
            input_modalities=["text", "image"],
            output_modalities=["embedding"],
            vision=True,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )

    # =====================================================================
    # Titan family
    # =====================================================================
    models.append(
        base(
            model_id="titan-text-premier-v1",
            display="Amazon Titan Text Premier",
            ctx=42_000,
            max_out=32_000,
            pricing={"input": 0.50, "output": 1.50},
            extra=text_extra(cache_hit=0.125),
            aliases=[
                "amazon/titan-text-premier-v1",
                "amazon.titan-text-premier-v1:0",
                "amazon.titan-text-premier-v1",
            ],
            knowledge_cutoff="2023-12",
            input_modalities=["text"],
            output_modalities=["text"],
            vision=False,
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="titan-text-express-v1",
            display="Amazon Titan Text Express",
            ctx=42_000,
            max_out=8_000,
            pricing={"input": 0.20, "output": 0.60},
            extra=text_extra(cache_hit=0.05),
            aliases=[
                "amazon/titan-text-express-v1",
                "amazon.titan-text-express-v1:0",
                "amazon.titan-text-express-v1",
            ],
            knowledge_cutoff="2023-12",
            input_modalities=["text"],
            output_modalities=["text"],
            vision=False,
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="titan-text-lite-v1",
            display="Amazon Titan Text Lite",
            ctx=42_000,
            max_out=4_000,
            pricing={"input": 0.15, "output": 0.20},
            extra=text_extra(
                cache_hit=0.0375,
                notes={"note": "corrected from prior catalog $0.30/$0.40"},
            ),
            aliases=[
                "amazon/titan-text-lite-v1",
                "amazon.titan-text-lite-v1:0",
                "amazon.titan-text-lite-v1",
            ],
            knowledge_cutoff="2023-12",
            input_modalities=["text"],
            output_modalities=["text"],
            vision=False,
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="titan-embed-text-v2",
            display="Amazon Titan Text Embeddings V2",
            ctx=8_192,
            max_out=0,
            pricing={"input": 0.02, "output": None},
            extra={
                "unit": "token",
                "text_input_per_1m": 0.02,
                "note": "Titan Embed Text V2 $0.02/1M tokens",
            },
            aliases=[
                "amazon/titan-embed-text-v2",
                "amazon.titan-embed-text-v2:0",
                "amazon.titan-embed-text-v2",
            ],
            input_modalities=["text"],
            output_modalities=["embedding"],
            vision=False,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )
    models.append(
        base(
            model_id="titan-embed-text-v1",
            display="Amazon Titan Text Embeddings G1",
            ctx=8_192,
            max_out=0,
            pricing={"input": 0.10, "output": None},
            extra={
                "unit": "token",
                "text_input_per_1m": 0.10,
                "note": "Titan Embed Text G1 $0.10/1M tokens",
            },
            aliases=[
                "amazon/titan-embed-text-v1",
                "amazon.titan-embed-text-v1:0",
                "amazon.titan-embed-text-v1",
            ],
            input_modalities=["text"],
            output_modalities=["embedding"],
            vision=False,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )
    models.append(
        base(
            model_id="titan-multimodal-embeddings-v1",
            display="Amazon Titan Multimodal Embeddings G1",
            ctx=8_192,
            max_out=0,
            pricing={"input": 0.0008, "output": None},
            extra={
                "unit": "token_and_image",
                "text_input_per_1m": 0.0008,
                "price_per_image": 0.00006,
                "note": (
                    "Titan Multimodal Embeddings: text ~$0.0008/1M; "
                    "image ~$0.00006/image (US East; verify on Bedrock pricing)"
                ),
            },
            aliases=[
                "amazon/titan-multimodal-embeddings-v1",
                "amazon.titan-multimodal-embeddings-v1:0",
                "amazon.titan-multimodal-embeddings-v1",
            ],
            input_modalities=["text", "image"],
            output_modalities=["embedding"],
            vision=True,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )
    models.append(
        base(
            model_id="titan-image-generator-v2",
            display="Amazon Titan Image Generator G1 v2",
            ctx=1,
            max_out=0,
            pricing=None,
            extra={
                "unit": "image",
                "price_per_image_std_512": 0.008,
                "price_per_image_std_1024": 0.01,
                "price_per_image_premium_512": 0.01,
                "price_per_image_premium_1024": 0.012,
                "note": "Titan Image Generator v2 approximate US East rates",
            },
            aliases=[
                "amazon/titan-image-generator-v2",
                "amazon.titan-image-generator-v2:0",
                "amazon.titan-image-generator-v2",
                "titan-image-generator-v1-v2",  # legacy catalog id
            ],
            input_modalities=["text", "image"],
            output_modalities=["image"],
            vision=True,
            function_calling=False,
            streaming=False,
            chat=False,
        )
    )

    return dedupe_model_ids(models)


def dedupe_model_ids(models: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for m in models:
        mid = m["model_id"]
        if mid not in by_id:
            by_id[mid] = m
            order.append(mid)
            continue
        existing = by_id[mid]
        seen = set(existing.get("aliases") or [])
        for a in m.get("aliases") or []:
            if a not in seen:
                existing.setdefault("aliases", []).append(a)
                seen.add(a)
    for mid, m in by_id.items():
        aliases: list[str] = []
        seen: set[str] = set()
        for a in m.get("aliases") or []:
            if a == mid or a in seen:
                continue
            if a.startswith("amazon/amazon/"):
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
        or (m.get("extra") or {}).get("price_per_image_std_le_1024") is not None
        or (m.get("extra") or {}).get("price_per_second_720p") is not None
        or (m.get("extra") or {}).get("text_input_per_1m") is not None
    )
    print(
        f"amazon.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        p = m.get("pricing") or {}
        pin = p.get("input_per_1m")
        pout = p.get("output_per_1m")
        if pin is not None:
            print(
                f"  {m['model_id']:36} ${pin}/${pout} ctx={m['context_window']}",
                flush=True,
            )
        else:
            unit = (m.get("extra") or {}).get("unit", "specialty")
            print(
                f"  {m['model_id']:36} specialty({unit}) ctx={m['context_window']}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Amazon Nova / Bedrock refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Bedrock pricing: {SOURCE_BEDROCK}\n"
        f"- Nova pricing: {SOURCE_NOVA}\n"
        f"- Metered unit map: {SOURCE_API}\n"
        f"- Scratch: `_scratch_amazon_nova_pricing_live.html`\n"
        f"- Apply: `scripts/_update_amazon.py`\n\n"
        f"### Result\n"
        f"- amazon.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- Nova 2 Lite Global $0.30/$2.50 (geo $0.33/$2.75); "
        f"Nova 2 Pro Preview $1.25/$10; Nova 2 Omni Preview $0.30/$2.50\n"
        f"- Nova 1.0: Micro $0.035/$0.14, Lite $0.06/$0.24, "
        f"Pro $0.80/$3.20 (+latency-opt $1/$4), Premier $2.50/$12.50\n"
        f"- Sonic speech/text dual rates in extra; Canvas/Reel/Embeddings priced\n"
        f"- Titan Lite corrected to $0.15/$0.20; dual aliases amazon/* + amazon.*:0\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
