"""Fetch Amazon Bedrock regional availability from the official AWS docs.

Source: the "Regional availability by models" page, read as Markdown
(https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.md).

Each model section links to its model card and carries one table whose rows
are AWS Regions and whose columns are the inference options:

- ``locations``: union of the In-Region columns (`bedrock-runtime` and
  `bedrock-mantle`). A model counts as directly available in a Region when
  either endpoint serves it there. (The page gained a separate Mantle
  column; the runtime column alone would report some models, e.g. Claude
  Haiku 4.5, as available nowhere.)
- ``geographic_inference_regions``: source Regions of the Geo column.
- ``global_inference_regions``: source Regions of the Global column.

A cell counts as supported when it carries the supported icon or a legacy
note such as ``Legacy (EOL: 2026-11-26)`` / ``EOL: 2026-07-30`` (the model
is still available in that Region until the stated date). A refresh dated
after the stated EOL date no longer counts the cell as supported.

Model sections are keyed by model-card slug. Slugs are resolved to catalog
model IDs by fetching each card and matching the IDs it names against the
IDs and aliases present in ``amazon.json``; cards whose model is not in the
catalog are skipped.
"""

from __future__ import annotations

import datetime
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from scripts.provider_updates._http import fetch_bytes
except ModuleNotFoundError:  # Running this scraper directly from the scripts directory.
    from provider_updates._http import fetch_bytes

REGIONS_URL = (
    "https://docs.aws.amazon.com/bedrock/latest/userguide/"
    "models-region-compatibility.md"
)
REGIONS_PAGE_URL = (
    "https://docs.aws.amazon.com/bedrock/latest/userguide/"
    "models-region-compatibility.html"
)
CARDS_BASE = "https://docs.aws.amazon.com/bedrock/latest/userguide/"
AMAZON_JSON = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "amazon.json"
)

_HEADING = re.compile(
    r"\*\*\[[^\]]+\]\(model-card-([^)#]+)\.md(?:#[^)]*)?\)[^\n*]*\*\*"
)
_REGION_ID = re.compile(r"^([a-z]{2}(?:-[a-z]+)+-\d+)\s*\(")


def _fetch(url: str) -> bytes:
    return fetch_bytes(
        url,
        headers={"User-Agent": "llmcapa catalog updater"},
        timeout=30,
    )


_EOL_DATE = re.compile(r"EOL:\s*(\d{4}-\d{2}-\d{2})")


def _supported(cell: str, as_of: datetime.date | None = None) -> bool:
    cell = cell.strip()
    if not cell:
        return False
    if "icon-no" in cell:
        return False
    eol = _EOL_DATE.search(cell)
    if (
        eol is not None
        and as_of is not None
        and datetime.date.fromisoformat(eol.group(1)) < as_of
    ):
        # A legacy/EOL note means availability ends on the stated date;
        # a refresh after that date must not keep listing the Region.
        return False
    return "icon-yes" in cell or not cell.startswith("![")


def parse_region_tables(
    markdown: str, as_of: datetime.date | None = None
) -> dict[str, dict[str, list[str]]]:
    """Parse the regional-availability Markdown keyed by model-card slug.

    ``as_of`` is the refresh date: legacy cells whose stated EOL date has
    passed by then no longer count as supported.
    """
    result: dict[str, dict[str, list[str]]] = {}
    parts = _HEADING.split(markdown)
    # parts: [prelude, slug, body, slug, body, ...]
    for i in range(1, len(parts) - 1, 2):
        slug, body = parts[i], parts[i + 1]
        table = _parse_first_table(body, as_of)
        if table is None:
            continue
        if slug not in result:
            result[slug] = table
            continue
        # The page lists a few models twice with partial tables (e.g.
        # MiniMax M2.5); merge by union so no supported Region is lost.
        merged = result[slug]
        for key, values in table.items():
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)
    return result


