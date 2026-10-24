"""Refresh the Modellix LLM gateway catalog from its official model page.

The public LLM page is JavaScript-rendered and exposes its complete, paginated
price table. Playwright is an updater-only dependency (also used by the
Fireworks updater); the library itself remains dependency-free.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "modellix.json"
SOURCE = "https://www.modellix.ai/llm"
GATEWAY = "https://llm.modellix.ai/v1"
PAGE_SIZE_LIMIT = 100


def _number(value: object) -> float | None:
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_context_window(value: object) -> int:
    match = re.search(r"([\d,.]+)\s*([kKmM]?)", str(value or ""))
    if not match:
        return 0
    amount = float(match.group(1).replace(",", ""))
    suffix = match.group(2).lower()
    return int(amount * (1_000 if suffix == "k" else 1_000_000 if suffix == "m" else 1))


def normalize_modality(value: str) -> str | None:
    key = value.strip().casefold()
    return {
        "text": "text", "image": "image", "audio": "audio", "video": "video",
        "embedding": "embedding", "embeddings": "embedding", "rerank": "rerank",
    }.get(key)


def parse_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize rows extracted from the official HTML table."""
    parsed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("model_id", "")).strip()
        if not model_id or "/" not in model_id:
            continue
        inputs = [normalize_modality(str(x)) for x in row.get("input_modalities", [])]
        outputs = [normalize_modality(str(x)) for x in row.get("output_modalities", [])]
        inputs = list(dict.fromkeys(x for x in inputs if x))
        outputs = list(dict.fromkeys(x for x in outputs if x))
        if not inputs or not outputs:
            continue
        tiers = []
        for tier in row.get("price_tiers", []):
            if not isinstance(tier, dict):
                continue
            item = {"input_context": str(tier.get("input_context", "")).strip() or None}
            for source_key, target_key in (
                ("input_per_1m", "input_per_1m"),
                ("output_per_1m", "output_per_1m"),
                ("cache_read_per_1m", "cache_read_per_1m"),
                ("cache_write_per_1m", "cache_write_per_1m"),
            ):
                value = tier.get(source_key)
                if isinstance(value, (int, float)) and value >= 0:
                    item[target_key] = float(value)
            if "input_per_1m" in item and "output_per_1m" in item:
                tiers.append(item)
        if not tiers and isinstance(row.get("pricing"), dict):
            price = row["pricing"]
            if isinstance(price.get("input_per_1m"), (int, float)) and isinstance(price.get("output_per_1m"), (int, float)):
                tiers.append({key: price[key] for key in ("input_per_1m", "output_per_1m", "cache_read_per_1m", "cache_write_per_1m") if key in price})
        parsed[model_id.casefold()] = {
            "provider": "modellix",
            "model_id": model_id,
            "display_name": str(row.get("display_name") or model_id.rsplit("/", 1)[-1]),
            "context_window": parse_context_window(row.get("context_window")),
            "input_modalities": inputs,
            "output_modalities": outputs,
            "price_tiers": tiers,
        }
    if not parsed:
        raise ValueError("official Modellix LLM price table contained no valid model rows")
    return list(parsed.values())


