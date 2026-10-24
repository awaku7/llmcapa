"""Refresh Z.AI chat, vision, and audio model inventories from official pricing docs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
try:
    from scripts.provider_updates._http import fetch_text
except ModuleNotFoundError:  # Running this updater directly from its own directory.
    from _http import fetch_text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "z-ai.json"
SOURCE = "https://docs.z.ai/guides/overview/pricing"
BASE_URL = "https://api.z.ai/api"


def fetch_docs() -> str:
    text = fetch_text(
        SOURCE + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
        timeout=30,
        max_bytes=2_000_000,
    )
    if "## Models" not in text or "### Text Models" not in text:
        raise RuntimeError("Z.AI pricing documentation did not contain the expected model tables")
    return text


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _model_id(label: str) -> str:
    label = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", label)
    label = re.sub(r"[*`_]+", "", label).strip()
    label = re.sub(r"\s+", "-", label)
    return label.casefold()


def _price(value: str) -> float | None:
    cleaned = value.replace("\\$", "$").strip()
    if re.search(r"\bfree\b", cleaned, re.I):
        return 0.0
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", cleaned)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_model_inventory(markdown: str) -> list[dict]:
    """Extract API model names only; ignore image/video generation and agents."""
    category = ""
    rows: dict[str, dict] = {}
    in_models = False
    for line in markdown.splitlines():
        heading = re.match(r"^\s*#{2,4}\s+(.+?)\s*#*\s*$", line)
        if heading:
            title = heading.group(1).strip().casefold()
            if title == "models":
                in_models = True
                category = ""
                continue
            if in_models:
                if title in {"text models", "vision models", "audio models", "latest models"}:
                    category = title
                elif title in {"built-in tools", "image generation models", "video generation models", "agents"}:
                    category = ""
                elif line.startswith("## "):
                    in_models = False
                    category = ""
        if not in_models or category not in {"text models", "vision models", "audio models", "latest models"}:
            continue
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 2 or cells[0].casefold() in {"model", "-"} or re.fullmatch(r"[:\- ]+", cells[0]):
            continue
        model_id = _model_id(cells[0])
        if not re.match(r"^glm(?:-|$)", model_id):
            continue
        kind = "vision" if category == "vision models" else "audio" if category == "audio models" else "chat"
        input_price = output_price = None
        if kind != "audio" and len(cells) >= 5:
            # Text/Vision and Latest tables expose Input in column 2, Output last.
            input_price = _price(cells[1])
            output_price = _price(cells[-1])
        snapshot = {
            "model_id": model_id,
            "display_name": cells[0].replace("**", "").replace("`", "").strip(),
            "kind": kind,
            "input_per_1m": input_price,
            "output_per_1m": output_price,
        }
        # Prefer the richer modality-specific section to a duplicate in Latest Models.
        previous = rows.get(model_id)
        if previous is None or (previous["kind"] == "chat" and kind in {"vision", "audio"}):
            rows[model_id] = snapshot
    if not rows:
        raise ValueError("No Z.AI chat/vision/audio model IDs were parsed from official pricing docs")
    return sorted(rows.values(), key=lambda row: row["model_id"])


def _new_record(snapshot: dict) -> dict:
    inputs = ["text", "image"] if snapshot["kind"] == "vision" else ["audio"] if snapshot["kind"] == "audio" else ["text"]
    outputs = ["text"]
    return {
        "provider": "z-ai",
        "model_id": snapshot["model_id"],
        "display_name": snapshot["display_name"],
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": inputs,
        "output_modalities": outputs,
        "supports_function_calling": None,
        "supports_json_mode": None,
        "supports_json_schema": None,
        "supports_streaming": None,
        "supports_vision": snapshot["kind"] == "vision",
        "supports_reasoning": None,
        "supports_chat_completion": True if snapshot["kind"] != "audio" else None,
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
        row.update({"provider": "z-ai", "model_id": snapshot["model_id"], "display_name": snapshot["display_name"]})
        # The official pricing tables list accepted model families, not complete
        # token limits or feature matrices. Do not replace existing curated specs.
        if snapshot.get("input_per_1m") is not None and snapshot.get("output_per_1m") is not None:
            row["pricing"] = {
                "input_per_1m": snapshot["input_per_1m"],
                "output_per_1m": snapshot["output_per_1m"],
                "currency": "USD",
            }
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_z_ai_pricing_model_inventory",
                "model_type": snapshot["kind"],
                "endpoints": [
                    {
                        "base_url": f"{BASE_URL}/paas/v4",
                        "protocol": "openai-compatible",
                        "auth": "bearer",
                        "source": SOURCE,
                    }
                ],
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
            extra.update({"official_source_checked_at": checked_at, "not_listed_in_current_docs": True})
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(snapshots: list[dict], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_inventory(snapshots, data.get("models") or [], checked_at)
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"z-ai.json: refreshed {len(snapshots)} official model IDs; total={len(models)}")
    return len(snapshots)


def main() -> None:
    update_catalog(parse_model_inventory(fetch_docs()))


if __name__ == "__main__":
    main()
