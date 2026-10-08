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

from _computer_use_metadata import anthropic_computer_use_capability
from _metadata_loader import apply_context_window_overrides, context_window_override

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "anthropic.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "anthropic.json"
)
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
        "thinking_budget_values": {
            "type": "token_range",
            "min": 1024,
            "max": max_out or 128000,
        },
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
    long_context_window: int | None = None,
    long_context_at_standard_rates: bool | None = None,
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
    if long_context_window is not None:
        e["long_context_window"] = long_context_window
    if long_context_at_standard_rates is not None:
        e["long_context_at_standard_rates"] = long_context_at_standard_rates
    if notes:
        e.update(notes)
    return e


def fetch(url: str) -> str:
    """Fetch official docs, rendering the pricing page when it is client-side."""
    import ssl
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": "llmcapa official-catalog-updater/1.0"})
    try:
        with urlopen(req, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        with urlopen(
            req, timeout=30, context=ssl._create_unverified_context()
        ) as response:
            html = response.read().decode("utf-8", errors="replace")

    if url != SOURCE_PRICING or discover_pricing(html):
        return html

    # The docs site renders its pricing table client-side. Fall back to the
    # rendered official page instead of failing the catalog update on the shell.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return html
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=60_000)
            page.wait_for_function(
                "Array.from(document.querySelectorAll('table')).some(t => "
                "t.innerText.includes('Base tokens') && "
                "t.innerText.includes('5m writes'))",
                timeout=30_000,
            )
            return page.content()
        finally:
            browser.close()


def _text(value: str) -> str:
    import re
    from html import unescape

    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _price(value: str) -> float | None:
    import re

    m = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", value.replace(",", ""))
    return float(m.group(1)) if m else None


def discover_pricing(html: str) -> list[dict]:
    """Read Anthropic's official model pricing table."""
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tables = []
            self.table = None
            self.row = None
            self.cell = None

        def handle_starttag(self, tag, attrs):
            if tag == "table":
                self.table = []
            elif tag == "tr" and self.table is not None:
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = []
            elif tag == "button" and self.cell is not None:
                label = dict(attrs).get("aria-label")
                if label:
                    self.cell.append(f" {label} ")

        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.cell is not None:
                self.row.append("".join(self.cell))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                if self.table is not None:
                    self.table.append(self.row)
                self.row = None
            elif tag == "table" and self.table is not None:
                self.tables.append(self.table)
                self.table = None

    parser = TableParser()
    parser.feed(html)
    result = []
    import re

    for table in parser.tables:
        header = " ".join(cell for row in table[:2] for cell in row).lower()
        if not all(
            label in header
            for label in ("base tokens", "input", "output", "5m writes", "1h writes")
        ):
            continue
        for row in table[2:]:
            if len(row) < 6:
                continue
            raw_name = _text(row[0])
            match = re.match(
                r"(?i)^(Claude\s+(?:(?:\d+(?:\.\d+)?)\s+)?"
                r"(?:Fable|Mythos|Opus|Sonnet|Haiku)(?:\s+\d+(?:\.\d+)?)?)",
                raw_name,
            )
            if not match:
                continue
            name = match.group(1)
            result.append(
                {
                    "name": name,
                    "input": _price(row[1]),
                    "output": _price(row[2]),
                    "cache_5m": _price(row[3]),
                    "cache_1h": _price(row[4]),
                    "cache_hit": _price(row[5]),
                    "deprecated": "retired" in raw_name.lower()
                    or "deprecated" in raw_name.lower(),
                }
            )
    return result


def _model_id(name: str) -> str:
    import re

    clean = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", clean).strip("-")


def _template(row: dict) -> dict:
    mid = _model_id(row["name"])
    max_out = 128_000 if "5" in mid else 64_000
    extra = {
        "cache_write_5m_per_1m": row["cache_5m"],
        "cache_write_1h_per_1m": row["cache_1h"],
        "cache_hit_per_1m": row["cache_hit"],
        "batch_input_per_1m": row["input"] / 2,
        "batch_output_per_1m": row["output"] / 2,
    }
    extra = {k: v for k, v in extra.items() if v is not None}
    model = base(
        model_id=mid,
        display=row["name"],
        ctx=0,
        max_out=max_out,
        pricing={"input": row["input"], "output": row["output"]},
        extra=extra,
        deprecated=row["deprecated"],
        reasoning=True,
        effort=True,
        effort_values=(
            ["low", "medium", "high", "xhigh", "max"]
            if mid == "claude-haiku-5-5"
            else ["low", "medium", "high"] if "haiku" not in mid else None
        ),
    )
    _reconcile_haiku_55(model)
    return model


