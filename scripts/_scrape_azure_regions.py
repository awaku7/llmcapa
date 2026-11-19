"""Fetch Azure Foundry model region availability from Microsoft Learn.

Source: the "Region availability for Foundry Models sold by Azure" page
(https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/
models-sold-directly-by-azure-region-availability).

The page groups matrix tables by deployment type (Global Standard,
Data Zone Standard, Standard/Regional, the provisioned and batch
variants). Each table lists model versions as rows and Azure regions
(``eastus``, ``japaneast``, ...) as columns; a cell with a check mark
means that version can be deployed in that region under that
deployment type.

``azure_foundry.json`` carries one record per model name rather than
per version, so the regions recorded here are the union over every
listed version and every deployment type: the regions where the model
can be deployed at all. Which deployment types a region supports is a
deployment-time choice documented on the source page. Only models
present in ``azure_foundry.json`` are returned. A listed model with no
supported region at all still gets an explicit record (source and
check date only) so a refresh clears any regional availability it
carried before; models absent from the page are not returned.
"""

from __future__ import annotations

import datetime
import json
import re
from html.parser import HTMLParser
from pathlib import Path

try:
    from scripts.provider_updates._http import fetch_bytes
except ModuleNotFoundError:  # Running this scraper directly from the scripts directory.
    from provider_updates._http import fetch_bytes

REGIONS_PAGE_URL = (
    "https://learn.microsoft.com/en-us/azure/foundry/foundry-models/"
    "concepts/models-sold-directly-by-azure-region-availability"
)
AZURE_FOUNDRY_JSON = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "llmcapa"
    / "data"
    / "azure_foundry.json"
)

# The h2 section ids whose tables carry region availability. Tables
# anywhere else on the page are not model availability matrices.
_DEPLOYMENT_SECTIONS = {
    "global-standard",
    "data-zone-standard",
    "standardregional",
    "global-provisioned-managed",
    "data-zone-provisioned-managed",
    "regional-provisioned-managed",
    "global-batch",
    "data-zone-batch",
}
_REGION_HEADER = re.compile(r"[a-z][a-z0-9]*")


def _fetch(url: str) -> bytes:
    return fetch_bytes(
        url,
        headers={"User-Agent": "llmcapa catalog updater"},
        timeout=60,
    )


class _AvailabilityParser(HTMLParser):
    """Collect per-model deployment regions from the availability tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section: str | None = None
        self._in_h2 = False
        self._in_table = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row: list[str] | None = None
        self._headers: list[str] | None = None
        # Page model name -> supported regions, in document order.
        self.models: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h2":
            self._in_h2 = True
            section = dict(attrs).get("id")
            self.section = section if section in _DEPLOYMENT_SECTIONS else None
        elif tag == "table" and self.section is not None:
            self._in_table = True
            self._headers = None
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_h2 = False
        elif tag in ("th", "td") and self._in_cell:
            self._in_cell = False
            if self._row is not None:
                self._row.append("".join(self._cell_parts).strip())
        elif tag == "tr" and self._row is not None:
            row, self._row = self._row, None
            if self._headers is None:
                if (
                    len(row) >= 3
                    and row[0].casefold() == "model"
                    and row[1].casefold() == "version"
                    and all(_REGION_HEADER.fullmatch(h) for h in row[2:])
                ):
                    self._headers = row[2:]
                return
            if len(row) != len(self._headers) + 2 or not row[0]:
                return
            regions = self.models.setdefault(row[0], [])
            for region, cell in zip(self._headers, row[2:]):
                if "✅" in cell and region not in regions:
                    regions.append(region)
        elif tag == "table":
            self._in_table = False
            self._headers = None

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


def parse_availability_html(html: str) -> dict[str, list[str]]:
    """Parse the region availability page into per-model region lists."""
    parser = _AvailabilityParser()
    parser.feed(html)
    return parser.models


def fetch_azure_regions(checked_at: str) -> dict[str, dict]:
    """Return regional availability keyed by azure_foundry.json model ID."""
    html = _fetch(REGIONS_PAGE_URL).decode("utf-8", errors="replace")
    parsed = parse_availability_html(html)
    if not parsed:
        raise RuntimeError("no Azure region tables found in official page")
    payload = json.loads(AZURE_FOUNDRY_JSON.read_text(encoding="utf-8"))
    known = {model["model_id"] for model in payload["models"]}
    by_casefold: dict[str, str] = {}
    for model_id in known:
        by_casefold.setdefault(model_id.casefold(), model_id)

    result: dict[str, dict] = {}
    for name, regions in parsed.items():
        model_id = name if name in known else by_casefold.get(name.casefold())
        if model_id is None:
            continue
        record: dict[str, object] = {}
        if regions:
            record["locations"] = regions
        # A model listed with no supported region keeps an explicit
        # record (source + check date only) so a refresh clears stale
        # regions instead of leaving them in place.
        record["source_url"] = REGIONS_PAGE_URL
        record["checked_at"] = checked_at
        result[model_id] = record  # type: ignore[assignment]
    return result


if __name__ == "__main__":
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    print(json.dumps(fetch_azure_regions(today), ensure_ascii=False, indent=2))
