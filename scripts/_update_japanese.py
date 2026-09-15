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

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "japanese.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "japanese.json"
)
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
    """Load source-backed Japanese provider records from external metadata."""
    manifest = json.loads(
        (Path(__file__).parent / "metadata" / "japanese_legacy_models.json").read_text(
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