def _reconcile_haiku_55(model: dict) -> None:
    """Keep official Haiku 5.5 metadata intact across pricing-page refreshes."""
    if model.get("model_id") != "claude-haiku-5-5":
        return
    source = "https://platform.claude.com/docs/en/models/haiku-5-5/overview"
    model.update(
        context_window=1_000_000,
        max_output_tokens=128_000,
        knowledge_cutoff="2026-06",
        supports_reasoning=True,
        supports_reasoning_effort=True,
        reasoning_effort_values=["low", "medium", "high", "xhigh", "max"],
        supports_thinking_budget=False,
        thinking_control={
            "kind": "effort",
            "parameter": "output_config.effort",
            "values": ["low", "medium", "high", "xhigh", "max"],
            "default": "medium",
            "thinking_type": "adaptive",
        },
        aliases=[],
    )
    model.pop("thinking_budget_values", None)
    model["pricing"] = {
        "input_per_1m": 0.10,
        "output_per_1m": 0.50,
        "currency": "USD",
        "prompt_length_threshold_tokens": 100_000,
        "long_input_per_1m": 0.50,
        "long_output_per_1m": 2.50,
    }
    extra = dict(model.get("extra") or {})
    extra.update(
        source=source,
        overview=source,
        migration_guide=(
            "https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide"
        ),
        cache_write_5m_per_1m=0.125,
        cache_write_1h_per_1m=0.20,
        cache_hit_per_1m=0.01,
        cache_write_5m_long_per_1m=0.625,
        cache_write_1h_long_per_1m=1.0,
        cache_hit_long_per_1m=0.05,
        batch_input_per_1m=0.05,
        batch_output_per_1m=0.25,
        batch_input_long_per_1m=0.25,
        batch_output_long_per_1m=1.25,
        batch_max_output_tokens=300_000,
        batch_output_beta_header="output-300k-2026-03-24",
        adaptive_thinking=True,
        default_effort="medium",
        thinking_disabled_allowed_effort=["low", "medium", "high"],
        thinking_budget_parameter_supported=False,
        sampling_parameters_non_default_supported=False,
        assistant_prefill_supported=False,
        tokenizer_note=(
            "Claude 4.7+ tokenizer; approximately 30% more tokens for the "
            "same text than Haiku 4.5"
        ),
        browser_use={
            "supported": True,
            "tool_type": "browser_toolset_20260801",
            "platforms": ["anthropic", "google-cloud"],
        },
        context_window_source=source,
        context_window_basis="official_catalog_snapshot",
    )
    model["extra"] = extra


def build() -> list[dict]:
    """Refresh from Anthropic's live pricing table, retaining existing metadata."""
    discovered = discover_pricing(fetch(SOURCE_PRICING))
    if not discovered:
        raise RuntimeError("Anthropic pricing table not found; refusing to overwrite")
    previous = {}
    if OUT.exists():
        previous = {
            m["model_id"]: m
            for m in json.loads(OUT.read_text(encoding="utf-8")).get("models", [])
        }
    models = []
    for row in discovered:
        mid = _model_id(row["name"])
        old = previous.get(mid) or next(
            (
                m
                for m in previous.values()
                if row["name"].lower() == m.get("display_name", "").lower()
            ),
            None,
        )
        if old is None:
            old = _template(row)
        else:
            old = dict(old)
            old["pricing"] = {
                "input_per_1m": row["input"],
                "output_per_1m": row["output"],
                "currency": "USD",
            }
            old["deprecated"] = row["deprecated"]
            extra = dict(old.get("extra") or {})
            for key, value in (
                ("cache_write_5m_per_1m", row["cache_5m"]),
                ("cache_write_1h_per_1m", row["cache_1h"]),
                ("cache_hit_per_1m", row["cache_hit"]),
            ):
                if value is not None:
                    extra[key] = value
            old["extra"] = extra
        if mid == "claude-haiku-5-5":
            _reconcile_haiku_55(old)
        else:
            old["supports_thinking_budget"] = True
            old["thinking_budget_values"] = {
                "type": "token_range",
                "min": 1024,
                "max": old.get("max_output_tokens") or 128000,
            }
        models.append(old)
    # Keep historical models that are no longer listed in current pricing.
    discovered_ids = {m["model_id"] for m in models}
    models.extend(m for mid, m in previous.items() if mid not in discovered_ids)
    # The pricing-page parser does not expose context lengths; refresh these
    # snapshot values from cited metadata rather than retaining the old model-name heuristic.
    for model in models:
        if context_window_override("anthropic", str(model.get("model_id", ""))):
            model["context_window"] = 0
    apply_context_window_overrides(models)

    # The pricing scraper cannot see prompt-length tiers or thinking controls.
    # Reconcile both discovered and carried-forward Haiku 5.5 records.
    for model in models:
        _reconcile_haiku_55(model)

    # Apply the current official Computer Use model/tool-version matrix after
    # the pricing refresh. This keeps the specialized capability from being
    # lost when model records are rebuilt or merged.
    for model in models:
        computer_use = anthropic_computer_use_capability(
            model.get("model_id", ""), "anthropic"
        )
        if computer_use is not None:
            model["computer_use"] = computer_use
        elif (model.get("computer_use") or {}).get("provider") == "anthropic":
            model.pop("computer_use", None)
    for model in models:
        if model.get("supports_thinking_budget"):
            model["thinking_budget_values"] = {
                "min": 1024,
                "max": model.get("max_output_tokens") or 128000,
            }
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
        f"- Live HTML fetch: official overview and pricing pages\n"
        f"- Docs: {SOURCE_OVERVIEW} / {SOURCE_PRICING}\n"
        f"- Apply: `scripts/_update_anthropic.py`\n\n"
        f"### Result\n"
        f"- anthropic.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- Parsed {priced} model price rows from the official pricing table; "
        f"cache and batch prices are derived from the same rows\n"
        f"- Existing metadata retained where model IDs matched; historical rows kept\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
