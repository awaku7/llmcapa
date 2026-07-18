"""Refresh nvidia.json key Nemotron API models from build.nvidia.com.

Sources (Playwright live 2026-07-18):
- https://build.nvidia.com/models
- https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b
- https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b
- https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b
- https://docs.api.nvidia.com/nim/reference/llm-apis

NVIDIA free endpoints exist; partner serverless prices vary. We store a
representative partner price (Deep Infra / OpenRouter when available) plus
partner_price_range in extra.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "nvidia.json"
INSTALLED_DIR = Path(r"F:\Python314\Lib\site-packages\llmcapa\data")
LOG = WORKDIR / "provider_update_log.md"
SOURCE = "https://build.nvidia.com/models"


def base_row(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    inp: float | None,
    out: float | None,
    free_endpoint: bool = True,
    reasoning: bool = True,
    vision: bool = False,
    modalities_in: list[str] | None = None,
    modalities_out: list[str] | None = None,
    aliases: list[str] | None = None,
    extra: dict | None = None,
    license_type: str = "api",
    deprecated: bool = False,
    chat: bool = True,
) -> dict:
    modalities_in = modalities_in or (["text", "image"] if vision else ["text"])
    modalities_out = modalities_out or ["text"]
    aliases = list(aliases or [])
    bare = model_id.split("/")[-1]
    for a in (bare, f"nvidia/{bare}"):
        if a not in aliases and a != model_id:
            aliases.append(a)
    row: dict = {
        "provider": "nvidia",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": modalities_in,
        "output_modalities": modalities_out,
        "supports_function_calling": chat,
        "supports_json_mode": chat,
        "supports_streaming": True,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": reasoning and chat,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": license_type,
        "extra": {
            "source": SOURCE,
            "free_endpoint": free_endpoint,
            "api_base": "https://integrate.api.nvidia.com/v1",
            **(extra or {}),
        },
    }
    if inp is not None and out is not None:
        row["pricing"] = {
            "input_per_1m": inp,
            "output_per_1m": out,
            "currency": "USD",
        }
    return row


# Official NIM model IDs + partner serverless prices (Playwright 2026-07-18)
UPSERTS: list[dict] = [
    base_row(
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        display="NVIDIA Nemotron 3 Ultra 550B-A55B",
        ctx=1_048_576,
        max_out=16384,
        inp=0.50,
        out=2.20,
        free_endpoint=True,
        reasoning=True,
        aliases=[
            "nemotron-3-ultra",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
        ],
        extra={
            "params": "561B",
            "architecture": "hybrid Mamba-Transformer MoE",
            "partner_prices": {
                "deep_infra": {"input_per_1m": 0.50, "output_per_1m": 2.20},
                "lightning_ai": {"input_per_1m": 0.41, "output_per_1m": 1.20},
                "openrouter": {"input_per_1m": 0.60, "output_per_1m": 3.60},
                "together_ai": {"input_per_1m": 0.60, "output_per_1m": 3.60},
                "bitdeer_ai": {"input_per_1m": 0.80, "output_per_1m": 2.60},
                "gmi_cloud": {"input_per_1m": 0.80, "output_per_1m": 2.60},
                "digital_ocean": {"input_per_1m": 0.90, "output_per_1m": 1.70},
            },
            "pricing_note": "pricing.input/output = Deep Infra partner; free endpoint also available",
            "enable_thinking": True,
            "reasoning_budget_default": 16384,
        },
    ),
    base_row(
        model_id="nvidia/nemotron-3-super-120b-a12b",
        display="NVIDIA Nemotron 3 Super 120B-A12B",
        ctx=1_048_576,
        max_out=16384,
        inp=0.20,
        out=0.80,
        free_endpoint=True,
        reasoning=True,
        aliases=[
            "nemotron-3-super",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        extra={
            "architecture": "hybrid Mamba-Transformer MoE",
            "partner_prices": {
                "bitdeer_ai": {"input_per_1m": 0.20, "output_per_1m": 0.80},
                "coreweave": {"input_per_1m": 0.20, "output_per_1m": 0.80},
                "openrouter": {"input_per_1m": 0.21, "output_per_1m": 0.46},
                "digital_ocean": {"input_per_1m": 0.30, "output_per_1m": 0.65},
            },
            "pricing_note": "pricing = Bitdeer/CoreWeave partner; free endpoint available",
            "enable_thinking": True,
            "reasoning_budget_default": 16384,
            "api_calls_30d": "60M",
        },
    ),
    base_row(
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        display="NVIDIA Nemotron 3 Nano 30B-A3B",
        ctx=1_048_576,
        max_out=16384,
        inp=0.05,
        out=0.20,
        free_endpoint=True,
        reasoning=True,
        aliases=[
            "nemotron-3-nano",
            "nvidia/nemotron-3-nano-30b-a3b:free",
        ],
        extra={
            "architecture": "MoE",
            "partner_prices": {
                "deep_infra": {"input_per_1m": 0.05, "output_per_1m": 0.20},
                "openrouter": {"input_per_1m": 0.05, "output_per_1m": 0.20},
            },
            "pricing_note": "pricing = Deep Infra / OpenRouter; free endpoint available",
            "reasoning_budget_default": 16384,
        },
    ),
    base_row(
        model_id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        display="NVIDIA Nemotron 3 Nano Omni 30B-A3B Reasoning",
        ctx=1_048_576,
        max_out=16384,
        inp=0.0,
        out=0.0,
        free_endpoint=True,
        reasoning=True,
        vision=True,
        modalities_in=["text", "image", "video", "speech", "audio"],
        aliases=[
            "nemotron-3-omni",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        ],
        extra={
            "pricing_status": "free_endpoint_primary",
            "capabilities": [
                "image_understanding",
                "video_understanding",
                "speech_understanding",
                "reasoning",
            ],
        },
    ),
    base_row(
        model_id="nvidia/nemotron-3-embed-1b",
        display="NVIDIA Nemotron 3 Embed 1B",
        ctx=8192,
        max_out=0,
        inp=0.0,
        out=0.0,
        free_endpoint=True,
        reasoning=False,
        chat=False,
        modalities_in=["text"],
        modalities_out=["embedding"],
        aliases=["nemotron-3-embed-1b"],
        extra={
            "pricing_status": "free_endpoint",
            "use_case": "semantic search / retrieval / RAG",
            "api_kind": "embeddings",
        },
    ),
    base_row(
        model_id="nvidia/nemotron-3.5-content-safety",
        display="NVIDIA Nemotron 3.5 Content Safety",
        ctx=32768,
        max_out=4096,
        inp=0.0,
        out=0.0,
        free_endpoint=True,
        reasoning=False,
        vision=True,
        aliases=[
            "nemotron-3.5-content-safety",
            "nvidia/nemotron-3.5-content-safety:free",
        ],
        extra={
            "pricing_status": "free_endpoint",
            "use_case": "multilingual multimodal content safety",
        },
    ),
    base_row(
        model_id="nvidia/cosmos3-nano",
        display="NVIDIA Cosmos 3 Nano",
        ctx=0,
        max_out=0,
        inp=None,
        out=None,
        free_endpoint=True,
        reasoning=False,
        chat=False,
        modalities_in=["text", "image"],
        modalities_out=["video"],
        aliases=["cosmos3-nano"],
        license_type="api",
        extra={
            "pricing_status": "free_endpoint",
            "use_case": "physics-aware video generation for physical AI",
        },
    ),
    base_row(
        model_id="nvidia/cosmos3-nano-reasoner",
        display="NVIDIA Cosmos 3 Nano Reasoner",
        ctx=131072,
        max_out=8192,
        inp=0.0,
        out=0.0,
        free_endpoint=True,
        reasoning=True,
        vision=True,
        modalities_in=["text", "image", "video"],
        aliases=["cosmos3-nano-reasoner"],
        extra={
            "pricing_status": "free_endpoint",
            "use_case": "physical-world video/image reasoning",
        },
    ),
]


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    models: list[dict] = list(data.get("models") or [])
    by_id = {m["model_id"]: i for i, m in enumerate(models)}

    # Also index bare aliases for soft match
    bare_index: dict[str, int] = {}
    for i, m in enumerate(models):
        bare_index[m["model_id"]] = i
        bare_index[m["model_id"].split("/")[-1]] = i
        for a in m.get("aliases") or []:
            bare_index[a] = i

    changed: list[str] = []
    for row in UPSERTS:
        mid = row["model_id"]
        bare = mid.split("/")[-1]
        idx = by_id.get(mid)
        if idx is None:
            # replace bare-name legacy entry if present
            idx = bare_index.get(bare)
            if idx is not None and models[idx]["model_id"] != mid:
                # keep old as alias if different
                old = models[idx]
                if old["model_id"] not in row["aliases"]:
                    row["aliases"].append(old["model_id"])
                models[idx] = row
                by_id[mid] = idx
                changed.append(f"replaced:{old['model_id']}->{mid}")
                continue
        if idx is None:
            models.append(row)
            by_id[mid] = len(models) - 1
            changed.append(f"inserted:{mid}")
        else:
            models[idx] = row
            changed.append(f"updated:{mid}")

    # Sync free-endpoint twin pricing for known free aliases
    free_twins = {
        "nvidia/nemotron-3-ultra-550b-a55b:free": "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3-super-120b-a12b:free": "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b:free": "nvidia/nemotron-3-nano-30b-a3b",
    }
    for free_id, paid_id in free_twins.items():
        if free_id in by_id:
            src = models[by_id[paid_id]]
            twin = dict(src)
            twin["model_id"] = free_id
            twin["display_name"] = src["display_name"] + " (Free)"
            twin["pricing"] = {
                "input_per_1m": 0.0,
                "output_per_1m": 0.0,
                "currency": "USD",
            }
            twin["license_type"] = "free"
            twin["aliases"] = [a for a in src.get("aliases") or [] if a != free_id]
            twin["extra"] = {
                **(src.get("extra") or {}),
                "free_endpoint": True,
                "pricing_status": "free_endpoint",
            }
            models[by_id[free_id]] = twin
            changed.append(f"synced_free:{free_id}")
        else:
            # insert free twin
            src = models[by_id[paid_id]]
            twin = dict(src)
            twin["model_id"] = free_id
            twin["display_name"] = src["display_name"] + " (Free)"
            twin["pricing"] = {
                "input_per_1m": 0.0,
                "output_per_1m": 0.0,
                "currency": "USD",
            }
            twin["license_type"] = "free"
            twin["aliases"] = []
            twin["extra"] = {
                **(src.get("extra") or {}),
                "free_endpoint": True,
                "pricing_status": "free_endpoint",
            }
            models.append(twin)
            by_id[free_id] = len(models) - 1
            changed.append(f"inserted_free:{free_id}")

    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if INSTALLED_DIR.exists():
        shutil.copy2(OUT, INSTALLED_DIR / OUT.name)

    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"nvidia.json: {len(models)} models (active={active} / priced={priced})",
        flush=True,
    )
    for c in changed:
        print(f"  {c}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## NVIDIA NIM refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Catalog: {SOURCE}\n"
        f"- Model pages: nemotron-3-ultra / super / nano (Playwright live)\n"
        f"- Docs: https://docs.api.nvidia.com/nim/reference/llm-apis\n"
        f"- Apply: `scripts/_update_nvidia.py`\n\n"
        f"### Result\n"
        f"- nvidia.json: **{len(models)}** models (active={active}, priced={priced})\n"
        f"- **nemotron-3-ultra-550b-a55b**: $0.50/$2.20 (Deep Infra); partners $0.41–$0.90 in\n"
        f"- **nemotron-3-super-120b-a12b**: $0.20/$0.80 (Bitdeer/CoreWeave)\n"
        f"- **nemotron-3-nano-30b-a3b**: $0.05/$0.20\n"
        f"- Free endpoint twins synced; omni / embed / cosmos3-nano* added\n"
        f"- Free NVIDIA trial endpoints remain available for evaluation\n"
        f"- Install copy synced\n"
        f"- Changes: {', '.join(changed)}\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
