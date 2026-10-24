"""Refresh Relace's public model inventory by scraping official model docs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "relace.json"
BASE_URL = "https://models.relace.ai/v1"
OPEN_MODELS_SOURCE = "https://docs.relace.ai/docs/open-models/quickstart"
APPLY_SOURCE = "https://docs.relace.ai/api-reference/instant-apply/apply"
SEARCH_SOURCE = "https://docs.relace.ai/api-reference/fast-agentic-search/search"


def _fetch_markdown(url: str) -> str:
    request = Request(
        url + ".md",
        headers={
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read(2_000_000).decode("utf-8", "replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(
            f"Relace official model documentation fetch failed ({url}): {exc}"
        ) from exc


def fetch_inventory() -> dict[str, str]:
    pages = {
        "open_models": _fetch_markdown(OPEN_MODELS_SOURCE),
        "apply": _fetch_markdown(APPLY_SOURCE),
        "search": _fetch_markdown(SEARCH_SOURCE),
    }
    if (
        "Slug" not in pages["open_models"]
        or "relace-apply-3" not in pages["apply"]
        or "relace-search" not in pages["search"]
    ):
        raise RuntimeError(
            "Relace public docs did not include all expected model references"
        )
    return pages


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _number(value: str) -> float | None:
    value = value.replace("\\$", "$")
    match = re.search(r"\$\s*([\d,.]+)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _context(value: str) -> int:
    match = re.search(r"([\d,.]+)\s*([KM]?)", value, re.I)
    if not match:
        return 0
    number = float(match.group(1).replace(",", ""))
    return int(number * {"k": 1_000, "m": 1_000_000}.get(match.group(2).casefold(), 1))


def parse_model_inventory(docs: dict[str, str]) -> list[dict]:
    """Read documented open models plus Relace's Apply and Search products."""
    if not isinstance(docs, dict):
        raise ValueError("Relace scraper expects public docs pages")
    table = docs.get("open_models", "")
    header: list[str] | None = None
    result: dict[str, dict] = {}
    for line in table.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if (
            cells
            and cells[0].casefold() == "model"
            and any("slug" in cell.casefold() for cell in cells)
        ):
            header = [cell.casefold() for cell in cells]
            continue
        if header is None or len(cells) != len(header):
            continue
        index = {name: position for position, name in enumerate(header)}
        slug_cell = cells[index["slug"]]
        ids = re.findall(r"`([^`]+)`", slug_cell)
        if not ids:
            continue
        model_id = ids[0].strip()
        model_name = re.sub(
            r"\[([^]]+)\]\([^)]+\)", r"\1", cells[index["model"]]
        ).strip()
        input_price = _number(cells[index["input"]]) if "input" in index else None
        output_price = _number(cells[index["output"]]) if "output" in index else None
        cached_price = (
            _number(cells[index["cached input"]]) if "cached input" in index else None
        )
        pricing = None
        if input_price is not None and output_price is not None:
            pricing = {
                "input_per_1m": input_price,
                "output_per_1m": output_price,
                "currency": "USD",
            }
        result[model_id.casefold()] = {
            "model_id": model_id,
            "display_name": model_name or model_id,
            "context_window": (
                _context(cells[index["context"]]) if "context" in index else 0
            ),
            "max_output_tokens": 0,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_function_calling": True,
            "supports_json_mode": True,
            "supports_json_schema": True,
            "supports_streaming": True,
            "supports_vision": False,
            "supports_reasoning": None,
            "pricing": pricing,
            "cached_input_per_1m": cached_price,
        }
    apply_text = docs.get("apply", "")
    apply_match = re.search(r"`(relace-apply-\d+)`", apply_text)
    if apply_match:
        model_id = apply_match.group(1)
        result[model_id.casefold()] = {
            "model_id": model_id,
            "display_name": "Relace Apply",
            "context_window": 128_000,
            "max_output_tokens": 128_000,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_function_calling": None,
            "supports_json_mode": None,
            "supports_json_schema": None,
            "supports_streaming": True,
            "supports_vision": False,
            "supports_reasoning": None,
            "pricing": None,
        }
    search_text = docs.get("search", "")
    if re.search(r"`relace-search`", search_text):
        result["relace-search"] = {
            "model_id": "relace-search",
            "display_name": "Relace Search",
            "context_window": 0,
            "max_output_tokens": 0,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_function_calling": True,
            "supports_json_mode": None,
            "supports_json_schema": None,
            "supports_streaming": True,
            "supports_vision": False,
            "supports_reasoning": None,
            "pricing": None,
        }
    if not result:
        raise ValueError("Relace public docs contained no model IDs")
    return sorted(result.values(), key=lambda row: row["model_id"].casefold())


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
        old = old_by_id.get(key)
        row = dict(old or {})
        row.update(
            {
                "provider": "relace",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "context_window": snapshot["context_window"]
                or row.get("context_window", 0),
                "max_output_tokens": snapshot["max_output_tokens"]
                or row.get("max_output_tokens", 0),
                "input_modalities": snapshot["input_modalities"],
                "output_modalities": snapshot["output_modalities"],
                "supports_chat_completion": True,
                "deprecated": False,
            }
        )
        for field in (
            "supports_function_calling",
            "supports_json_mode",
            "supports_json_schema",
            "supports_streaming",
            "supports_vision",
            "supports_reasoning",
        ):
            if snapshot.get(field) is not None:
                row[field] = snapshot[field]
        if snapshot.get("pricing") is not None:
            row["pricing"] = snapshot["pricing"]
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": OPEN_MODELS_SOURCE,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_relace_public_docs_inventory",
                "base_url": BASE_URL,
                "cached_input_per_1m": snapshot.get("cached_input_per_1m"),
                "not_listed_in_current_docs": False,
            }
        )
        if snapshot["model_id"] == "relace-apply-3":
            extra["official_source"] = APPLY_SOURCE
        elif snapshot["model_id"] == "relace-search":
            extra["official_source"] = SEARCH_SOURCE
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
        f"relace.json: refreshed {len(snapshots)} public-doc model IDs; total={len(models)}"
    )
    return len(snapshots)


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_model_inventory(fetch_inventory()), checked_at=checked_at)


if __name__ == "__main__":
    main()
