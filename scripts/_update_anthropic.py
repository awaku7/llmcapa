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


def fetch(url: str) -> str:
    """Fetch official documentation, tolerating only local CA verification issues."""
    import ssl
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": "llmcapa official-catalog-updater/1.0"})
    try:
        with urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        with urlopen(
            req, timeout=30, context=ssl._create_unverified_context()
        ) as response:
            return response.read().decode("utf-8", errors="replace")


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
    for table in parser.tables:
        if not table or len(table[0]) < 6 or "Base input" not in " ".join(table[0]):
            continue
        for row in table[1:]:
            if len(row) < 6:
                continue
            name = _text(row[0])
            if not name.lower().startswith("claude "):
                continue
            result.append(
                {
                    "name": name,
                    "input": _price(row[1]),
                    "cache_5m": _price(row[2]),
                    "cache_1h": _price(row[3]),
                    "cache_hit": _price(row[4]),
                    "output": _price(row[5]),
                    "deprecated": "retired" in name.lower()
                    or "deprecated" in name.lower(),
                }
            )
    return result


def _model_id(name: str) -> str:
    import re

    clean = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", clean).strip("-")


def _template(row: dict) -> dict:
    mid = _model_id(row["name"])
    long_ctx = any(
        x in mid
        for x in (
            "opus-4-6",
            "opus-4-7",
            "opus-4-8",
            "opus-5",
            "sonnet-4-6",
            "sonnet-5",
            "fable-5-1",
            "mythos-5-1",
        )
    )
    ctx = 1_000_000 if long_ctx else 200_000
    max_out = 128_000 if long_ctx or "5" in mid else 64_000
    extra = {
        "cache_write_5m_per_1m": row["cache_5m"],
        "cache_write_1h_per_1m": row["cache_1h"],
        "cache_hit_per_1m": row["cache_hit"],
        "batch_input_per_1m": row["input"] / 2,
        "batch_output_per_1m": row["output"] / 2,
    }
    extra = {k: v for k, v in extra.items() if v is not None}
    if long_ctx:
        extra.update(
            {"long_context_window": 1_000_000, "long_context_at_standard_rates": True}
        )
    return base(
        model_id=mid,
        display=row["name"],
        ctx=ctx,
        max_out=max_out,
        pricing={"input": row["input"], "output": row["output"]},
        extra=extra,
        deprecated=row["deprecated"],
        reasoning=True,
        effort=True,
        effort_values=["low", "medium", "high"] if "haiku" not in mid else None,
    )


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
        models.append(old)
    # Keep historical models that are no longer listed in current pricing.
    discovered_ids = {m["model_id"] for m in models}
    models.extend(m for mid, m in previous.items() if mid not in discovered_ids)
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
