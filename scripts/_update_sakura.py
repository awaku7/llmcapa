"""Build/refresh sakura.json — さくらインターネット さくらのAI Engine.

Sources (live Playwright scrape):
- https://ai.sakura.ad.jp/sakura-ai/ai-engine/
- https://playground.aipf.sakura.ad.jp/

Model IDs, categories, published prices, and public-preview/closed rows are
read from the current official product tables; no local model manifest is read.

Pricing on the official page is tax-included JPY per 10,000 tokens
(or per 60s audio / 10,000 mora TTS / 100 RAG chunks). Catalog stores
USD shell at ~150 JPY/USD with exact JPY in extra.pricing_jpy.
"""

from __future__ import annotations

import json
import re
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


def _fetch_source_tables() -> list[dict]:
    """Read the current model/pricing tables from Sakura's public product page."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SRC, wait_until="domcontentloaded", timeout=60_000)
        page.locator("table").first.wait_for(timeout=30_000)
        tables = page.evaluate(
            r"""() => Array.from(document.querySelectorAll('table')).map((table, index) => ({
                index,
                rows: Array.from(table.querySelectorAll('tr')).map(row =>
                    Array.from(row.querySelectorAll('th,td')).map(cell =>
                        (cell.innerText || '').trim().replace(/\s+/g, ' ')
                    )
                ).filter(row => row.some(cell => cell)),
            }))"""
        )
        body = page.locator("body").inner_text()
        browser.close()
    if not tables or not any(table.get("rows") for table in tables):
        raise RuntimeError("Sakura official product page has no model/pricing tables")
    return tables, body


def _model_cell_name(value: str) -> str | None:
    text = " ".join(str(value or "").split())
    text = re.sub(r"^提供モデル\s*[:：]\s*", "", text)
    text = re.sub(r"\s*提供元[：:]?.*$", "", text)
    text = re.sub(r"\s*\(\d{4}年[^)]*\)", "", text)
    text = re.sub(r"[※*]+$", "", text)
    text = text.strip()
    if not text or text.lower() in {
        "提供モデル", "無償枠", "対象外", "service item", "model name",
    }:
        return None
    if any(token in text.lower() for token in ("input", "output", "リクエストまで", "チャンク")):
        return None
    if text.startswith("提供元") or "提供元：" in text:
        return None
    return text


def _price_per_10k(text: str, label: str) -> float | None:
    match = re.search(
        rf"{re.escape(label)}\s*([0-9]+(?:\.[0-9]+)?)\s*円\s*/\s*10,000\s*トークン",
        text,
        re.I,
    )
    return float(match.group(1)) if match else None


def _build_from_tables(tables: list[dict], body: str) -> list[dict]:
    rows_by_id: dict[str, dict] = {}
    current_category = ""
    for table in tables:
        rows = table.get("rows") or []
        inherited_tts_rate: float | None = None
        inherited_quota: int | None = None
        if not rows:
            continue
        header = " ".join(rows[0]).lower()
        if not any(word in header for word in ("提供モデル", "category", "model")):
            continue
        closed = "提供モデル・提供元" in " ".join(rows[0])
        preview = table.get("index") not in (0, 1) and not closed
        current_category = "Chat Completions" if closed else ("Public Preview" if preview else "")
        for cells in rows[1:]:
            if not cells:
                continue
            first = cells[0].strip()
            known_categories = {
                "Chat completions", "Audio transcription", "Embeddings",
                "Text-to-Speech", "ドキュメント（RAG）", "Chat Completions",
            }
            if first in known_categories:
                current_category = first
                model_cell = cells[1] if len(cells) > 1 else ""
            elif closed and len(cells) > 1 and ("提供モデル" in first or "提供元" in first):
                model_cell = first
            else:
                model_cell = first
            name = _model_cell_name(model_cell)
            if not name:
                continue

            category = current_category.lower()
            text = " ".join(cells)
            input_price = _price_per_10k(text, "input")
            output_price = _price_per_10k(text, "output")
            token_pricing = None
            extra: dict = {
                "source": SRC,
                "official_catalog_checked_at": datetime.now(timezone.utc).date().isoformat(),
            }
            if input_price is not None:
                output_price = output_price if output_price is not None else 0.0
                token_pricing, pricing_jpy = chat_price(input_price, output_price)
                extra["pricing_jpy"] = pricing_jpy
            audio_meter = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*円\s*/\s*60秒", text)
            tts_meter = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*円\s*/\s*10,000\s*モーラ", text)
            tts_rate = float(tts_meter.group(1)) if tts_meter else None
            if tts_rate is not None:
                inherited_tts_rate = tts_rate
            elif "text-to-speech" in category:
                tts_rate = inherited_tts_rate
            if audio_meter:
                extra["price_per_60_seconds_jpy"] = float(audio_meter.group(1))
            if tts_rate is not None:
                extra["price_per_10k_mora_jpy"] = tts_rate
            quota = re.search(r"([0-9,]+)\s*リクエストまで", text)
            quota_value = int(quota.group(1).replace(",", "")) if quota else None
            if quota_value is not None:
                inherited_quota = quota_value
            elif category in {"text-to-speech", "audio transcription", "embeddings"}:
                quota_value = inherited_quota
            if quota_value is not None:
                extra["free_requests_per_month"] = quota_value

            if "audio transcription" in category:
                input_modalities, output_modalities = ["audio"], ["text"]
                chat = False
            elif "embeddings" in category or "embedding" in name.lower():
                input_modalities, output_modalities = ["text"], ["embedding"]
                chat = False
            elif "text-to-speech" in category or "voicevox:" in name.lower():
                input_modalities, output_modalities = ["text"], ["audio"]
                chat = False
            elif "chat completions" in category or "chat completions" in text.lower():
                input_modalities, output_modalities = ["text"], ["text"]
                chat = True
            else:
                input_modalities, output_modalities = ["text"], ["text"]
                chat = None if preview else True

            if "public preview" in category:
                extra["tier"] = "preview"
            elif closed:
                extra["tier"] = "closed"
                extra["pricing_status"] = "quote/application; price not published on product page"
            else:
                extra["tier"] = "standard"
            if tts_meter:
                extra["unit"] = "10k_mora"
            if audio_meter:
                extra["unit"] = "60_seconds"
            if not token_pricing and not audio_meter and tts_rate is None:
                extra.setdefault("pricing_status", "not listed for this model on current product page")

            model_id = name
            row = base(
                model_id=model_id,
                display=name,
                ctx=0,
                max_out=0,
                pricing=token_pricing,
                extra=extra,
                input_modalities=input_modalities,
                output_modalities=output_modalities,
                vision="image" in input_modalities,
                chat=chat,
                function_calling=None,
                streaming=None,
                json_mode=None,
                responses_api=None,
                license_type="custom" if closed else "api",
            )
            if closed:
                row["supports_function_calling"] = None
                row["supports_json_mode"] = None
            rows_by_id[model_id.casefold()] = row

    if not rows_by_id:
        raise RuntimeError("Sakura official product page produced no model records")
    return list(rows_by_id.values())


def build() -> list[dict]:
    """Discover Sakura AI Engine models from the live official product tables."""
    tables, body = _fetch_source_tables()
    models = _build_from_tables(tables, body)
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
        f"- Playground: {SRC_PLAYGROUND}\n"
        f"- Apply: `scripts/_update_sakura.py`\n\n"
        f"### Result\n"
        f"- sakura.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, "
        f"priced={priced}, extra={extra_n})\n"
        f"- Tiers: {by_tier}\n"
        f"- Model IDs and categories were discovered from the live product tables; values absent from the page remain unknown.\n"
        f"- Token/audio/TTS prices are parsed from the current table; quote-only closed models remain unpriced.\n"
        f"- No local sakura_legacy_models.json manifest or hard-coded model catalog is used.\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
