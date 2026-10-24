"""Refresh Sakana model IDs by scraping its public official model docs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "sakana.json"
BASE_URL = "https://api.sakana.ai/v1"
SOURCE_GET_STARTED = "https://console.sakana.ai/get-started"
SOURCE_MODELS = "https://console.sakana.ai/models"
SOURCE_PRICING = "https://console.sakana.ai/pricing"
MODEL_REFERENCE = re.compile(
    r"(?:\bmodel\s*[:=]\s*[\"'`]?|[\"']slug[\"']\s*:\s*[\"'`]?)([a-z][a-z0-9.-]*)",
    re.I,
)
VALID_MODEL_ID = re.compile(
    r"^(?:fugu(?:-[a-z0-9.]+)*|sakana-namazu(?:-[a-z0-9.]+)*)$", re.I
)


class _VisibleText(HTMLParser):
    """Extract visible SSR text, excluding scripts and styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "svg"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "svg"} and self._skip:
            self._skip -= 1
        elif not self._skip and tag.casefold() in {
            "p",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "pre",
            "code",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip() + " ")


def _fetch_page(url: str) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": "Mozilla/5.0 (compatible; llmcapa-provider-updater/1.0)",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(4_000_000).decode("utf-8", "replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(
            f"Sakana public model documentation fetch failed ({url}): {exc}"
        ) from exc
    parser = _VisibleText()
    parser.feed(raw)
    return "\n".join(parser.parts)


def fetch_inventory() -> dict[str, str]:
    pages = {
        "get_started": _fetch_page(SOURCE_GET_STARTED),
        "models": _fetch_page(SOURCE_MODELS),
        "pricing": _fetch_page(SOURCE_PRICING),
    }
    if "Fugu" not in pages["models"] or "Sakana Namazu" not in pages["get_started"]:
        raise RuntimeError(
            "Sakana public model docs did not contain expected model families"
        )
    return pages


def parse_model_inventory(docs: dict[str, str]) -> list[dict]:
    """Extract model parameter values and versioned API IDs shown in public docs."""
    if not isinstance(docs, dict) or not all(
        isinstance(docs.get(key), str) for key in ("get_started", "models", "pricing")
    ):
        raise ValueError(
            "Sakana scraper expects get-started, models, and pricing documentation"
        )
    combined = "\n".join(docs.values())
    ids: dict[str, str] = {}
    for match in MODEL_REFERENCE.finditer(combined):
        model_id = match.group(1).strip().rstrip(".,;:")
        if VALID_MODEL_ID.fullmatch(model_id):
            ids[model_id.casefold()] = model_id
    for match in re.finditer(
        r"`((?:fugu|sakana-namazu)(?:-[a-z0-9.]+)*)`", combined, re.I
    ):
        model_id = match.group(1)
        if VALID_MODEL_ID.fullmatch(model_id):
            ids[model_id.casefold()] = model_id
    for match in re.finditer(r"Fixed pricing for\s+(fugu-[a-z0-9.-]+)", combined, re.I):
        model_id = match.group(1).rstrip(".,;:")
        if VALID_MODEL_ID.fullmatch(model_id):
            ids[model_id.casefold()] = model_id
    # The docs identify Sakana Namazu by name and give its exact versioned SKU
    # in the public pricing section; both are documented model spellings.
    for model_id in (
        "fugu",
        "fugu-ultra",
        "fugu-max",
        "fugu-cyber",
        "sakana-namazu",
        "sakana-namazu-v1.0",
    ):
        if re.search(r"\b" + re.escape(model_id) + r"\b", combined, re.I):
            ids.setdefault(model_id.casefold(), model_id)
    if not ids:
        raise ValueError("Sakana public docs contained no API model IDs")
    return [
        {
            "model_id": model_id,
            "display_name": model_id.replace("-", " ").title(),
            "created": None,
            "owned_by": "sakana",
        }
        for model_id in sorted(ids.values(), key=str.casefold)
    ]


def merge_inventory(
    snapshots: list[dict], previous: list[dict], checked_at: str
) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    merged = []
    seen: set[str] = set()
    for snapshot in snapshots:
        key = snapshot["model_id"].casefold()
        row = dict(old_by_id.get(key) or {})
        row.update(
            {
                "provider": "sakana",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "deprecated": False,
            }
        )
        row.setdefault("context_window", 0)
        row.setdefault("max_output_tokens", 0)
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE_MODELS,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_sakana_public_docs",
                "base_url": BASE_URL,
                "api_model_owner": snapshot.get("owned_by"),
                "not_listed_in_current_docs": False,
            }
        )
        row["extra"] = extra
        merged.append(row)
        seen.add(key)
    for old in previous:
        if not isinstance(old, dict):
            continue
        key = str(old.get("model_id", "")).casefold()
        if key and key not in seen:
            row = dict(old)
            extra = dict(row.get("extra") or {})
            extra.update(
                {
                    "official_source_checked_at": checked_at,
                    "not_listed_in_current_docs": True,
                }
            )
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(snapshots: list[dict], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_inventory(snapshots, data.get("models") or [], checked_at)
    DATA.write_text(
        json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"sakana.json: refreshed {len(snapshots)} public-doc model IDs; total={len(models)}"
    )
    return len(snapshots)


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_model_inventory(fetch_inventory()), checked_at=checked_at)


if __name__ == "__main__":
    main()
