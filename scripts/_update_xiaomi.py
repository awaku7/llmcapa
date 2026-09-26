"""Build/refresh xiaomi.json (MiMo) from official mimo.mi.com docs.

Sources (Playwright live 2026-07-18):
- https://mimo.mi.com/docs/en-US/price/pay-as-you-go
- https://mimo.mi.com/docs/en-US/quick-start/summary/model
- V2 series deprecated 2026-06-30; V2.5 is current.
- Overseas (USD) pricing used for pricing fields; CNY kept in extra.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "xiaomi.json"
INSTALLED_DIR = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"
LOG = WORKDIR / "provider_update_log.md"
SOURCE_PRICE = "https://mimo.mi.com/docs/en-US/price/pay-as-you-go"
SOURCE_MODELS = "https://mimo.mi.com/docs/en-US/quick-start/summary/model"


def base(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    input_modalities: list[str],
    output_modalities: list[str],
    pricing: dict | None = None,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    reasoning: bool = False,
    vision: bool = False,
    fc: bool = False,
    json_mode: bool = False,
    chat: bool | None = True,
    streaming: bool | None = None,
    responses_api: bool | None = None,
    license_type: str = "api",
    knowledge_cutoff: str | None = None,
    extra: dict | None = None,
) -> dict:
    aliases = list(aliases or [])
    bare = model_id.split("/")[-1]
    # Native catalog only. Route-qualified IDs such as xiaomi/<id>
    # belong to the openrouter catalog and must not be added here.
    for a in (bare,):
        if a not in aliases and a != model_id:
            aliases.append(a)
    row = {
        "provider": "xiaomi",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_function_calling": fc,
        "supports_json_mode": json_mode,
        "supports_streaming": streaming,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": responses_api,
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
        "extra": {
            "source_pricing": SOURCE_PRICE,
            "source_models": SOURCE_MODELS,
            **(extra or {}),
        },
    }
    if pricing is not None:
        row["pricing"] = pricing
    return row


MODEL_ID_RE = re.compile(r"mimo-[a-z0-9][a-z0-9.-]*", re.IGNORECASE)


def _fetch_tables(page, url: str) -> tuple[list[dict], str]:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.locator("table").first.wait_for(timeout=30_000)
    page.wait_for_timeout(500)
    result = page.evaluate(
        r"""() => ({
            text: document.body?.innerText || '',
            tables: Array.from(document.querySelectorAll('table')).map((table, index) => ({
                index,
                rows: Array.from(table.querySelectorAll('tr')).map(row =>
                    Array.from(row.querySelectorAll('th,td')).map(cell =>
                        (cell.innerText || '').trim().replace(/\s+/g, ' ')
                    )
                ).filter(row => row.some(cell => cell)),
            })),
        })"""
    )
    return result["tables"], result["text"]


def _number_with_unit(text: str, label: str) -> int:
    match = re.search(rf"{re.escape(label)}\s*:\s*([\d,.]+)\s*([kKmM]?)", text, re.I)
    if not match:
        return 0
    value = float(match.group(1).replace(",", ""))
    unit = match.group(2).lower()
    return int(value * (1_000 if unit == "k" else 1_000_000 if unit == "m" else 1))


def build() -> list[dict]:
    """Discover model IDs, limits, modalities, and prices from MiMo's live docs."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        model_tables, _ = _fetch_tables(page, SOURCE_MODELS)
        price_tables, price_text = _fetch_tables(page, SOURCE_PRICE)
        browser.close()

    specs: dict[str, dict] = {}
    for table in model_tables:
        rows = table.get("rows") or []
        if not rows or not any("model id" in cell.lower() for cell in rows[0]):
            continue
        group = "text"
        inherited_capabilities = ""
        inherited_context = 0
        inherited_output = 0
        for cells in rows[1:]:
            joined = " ".join(cells)
            ids = list(dict.fromkeys(MODEL_ID_RE.findall(cells[0] if cells else "")))
            if not ids:
                continue
            if any(name.lower().endswith("-asr") for name in ids):
                group = "asr"
            elif any("-tts" in name.lower() for name in ids):
                group = "tts"
            facts = " ".join(cells[1:])
            if re.search(r"Context Window\s*:", facts, re.I):
                inherited_context = _number_with_unit(facts, "Context Window")
            if re.search(r"Maximum Output\s*:", facts, re.I):
                inherited_output = _number_with_unit(facts, "Maximum Output")
            if any(
                phrase in facts.lower()
                for phrase in ("text generation", "full-modal understanding", "speech recognition", "speech synthesis")
            ):
                inherited_capabilities = facts
            capabilities = facts or inherited_capabilities
            context = _number_with_unit(facts, "Context Window") or inherited_context
            max_output = _number_with_unit(facts, "Maximum Output") or inherited_output
            for model_id in ids:
                specs[model_id.lower()] = {
                    "model_id": model_id,
                    "group": group,
                    "capabilities": capabilities,
                    "context_window": context,
                    "max_output_tokens": max_output,
                }

    if not specs:
        raise RuntimeError("MiMo official model tables yielded no model IDs")

    prices: dict[str, dict] = {}
    billing_type = "realtime"
    for table in price_tables:
        for cells in (table.get("rows") or [])[1:]:
            if not cells:
                continue
            first = cells[0].strip().lower()
            if first in {"real-time api", "batch api"}:
                billing_type = "batch" if first == "batch api" else "realtime"
            model_ids = list(dict.fromkeys(MODEL_ID_RE.findall(" ".join(cells))))
            if not model_ids:
                continue
            money = [float(value) for value in re.findall(r"\$([0-9]+(?:\.[0-9]+)?)", " ".join(cells))]
            if len(money) >= 3:
                for model_id in model_ids:
                    slot = prices.setdefault(model_id.lower(), {})
                    entry = {
                        "cached_input_per_1m": money[-3],
                        "input_per_1m": money[-2],
                        "output_per_1m": money[-1],
                        "currency": "USD",
                    }
                    if billing_type == "batch":
                        slot["batch"] = entry
                    else:
                        slot["realtime"] = entry
            elif model_ids[0].lower().endswith("-asr") and money:
                prices.setdefault(model_ids[0].lower(), {})["price_per_hour_usd"] = money[-1]

    deprecated_match = re.search(
        r"(?:deprecated|deprecation)[^\n]{0,120}?(October\s+\d{1,2},?\s*\d{4})",
        price_text,
        re.I,
    )
    deprecation_date = None
    if deprecated_match:
        date_text = re.sub(r",\s*", ", ", deprecated_match.group(1))
        try:
            deprecation_date = datetime.strptime(date_text, "%B %d, %Y").date().isoformat()
        except ValueError:
            pass

    models: list[dict] = []
    for key, spec in sorted(specs.items()):
        model_id = spec["model_id"]
        group = spec["group"]
        caps = spec["capabilities"].lower()
        if group == "asr":
            input_modalities, output_modalities = ["audio"], ["text"]
            chat, vision, audio_input, audio_output = False, False, True, False
        elif group == "tts":
            is_clone = "voiceclone" in model_id.lower()
            input_modalities = ["text", "audio"] if is_clone else ["text"]
            output_modalities = ["audio"]
            chat, vision, audio_input, audio_output = False, False, is_clone, True
        else:
            full_modality = "full-modal understanding" in caps
            input_modalities = ["text", "image", "audio", "video"] if full_modality else ["text"]
            output_modalities = ["text"]
            chat = "text generation" in caps or "deep thinking" in caps
            vision = "image" in input_modalities
            audio_input = "audio" in input_modalities
            audio_output = False

        pricing_info = prices.get(key, {})
        realtime = pricing_info.get("realtime")
        pricing = None
        extra: dict = {
            "source_models": SOURCE_MODELS,
            "source_pricing": SOURCE_PRICE,
            "official_capabilities": spec["capabilities"],
        }
        if realtime:
            pricing = {
                "input_per_1m": realtime["input_per_1m"],
                "output_per_1m": realtime["output_per_1m"],
                "currency": "USD",
            }
            extra["cached_input_per_1m"] = realtime["cached_input_per_1m"]
        if pricing_info.get("batch"):
            extra["batch_pricing"] = pricing_info["batch"]
        if pricing_info.get("price_per_hour_usd") is not None:
            extra["price_per_hour_usd"] = pricing_info["price_per_hour_usd"]
        if group == "tts" and "free for a limited time" in price_text.lower():
            extra["pricing_status"] = "free for a limited time; official price not posted"
        if deprecation_date and model_id.lower() in {"mimo-v2.5", "mimo-v2.5-pro"}:
            extra["deprecation_date"] = deprecation_date
        deprecated = bool(
            deprecation_date
            and model_id.lower() in {"mimo-v2.5", "mimo-v2.5-pro"}
            and datetime.fromisoformat(deprecation_date).date() <= datetime.now(timezone.utc).date()
        )
        model = base(
            model_id=model_id,
            display=model_id,
            ctx=spec["context_window"],
            max_out=spec["max_output_tokens"],
            input_modalities=input_modalities,
            output_modalities=output_modalities,
            pricing=pricing,
            deprecated=deprecated,
            reasoning="deep thinking" in caps,
            vision=vision,
            fc="function call" in caps,
            json_mode="structured output" in caps,
            chat=chat,
            streaming=("streaming output" in caps) if chat else None,
            responses_api=True if chat else False,
            extra=extra,
        )
        model["supports_audio_input"] = audio_input
        model["supports_audio_output"] = audio_output
        models.append(model)
    return models


def main() -> None:
    models = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if INSTALLED_DIR.exists() and OUT.resolve() != (INSTALLED_DIR / OUT.name).resolve():
        shutil.copy2(OUT, INSTALLED_DIR / OUT.name)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1 for m in models if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"xiaomi.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        if m.get("deprecated"):
            continue
        p = m.get("pricing") or {}
        print(
            f"  {m['model_id']:32} in={p.get('input_per_1m')} out={p.get('output_per_1m')} "
            f"ctx={m['context_window']}",
            flush=True,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Xiaomi MiMo refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Models: {SOURCE_MODELS}\n"
        f"- Pricing: {SOURCE_PRICE} (Playwright live)\n"
        f"- Apply: `scripts/_update_xiaomi.py`\n\n"
        f"### Result\n"
        f"- xiaomi.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- Catalog rows, limits, capabilities, and published prices are parsed from live official tables.\n"
        f"- ASR hourly rates, TTS promotional pricing, batch pricing, and deprecation dates are parsed when published.\n"
        f"- No local xiaomi_legacy_models.json manifest or hard-coded model list is used.\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
