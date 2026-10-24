"""Refresh Poolside's public supported-model inventory by scraping its official docs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "poolside.json"
SOURCE_MODELS = "https://docs.poolside.ai/get-started/supported-models"
SOURCE_API = "https://docs.poolside.ai/api/openai-api-examples"
BASE_URL = "https://inference.poolside.ai/v1"


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
            f"Poolside official documentation fetch failed ({url}): {exc}"
        ) from exc


def fetch_inventory() -> dict[str, str]:
    models = _fetch_markdown(SOURCE_MODELS)
    api = _fetch_markdown(SOURCE_API)
    if "Compare models" not in models or "List available models" not in api:
        raise RuntimeError("Poolside supported-model/API docs were not recognizable")
    return {"models": models, "api": api}


def _context(value: str) -> int:
    match = re.search(r"([\d,.]+)\s*([KM]?)", value, re.IGNORECASE)
    if not match:
        return 0
    size = float(match.group(1).replace(",", ""))
    return int(size * {"k": 1_000, "m": 1_000_000}.get(match.group(2).casefold(), 1))


def parse_model_inventory(docs: dict[str, str]) -> list[dict]:
    """Parse the public supported-model table and its documented API ID convention."""
    if (
        not isinstance(docs, dict)
        or not isinstance(docs.get("models"), str)
        or not isinstance(docs.get("api"), str)
    ):
        raise TypeError(
            "Poolside scraper expects supported-model and API documentation"
        )
    model_doc, api_doc = docs["models"], docs["api"]
    headings = re.findall(
        r"\[([^]]*Laguna[^]]*)\]\(/release-notes/models#([a-z0-9-]+)\)",
        model_doc,
        re.IGNORECASE,
    )
    if not headings:
        raise ValueError(
            "Poolside public supported-model page had no Laguna model anchors"
        )
    contexts: list[int] = []
    for line in model_doc.splitlines():
        if line.lstrip().startswith("|") and re.search(
            r"\|\s*Context window\s*\|", line, re.IGNORECASE
        ):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            contexts = [_context(cell) for cell in cells[1:]]
            break
    api_ids = set(
        re.findall(r"poolside/([a-z0-9][a-z0-9._-]*)", api_doc, re.IGNORECASE)
    )
    rows: dict[str, dict] = {}
    for index, (name, anchor) in enumerate(headings):
        # Poolside's release-note anchors spell version separators as hyphens;
        # the public API example establishes dotted Laguna 2.1 IDs.
        model_id = anchor
        if anchor.endswith("-2-1"):
            model_id = anchor[:-4] + "-2.1"
        if model_id.casefold() in {value.casefold() for value in rows}:
            continue
        api_model_id = next(
            (value for value in api_ids if value.casefold() == model_id.casefold()),
            None,
        )
        # The API quickstart publishes the provider namespace on its sample ID.
        # Keep canonical IDs unqualified in llmcapa, and preserve the exact API ID.
        api_model_id = api_model_id or f"poolside/{model_id}"
        rows[model_id.casefold()] = {
            "model_id": model_id,
            "display_name": name.strip(),
            "context_window": contexts[index] if index < len(contexts) else 0,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_vision": False,
            "supports_reasoning": True,
            "supports_function_calling": True,
            "deprecated": False,
            "api_model_id": api_model_id,
        }
    if not rows:
        raise ValueError("Poolside docs contained no supported model IDs")
    return sorted(rows.values(), key=lambda row: row["model_id"].casefold())


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
                "provider": "poolside",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "context_window": snapshot["context_window"]
                or row.get("context_window", 0),
                "input_modalities": snapshot["input_modalities"],
                "output_modalities": snapshot["output_modalities"],
                "supports_vision": snapshot["supports_vision"],
                "supports_reasoning": snapshot["supports_reasoning"],
                "supports_function_calling": snapshot["supports_function_calling"],
                "deprecated": snapshot["deprecated"],
            }
        )
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE_MODELS,
                "official_api_id_source": SOURCE_API,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_poolside_docs_inventory",
                "api_base_url": BASE_URL,
                "api_model_id": snapshot["api_model_id"],
                "not_listed_in_current_docs": False,
                "endpoints": [
                    {
                        "base_url": BASE_URL,
                        "protocol": "openai-compatible",
                        "auth": "bearer",
                        "source": SOURCE_API,
                    }
                ],
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
        f"poolside.json: refreshed {len(snapshots)} public-doc model IDs; total={len(models)}"
    )
    return len(snapshots)


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_model_inventory(fetch_inventory()), checked_at=checked_at)


if __name__ == "__main__":
    main()