def _parse_first_table(
    body: str, as_of: datetime.date | None = None
) -> dict[str, list[str]] | None:
    lines = body.splitlines()
    header_at = None
    columns: dict[str, int | list[int]] = {}
    for idx, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0].strip("*") != "Region":
            continue
        for pos, name in enumerate(cells):
            plain = name.strip("*")
            if "In-Region" in plain:
                # Runtime and Mantle columns both mean direct availability;
                # they are merged per row below to keep the page order.
                columns.setdefault("locations", []).append(pos)
            elif plain.startswith("Geo"):
                columns.setdefault("geographic_inference_regions", pos)
            elif plain.startswith("Global"):
                columns.setdefault("global_inference_regions", pos)
        if columns:
            header_at = idx
            break
    if header_at is None:
        return None

    found: dict[str, list[str]] = {
        "locations": [],
        "geographic_inference_regions": [],
        "global_inference_regions": [],
    }
    for line in lines[header_at + 1 :]:
        if not line.lstrip().startswith("|"):
            if found["locations"]:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", " "}:
            continue  # separator row
        match = _REGION_ID.match(cells[0])
        if not match:
            continue
        region = match.group(1)
        for key, pos in columns.items():
            positions = pos if isinstance(pos, list) else [pos]
            if any(p < len(cells) and _supported(cells[p], as_of) for p in positions):
                found[key].append(region)
    return found


_GEO_PREFIXES = ("us.", "eu.", "au.", "jp.", "in.", "ca.", "global.", "apac.")


def _catalog_owners() -> dict[str, set[str]]:
    """Map every known ID token (model IDs and aliases) to its records."""
    payload = json.loads(AMAZON_JSON.read_text(encoding="utf-8"))
    owners: dict[str, set[str]] = {}
    for model in payload["models"]:
        record = model["model_id"]
        owners.setdefault(record, set()).add(record)
        for alias in model.get("aliases") or []:
            owners.setdefault(alias, set()).add(record)
    return owners


def _base_id(token: str) -> str:
    for prefix in _GEO_PREFIXES:
        if token.startswith(prefix):
            return token[len(prefix) :]
    return token


def _resolve_card_records(slug: str, owners: dict[str, set[str]]) -> set[str]:
    """Return the catalog records one model card describes.

    Cards name their model mostly through inference-profile IDs
    (``us.``/``eu.``/``global.``/... forms) and only rarely by the bare
    model ID, so tokens are grouped by their prefix-stripped base ID and
    the most-mentioned base wins. The catalog keeps some models as
    duplicate records (a bare-ID record and a provider-prefixed record
    sharing the same aliases); every record owning the winning base ID or
    one of its prefixed forms is returned so all of them get the data.
    """
    try:
        text = _fetch(f"{CARDS_BASE}model-card-{slug}.md").decode(
            "utf-8", errors="replace"
        )
    except Exception:  # noqa: BLE001 - a failed card fetch resolves to no records
        return set()
    counts: dict[str, int] = {}
    for token in re.findall(r"[a-z0-9][a-z0-9._:-]*", text):
        if token in owners:
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return set()
    base_scores: dict[str, int] = {}
    for token, count in counts.items():
        base = _base_id(token)
        base_scores[base] = base_scores.get(base, 0) + count
    best = max(base_scores, key=lambda b: (base_scores[b], len(b)))
    records: set[str] = set()
    for token in counts:
        if _base_id(token) == best:
            records.update(owners[token])
    return records


def fetch_bedrock_regions(checked_at: str) -> dict[str, dict]:
    """Return regional availability keyed by amazon.json model ID."""
    markdown = _fetch(REGIONS_URL).decode("utf-8", errors="replace")
    tables = parse_region_tables(
        markdown, as_of=datetime.date.fromisoformat(checked_at)
    )
    if not tables:
        raise RuntimeError("no Bedrock region tables found in official AWS page")
    owners = _catalog_owners()

    resolved: dict[str, set[str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_resolve_card_records, slug, owners): slug for slug in tables
        }
        for future in as_completed(futures):
            records = future.result()
            if records:
                resolved[futures[future]] = records

    result: dict[str, dict] = {}
    for slug, records in resolved.items():
        table = tables[slug]
        regions: dict[str, object] = {}
        for key in (
            "locations",
            "geographic_inference_regions",
            "global_inference_regions",
        ):
            if table[key]:
                regions[key] = table[key]
        regions["source_url"] = REGIONS_PAGE_URL
        regions["checked_at"] = checked_at
        for record in records:
            result[record] = regions
    return result


if __name__ == "__main__":
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    print(json.dumps(fetch_bedrock_regions(today), ensure_ascii=False, indent=2))
