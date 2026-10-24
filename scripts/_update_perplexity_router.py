"""Refresh Perplexity Router catalog rows from its official Router docs.

The unauthenticated docs table publishes the current model IDs, input/output
prices, cache-read prices, and native model-card links. Provider-specific
capabilities are preserved for known IDs and left unknown for new routes.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "perplexity-router.json"
SOURCE = "https://docs.perplexity.ai/docs/router/models"
API_BASE = "https://api.perplexity.ai/router/v1"


def fetch_docs() -> str:
    request = Request(
        SOURCE + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        text = response.read(1_000_000).decode("utf-8", "replace")
    if "Perplexity-Hosted Models" not in text or "Input" not in text:
        raise RuntimeError("Perplexity Router model docs were not recognizable")
    return text


def _price(cell: str) -> float | None:
    match = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", cell)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_model_table(markdown: str) -> list[dict]:
    """Extract only rows in the Perplexity-hosted Router pricing table."""
    match = re.search(r"(?im)^##\s+Perplexity-Hosted Models\s*$", markdown)
    if not match:
        raise ValueError("Perplexity Router docs have no hosted-model table")
    section = markdown[match.end() :]
    rows: dict[str, dict] = {}
    for line in section.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [item.strip() for item in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        model_id_match = re.search(r"`([^`]+)`", cells[0])
        source_link = re.search(r"\[([^]]+)\]\((https?://[^)]+)\)", cells[4])
        if not model_id_match:
            continue
        model_id = model_id_match.group(1).strip()
        if not model_id.startswith("perplexity/"):
            continue
        input_price = _price(cells[1])
        output_price = _price(cells[2])
        cache_read = _price(cells[3])
        if input_price is None or output_price is None:
            continue
        native_source = source_link.group(2) if source_link else None
        path_parts = [part for part in urlparse(native_source or "").path.split("/") if part]
        native_provider = path_parts[0] if len(path_parts) > 1 and urlparse(native_source or "").hostname == "huggingface.co" else None
        rows[model_id.casefold()] = {
            "provider": "perplexity-router",
            "model_id": model_id,
            "display_name": f"Perplexity Router: {source_link.group(1) if source_link else model_id.split('/', 1)[-1]}",
            "input_per_1m": input_price,
            "output_per_1m": output_price,
            "cache_read_per_1m": cache_read,
            "native_model_source": native_source,
            "native_provider": native_provider,
        }
    if not rows:
        raise ValueError("No Perplexity-hosted Router model pricing rows were parsed")
    return list(rows.values())


def _base_record(snapshot: dict, old: dict | None, checked_at: str) -> dict:
    result = dict(old or {})
    result.update(
        {
            "provider": "perplexity-router",
            "model_id": snapshot["model_id"],
            "display_name": snapshot["display_name"],
            "input_modalities": old.get("input_modalities", ["text"]) if old else ["text"],
            "output_modalities": old.get("output_modalities", ["text"]) if old else ["text"],
            "supports_streaming": True,
            "supports_chat_completion": True,
            "supports_responses_api": True,
            "supports_anthropic_api": True,
            "license_type": "api",
            "deprecated": old.get("deprecated", False) if old else False,
            "aliases": old.get("aliases", [snapshot["model_id"].split("/", 1)[-1]]) if old else [snapshot["model_id"].split("/", 1)[-1]],
            "pricing": {
                "input_per_1m": snapshot["input_per_1m"],
                "output_per_1m": snapshot["output_per_1m"],
                "currency": "USD",
            },
        }
    )
    extra = dict(old.get("extra") or {}) if old else {}
    extra.update(
        {
            "official_source": SOURCE,
            "official_source_checked_at": checked_at,
            "router_api_base_url": API_BASE,
            "chat_completions_endpoint": f"{API_BASE}/chat/completions",
            "responses_endpoint": f"{API_BASE}/responses",
            "messages_endpoint": f"{API_BASE}/messages",
            "model_catalog_endpoint": f"{API_BASE}/models",
            "router_preview": True,
            "api_schema_support": ["openai-chat-completions", "openai-responses", "anthropic-messages"],
        }
    )
    if snapshot["cache_read_per_1m"] is not None:
        extra["cache_read_per_1m"] = snapshot["cache_read_per_1m"]
        # The docs state cache writes use the input rate when a dedicated write
        # rate is not listed.
        extra["cache_write_per_1m"] = snapshot["input_per_1m"]
    if snapshot["native_model_source"]:
        extra["native_model_source"] = snapshot["native_model_source"]
    if snapshot["native_provider"] and not extra.get("native_provider"):
        extra["native_provider"] = snapshot["native_provider"]
    result["extra"] = extra
    return result


def merge_catalog(snapshots: list[dict], previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    merged = []
    seen: set[str] = set()
    for snapshot in snapshots:
        key = snapshot["model_id"].casefold()
        merged.append(_base_record(snapshot, old_by_id.get(key), checked_at))
        seen.add(key)
    # Preserve old routes absent from the docs rather than treating omission as
    # proof of retirement; add a flag so the change is reviewable.
    for old in previous:
        if not isinstance(old, dict):
            continue
        key = str(old.get("model_id", "")).casefold()
        if key and key not in seen:
            row = dict(old)
            extra = dict(row.get("extra") or {})
            extra["not_listed_in_current_docs"] = True
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(snapshots: list[dict], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    previous = data.get("models") or []
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_catalog(snapshots, previous, checked_at)
    if not models:
        raise ValueError("refusing to write an empty Perplexity Router catalog")
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"perplexity-router.json: refreshed {len(snapshots)} documented routes; total={len(models)}")
    return len(snapshots)


def main() -> None:
    snapshots = parse_model_table(fetch_docs())
    update_catalog(snapshots)


if __name__ == "__main__":
    main()
