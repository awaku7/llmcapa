"""Refresh ByteDance Seed catalog rows from Volcengine's public model-list page."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "bytedance-seed.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.volcengine.com/docs/ark/model-list?lang=zh"
MODEL_ID_PATTERN = re.compile(r"\b(doubao-(?:seed(?:ream)?|seedance)-[a-z0-9]+(?:[.-][a-z0-9]+)*)\b", re.I)


class _TableRows(HTMLParser):
    """Collect visible text for each HTML table row without third-party packages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[str] = []
        self._depth = 0
        self._current: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "tr":
            if self._depth == 0:
                self._current = []
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "tr" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self.rows.append(" ".join(self._current))
                self._current = []

    def handle_data(self, data: str) -> None:
        if self._depth and data.strip():
            self._current.append(data.strip())


def fetch_inventory() -> str:
    request = Request(
        SOURCE,
        headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0 (compatible; llmcapa-provider-updater/1.0)"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            page = response.read(12_000_000).decode("utf-8", "replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Volcengine official model-list page could not be fetched: {exc}") from exc
    if "模型列表" not in page or "Model ID" not in page:
        raise RuntimeError("Volcengine model-list page did not contain its expected catalog headings")
    return page


def _tokens(value: str) -> int:
    match = re.search(r"([\d,.]+)\s*([kKmM]?)", value)
    if not match:
        return 0
    amount = float(match.group(1).replace(",", ""))
    multiplier = {"k": 1_000, "m": 1_000_000}.get(match.group(2).casefold(), 1)
    return int(amount * multiplier)


def _row_context(row: str, label: str) -> int:
    match = re.search(label + r"\s*[:：]\s*([\d,.]+\s*[kKmM]?)", row, re.I)
    return _tokens(match.group(1)) if match else 0


def parse_model_inventory(page: str) -> list[dict]:
    """Parse Seed text and Seedream rows only; ignore other Ark provider families."""
    parser = _TableRows()
    parser.feed(page)
    rows: dict[str, dict] = {}
    for table_row in parser.rows:
        for match in MODEL_ID_PATTERN.finditer(table_row):
            model_id = match.group(1).strip().rstrip(".")
            if model_id.casefold().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            lowered_id = model_id.casefold()
            kind = "image" if lowered_id.startswith("doubao-seedream-") else "video" if lowered_id.startswith("doubao-seedance-") else "text"
            input_modalities = ["text"]
            output_modalities = ["image"] if kind == "image" else ["video"] if kind == "video" else ["text"]
            if kind == "image" and re.search(r"图生图|参考图", table_row):
                input_modalities.append("image")
            elif kind == "video" and re.search(r"图生视频|视频编辑|参考图|首尾帧", table_row):
                input_modalities.append("image")
            elif kind == "text" and "多模态理解" in table_row:
                input_modalities.append("image")
            record = {
                "model_id": model_id,
                "display_name": model_id,
                "kind": kind,
                "context_window": _row_context(table_row, "上下文窗口"),
                "max_output_tokens": _row_context(table_row, r"最大回答(?:\s*\(.*?\))?"),
                "input_modalities": input_modalities,
                "output_modalities": output_modalities,
                "supports_vision": "image" in input_modalities,
                "supports_function_calling": True if "工具调用" in table_row else None,
                "supports_json_mode": True if "结构化输出" in table_row else None,
                "supports_reasoning": True if "深度思考" in table_row else None,
                "deprecated": "即将下线" in table_row or "已下线" in table_row,
            }
            key = model_id.casefold()
            old = rows.get(key)
            if old:
                record["context_window"] = max(record["context_window"], old["context_window"])
                record["max_output_tokens"] = max(record["max_output_tokens"], old["max_output_tokens"])
                record["input_modalities"] = sorted(set(record["input_modalities"]) | set(old["input_modalities"]))
                for field in ("supports_function_calling", "supports_json_mode", "supports_reasoning"):
                    if record[field] is None:
                        record[field] = old[field]
                record["deprecated"] = record["deprecated"] or old["deprecated"]
            rows[key] = record
    if not rows:
        # Volcengine sometimes delivers its server-rendered editor table as a
        # serialized document payload instead of literal <tr> elements. The
        # model IDs remain in that official page payload; fall back to those
        # exact ID tokens, leaving specs unknown rather than fabricating them.
        raw_text = page.replace(r"\u003C", "<").replace(r"\u003E", ">").replace(r"\u002F", "/")
        for match in MODEL_ID_PATTERN.finditer(raw_text):
            model_id = match.group(1).strip().rstrip(".")
            if model_id.casefold().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            lowered_id = model_id.casefold()
            kind = "image" if lowered_id.startswith("doubao-seedream-") else "video" if lowered_id.startswith("doubao-seedance-") else "text"
            key = model_id.casefold()
            rows[key] = {
                "model_id": model_id,
                "display_name": model_id,
                "kind": kind,
                "context_window": 0,
                "max_output_tokens": 0,
                "input_modalities": ["text"],
                "output_modalities": ["image"] if kind == "image" else ["video"] if kind == "video" else ["text"],
                "supports_vision": None,
                "supports_function_calling": None,
                "supports_json_mode": None,
                "supports_reasoning": None,
                "deprecated": False,
            }
    if not rows:
        raise ValueError("Volcengine model-list page contained no ByteDance Seed or Seedream model rows")
    return sorted(rows.values(), key=lambda row: row["model_id"].casefold())


def merge_inventory(snapshots: list[dict], previous: list[dict], checked_at: str) -> list[dict]:
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
                "provider": "bytedance-seed",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "input_modalities": snapshot["input_modalities"],
                "output_modalities": snapshot["output_modalities"],
                "deprecated": snapshot["deprecated"],
            }
        )
        row.setdefault("context_window", 0)
        row.setdefault("max_output_tokens", 0)
        for field in ("context_window", "max_output_tokens"):
            if snapshot[field]:
                row[field] = snapshot[field]
        for field in ("supports_vision", "supports_function_calling", "supports_json_mode", "supports_reasoning"):
            if snapshot[field] is not None:
                row[field] = snapshot[field]
        extra = dict(row.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_volcengine_model_list_page",
                "model_family": snapshot["kind"],
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
    heading = f"## ByteDance Seed official model inventory refresh ({checked_at})"
    old_log = LOG.read_text(encoding="utf-8")
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" + (old_log[end + 1 :] if end >= 0 else "")
    entry = (
        f"\n{heading}\n\n- Source: {SOURCE} (public Volcengine model-list page)\n"
        f"- Seed text and Seedream model IDs parsed: {len(snapshots)}\n"
        "- Other Ark model families are intentionally excluded; older catalog rows are retained as historical.\n"
    )
    LOG.write_text(old_log.rstrip() + "\n" + entry, encoding="utf-8")
    print(f"bytedance-seed.json: refreshed {len(snapshots)} documented model IDs; total={len(models)}")
    return len(snapshots)


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_model_inventory(fetch_inventory()), checked_at=checked_at)


if __name__ == "__main__":
    main()
