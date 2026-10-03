"""Refresh Baseten's Model APIs catalog when an API key is available.

Source: https://api.baseten.co/v1/model_apis
Set BASETEN_API_KEY to query the official authenticated catalog. Without a key,
the checked-in, manually verified model snapshot is left unchanged.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "baseten.json"
SOURCE = "https://api.baseten.co/v1/model_apis"
DOCS = "https://docs.baseten.co/inference/model-apis/overview"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_catalog(auth_token: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        params = {"limit": "100"}
        if cursor:
            if cursor in seen_cursors:
                raise RuntimeError("Baseten API repeated a pagination cursor")
            seen_cursors.add(cursor)
            params["cursor"] = cursor
        request = urllib.request.Request(
            f"{SOURCE}?{urllib.parse.urlencode(params)}",
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Accept": "application/json",
                "User-Agent": "llmcapa provider catalog updater",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Unexpected Baseten Model APIs response")
        rows.extend(row for row in payload["items"] if isinstance(row, dict))
        pagination = payload.get("pagination") or {}
        if not pagination.get("has_more"):
            break
        cursor_value = pagination.get("cursor")
        if not cursor_value:
            raise ValueError("Baseten API indicated more results without a cursor")
        cursor = str(cursor_value)
    return rows


def catalog_to_models(
    rows: list[dict[str, Any]], existing: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    old_by_id = {
        str(model.get("model_id", "")).casefold(): model
        for model in (existing or [])
        if isinstance(model, dict)
    }
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        model_id = str(row.get("name", "")).strip()
        if not model_id:
            continue
        old = old_by_id.get(model_id.casefold(), {})
        entry = dict(old)
        entry.update(
            {
                "provider": "baseten",
                "model_id": model_id,
                "display_name": row.get("display_name") or old.get("display_name") or model_id,
                "context_window": int(_number(row.get("context_length")) or old.get("context_window", 0)),
                "max_output_tokens": int(old.get("max_output_tokens", 0) or 0),
                "input_modalities": list(old.get("input_modalities") or ["text"]),
                "output_modalities": list(old.get("output_modalities") or ["text"]),
                "supports_chat_completion": True,
                "supports_streaming": old.get("supports_streaming", True),
                "deprecated": False,
                "aliases": list(old.get("aliases") or []),
                "license_type": "api",
            }
        )
        input_price = _number(row.get("cost_per_million_input_tokens"))
        output_price = _number(row.get("cost_per_million_output_tokens"))
        if input_price is not None and output_price is not None:
            entry["pricing"] = {
                "input_per_1m": input_price,
                "output_per_1m": output_price,
                "currency": "USD",
            }
        elif "pricing" not in old:
            entry["pricing"] = None
        extra = dict(old.get("extra") or {})
        extra.update(
            {
                "source": DOCS,
                "model_api_catalog": SOURCE,
                "model_family": row.get("model_family"),
                "invoke_url": row.get("invoke_url"),
            }
        )
        entry["extra"] = extra
        by_id[model_id.casefold()] = entry
    return [by_id[key] for key in sorted(by_id)]


def main() -> None:
    auth_token = os.environ.get("BASETEN_API_KEY", "").strip()
    if not auth_token:
        print(
            "Baseten refresh skipped: set BASETEN_API_KEY to query the official "
            "catalog; bundled documentation snapshot is unchanged."
        )
        return

    existing_payload = json.loads(DATA.read_text(encoding="utf-8"))
    rows = fetch_catalog(auth_token)
    models = catalog_to_models(rows, existing_payload.get("models", []))
    if not models:
        raise RuntimeError("Baseten API returned no usable Model APIs")
    DATA.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"baseten.json: {len(models)} models refreshed from official catalog")


if __name__ == "__main__":
    main()
