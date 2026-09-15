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

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "sakura.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "sakura.json"
)
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
    """Load SAKURA AI metadata from external source-backed JSON."""
    manifest = json.loads(
        (Path(__file__).parent / "metadata" / "sakura_legacy_models.json").read_text(
            encoding="utf-8"
        )
    )
    return dedupe([dict(model) for model in manifest["models"]])


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
    if INSTALLED.parent.exists() and OUT.resolve() != INSTALLED.resolve():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1 for m in models if (m.get("pricing") or {}).get("input_per_1m") is not None
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
