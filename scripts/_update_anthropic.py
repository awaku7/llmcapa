"""Build/refresh anthropic.json from official Claude Platform docs.

Sources (Playwright scrapes):
- _scratch_anthropic_overview_live3.html
- _scratch_anthropic_pricing_live3.html
- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/pricing

Shape: Capability JSON with pricing + extra (cache 5m/1h/hit, batch, intro pricing)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "anthropic.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\anthropic.json")
LOG = WORKDIR / "provider_update_log.md"
SOURCE_OVERVIEW = "https://platform.claude.com/docs/en/about-claude/models/overview"
SOURCE_PRICING = "https://platform.claude.com/docs/en/about-claude/pricing"


def base(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    pricing: dict,
    extra: dict,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    knowledge_cutoff: str | None = None,
    reasoning: bool = True,
    effort: bool = False,
    effort_values: list[str] | None = None,
    vision: bool = True,
) -> dict:
    aliases = list(aliases or [])
    # OpenRouter-style prefix aliases (deduped later)
    or_id = f"anthropic/{model_id}"
    if or_id not in aliases:
        aliases.append(or_id)
    row = {
        "provider": "anthropic",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": ["text", "image"] if vision else ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": effort,
        "supports_thinking_budget": True,
        "supports_anthropic_api": True,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": knowledge_cutoff,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": "api",
        "pricing": {
            "input_per_1m": pricing["input"],
            "output_per_1m": pricing["output"],
            "currency": "USD",
        },
        "extra": {
            "source": SOURCE_PRICING,
            "overview": SOURCE_OVERVIEW,
            **extra,
        },
    }
    if effort and effort_values:
        row["reasoning_effort_values"] = effort_values
    return row


def cache_extra(
    write_5m: float,
    write_1h: float,
    hit: float,
    *,
    batch_in: float | None = None,
    batch_out: float | None = None,
    long_ctx: bool = True,
    notes: dict | None = None,
) -> dict:
    e: dict = {
        "cache_write_5m_per_1m": write_5m,
        "cache_write_1h_per_1m": write_1h,
        "cache_hit_per_1m": hit,
    }
    if batch_in is not None:
        e["batch_input_per_1m"] = batch_in
    if batch_out is not None:
        e["batch_output_per_1m"] = batch_out
    if long_ctx:
        e["long_context_window"] = 1_000_000
        e["long_context_at_standard_rates"] = True
    if notes:
        e.update(notes)
    return e


def build() -> list[dict]:
    models: list[dict] = []

    # --- Active flagship / current ---
    models.append(
        base(
            model_id="claude-fable-5",
            display="Claude Fable 5",
            ctx=1_000_000,
            max_out=128_000,
            pricing={"input": 10.0, "output": 50.0},
            extra=cache_extra(
                12.50,
                20.0,
                1.0,
                batch_in=5.0,
                batch_out=25.0,
                notes={
                    "project": "Glasswing",
                    "availability": "ga",
                    "ga_date": "2026-06-09",
                    "adaptive_thinking": "always-on",
                    "newer_tokenizer": True,
                    "note": "Claude Fable 5 GA from 2026-06-09 (Claude API, Bedrock, AWS, GCP, Foundry)",
                },
            ),
            aliases=["claude-fable-5-latest"],
            knowledge_cutoff="2026-01",
            reasoning=True,
            effort=True,
            effort_values=["adaptive"],
        )
    )
    models.append(
        base(
            model_id="claude-mythos-5",
            display="Claude Mythos 5",
            ctx=1_000_000,
            max_out=128_000,
            pricing={"input": 10.0, "output": 50.0},
            extra=cache_extra(
                12.50,
                20.0,
                1.0,
                batch_in=5.0,
                batch_out=25.0,
                notes={
                    "project": "Glasswing",
                    "availability": "limited",
                    "adaptive_thinking": True,
                    "newer_tokenizer": True,
                    "note": "Claude Mythos 5 (Project Glasswing, limited; shares Fable 5 specs/pricing)",
                },
            ),
            aliases=["claude-mythos-5-latest", "claude-mythos-preview"],
            knowledge_cutoff="2026-01",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high"],
        )
    )
    models.append(
        base(
            model_id="claude-opus-4-8",
            display="Claude Opus 4.8",
            ctx=1_000_000,
            max_out=128_000,
            pricing={"input": 5.0, "output": 25.0},
            extra=cache_extra(
                6.25,
                10.0,
                0.50,
                batch_in=2.50,
                batch_out=12.50,
                notes={
                    "fast_mode_input_per_1m": 10.0,
                    "fast_mode_output_per_1m": 50.0,
                    "effort_default": "high",
                    "newer_tokenizer": True,
                    "batch_max_output_tokens": 300000,
                },
            ),
            aliases=["claude-opus-4-8-latest", "claude-opus-latest"],
            knowledge_cutoff="2026-01",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high", "max"],
        )
    )
    models.append(
        base(
            model_id="claude-opus-4-7",
            display="Claude Opus 4.7",
            ctx=1_000_000,
            max_out=128_000,
            pricing={"input": 5.0, "output": 25.0},
            extra=cache_extra(
                6.25,
                10.0,
                0.50,
                batch_in=2.50,
                batch_out=12.50,
                notes={
                    "fast_mode_input_per_1m": 30.0,
                    "fast_mode_output_per_1m": 150.0,
                    "fast_mode_deprecated_on": "2026-07-24",
                    "newer_tokenizer": True,
                },
            ),
            aliases=["claude-opus-4-7-latest"],
            knowledge_cutoff="2026-01",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high", "max"],
        )
    )
    models.append(
        base(
            model_id="claude-opus-4-6",
            display="Claude Opus 4.6",
            ctx=1_000_000,
            max_out=128_000,
            pricing={"input": 5.0, "output": 25.0},
            extra=cache_extra(6.25, 10.0, 0.50, batch_in=2.50, batch_out=12.50),
            aliases=["claude-opus-4-6-latest"],
            knowledge_cutoff="2025-08",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high"],
        )
    )
    models.append(
        base(
            model_id="claude-opus-4-5",
            display="Claude Opus 4.5",
            ctx=200_000,
            max_out=64_000,
            pricing={"input": 5.0, "output": 25.0},
            extra=cache_extra(
                6.25,
                10.0,
                0.50,
                batch_in=2.50,
                batch_out=12.50,
                long_ctx=False,
            ),
            aliases=["claude-opus-4-5-latest", "claude-opus-4-5-20251101"],
            knowledge_cutoff="2025-08",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high"],
        )
    )

    # Sonnet 5 — introductory pricing through 2026-08-31
    models.append(
        base(
            model_id="claude-sonnet-5",
            display="Claude Sonnet 5",
            ctx=1_000_000,
            max_out=128_000,
            pricing={"input": 2.0, "output": 10.0},
            extra=cache_extra(
                2.50,
                4.0,
                0.20,
                batch_in=1.0,
                batch_out=5.0,
                notes={
                    "intro_pricing_until": "2026-08-31",
                    "standard_input_per_1m": 3.0,
                    "standard_output_per_1m": 15.0,
                    "standard_cache_write_5m_per_1m": 3.75,
                    "standard_cache_write_1h_per_1m": 6.0,
                    "standard_cache_hit_per_1m": 0.30,
                    "standard_batch_input_per_1m": 1.50,
                    "standard_batch_output_per_1m": 7.50,
                    "newer_tokenizer": True,
                    "batch_max_output_tokens": 300000,
                    "note": "Intro $2/$10 through 2026-08-31; then $3/$15",
                },
            ),
            aliases=["claude-sonnet-5-latest", "claude-sonnet-latest"],
            knowledge_cutoff="2026-01",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high"],
        )
    )
    models.append(
        base(
            model_id="claude-sonnet-4-6",
            display="Claude Sonnet 4.6",
            ctx=1_000_000,
            max_out=64_000,
            pricing={"input": 3.0, "output": 15.0},
            extra=cache_extra(3.75, 6.0, 0.30, batch_in=1.50, batch_out=7.50),
            aliases=["claude-sonnet-4-6-latest"],
            knowledge_cutoff="2025-08",
            reasoning=True,
            effort=True,
            effort_values=["low", "medium", "high"],
        )
    )
    models.append(
        base(
            model_id="claude-sonnet-4-5",
            display="Claude Sonnet 4.5",
            ctx=200_000,
            max_out=64_000,
            pricing={"input": 3.0, "output": 15.0},
            extra=cache_extra(
                3.75,
                6.0,
                0.30,
                batch_in=1.50,
                batch_out=7.50,
                long_ctx=False,
            ),
            aliases=["claude-sonnet-4-5-latest", "claude-sonnet-4-5-20250929"],
            knowledge_cutoff="2025-07",
            reasoning=True,
            effort=False,
        )
    )

    models.append(
        base(
            model_id="claude-haiku-4-5",
            display="Claude Haiku 4.5",
            ctx=200_000,
            max_out=64_000,
            pricing={"input": 1.0, "output": 5.0},
            extra=cache_extra(
                1.25,
                2.0,
                0.10,
                batch_in=0.50,
                batch_out=2.50,
                long_ctx=False,
                notes={"extended_thinking": True},
            ),
            aliases=[
                "claude-haiku-4-5-latest",
                "claude-haiku-4-5-20251001",
                "claude-haiku-latest",
            ],
            knowledge_cutoff="2025-02",
            reasoning=True,
            effort=False,
        )
    )

    # --- Deprecated / retired (kept for lookup) ---
    models.append(
        base(
            model_id="claude-opus-4-1",
            display="Claude Opus 4.1",
            ctx=200_000,
            max_out=32_000,
            pricing={"input": 15.0, "output": 75.0},
            extra=cache_extra(
                18.75,
                30.0,
                1.50,
                batch_in=7.50,
                batch_out=37.50,
                long_ctx=False,
                notes={"status": "deprecated"},
            ),
            aliases=["claude-opus-4-1-20250805"],
            deprecated=True,
            knowledge_cutoff="2025-03",
            reasoning=True,
        )
    )
    models.append(
        base(
            model_id="claude-opus-4",
            display="Claude Opus 4",
            ctx=200_000,
            max_out=32_000,
            pricing={"input": 15.0, "output": 75.0},
            extra=cache_extra(
                18.75,
                30.0,
                1.50,
                batch_in=7.50,
                batch_out=37.50,
                long_ctx=False,
                notes={
                    "status": "retired",
                    "still_available_on": ["google-cloud"],
                },
            ),
            aliases=["claude-opus-4-20250514"],
            deprecated=True,
            knowledge_cutoff="2025-03",
            reasoning=True,
        )
    )
    models.append(
        base(
            model_id="claude-sonnet-4",
            display="Claude Sonnet 4",
            ctx=200_000,
            max_out=64_000,
            pricing={"input": 3.0, "output": 15.0},
            extra=cache_extra(
                3.75,
                6.0,
                0.30,
                batch_in=1.50,
                batch_out=7.50,
                long_ctx=False,
                notes={
                    "status": "retired",
                    "still_available_on": ["bedrock", "google-cloud"],
                },
            ),
            aliases=["claude-sonnet-4-20250514"],
            deprecated=True,
            knowledge_cutoff="2025-03",
            reasoning=True,
        )
    )
    models.append(
        base(
            model_id="claude-haiku-3-5",
            display="Claude Haiku 3.5",
            ctx=200_000,
            max_out=8192,
            pricing={"input": 0.80, "output": 4.0},
            extra=cache_extra(
                1.0,
                1.60,
                0.08,
                batch_in=0.40,
                batch_out=2.0,
                long_ctx=False,
                notes={
                    "status": "retired",
                    "still_available_on": ["bedrock", "google-cloud"],
                },
            ),
            aliases=["claude-3-5-haiku-latest", "claude-3-5-haiku-20241022"],
            deprecated=True,
            knowledge_cutoff="2024-07",
            reasoning=False,
            vision=True,
        )
    )
    models.append(
        base(
            model_id="claude-3-5-sonnet-20241022",
            display="Claude 3.5 Sonnet (20241022)",
            ctx=200_000,
            max_out=8192,
            pricing={"input": 3.0, "output": 15.0},
            extra=cache_extra(
                3.75,
                6.0,
                0.30,
                long_ctx=False,
                notes={"status": "legacy", "note": "retained for historical lookup"},
            ),
            aliases=["claude-3-5-sonnet-latest", "claude-3-5-sonnet"],
            deprecated=True,
            knowledge_cutoff="2024-04",
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="claude-3-opus-20240229",
            display="Claude 3 Opus",
            ctx=200_000,
            max_out=4096,
            pricing={"input": 15.0, "output": 75.0},
            extra=cache_extra(
                18.75,
                30.0,
                1.50,
                long_ctx=False,
                notes={"status": "legacy"},
            ),
            aliases=["claude-3-opus-latest", "claude-3-opus"],
            deprecated=True,
            knowledge_cutoff="2023-08",
            reasoning=False,
        )
    )
    models.append(
        base(
            model_id="claude-3-haiku-20240307",
            display="Claude 3 Haiku",
            ctx=200_000,
            max_out=4096,
            pricing={"input": 0.25, "output": 1.25},
            extra={
                "source": SOURCE_PRICING,
                "status": "legacy",
                "cache_write_5m_per_1m": 0.30,
                "cache_hit_per_1m": 0.03,
            },
            aliases=["claude-3-haiku-latest", "claude-3-haiku"],
            deprecated=True,
            knowledge_cutoff="2023-08",
            reasoning=False,
        )
    )

    return dedupe_model_ids(models)


def dedupe_model_ids(models: list[dict]) -> list[dict]:
    """Keep first occurrence of each model_id; merge unique aliases."""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for m in models:
        mid = m["model_id"]
        if mid not in by_id:
            by_id[mid] = m
            order.append(mid)
            continue
        # merge aliases
        existing = by_id[mid]
        seen = set(existing.get("aliases") or [])
        for a in m.get("aliases") or []:
            if a not in seen:
                existing.setdefault("aliases", []).append(a)
                seen.add(a)
    # strip OpenRouter-only duplicate bare prefixes that collide with model_id
    for mid, m in by_id.items():
        aliases = []
        seen = set()
        for a in m.get("aliases") or []:
            # drop pure openrouter pollution like "anthropic/anthropic/..."
            if a.startswith("anthropic/anthropic/"):
                continue
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
        f"anthropic.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        if not m.get("deprecated"):
            p = m["pricing"]
            print(
                f"  {m['model_id']:28} ${p['input_per_1m']}/${p['output_per_1m']} "
                f"ctx={m['context_window']}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Anthropic refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Overview + pricing Playwright: "
        f"`_scratch_anthropic_overview_live3.html`, "
        f"`_scratch_anthropic_pricing_live3.html`\n"
        f"- Docs: {SOURCE_OVERVIEW} / {SOURCE_PRICING}\n"
        f"- Apply: `scripts/_update_anthropic.py`\n\n"
        f"### Result\n"
        f"- anthropic.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- New: Fable 5 / Mythos 5 $10/$50; Opus 4.8 $5/$25; "
        f"Sonnet 5 intro $2/$10→$3/$15; Haiku 4.5 $1/$5\n"
        f"- Cache pricing (5m/1h/hit) + batch in extra; OpenRouter aliases deduped\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
