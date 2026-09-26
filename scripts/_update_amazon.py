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

try:
    from scripts._scrape_amazon import fetch_nova_prices
except ModuleNotFoundError:  # Direct execution: python scripts/_update_amazon.py
    from _scrape_amazon import fetch_nova_prices

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "amazon.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "amazon.json"
)
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
    # Native catalog: Bedrock harness alias amazon.<id>:0 only.
    # Route-qualified IDs such as amazon/<id> belong to the
    # openrouter catalog and must not be added as native aliases.
    bare = model_id
    bare = bare.removeprefix("amazon/")
    br_id = f"amazon.{bare}:0" if not bare.startswith("amazon.") else bare
    # also bare without version suffix variants handled by caller
    for a in (br_id,):
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
        if (
            pricing.get("input") is None
            and pricing.get("output") is None
            and "unit" in (extra or {})
        ):
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


def build(nova_prices: dict[str, dict[str, float]]) -> list[dict]:
    """Refresh Nova prices and carry forward records from the published catalog.

    The updater does not read a separately curated legacy-model manifest. The
    existing catalog is used only to preserve metadata for records not covered
    by the current Nova pricing page.
    """
    if not nova_prices:
        raise RuntimeError("official AWS pricing returned no Nova models")
    try:
        current = json.loads(OUT.read_text(encoding="utf-8"))
        models = [dict(model) for model in current.get("models", [])]
    except (OSError, json.JSONDecodeError):
        models = []

    by_id = {str(model.get("model_id", "")): model for model in models}
    for model_id, rate in nova_prices.items():
        model = by_id.get(model_id)
        if model is None:
            model = base(
                model_id=model_id,
                display=model_id.replace("-", " ").title(),
                ctx=0,
                max_out=0,
                pricing=rate,
                extra={"catalog_metadata_status": "official price only; limits unknown"},
            )
            models.append(model)
            by_id[model_id] = model
        else:
            model["pricing"] = {
                "input_per_1m": rate.get("input"),
                "output_per_1m": rate.get("output"),
                "currency": "USD",
            }
            model.setdefault("extra", {})["pricing_source"] = SOURCE_NOVA
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
    nova_prices = fetch_nova_prices()
    models = build(nova_prices)
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
        f"- Current Nova token prices are fetched from official AWS sources\n"
        f"- Historical Titan and specialty metadata remains static\n"
        f"- Bedrock aliases are generated as amazon.*:0\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
