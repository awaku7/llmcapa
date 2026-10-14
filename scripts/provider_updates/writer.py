"""Refresh Writer Palmyra model inventory and prices from public official docs."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "writer.json"
LOG = ROOT / "provider_update_log.md"
BASE_URL = "https://api.writer.com/v1"
MODELS_SOURCE = "https://dev.writer.com/home/models"
PRICING_SOURCE = "https://dev.writer.com/home/pricing"


def _fetch_markdown(url: str) -> str:
    request = Request(
        url + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read(4_000_000).decode("utf-8", "replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Writer official documentation fetch failed ({url}): {exc}") from exc


def fetch_inventory() -> dict[str, str]:
    models = _fetch_markdown(MODELS_SOURCE)
    pricing = _fetch_markdown(PRICING_SOURCE)
    if "API model ID" not in models or "## Base model" not in pricing:
        raise RuntimeError("Writer public model/pricing docs did not contain their expected model tables")
    return {"models": models, "pricing": pricing}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _clean(text: str) -> str:
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*`_]", "", text).strip()


def _token_count(value: str) -> int:
    match = re.search(r"([\d,.]+)\s*([kKmM]?)", value)
    if not match:
        return 0
    number = float(match.group(1).replace(",", ""))
    scale = {"k": 1_000, "m": 1_000_000}.get(match.group(2).casefold(), 1)
    return int(number * scale)


def _price(value: str) -> float | None:
    value = value.replace("\\$", "$")
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _model_specs(markdown: str) -> dict[str, dict]:
    lines = markdown.splitlines()
    header: list[str] | None = None
    model_names: list[str] = []
    spec_rows: dict[str, list[str]] = {}
    in_comparison = False
    for line in lines:
        if re.match(r"^##\s+Model comparison\s*$", line):
            in_comparison = True
            continue
        if in_comparison and line.startswith("## "):
            break
        if not in_comparison or not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if cells and cells[0].casefold() == "feature" and any("palmyra" in cell.casefold() for cell in cells[1:]):
            header = cells[1:]
            model_names = [_clean(cell) for cell in header]
            continue
        if header is None or len(cells) != len(header) + 1:
            continue
        label = _clean(cells[0]).casefold()
        if label in {"api model id", "pricing (input)", "pricing (output)", "context window", "max output"}:
            spec_rows[label] = cells[1:]
    if not model_names or "api model id" not in spec_rows:
        raise ValueError("Writer public model comparison table had no API model IDs")
    result: dict[str, dict] = {}
    deprecation = re.search(r"will be deprecated on\s+\*\*(\d{4}-\d{2}-\d{2})\*\*", markdown, re.I)
    retirement_date = date.fromisoformat(deprecation.group(1)) if deprecation else None
    is_deprecated = retirement_date is not None and retirement_date <= datetime.now(timezone.utc).date()
    for index, cell in enumerate(spec_rows["api model id"]):
        ids = re.findall(r"`([^`]+)`", cell)
        if not ids:
            continue
        model_id = ids[0].strip()
        if not model_id:
            continue
        result[model_id.casefold()] = {
            "model_id": model_id,
            "display_name": model_names[index] if index < len(model_names) else model_id,
            "context_window": _token_count(spec_rows.get("context window", [""] * len(model_names))[index]),
            "max_output_tokens": _token_count(spec_rows.get("max output", [""] * len(model_names))[index]),
            "deprecated": is_deprecated and model_id.casefold() in {"palmyra-x4", "palmyra-x5"},
            "input_per_1m": None,
            "output_per_1m": None,
        }
    if not result:
        raise ValueError("Writer model table did not yield any API model IDs")
    return result


def _parse_base_model_prices(markdown: str) -> dict[str, tuple[float, float]]:
    section_match = re.search(r"(?ims)^##\s+Base model\s*$(.*?)(?=^##\s+|\Z)", markdown)
    if not section_match:
        raise ValueError("Writer pricing docs have no Base model section")
    prices: dict[str, tuple[float, float]] = {}
    for line in section_match.group(1).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 4 or cells[0].casefold() in {"model name", "-"}:
            continue
        model_ids = re.findall(r"`([^`]+)`", cells[1])
        input_price = _price(cells[2])
        output_price = _price(cells[3])
        if model_ids and input_price is not None and output_price is not None:
            prices[model_ids[0].casefold()] = (input_price, output_price)
    if not prices:
        raise ValueError("Writer Base model pricing table had no model rows")
    return prices


def parse_model_inventory(docs: dict[str, str]) -> list[dict]:
    if not isinstance(docs, dict) or not isinstance(docs.get("models"), str) or not isinstance(docs.get("pricing"), str):
        raise ValueError("Writer scraper expects public model and pricing documentation text")
    snapshots = _model_specs(docs["models"])
    prices = _parse_base_model_prices(docs["pricing"])
    for key, snapshot in snapshots.items():
        if key in prices:
            snapshot["input_per_1m"], snapshot["output_per_1m"] = prices[key]
    return sorted(snapshots.values(), key=lambda row: row["model_id"].casefold())


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
                "provider": "writer",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "context_window": snapshot["context_window"] or row.get("context_window", 0),
                "max_output_tokens": snapshot["max_output_tokens"] or row.get("max_output_tokens", 0),
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
                "official_source": MODELS_SOURCE,
                "official_pricing_source": PRICING_SOURCE,
                "official_source_checked_at": checked_at,
                "official_spec_refresh": "official_writer_model_docs",
                "api_base_url": BASE_URL,
                "not_listed_in_current_docs": False,
                "endpoints": [{"base_url": BASE_URL, "protocol": "openai-compatible", "auth": "bearer", "source": MODELS_SOURCE}],
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
    heading = f"## Writer official model inventory refresh ({checked_at})"
    old_log = LOG.read_text(encoding="utf-8")
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" + (old_log[end + 1 :] if end >= 0 else "")
    entry = (
        f"\n{heading}\n\n- Source: {MODELS_SOURCE} and {PRICING_SOURCE} (public Writer docs)\n"
        f"- Public Palmyra API model IDs and official pricing: {len(snapshots)}\n"
        "- No account API key is required; model features and context are sourced from public docs.\n"
    )
    LOG.write_text(old_log.rstrip() + "\n" + entry, encoding="utf-8")
    print(f"writer.json: refreshed {len(snapshots)} public model IDs; total={len(models)}")
    return len(snapshots)


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_model_inventory(fetch_inventory()), checked_at=checked_at)


if __name__ == "__main__":
    main()
