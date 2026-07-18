"""Build/refresh moonshot.json (Kimi) from official platform.kimi.ai pricing.

Sources (Playwright live 2026-07-18):
- https://platform.kimi.ai/docs/pricing/chat
- https://platform.kimi.ai/docs/pricing/chat-k27-code
- https://platform.kimi.ai/docs/pricing/chat-k26
- https://platform.kimi.ai/docs/pricing/chat-k25
- Overview: multimodal for K3 / K2.7 Code / K2.6 (text+image+video)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
DATA = WORKDIR / "src" / "llmcapa" / "data"
INSTALLED_DIR = Path(r"F:\Python314\Lib\site-packages\llmcapa\data")
LOG = WORKDIR / "provider_update_log.md"
SOURCE = "https://platform.kimi.ai/docs/pricing/chat"


def row(
    *,
    model_id: str,
    display: str,
    ctx: int,
    inp: float,
    out: float,
    cache_hit: float | None = None,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    reasoning: bool = True,
    vision: bool = False,
    video: bool = False,
    max_out: int = 0,
    extra_notes: dict | None = None,
) -> dict:
    aliases = list(aliases or [])
    for a in (f"moonshotai/{model_id}", f"moonshot/{model_id}", f"kimi/{model_id}"):
        if a not in aliases:
            aliases.append(a)
    modalities = ["text"]
    if vision:
        modalities.append("image")
    if video:
        modalities.append("video")
    extra: dict = {"source": SOURCE}
    if cache_hit is not None:
        extra["cached_input_per_1m"] = cache_hit
        # official tables: Cache Hit / Cache Miss / Output
        # pricing.input_per_1m = cache miss
        extra["cache_miss_input_per_1m"] = inp
    if extra_notes:
        extra.update(extra_notes)
    return {
        "provider": "moonshot",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": modalities,
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": reasoning,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": "api",
        "pricing": {
            "input_per_1m": inp,
            "output_per_1m": out,
            "currency": "USD",
        },
        "extra": extra,
    }


def build() -> list[dict]:
    models: list[dict] = []

    # Flagship K3 — official: Cache Hit $0.30 / Cache Miss $3.00 / Output $15 @ 1M
    models.append(
        row(
            model_id="kimi-k3",
            display="Kimi K3",
            ctx=1_048_576,
            inp=3.0,
            out=15.0,
            cache_hit=0.30,
            aliases=["kimi-latest", "moonshotai/kimi-k3", "moonshotai/kimi-latest"],
            reasoning=True,
            vision=True,
            video=True,
            extra_notes={
                "flagship": True,
                "params": "2.8T",
                "note": "Always reasons; tool_choice + dynamically loaded tools; reasoning_effort=max",
                "official_table": "cache_hit=$0.30 cache_miss=$3.00 output=$15.00 @1M ctx",
            },
        )
    )

    # K2.7 Code — official: $0.19 / $0.95 / $4.00 @ 256k
    models.append(
        row(
            model_id="kimi-k2.7-code",
            display="Kimi K2.7 Code",
            ctx=262_144,
            inp=0.95,
            out=4.0,
            cache_hit=0.19,
            aliases=["moonshotai/kimi-k2.7-code"],
            reasoning=True,
            vision=True,
            video=True,
            extra_notes={
                "specialty": "code",
                "official_table": "cache_hit=$0.19 cache_miss=$0.95 output=$4.00 @256k",
            },
        )
    )
    # K2.7 Code HighSpeed — official: $0.38 / $1.90 / $8.00 (~180 tok/s, up to 260)
    models.append(
        row(
            model_id="kimi-k2.7-code-highspeed",
            display="Kimi K2.7 Code HighSpeed",
            ctx=262_144,
            inp=1.90,
            out=8.0,
            cache_hit=0.38,
            aliases=["moonshotai/kimi-k2.7-code-highspeed"],
            reasoning=True,
            vision=True,
            video=True,
            extra_notes={
                "specialty": "code",
                "highspeed": True,
                "approx_output_tps": 180,
                "peak_output_tps_short_ctx": 260,
                "official_table": "cache_hit=$0.38 cache_miss=$1.90 output=$8.00 @256k",
            },
        )
    )
    # K2.6 — official: $0.16 / $0.95 / $4.00
    models.append(
        row(
            model_id="kimi-k2.6",
            display="Kimi K2.6",
            ctx=262_144,
            inp=0.95,
            out=4.0,
            cache_hit=0.16,
            aliases=["moonshotai/kimi-k2.6"],
            reasoning=True,
            vision=True,
            video=True,
            extra_notes={
                "official_table": "cache_hit=$0.16 cache_miss=$0.95 output=$4.00 @256k",
            },
        )
    )
    # K2.5 — official: $0.10 / $0.60 / $3.00
    models.append(
        row(
            model_id="kimi-k2.5",
            display="Kimi K2.5",
            ctx=262_144,
            inp=0.60,
            out=3.0,
            cache_hit=0.10,
            aliases=["moonshotai/kimi-k2.5"],
            reasoning=True,
            vision=True,
            video=True,
            extra_notes={
                "official_table": "cache_hit=$0.10 cache_miss=$0.60 output=$3.00 @256k",
            },
        )
    )
    # Older K2 family — retain prior catalog prices (not re-listed on main pricing nav)
    models.append(
        row(
            model_id="kimi-k2-thinking",
            display="Kimi K2 Thinking",
            ctx=262_144,
            inp=0.60,
            out=2.50,
            cache_hit=0.15,
            aliases=["moonshotai/kimi-k2-thinking"],
            reasoning=True,
            extra_notes={"status": "legacy-k2-family"},
        )
    )
    models.append(
        row(
            model_id="kimi-k2-0905",
            display="Kimi K2 0905",
            ctx=262_144,
            inp=0.60,
            out=2.50,
            aliases=["moonshotai/kimi-k2-0905"],
            reasoning=True,
            extra_notes={"status": "legacy-k2-family"},
        )
    )
    models.append(
        row(
            model_id="kimi-k2",
            display="Kimi K2",
            ctx=131_072,
            inp=0.57,
            out=2.30,
            aliases=["moonshotai/kimi-k2"],
            reasoning=True,
            extra_notes={"status": "legacy-k2-family"},
        )
    )

    # Moonshot V1 legacy family
    for mid, disp, ctx, inp, out in [
        ("moonshot-v1-8k", "Moonshot V1 8K", 8192, 0.20, 2.0),
        ("moonshot-v1-32k", "Moonshot V1 32K", 32768, 1.0, 3.0),
        ("moonshot-v1-128k", "Moonshot V1 128K", 131072, 2.0, 5.0),
    ]:
        models.append(
            row(
                model_id=mid,
                display=disp,
                ctx=ctx,
                inp=inp,
                out=out,
                aliases=[f"moonshotai/{mid}"],
                reasoning=False,
                deprecated=True,
                extra_notes={"status": "legacy-v1"},
            )
        )

    return models


def resolve_out_path() -> Path:
    for name in ("moonshot.json", "moonshotai.json"):
        p = DATA / name
        if p.exists():
            return p
    return DATA / "moonshot.json"


def main() -> None:
    models = build()
    out = resolve_out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if INSTALLED_DIR.exists():
        shutil.copy2(out, INSTALLED_DIR / out.name)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"{out.name}: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        if not m.get("deprecated"):
            p = m["pricing"]
            ch = (m.get("extra") or {}).get("cached_input_per_1m")
            print(
                f"  {m['model_id']:28} ${p['input_per_1m']}/${p['output_per_1m']}"
                f" cache_hit={ch} ctx={m['context_window']}",
                flush=True,
            )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Moonshot / Kimi refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Official: {SOURCE} + chat-k27-code / chat-k26 / chat-k25 (Playwright live)\n"
        f"- Apply: `scripts/_update_moonshot.py`\n\n"
        f"### Result\n"
        f"- {out.name}: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- **Kimi K3**: $3/$15 @1M; cache hit $0.30 (fixed cache_miss mapping)\n"
        f"- **K2.7 Code**: $0.95/$4.00; cache hit $0.19 (was $1.0/$4.4)\n"
        f"- **K2.7 Code HighSpeed** added: $1.90/$8.00; cache hit $0.38\n"
        f"- **K2.6**: $0.95/$4.00; cache hit $0.16\n"
        f"- **K2.5**: $0.60/$3.00; cache hit $0.10 (was $0.57/$2.85)\n"
        f"- Multimodal (image+video) for K3 / K2.7 Code / K2.6 / K2.5\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
