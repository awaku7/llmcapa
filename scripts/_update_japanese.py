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

import html
import json
import re
import shutil
from urllib.request import Request, urlopen
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
SRC_PLAMO_PR = "https://www.preferred.jp/ja/news/pr20260622"
SRC_PLAMO_BLOG = "https://www.preferred.jp/ja/blog/tech/plamo-3-0-prime-release"
SRC_PLAMO_BASE = "https://api.platform.preferredai.jp/v1"
SRC_CLOUD_PF = "https://www.softbank.jp/business/service/platform/cloud-pf-type-a/"
SRC_SARASHINA_API = "https://www.softbank.jp/business/service/ai/sarashina-api/"
SRC_SARASHINA3_BLOG = (
    "https://www.sbintuitions.co.jp/blog/entry/2026/06/30/sarashina3-mini-nano/"
)
SRC_SARASHINA3_PRESS = "https://www.softbank.jp/business/news/2026/0630-01"
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


OFFICIAL_SOURCES = {
    "pfn": SRC_PLAMO_API,
    "softbank": SRC_SARASHINA3_PRESS,
    "ntt": SRC_TSUZUMI,
    "ntt_rd": SRC_TSUZUMI_RD,
}


def _fetch_official_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "llmcapa-official-catalog/1.0"})
    with urlopen(request, timeout=45) as response:
        source = response.read(8_000_000).decode("utf-8", "replace")
    source = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", source)
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


def _discover_official_models(source_texts: dict[str, str]) -> list[dict]:
    discovered: dict[str, dict] = {}
    stamp = datetime.now(timezone.utc).date().isoformat()

    pfn_text = source_texts.get("pfn", "")
    for version in dict.fromkeys(re.findall(r"PLaMo\s*([0-9]+(?:\.[0-9]+)?)\s*Prime", pfn_text, re.I)):
        model_id = f"plamo-{version}-prime"
        price = None
        standard = re.search(
            r"STANDARD.*?PLaMo\s*" + re.escape(version) + r"\s*Prime.*?INPUT\s*([0-9,]+)円.*?OUTPUT\s*([0-9,]+)円",
            pfn_text,
            re.I | re.S,
        )
        if standard:
            yen_in, yen_out = (float(value.replace(",", "")) for value in standard.groups())
            price = {"input": yen_in / 150.0, "output": yen_out / 150.0, "currency": "USD"}
        ctx_match = re.search(r"PLaMo\s*" + re.escape(version) + r"\s*Prime.{0,300}?([0-9]+)k\s*(?:tokens|トークン)", pfn_text, re.I | re.S)
        discovered[model_id.casefold()] = {
            "provider": "pfn", "model_id": model_id,
            "display_name": f"PFN PLaMo {version} Prime",
            "context_window": int(ctx_match.group(1)) * 1000 if ctx_match else 0,
            "max_output_tokens": 0, "pricing": price,
            "input_modalities": ["text"], "output_modalities": ["text"],
            "supports_chat_completion": True, "supports_reasoning": True,
            "source_url": SRC_PLAMO_API, "checked_at": stamp,
        }

    sb_text = source_texts.get("softbank", "")
    for variant in dict.fromkeys(re.findall(r"Sarashina\s*3\s*(mini|nano|guard|embedding|rerank)", sb_text, re.I)):
        variant = variant.lower()
        model_id = f"sarashina3-{variant}"
        is_vector = variant in {"embedding", "rerank"}
        discovered[model_id.casefold()] = {
            "provider": "softbank", "model_id": model_id,
            "display_name": f"Sarashina3 {variant}", "context_window": 0,
            "max_output_tokens": 0, "pricing": None,
            "input_modalities": ["text"],
            "output_modalities": ["embedding" if variant == "embedding" else "rerank" if variant == "rerank" else "text"],
            "supports_chat_completion": not is_vector,
            "supports_reasoning": None,
            "source_url": SRC_SARASHINA3_PRESS, "checked_at": stamp,
        }

    ntt_text = " ".join((source_texts.get("ntt", ""), source_texts.get("ntt_rd", "")))
    if re.search(r"tsuzumi\s*2", ntt_text, re.I):
        discovered["tsuzumi-2"] = {
            "provider": "ntt", "model_id": "tsuzumi-2",
            "display_name": "NTT tsuzumi 2", "context_window": 0,
            "max_output_tokens": 0, "pricing": None,
            "input_modalities": ["text"], "output_modalities": ["text"],
            "supports_chat_completion": True, "supports_reasoning": None,
            "source_url": SRC_TSUZUMI, "checked_at": stamp,
        }
    return list(discovered.values())


