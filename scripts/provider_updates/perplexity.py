"""Refresh Perplexity model IDs and prices from its official pricing docs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "perplexity.json"
SOURCE = "https://docs.perplexity.ai/docs/getting-started/pricing"
BASE_URL = "https://api.perplexity.ai"


def fetch_docs() -> str:
    request = Request(
        SOURCE + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        text = response.read(5_000_000).decode("utf-8", "replace")
    if "export const PRICING" not in text or '"sonar"' not in text:
        raise RuntimeError("Perplexity pricing documentation did not contain the official model data")
    return text


def _extract_pricing_object(markdown: str) -> dict:
    marker = "export const PRICING ="
    start = markdown.find(marker)
    if start < 0:
        raise ValueError("Perplexity docs have no machine-readable PRICING object")
    start = markdown.find("{", start + len(marker))
    if start < 0:
        raise ValueError("Perplexity pricing object did not start with an object")
    depth = 0
    in_string = False
    escaped = False
    end = -1
    for index in range(start, len(markdown)):
        char = markdown[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        raise ValueError("Perplexity pricing object is incomplete")
    source = markdown[start:end]
    source = re.sub(r",\s*([}\]])", r"\1", source)
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ValueError("Perplexity pricing object was not valid JSON-compatible data") from exc
    if not isinstance(payload, dict):
        raise ValueError("Perplexity pricing object is not a mapping")
    return payload


def parse_model_inventory(markdown: str) -> list[dict]:
    pricing = _extract_pricing_object(markdown)
    rows: dict[str, dict] = {}
    sonar = pricing.get("sonar", {}).get("models", [])
    for item in sonar:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        model_id = str(item["id"])
        row = {
            "model_id": model_id,
            "display_name": str(item.get("label") or model_id),
            "kind": "chat",
            "input_per_1m": item.get("input"),
            "output_per_1m": item.get("output"),
            "request_pricing": item.get("request"),
        }
        for key in ("citation", "reasoning", "searchQueries"):
            if key in item:
                row["request_pricing"] = dict(row.get("request_pricing") or {}, **{key: item[key]})
        rows[model_id.casefold()] = row
    for item in pricing.get("embeddings", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        model_id = str(item["id"])
        rows[model_id.casefold()] = {
            "model_id": model_id,
            "display_name": f"Perplexity: {model_id}",
            "kind": "embedding",
            "input_per_1m": item.get("rate"),
            "output_per_1m": 0.0,
            "dimensions": item.get("dims"),
        }
    decisions = pricing.get("decisions", {})
    decision_rows = decisions.get("models", []) if isinstance(decisions, dict) else []
    for item in decision_rows:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        model_id = str(item["id"])
        rows[model_id.casefold()] = {
            "model_id": model_id,
            "display_name": f"Perplexity: {model_id}",
            "kind": "decision",
            "input_per_1m": decisions.get("input"),
            "output_per_1m": 0.0,
        }
    if not rows:
        raise ValueError("Perplexity pricing docs contained no model IDs")
    return sorted(rows.values(), key=lambda row: row["model_id"].casefold())


def _new_record(snapshot: dict) -> dict:
    embedding = snapshot["kind"] == "embedding"
    return {
        "provider": "perplexity",
        "model_id": snapshot["model_id"],
        "display_name": snapshot["display_name"],
        "context_window": 32000 if embedding else 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["embeddings"] if embedding else ["text"],
        "supports_function_calling": None,
        "supports_json_mode": None,
        "supports_json_schema": None,
        "supports_streaming": None,
        "supports_vision": False,
        "supports_reasoning": None,
        "supports_chat_completion": snapshot["kind"] == "chat",
        "supports_responses_api": None,
        "pricing": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
    }


def merge_inventory(snapshots: list[dict], previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for snapshot in snapshots:
        key = snapshot["model_id"].casefold()
        row = dict(old_by_id.get(key) or _new_record(snapshot))
        row.update({"provider": "perplexity", "model_id": snapshot["model_id"], "display_name": snapshot["display_name"]})
        row["supports_chat_completion"] = snapshot["kind"] == "chat"
        row["pricing"] = {
            "input_per_1m": snapshot.get("input_per_1m"),
            "output_per_1m": snapshot.get("output_per_1m"),
            "currency": "USD",
        }
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_perplexity_pricing_model_inventory",
                "model_type": snapshot["kind"],
                "base_url": BASE_URL,
                "not_listed_in_current_docs": False,
            }
        )
        if snapshot.get("request_pricing"):
            extra["request_pricing"] = snapshot["request_pricing"]
        if snapshot.get("dimensions") is not None:
            extra["embedding_dimensions"] = snapshot["dimensions"]
            row.setdefault(
                "embedding",
                {"embedding": True, "output_formats": ["float"], "status": "official_docs", "checked_at": checked_at},
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
            extra.update({"official_source_checked_at": checked_at, "not_listed_in_current_docs": True})
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(snapshots: list[dict], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_inventory(snapshots, data.get("models") or [], checked_at)
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"perplexity.json: refreshed {len(snapshots)} official models; total={len(models)}")
    return len(snapshots)


def main() -> None:
    update_catalog(parse_model_inventory(fetch_docs()))


if __name__ == "__main__":
    main()