def extract_page_rows(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          const table = document.querySelector('table[aria-label="Price table"]');
          if (!table) return [];
          const price = (cell) => {
            if (!cell) return null;
            const text = (cell.querySelector('strong')?.innerText || cell.innerText || '').trim();
            const match = text.match(/\\$\\s*([\\d,]+(?:\\.\\d+)?)/);
            return match ? Number(match[1].replaceAll(',', '')) : null;
          };
          return Array.from(table.querySelectorAll('tbody.llm-table__group')).map(group => {
            const rows = Array.from(group.querySelectorAll(':scope > tr'));
            const first = rows[0];
            if (!first) return null;
            const cells = Array.from(first.querySelectorAll(':scope > td'));
            const modelCell = cells[0];
            const modalityGroups = Array.from(cells[1]?.querySelectorAll('.llm-modalities__group') || []);
            const labels = groupEl => Array.from(groupEl?.querySelectorAll('[aria-label]') || [])
              .map(el => el.getAttribute('aria-label'));
            const priceTiers = rows.map((tr, index) => {
              const tds = Array.from(tr.querySelectorAll(':scope > td'));
              const offset = index === 0 ? 4 : 1;
              return {
                input_context: tds[index === 0 ? 3 : 0]?.innerText?.trim() || '',
                input_per_1m: price(tds[offset]),
                output_per_1m: price(tds[offset + 1]),
                cache_read_per_1m: price(tds[offset + 2]),
                cache_write_per_1m: price(tds[offset + 3])
              };
            });
            return {
              model_id: modelCell?.querySelector('code')?.innerText?.trim() || '',
              display_name: modelCell?.querySelector('strong')?.innerText?.trim() || '',
              input_modalities: labels(modalityGroups[0]),
              output_modalities: labels(modalityGroups[1]),
              context_window: cells[2]?.innerText?.trim() || '',
              price_tiers: priceTiers
            };
          }).filter(Boolean);
        }"""
    )


def fetch_catalog() -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("Install Playwright to run the Modellix LLM updater") from exc

    collected: dict[str, dict[str, Any]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(SOURCE, wait_until="networkidle", timeout=90_000)
            page.locator('table[aria-label="Price table"] tbody.llm-table__group').first.wait_for(timeout=45_000)
            for page_number in range(PAGE_SIZE_LIMIT):
                for row in extract_page_rows(page):
                    key = str(row.get("model_id", "")).casefold()
                    if key:
                        collected[key] = row
                next_page = page.locator('button[aria-label="Next page"]')
                if next_page.count() == 0 or next_page.is_disabled():
                    break
                previous_ids = page.locator('table[aria-label="Price table"] tbody.llm-table__group code').all_inner_texts()
                next_page.click()
                page.wait_for_function(
                    "previous => { const code = document.querySelector('table[aria-label=\"Price table\"] tbody.llm-table__group code'); return code && code.textContent.trim() !== previous[0]; }",
                    arg=previous_ids,
                    timeout=30_000,
                )
            else:
                raise RuntimeError(f"Modellix pagination exceeded {PAGE_SIZE_LIMIT} pages")
        finally:
            browser.close()
    return parse_table_rows(list(collected.values()))


def merge_catalog(fresh: list[dict[str, Any]], previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    result: list[dict] = []
    seen: set[str] = set()
    for snapshot in fresh:
        key = snapshot["model_id"].casefold()
        old = old_by_id.get(key, {})
        model = dict(old)
        model.update(
            {
                "provider": "modellix",
                "model_id": snapshot["model_id"],
                "display_name": snapshot["display_name"],
                "context_window": snapshot["context_window"] or old.get("context_window", 0),
                "max_output_tokens": old.get("max_output_tokens", 0),
                "input_modalities": snapshot["input_modalities"],
                "output_modalities": snapshot["output_modalities"],
                "supports_vision": "image" in snapshot["input_modalities"],
                "supports_chat_completion": "text" in snapshot["output_modalities"],
                "supports_streaming": "text" in snapshot["output_modalities"],
                "supports_responses_api": "text" in snapshot["output_modalities"],
                "supports_anthropic_api": "text" in snapshot["output_modalities"],
                "license_type": old.get("license_type", "api"),
                "deprecated": old.get("deprecated", False),
                "aliases": old.get("aliases", []),
            }
        )
        tiers = snapshot["price_tiers"]
        if tiers:
            first = tiers[0]
            pricing = dict(old.get("pricing") or {})
            pricing.update(
                {
                    "input_per_1m": first["input_per_1m"],
                    "output_per_1m": first["output_per_1m"],
                    "currency": "USD",
                }
            )
            for key_name in ("cache_read_per_1m", "cache_write_per_1m"):
                if key_name in first:
                    pricing[key_name] = first[key_name]
            model["pricing"] = pricing
        extra = dict(old.get("extra") or {})
        extra.update(
            {
                "official_source": SOURCE,
                "gateway_base_url": GATEWAY,
                "checked_at": checked_at,
                "catalog_source": "official_modellix_llm_price_table",
            }
        )
        if len(tiers) > 1:
            extra["input_context_pricing_tiers"] = tiers
        model["extra"] = extra
        seen.add(key)
        result.append(model)

    # Preserve older curated IDs absent from the current page; the updater does
    # not infer deprecation from a paginated pricing snapshot.
    result.extend(row for row in previous if isinstance(row, dict) and str(row.get("model_id", "")).casefold() not in seen)
    return result


def update_catalog(fresh: list[dict[str, Any]], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    previous = data.get("models") or []
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_catalog(fresh, previous, checked_at)
    if not models:
        raise ValueError("refusing to write an empty Modellix LLM catalog")
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"modellix.json: refreshed {len(fresh)} official rows; total={len(models)}")
    return len(fresh)


def main() -> None:
    update_catalog(fetch_catalog())


if __name__ == "__main__":
    main()