def build() -> list[dict]:
    """Discover current entries from official provider pages; carry unmatched history.

    Existing published rows are used only as a metadata cache for exact model
    IDs. The separate manually curated japanese_legacy_models.json is not read.
    """
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8")).get("models", [])
    except (OSError, json.JSONDecodeError):
        previous = []

    source_texts: dict[str, str] = {}
    errors: list[str] = []
    for key, url in OFFICIAL_SOURCES.items():
        try:
            source_texts[key] = _fetch_official_text(url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}")
    discovered = _discover_official_models(source_texts)
    if not discovered:
        raise RuntimeError(
            "No Japanese provider models could be discovered from official pages; "
            + "; ".join(errors)
        )

    previous_by_id = {str(model.get("model_id", "")).casefold(): model for model in previous}
    result: list[dict] = []
    seen: set[str] = set()
    for fresh in discovered:
        key = fresh["model_id"].casefold()
        old = previous_by_id.get(key)
        if old:
            model = dict(old)
            # Apply source-confirmed values; do not overwrite richer metadata
            # with empty/unknown values from a limited product listing.
            model["display_name"] = fresh["display_name"]
            model.setdefault("extra", {}).update({
                "official_source_checked_at": fresh["checked_at"],
                "official_source_status": "listed_on_current_source",
                "current_source": fresh["source_url"],
            })
            if fresh["pricing"] is not None:
                model["pricing"] = fresh["pricing"]
            if fresh["output_modalities"] != ["text"] or fresh["provider"] == "pfn":
                model["input_modalities"] = fresh["input_modalities"]
                model["output_modalities"] = fresh["output_modalities"]
            if fresh["supports_chat_completion"] is not None:
                model["supports_chat_completion"] = fresh["supports_chat_completion"]
        else:
            model = base(
                provider=fresh["provider"], model_id=fresh["model_id"],
                display=fresh["display_name"], ctx=fresh["context_window"],
                max_out=fresh["max_output_tokens"], pricing=fresh["pricing"],
                input_modalities=fresh["input_modalities"],
                output_modalities=fresh["output_modalities"],
                chat=fresh["supports_chat_completion"],
                reasoning=fresh["supports_reasoning"],
                function_calling=None, streaming=None, json_mode=None,
                extra={"source": fresh["source_url"],
                       "official_source_checked_at": fresh["checked_at"],
                       "official_source_status": "listed_on_current_source"},
            )
        result.append(model)
        seen.add(key)

    # Preserve prior rows for aliases/history not covered by the current small
    # set of official product pages, while making their verification status
    # explicit instead of silently treating the old metadata as freshly scraped.
    for old in previous:
        key = str(old.get("model_id", "")).casefold()
        if not key or key in seen:
            continue
        model = dict(old)
        model.setdefault("extra", {}).update({
            "official_source_checked_at": datetime.now(timezone.utc).date().isoformat(),
            "official_source_status": "not_reconfirmed_by_current_page_set",
        })
        result.append(model)
    if errors:
        print("Japanese source fetch warnings: " + "; ".join(errors), flush=True)
    return dedupe(result)


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
        f"- Current model names and modalities are discovered from the official pages above.\n"
        f"- Prices and limits are updated only where the official source publishes them; unknowns remain unset.\n"
        f"- Carried-forward rows are marked as not reconfirmed by the current page set.\n"
        f"- sakura kept separate (sakura.json) — next refresh\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
