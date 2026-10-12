"""Refresh Tinker model IDs, contexts, and pricing from official model docs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "thinkingmachines.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://tinker-docs.thinkingmachines.ai/tinker/models/models_and_pricing"


def fetch_docs() -> str:
    request = Request(
        SOURCE + "/index.md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        text = response.read(5_000_000).decode("utf-8", "replace")
    if "Tinker ID" not in text or "## Training" not in text:
        raise RuntimeError("Tinker model/pricing documentation was not recognizable")
    return text


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _context(value: str) -> int:
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KM])?", value, re.I)
    if not match:
        return 0
    amount = float(match.group(1))
    scale = {"k": 1_000, "m": 1_000_000}.get((match.group(2) or "").casefold(), 1)
    return int(amount * scale)


def _price(value: str) -> float | None:
    # The docs use ~~old price~~ new price during promotions; only read the
    # unstruck value as the currently charged amount.
    value = re.sub(r"~~.*?~~", "", value)
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _display_name(value: str) -> str:
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    return re.sub(r"\s+—\s+.*$", "", value).strip().replace("**", "")


def parse_model_inventory(markdown: str) -> list[dict]:
    """Parse the official Training and Serverless Inference model tables."""
    section = ""
    header: list[str] | None = None
    rows: dict[str, dict] = {}
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1).strip().casefold()
            section = "training" if title == "training" else "serverless" if title.startswith("serverless inference") else ""
            header = None
            continue
        if not section or not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if not cells:
            continue
        if cells[0].casefold() == "model" and any("tinker id" in cell.casefold() for cell in cells):
            header = [cell.casefold() for cell in cells]
            continue
        if header is None or len(cells) != len(header) or re.fullmatch(r"[\s|:-]+", line):
            continue
        indices = {name: index for index, name in enumerate(header)}
        id_index = next((idx for name, idx in indices.items() if "tinker id" in name), None)
        if id_index is None:
            continue
        model_id = cells[id_index].strip().strip("`")
        if not model_id or model_id.casefold() in {"-", "tinker id"}:
            continue
        name_index = indices.get("model", 0)
        context_index = next((idx for name, idx in indices.items() if name == "context"), None)
        prefill_index = next((idx for name, idx in indices.items() if "prefill" in name), None)
        sample_index = next((idx for name, idx in indices.items() if "sample" in name), None)
        type_index = next((idx for name, idx in indices.items() if name == "type"), None)
        context = _context(cells[context_index]) if context_index is not None else 0
        input_price = _price(cells[prefill_index]) if prefill_index is not None else None
        output_price = _price(cells[sample_index]) if sample_index is not None else None
        model_type = cells[type_index] if type_index is not None else ""
        model_name = _display_name(cells[name_index])
        key = model_id.casefold()
        previous = rows.get(key, {})
        rows[key] = {
            "model_id": model_id,
            "display_name": model_name or previous.get("display_name") or model_id,
            "context_window": context or previous.get("context_window", 0),
            "input_per_1m": input_price if input_price is not None else previous.get("input_per_1m"),
            "output_per_1m": output_price if output_price is not None else previous.get("output_per_1m"),
            "model_type": model_type or previous.get("model_type", ""),
            "inventory_section": section,
            "deprecated": bool(re.search(r"retir(?:e|ing|ed)", cells[name_index], re.I)) or previous.get("deprecated", False),
        }
    if not rows:
        raise ValueError("Tinker model docs contained no Tinker ID rows")
    return sorted(rows.values(), key=lambda row: row["model_id"].casefold())


def _new_record(snapshot: dict) -> dict:
    model_type = snapshot["model_type"].casefold()
    inputs = ["text"]
    if "vision" in model_type:
        inputs.append("image")
    if "audio" in model_type:
        inputs.append("audio")
    return {
        "provider": "thinkingmachines",
        "model_id": snapshot["model_id"],
        "display_name": snapshot["display_name"],
        "context_window": snapshot["context_window"],
        "max_output_tokens": 0,
        "input_modalities": inputs,
        "output_modalities": ["text"],
        "supports_function_calling": None,
        "supports_json_mode": None,
        "supports_json_schema": None,
        "supports_streaming": None,
        "supports_vision": "image" in inputs,
        "supports_reasoning": None,
        "supports_chat_completion": None,
        "supports_responses_api": None,
        "pricing": None,
        "deprecated": snapshot["deprecated"],
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
        row.update(
            {
                "provider": "thinkingmachines",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "context_window": snapshot["context_window"] or row.get("context_window", 0),
                "deprecated": snapshot["deprecated"],
            }
        )
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
                "official_spec_refresh": "official_tinker_model_inventory",
                "model_type": snapshot["model_type"],
                "inventory_section": snapshot["inventory_section"],
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
    heading = f"## Tinker official model inventory refresh ({checked_at})"
    old_log = LOG.read_text(encoding="utf-8")
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" + (old_log[end + 1 :] if end >= 0 else "")
    entry = (
        f"\n{heading}\n\n- Source: {SOURCE}\n"
        f"- Official Training and Serverless Inference model IDs parsed: {len(snapshots)}.\n"
        "- Context lengths and per-million input/output prices were updated from Tinker IDs and tables.\n"
    )
    LOG.write_text(old_log.rstrip() + "\n" + entry, encoding="utf-8")
    print(f"thinkingmachines.json: refreshed {len(snapshots)} official Tinker model IDs; total={len(models)}")
    return len(snapshots)


def main() -> None:
    update_catalog(parse_model_inventory(fetch_docs()))


if __name__ == "__main__":
    main()
