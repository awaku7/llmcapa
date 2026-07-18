"""Build/refresh deepseek.json from official DeepSeek API docs.

Sources (Playwright):
- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/updates/
- https://api-docs.deepseek.com/guides/thinking_mode/
- _scratch_deepseek_pricing_live.html

Active API models (2026-04-24+): deepseek-v4-flash, deepseek-v4-pro.
Legacy deepseek-chat / deepseek-reasoner map to v4-flash non-thinking /
thinking until 2026-07-24 15:59 UTC, then discontinued.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "deepseek.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\deepseek.json")
LOG = WORKDIR / "provider_update_log.md"
SOURCE_PRICING = "https://api-docs.deepseek.com/quick_start/pricing/"
SOURCE_UPDATES = "https://api-docs.deepseek.com/updates/"
SOURCE_THINKING = "https://api-docs.deepseek.com/guides/thinking_mode/"
BASE_URL = "https://api.deepseek.com"
BASE_URL_ANTHROPIC = "https://api.deepseek.com/anthropic"


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
    reasoning: bool = True,
    effort: bool = False,
    effort_values: list[str] | None = None,
    fim: bool = False,
    function_calling: bool = True,
    json_mode: bool = True,
    anthropic_api: bool = True,
) -> dict:
    aliases = list(aliases or [])
    or_id = f"deepseek/{model_id}"
    if or_id not in aliases and or_id != model_id:
        aliases.append(or_id)

    row: dict = {
        "provider": "deepseek",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": function_calling,
        "supports_json_mode": json_mode,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_reasoning": reasoning,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": effort,
        "supports_thinking_budget": False,
        "supports_anthropic_api": anthropic_api,
        "supports_google_api": False,
        "supports_fim": fim,
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
    else:
        row["pricing"] = None
    if effort and effort_values:
        row["reasoning_effort_values"] = effort_values

    row["extra"] = {
        "source": SOURCE_PRICING,
        "updates": SOURCE_UPDATES,
        "thinking_mode": SOURCE_THINKING,
        "base_url": BASE_URL,
        "base_url_anthropic": BASE_URL_ANTHROPIC,
        **(extra or {}),
    }
    return row


def cache_extra(
    hit: float,
    *,
    concurrency: int | None = None,
    notes: dict | None = None,
) -> dict:
    e: dict = {
        "cache_hit_per_1m": hit,
        "cache_miss_note": "primary pricing.input_per_1m is cache-miss rate",
        "features": [
            "json_output",
            "tool_calls",
            "chat_prefix_completion_beta",
            "fim_completion_beta_non_thinking_only",
            "thinking_mode_toggle",
            "anthropic_api",
        ],
    }
    if concurrency is not None:
        e["concurrency_limit"] = concurrency
    if notes:
        e.update(notes)
    return e


def build() -> list[dict]:
    models: list[dict] = []

    # =====================================================================
    # Active official API (DeepSeek-V4, 2026-04-24)
    # =====================================================================
    models.append(
        base(
            model_id="deepseek-v4-flash",
            display="DeepSeek V4 Flash",
            ctx=1_048_576,
            max_out=393_216,  # 384K
            pricing={"input": 0.14, "output": 0.28},
            extra=cache_extra(
                0.0028,
                concurrency=2500,
                notes={
                    "model_version": "DeepSeek-V4-Flash",
                    "thinking_default": "enabled",
                    "thinking_toggle": {"type": "enabled|disabled"},
                    "reasoning_effort": ["high", "max"],
                    "legacy_aliases_until": "2026-07-24T15:59:00Z",
                    "legacy_map": {
                        "deepseek-chat": "non-thinking mode of deepseek-v4-flash",
                        "deepseek-reasoner": "thinking mode of deepseek-v4-flash",
                    },
                },
            ),
            aliases=[
                "deepseek/deepseek-v4-flash",
                "deepseek-v4-flash-max",
                "deepseek-chat",  # until 2026-07-24 → non-thinking
                "deepseek-reasoner",  # until 2026-07-24 → thinking
                "deepseek/deepseek-chat",
                "deepseek/deepseek-reasoner",
            ],
            knowledge_cutoff="2025-12",
            reasoning=True,
            effort=True,
            effort_values=["high", "max"],
            fim=True,
        )
    )
    models.append(
        base(
            model_id="deepseek-v4-pro",
            display="DeepSeek V4 Pro",
            ctx=1_048_576,
            max_out=393_216,
            pricing={"input": 0.435, "output": 0.87},
            extra=cache_extra(
                0.003625,
                concurrency=500,
                notes={
                    "model_version": "DeepSeek-V4-Pro",
                    "thinking_default": "enabled",
                    "thinking_toggle": {"type": "enabled|disabled"},
                    "reasoning_effort": ["high", "max"],
                },
            ),
            aliases=[
                "deepseek/deepseek-v4-pro",
                "deepseek-v4-pro-max",
            ],
            knowledge_cutoff="2025-12",
            reasoning=True,
            effort=True,
            effort_values=["high", "max"],
            fim=True,
        )
    )

    # =====================================================================
    # Historical API generations (deprecated; last known public rates)
    # =====================================================================
    models.append(
        base(
            model_id="deepseek-v3.2",
            display="DeepSeek V3.2",
            ctx=131_072,
            max_out=65_536,
            pricing={"input": 0.28, "output": 0.42},
            extra={
                "source": SOURCE_UPDATES,
                "status": "superseded_by_v4",
                "note": (
                    "Was served as deepseek-chat / deepseek-reasoner "
                    "from 2025-12-01 until V4 cutover 2026-04-24. "
                    "Last public rates approximate; verify archives."
                ),
                "cache_hit_per_1m": 0.028,
            },
            aliases=[
                "deepseek/deepseek-v3.2",
                "deepseek-chat-v3.2",
            ],
            knowledge_cutoff="2025-07",
            reasoning=True,
            fim=True,
            deprecated=True,
        )
    )
    models.append(
        base(
            model_id="deepseek-v3.2-speciale",
            display="DeepSeek V3.2 Speciale",
            ctx=131_072,
            max_out=65_536,
            pricing={"input": 0.28, "output": 0.42},
            extra={
                "source": SOURCE_UPDATES,
                "status": "expired",
                "note": (
                    "Temporary endpoint "
                    "https://api.deepseek.com/v3.2_speciale_expires_on_20251215 "
                    "until 2025-12-15 15:59 UTC; same pricing as V3.2; no tool calls."
                ),
            },
            aliases=[
                "deepseek/deepseek-v3.2-speciale",
            ],
            knowledge_cutoff="2025-07",
            reasoning=True,
            function_calling=False,
            fim=False,
            deprecated=True,
        )
    )
    models.append(
        base(
            model_id="deepseek-v3.1",
            display="DeepSeek V3.1",
            ctx=131_072,
            max_out=65_536,
            pricing={"input": 0.27, "output": 1.10},
            extra={
                "source": SOURCE_UPDATES,
                "status": "superseded",
                "note": "Hybrid thinking; later Terminus 2025-09-22.",
                "aliases_historical": [
                    "deepseek/deepseek-v3.1-terminus",
                    "deepseek/deepseek-chat-v3.1",
                ],
            },
            aliases=[
                "deepseek/deepseek-v3.1",
                "deepseek/deepseek-v3.1-terminus",
                "deepseek/deepseek-chat-v3.1",
                "deepseek-chat-v3.1",
            ],
            knowledge_cutoff="2025-05",
            reasoning=True,
            fim=True,
            deprecated=True,
        )
    )
    models.append(
        base(
            model_id="deepseek-r1",
            display="DeepSeek R1",
            ctx=65_536,
            max_out=32_768,
            pricing={"input": 0.55, "output": 2.19},
            extra={
                "source": SOURCE_UPDATES,
                "status": "superseded",
                "note": (
                    "Original R1 (2025-01-20); upgraded to R1-0528 on 2025-05-28. "
                    "Historical rates vary by host; official API now V4."
                ),
            },
            aliases=[
                "deepseek/deepseek-r1",
                "deepseek-r1:671b",
            ],
            knowledge_cutoff="2024-07",
            reasoning=True,
            fim=False,
            deprecated=True,
        )
    )
    models.append(
        base(
            model_id="deepseek-r1-0528",
            display="DeepSeek R1 0528",
            ctx=131_072,
            max_out=65_536,
            pricing={"input": 0.55, "output": 2.19},
            extra={
                "source": SOURCE_UPDATES,
                "status": "superseded_by_v3.1_thinking",
                "note": "deepseek-reasoner upgraded to R1-0528 on 2025-05-28.",
            },
            aliases=[
                "deepseek/deepseek-r1-0528",
            ],
            knowledge_cutoff="2025-05",
            reasoning=True,
            fim=False,
            deprecated=True,
        )
    )
    models.append(
        base(
            model_id="deepseek-v3",
            display="DeepSeek V3",
            ctx=131_072,
            max_out=8_192,
            pricing={"input": 0.27, "output": 1.10},
            extra={
                "source": SOURCE_UPDATES,
                "status": "superseded",
                "note": "V3 (2024-12-26) then V3-0324 (2025-03-24).",
            },
            aliases=[
                "deepseek/deepseek-v3",
                "deepseek/deepseek-chat-v3-0324",
                "deepseek-v3-0324",
            ],
            knowledge_cutoff="2024-07",
            reasoning=False,
            fim=True,
            deprecated=True,
        )
    )

    # Open-weight distill family (no official DeepSeek API pricing)
    models.append(
        base(
            model_id="deepseek-r1-distill",
            display="DeepSeek R1 Distill (Qwen/Llama family)",
            ctx=131_072,
            max_out=32_768,
            pricing=None,
            extra={
                "source": "https://huggingface.co/deepseek-ai",
                "status": "open_weight",
                "note": (
                    "Distilled open-weight variants (1.5B–70B). "
                    "Not served on official DeepSeek API; host-dependent pricing."
                ),
                "license_type_note": "open_weight",
            },
            aliases=[
                "deepseek-r1-distill-qwen",
                "deepseek-r1-distill-7b",
                "deepseek-r1-distill-8b",
                "deepseek-r1-distill-14b",
                "deepseek-r1-distill-32b",
                "deepseek-r1-distill-70b",
                "deepseek/deepseek-r1-distill-qwen",
                "deepseek/deepseek-r1-distill-7b",
                "deepseek/deepseek-r1-distill-8b",
                "deepseek/deepseek-r1-distill-14b",
                "deepseek/deepseek-r1-distill-32b",
                "deepseek/deepseek-r1-distill-70b",
            ],
            knowledge_cutoff="2024-07",
            reasoning=True,
            function_calling=False,
            json_mode=False,
            fim=False,
            anthropic_api=False,
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
    print(
        f"deepseek.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        p = m.get("pricing") or {}
        pin, pout = p.get("input_per_1m"), p.get("output_per_1m")
        flag = " [deprecated]" if m.get("deprecated") else ""
        if pin is not None:
            print(
                f"  {m['model_id']:28} ${pin}/${pout} "
                f"ctx={m['context_window']}{flag}",
                flush=True,
            )
        else:
            print(
                f"  {m['model_id']:28} (no API price) "
                f"ctx={m['context_window']}{flag}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## DeepSeek refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Pricing: {SOURCE_PRICING}\n"
        f"- Change log: {SOURCE_UPDATES}\n"
        f"- Thinking mode: {SOURCE_THINKING}\n"
        f"- Scratch: `_scratch_deepseek_pricing_live.html`\n"
        f"- Apply: `scripts/_update_deepseek.py`\n\n"
        f"### Result\n"
        f"- deepseek.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- Active: V4 Flash $0.14/$0.28 (cache hit $0.0028); "
        f"V4 Pro $0.435/$0.87 (cache hit $0.003625); 1M ctx / 384K max out\n"
        f"- Legacy deepseek-chat/reasoner → v4-flash until 2026-07-24\n"
        f"- Historical V3.x/R1 kept as deprecated; distill open-weight unpriced\n"
        f"- Removed Azure/NPU catalog pollution from deepseek provider\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
