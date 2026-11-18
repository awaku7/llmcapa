"""Fetch Vertex AI endpoint locations from the official Google Cloud docs.

Source: the "Deployments and endpoints" page
(https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations).

The page groups models under Google / partner / open model headings, each
with the same sub-tables:

- ``Global``: models with a global endpoint -> ``global_endpoint``.
- ``Multi-region``: columns are the ``us`` / ``eu`` multi-regions ->
  ``multi_regions``.
- ``United States`` / ``Americas`` / ``Europe`` / ``Asia Pacific`` /
  ``Middle East``: columns are cloud locations (``us-central1``, ...) ->
  ``locations``.

A cell counts as supported when it carries ``aria-label="Supported"``
(the ``compare-yes`` class). Only models present in ``vertex-ai.json``
are returned. A listed model with no supported endpoint at all still
gets an explicit record (``global_endpoint: False`` with the source and
check date) so a refresh clears any regional availability it carried
before; models absent from the page are not returned.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

try:
    from scripts.provider_updates._http import fetch_bytes
except ModuleNotFoundError:  # Running this scraper directly from the scripts directory.
    from provider_updates._http import fetch_bytes

LOCATIONS_URL = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
    "resources/locations"
)
VERTEX_JSON = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "vertex-ai.json"
)

_GROUPS = {"google-models", "genai-partner-models", "genai-open-models"}
_LOCATION_SECTIONS = {
    "united-states",
    "americas",
    "europe",
    "asia-pacific",
    "middle-east",
}
_PAREN_ID = re.compile(r"\(([a-z0-9][a-z0-9._-]*)\)\s*$")
_QUOTED_ID = re.compile(r"'([a-z0-9][a-z0-9._-]*)'")


def _fetch(url: str) -> bytes:
    return fetch_bytes(
        url,
        headers={"User-Agent": "llmcapa catalog updater"},
        timeout=30,
    )


class _LocationsParser(HTMLParser):
    """Collect per-model endpoint support from the locations page tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.group: str | None = None
        self.section: str | None = None
        self._heading_tag: str | None = None
        self._heading_id: str | None = None
        self._in_table = False
        self._headers: list[str] = []
        self._row: list[tuple[str, bool]] | None = None
        self._cell_text: list[str] | None = None
        self._cell_supported = False
        self._cell_code: list[str] | None = None
        self._in_code = False
        self.models: dict[str, dict[str, object]] = {}

    # -- headings ---------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag in ("h2", "h3"):
            self._heading_tag = tag
            self._heading_id = attr.get("id")
        elif tag == "table" and self.group in _GROUPS and self.section:
            self._in_table = True
            self._headers = []
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._cell_text = []
            self._cell_code = []
            self._cell_supported = attr.get(
                "aria-label"
            ) == "Supported" or "compare-yes" in (attr.get("class") or "")
        elif tag == "code" and self._cell_text is not None:
            self._in_code = True

    def handle_endtag(self, tag):
        if tag in ("h2", "h3") and self._heading_tag == tag:
            if tag == "h2":
                self.group = self._heading_id if self._heading_id in _GROUPS else None
                self.section = None
            elif self.group in _GROUPS:
                self.section = self._heading_id
            self._heading_tag = None
            self._heading_id = None
        elif tag == "table" and self._in_table:
            self._in_table = False
        elif tag in ("th", "td") and self._cell_text is not None:
            text = " ".join("".join(self._cell_text).split())
            code = " ".join("".join(self._cell_code or []).split())
            if self._row is not None:
                self._row.append((code or text, self._cell_supported))
            if tag == "th":
                self._headers.append(text)
            self._cell_text = None
            self._cell_code = None
            self._in_code = False
        elif tag == "code":
            self._in_code = False
        elif tag == "tr" and self._row is not None:
            self._finish_row()
            self._row = None

    def handle_data(self, data):
        if self._cell_text is not None:
            self._cell_text.append(data)
            if self._in_code and self._cell_code is not None:
                self._cell_code.append(data)

    # -- rows ---------------------------------------------------------------
    def _finish_row(self) -> None:
        if not self._row:
            return
        model_cell = self._row[0][0]
        model_ids = _model_ids(model_cell)
        if not model_ids:
            return
        for model_id in model_ids:
            entry = self.models.setdefault(
                model_id,
                {"locations": [], "multi_regions": [], "global_endpoint": False},
            )
            for (cell_text, supported), header in zip(self._row, self._headers):
                if not supported:
                    continue
                region = _header_region(header)
                if self.section == "global":
                    entry["global_endpoint"] = True
                elif self.section == "multi-region" and region:
                    if region not in entry["multi_regions"]:
                        entry["multi_regions"].append(region)
                elif (
                    self.section in _LOCATION_SECTIONS
                    and region
                    and region not in entry["locations"]
                ):
                    entry["locations"].append(region)


def _model_ids(cell_text: str) -> list[str]:
    """Extract model IDs from a row's first cell code text."""
    text = cell_text.strip()
    if text.startswith("(["):
        return _QUOTED_ID.findall(text)
    match = _PAREN_ID.search(text)
    if match and any(c.isalpha() for c in match.group(1)):
        return [match.group(1)]
    # Bare code cells in the open-model tables can also be version tags
    # ("24.05") or status words; a model ID has a letter and a separator.
    if (
        re.fullmatch(r"[a-z0-9][a-z0-9._-]*", text)
        and any(c.isalpha() for c in text)
        and ("-" in text or "_" in text)
    ):
        return [text]
    return []


def _header_region(header: str) -> str | None:
    match = _PAREN_ID.search(header.strip())
    return match.group(1) if match else None


def parse_locations_html(html: str) -> dict[str, dict[str, object]]:
    """Parse the locations page HTML into per-model endpoint support."""
    parser = _LocationsParser()
    parser.feed(html)
    return parser.models


def fetch_vertex_regions(checked_at: str) -> dict[str, dict]:
    """Return endpoint locations keyed by vertex-ai.json model ID."""
    html = _fetch(LOCATIONS_URL).decode("utf-8", errors="replace")
    parsed = parse_locations_html(html)
    if not parsed:
        raise RuntimeError("no Vertex AI locations found in official page")
    payload = json.loads(VERTEX_JSON.read_text(encoding="utf-8"))
    known = {model["model_id"] for model in payload["models"]}

    result: dict[str, dict] = {}
    for model_id, entry in parsed.items():
        if model_id not in known:
            continue
        regions: dict[str, object] = {}
        if entry["locations"]:
            regions["locations"] = entry["locations"]
        if entry["multi_regions"]:
            regions["multi_regions"] = entry["multi_regions"]
        if entry["global_endpoint"]:
            regions["global_endpoint"] = True
        elif not regions:
            # Listed on the page but no endpoint is supported: keep an
            # explicit empty record so the refresh clears stale regions
            # instead of leaving them in place.
            regions["global_endpoint"] = False
        regions["source_url"] = LOCATIONS_URL
        regions["checked_at"] = checked_at
        result[model_id] = regions
    return result


if __name__ == "__main__":
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    print(json.dumps(fetch_vertex_regions(today), ensure_ascii=False, indent=2))
