"""Refresh the local LM Studio model inventory from its documented local API.

LM Studio's inventory is installation-specific; the updater queries the user's
running local server at LMSTUDIO_API_BASE (default: http://127.0.0.1:1234/api/v1).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "lmstudio.json"
LOG = ROOT / "provider_update_log.md"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/api/v1"
SOURCE = "https://lmstudio.ai/docs/developer/rest/list"


def fetch_inventory(base_url: str | None = None, api_key: str | None = None) -> list[dict]:
    base_url = (base_url or os.environ.get("LMSTUDIO_API_BASE") or DEFAULT_BASE_URL).rstrip("/")
    api_key = api_key or os.environ.get("LMSTUDIO_API_KEY")
    headers = {"Accept": "application/json", "User-Agent": "llmcapa-provider-updater/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{base_url}/models", headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read(3_000_000).decode("utf-8", "replace"))
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"LM Studio local model inventory unavailable at {base_url}: {exc}") from exc
    rows = payload.get("models", payload.get("data")) if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not any(isinstance(item, dict) and any(item.get(k) for k in ("id", "key", "model_key", "path")) for item in rows):
        raise ValueError("LM Studio /api/v1/models returned no model identifiers; refusing to clear the catalog")
    return rows


def parse_model_inventory(payload: list[dict]) -> list[dict]:
    result = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        model_id = next((str(item[key]).strip() for key in ("id", "key", "model_key", "path") if item.get(key)), "")
        if not model_id or model_id.casefold() in seen:
            continue
        result.append(
            {
                "model_id": model_id,
                "display_name": str(item.get("display_name") or item.get("name") or model_id),
                "type": item.get("type"),
                "publisher": item.get("publisher"),
                "quantization": item.get("quantization"),
                "context_length": item.get("max_context_length", item.get("context_length")),
            }
        )
        seen.add(model_id.casefold())
    if not result:
        raise ValueError("LM Studio local server returned an empty model inventory")
    return result


def merge_inventory(snapshots: list[dict], previous: list[dict], checked_at: str, base_url: str) -> list[dict]:
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
        row.update({"provider": "lmstudio", "model_id": snapshot["model_id"], "display_name": snapshot["display_name"]})
        context = snapshot.get("context_length")
        if isinstance(context, int) and context > 0:
            row["context_window"] = context
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "live_lm_studio_local_models_api",
                "model_server_base_url": base_url,
                "inventory_scope": "local_installation_only",
                "local_model_type": snapshot.get("type"),
                "publisher": snapshot.get("publisher"),
                "quantization": snapshot.get("quantization"),
                "not_listed_in_current_installation": False,
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
            extra.update({"official_source_checked_at": checked_at, "not_listed_in_current_installation": True})
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(snapshots: list[dict], *, base_url: str | None = None, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    base_url = (base_url or os.environ.get("LMSTUDIO_API_BASE") or DEFAULT_BASE_URL).rstrip("/")
    models = merge_inventory(snapshots, data.get("models") or [], checked_at, base_url)
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    heading = f"## LM Studio local inventory refresh ({checked_at})"
    old_log = LOG.read_text(encoding="utf-8")
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" + (old_log[end + 1 :] if end >= 0 else "")
    entry = (
        f"\n{heading}\n\n- Source: {base_url}/models\n"
        f"- Locally installed model IDs: {len(snapshots)}\n"
        "- LM Studio has no single global inventory; only this installation's local model list is synchronized.\n"
    )
    LOG.write_text(old_log.rstrip() + "\n" + entry, encoding="utf-8")
    print(f"lmstudio.json: refreshed {len(snapshots)} local model IDs; total={len(models)}")
    return len(snapshots)


def main() -> None:
    base_url = (os.environ.get("LMSTUDIO_API_BASE") or DEFAULT_BASE_URL).rstrip("/")
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_model_inventory(fetch_inventory(base_url)), base_url=base_url, checked_at=checked_at)


if __name__ == "__main__":
    main()
