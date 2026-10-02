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

from _computer_use_metadata import anthropic_computer_use_capability

try:
    from scripts._scrape_amazon import fetch_nova_prices as _fetch_nova_prices
except ModuleNotFoundError:
    try:
        from _scrape_amazon import fetch_nova_prices as _fetch_nova_prices
    except ModuleNotFoundError:
        _fetch_nova_prices = None

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "amazon.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "amazon.json"
)
LOG = WORKDIR / "provider_update_log.md"
SOURCE_BEDROCK = "https://aws.amazon.com/bedrock/pricing/"
SOURCE_NOVA = "https://aws.amazon.com/nova/pricing/"
ANTHROPIC_DATA = WORKDIR / "src" / "llmcapa" / "data" / "anthropic.json"
BEDROCK_CLAUDE_MODELS = {
    "anthropic.claude-opus-5-5": ("claude-opus-5-5", "anthropic-claude-opus-5-5"),
    "anthropic.claude-sonnet-5-5": ("claude-sonnet-5-5", "anthropic-claude-sonnet-5-5"),
    "anthropic.claude-opus-5": ("claude-opus-5", "anthropic-claude-opus-5"),
    "anthropic.claude-sonnet-5": ("claude-sonnet-5", "anthropic-claude-sonnet-5"),
    "anthropic.claude-opus-4-8": ("claude-opus-4-8", "anthropic-claude-opus-4-8"),
    "anthropic.claude-opus-4-7": ("claude-opus-4-7", "anthropic-claude-opus-4-7"),
    "anthropic.claude-opus-4-6-v1": ("claude-opus-4-6", "anthropic-claude-opus-4-6"),
    "anthropic.claude-sonnet-4-6": ("claude-sonnet-4-6", "anthropic-claude-sonnet-4-6"),
    "anthropic.claude-opus-4-5-20251101-v1:0": ("claude-opus-4-5", "anthropic-claude-opus-4-5"),
    "anthropic.claude-sonnet-4-5-20250929-v1:0": ("claude-sonnet-4-5", "anthropic-claude-sonnet-4-5"),
    "anthropic.claude-haiku-4-5-20251001-v1:0": ("claude-haiku-4-5", "anthropic-claude-haiku-4-5"),
}
SOURCE_API = (
    "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/"
    "bedrock/USD/current/bedrock.json"
)
REGION_NOTE = "US East (N. Virginia) on-demand standard"
NOVA_PRICING_MODE = "live"


def fetch_nova_prices() -> dict[str, dict[str, float]]:
    """Use the official Nova scraper, or reuse bundled pricing if absent.

    The repository snapshot may not include the optional legacy pricing
    scraper. In that case, reuse the last bundled Nova prices so catalog
    reconciliation remains runnable without claiming a live price refresh.
    """
    global NOVA_PRICING_MODE
    if _fetch_nova_prices is not None:
        NOVA_PRICING_MODE = "live"
        return _fetch_nova_prices()
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cached = {}
    for model in data.get("models", []):
        model_id = str(model.get("model_id", ""))
        pricing = model.get("pricing") or {}
        if not model_id.startswith("nova-"):
            continue
        if pricing.get("input_per_1m") is None or pricing.get("output_per_1m") is None:
            continue
        cached[model_id] = {
            "input": pricing["input_per_1m"],
            "output": pricing["output_per_1m"],
        }
    if not cached:
        raise RuntimeError("Nova price scraper unavailable and no bundled prices to reuse")
    NOVA_PRICING_MODE = "bundled-cache"
    return cached


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


def add_bedrock_claude_models(models: list[dict]) -> int:
    """Add Claude models whose AWS model cards explicitly expose Computer use."""
    anthropic_models = {
        model.get("model_id"): model
        for model in json.loads(ANTHROPIC_DATA.read_text(encoding="utf-8")).get(
            "models", []
        )
    }
    by_id = {model.get("model_id"): model for model in models}
    inserted = 0
    for bedrock_id, (anthropic_id, card_slug) in BEDROCK_CLAUDE_MODELS.items():
        if bedrock_id in by_id:
            continue
        source = anthropic_models.get(anthropic_id)
        if source is None:
            continue
        card_url = (
            "https://docs.aws.amazon.com/bedrock/latest/userguide/"
            f"model-card-{card_slug}.html"
        )
        model = base(
            model_id=bedrock_id,
            display=f"Anthropic {source.get('display_name', anthropic_id)} (Amazon Bedrock)",
            ctx=source.get("context_window") or 0,
            max_out=source.get("max_output_tokens") or 0,
            pricing=None,
            input_modalities=source.get("input_modalities") or ["text"],
            output_modalities=source.get("output_modalities") or ["text"],
            vision=source.get("supports_vision", False),
            reasoning=source.get("supports_reasoning", False),
            function_calling=source.get("supports_function_calling", True),
            extra={
                "bedrock_model_family": "anthropic-claude",
                "source": card_url,
                "computer_use_note": "Computer Use is documented on this Bedrock model card.",
            },
        )
        model["display_name"] = (
            f"Anthropic {source.get('display_name', anthropic_id)} (Amazon Bedrock)"
        )
        model["supports_anthropic_api"] = False
        model["extra"]["endpoints"] = [
            {
                "base_url": "https://bedrock-runtime.{region}.amazonaws.com",
                "protocol": "aws-bedrock",
                "auth": "sigv4",
                "source": card_url,
            }
        ]
        capability = anthropic_computer_use_capability(bedrock_id, "amazon")
        if capability is None:
            continue
        capability["source_url"] = card_url
        model["computer_use"] = capability
        models.append(model)
        by_id[bedrock_id] = model
        inserted += 1
    return inserted


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

    # AWS's current model card uses the versioned programmatic ID.
    for model in models:
        if model.get("model_id") == "anthropic.claude-opus-4-6":
            model["model_id"] = "anthropic.claude-opus-4-6-v1"
            model["computer_use"] = anthropic_computer_use_capability(
                model["model_id"], "amazon"
            )
    bedrock_claude_inserted = add_bedrock_claude_models(models)

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
    # Bedrock Claude entries are carried forward from the curated model
    # catalog. Reconcile their Computer Use beta/tool versions against the
    # current Anthropic/AWS compatibility table on every refresh.
    for model in models:
        computer_use = anthropic_computer_use_capability(
            model.get("model_id", ""), "amazon"
        )
        if computer_use is not None:
            model["computer_use"] = computer_use
        elif (model.get("computer_use") or {}).get("provider") == "amazon":
            model.pop("computer_use", None)
    print(f"Bedrock Claude Computer Use models inserted={bedrock_claude_inserted}")
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
    print(f"Nova pricing source mode: {NOVA_PRICING_MODE}", flush=True)
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
        f"- Nova pricing mode: {NOVA_PRICING_MODE}\n"
        f"- Current Nova token prices are refreshed only when the optional scraper is available\n"
        f"- Historical Titan and specialty metadata remains static\n"
        f"- Claude Bedrock Computer Use capabilities are reconciled from official model cards\n"
        f"- Bedrock aliases are generated as amazon.*:0\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
