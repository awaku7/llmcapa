"""Refresh AI21 Jamba model IDs from the official documentation inventory."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "ai21.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.ai21.com/docs/jamba-foundation-models"
BASE_URL = "https://api.ai21.com/studio/v1"


def fetch_docs() -> str:
    request = Request(
        SOURCE + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        text = response.read(1_000_000).decode("utf-8", "replace")
    if "Model Details" not in text or "API Endpoint" not in text:
        raise RuntimeError("AI21 Jamba model documentation was not recognizable")
    return text


def parse_model_ids(markdown: str) -> list[str]:
    """Read live API endpoint names and aliases, excluding retired endpoints."""
    ids: dict[str, str] = {}
    in_details = False
    for line in markdown.splitlines():
        if re.match(r"^##\s+Model Details\s*$", line, re.I):
            in_details = True
            continue
        if in_details and re.match(r"^##\s+", line):
            in_details = False
        if in_details and line.lstrip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 6 and cells[0].casefold() not in {"model", "-"}:
                endpoint = re.search(r"`([^`]+)`", cells[-1])
                if endpoint and endpoint.group(1).strip().casefold() != "n/a":
                    model_id = endpoint.group(1).strip()
                    ids[model_id.casefold()] = model_id
    versioning = re.search(
        r"(?ims)^##\s+API Versioning\s*$(.*?)(?=^##\s+|\Z)", markdown
    )
    if versioning:
        for line in versioning.group(1).splitlines():
            match = re.search(r"`([^`]+)`\s+(?:currently\s+)?points to\s+`([^`]+)`", line, re.I)
            if match:
                for model_id in match.groups():
                    ids[model_id.casefold()] = model_id
    if not ids:
        raise ValueError("AI21 docs contained no current Jamba API model IDs")
    return sorted(ids.values(), key=str.casefold)


def _new_record(model_id: str) -> dict:
    return {
        "provider": "ai21",
        "model_id": model_id,
        "display_name": model_id,
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": None,
        "supports_json_mode": None,
        "supports_json_schema": None,
        "supports_streaming": None,
        "supports_vision": None,
        "supports_reasoning": None,
        "supports_chat_completion": None,
        "supports_responses_api": None,
        "pricing": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
    }


def merge_catalog(model_ids: list[str], previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for model_id in model_ids:
        key = model_id.casefold()
        row = dict(old_by_id.get(key) or _new_record(model_id))
        row["provider"] = "ai21"
        row["model_id"] = model_id
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": checked_at,
                "official_model_inventory": "ai21_jamba_api_endpoints",
                "base_url": BASE_URL,
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
                    "official_source": SOURCE,
                    "official_source_checked_at": checked_at,
                    "not_listed_in_current_docs": True,
                }
            )
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(model_ids: list[str], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_catalog(model_ids, data.get("models") or [], checked_at)
    DATA.write_text(
        json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    heading = f"## AI21 official model inventory refresh ({checked_at})"
    old_log = LOG.read_text(encoding="utf-8")
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" + (old_log[end + 1 :] if end >= 0 else "")
    entry = (
        f"\n{heading}\n\n- Source: {SOURCE}\n"
        f"- Current model IDs and version aliases parsed: {len(model_ids)}.\n"
        "- Model-specific capabilities and prices are preserved; undocumented values remain unchanged or unknown.\n"
    )
    LOG.write_text(old_log.rstrip() + "\n" + entry, encoding="utf-8")
    print(f"ai21.json: refreshed {len(model_ids)} documented API model IDs; total={len(models)}")
    return len(model_ids)


def main() -> None:
    update_catalog(parse_model_ids(fetch_docs()))


if __name__ == "__main__":
    main()
