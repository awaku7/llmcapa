"""Refresh Baseten's public Model APIs inventory by scraping official docs.

Baseten's authenticated management API lists account/deployment-specific Model
APIs. The bundled catalog represents Baseten's public hosted catalog instead,
so this updater scrapes its public supported-model and feature tables. No API
key is needed.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "baseten.json"
SOURCE = "https://docs.baseten.co/inference/model-apis/overview"

_SUPPORTED_ROW = re.compile(
    r'model:\s*"([^"]+)"\s*,\s*slug:\s*"([^"]+)"\s*,\s*'
    r"context:\s*(\d+)\s*,\s*maxOutput:\s*(\d+)",
    re.DOTALL,
)
_FEATURE_ROW = re.compile(
    r'model:\s*"([^"]+)"\s*,\s*reasoning:\s*"([^"]+)"\s*,\s*'
    r'vision:\s*"([^"]+)"\s*,\s*sampling:\s*"([^"]+)"',
    re.DOTALL,
)


def _thousands(value: str) -> int:
    match = re.search(r"([\d,.]+)\s*([kKmM]?)", value)
    if not match:
        return 0
    amount = float(match.group(1).replace(",", ""))
    suffix = match.group(2).casefold()
    if suffix == "m":
        amount *= 1_000
    elif not suffix and amount >= 1_000:
        amount /= 1_000
    return int(amount)


def _rendered_tables_as_source(tables: list[list[list[str]]]) -> str:
    """Normalize the docs site's rendered tables to the existing parser format."""
    supported = None
    features = None
    for table in tables:
        if not table:
            continue
        headers = [cell.strip().casefold() for cell in table[0]]
        if {"model", "slug", "context", "max output"}.issubset(headers):
            supported = (headers, table[1:])
        if {"model", "reasoning", "vision", "sampling parameters"}.issubset(headers):
            features = (headers, table[1:])
    if supported is None or features is None:
        raise RuntimeError(
            "Baseten Model APIs page did not render its supported-model and feature tables"
        )

    supported_headers, supported_rows = supported
    feature_headers, feature_rows = features
    supported_lines = []
    for row in supported_rows:
        if len(row) < len(supported_headers):
            continue
        values = dict(zip(supported_headers, row))
        name = values["model"].strip()
        slug = values["slug"].strip()
        if not name or not slug:
            continue
        supported_lines.append(
            "model: "
            + json.dumps(name, ensure_ascii=False)
            + ", slug: "
            + json.dumps(slug, ensure_ascii=False)
            + f", context: {_thousands(values['context'])}, "
            + f"maxOutput: {_thousands(values['max output'])}"
        )

    feature_lines = []
    for row in feature_rows:
        if len(row) < len(feature_headers):
            continue
        values = dict(zip(feature_headers, row))
        name = values["model"].strip()
        if not name:
            continue
        feature_lines.append(
            "model: "
            + json.dumps(name, ensure_ascii=False)
            + ", reasoning: "
            + json.dumps(values["reasoning"].strip(), ensure_ascii=False)
            + ", vision: "
            + json.dumps(values["vision"].strip(), ensure_ascii=False)
            + ", sampling: "
            + json.dumps(values["sampling parameters"].strip(), ensure_ascii=False)
        )
    if not supported_lines or not feature_lines:
        raise RuntimeError("Baseten rendered catalog tables contained no model rows")
    return (
        "export const SupportedModelsTable = [\\n"
        + ",\\n".join("{" + line + "}" for line in supported_lines)
        + "\\n];\\nexport const FeatureSupportTable = [\\n"
        + ",\\n".join("{" + line + "}" for line in feature_lines)
        + "\\n];"
    )


def fetch_docs() -> str:
    """Read the current dynamic model tables from Baseten's public docs page."""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(SOURCE, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_function(
                    "document.body.innerText.includes('Slug') && "
                    "document.body.innerText.includes('Sampling parameters')",
                    timeout=60_000,
                )
                tables = page.evaluate(
                    """() => Array.from(document.querySelectorAll('[role=table], table'))
                        .map(table => Array.from(table.querySelectorAll('[role=row], tr'))
                            .map(row => Array.from(row.querySelectorAll(
                                '[role=columnheader], [role=cell], th, td'
                            )).map(cell => (cell.innerText || '').trim()))
                            .filter(row => row.length))"""
                )
            finally:
                browser.close()
    except Exception as exc:
        raise RuntimeError(
            f"Baseten public Model APIs docs could not be rendered: {exc}"
        ) from exc
    return _rendered_tables_as_source(tables)


def parse_model_inventory(markdown: str) -> list[dict[str, Any]]:
    """Parse the public supported-model list and model-specific feature table."""
    supported_section = markdown.split("export const SupportedModelsTable", 1)
    feature_section = markdown.split("export const FeatureSupportTable", 1)
    if len(supported_section) != 2 or len(feature_section) != 2:
        raise ValueError("Baseten docs are missing public model/feature table data")
    supported_matches = list(_SUPPORTED_ROW.finditer(supported_section[1]))
    feature_matches = list(
        _FEATURE_ROW.finditer(
            feature_section[1].split("export const SupportedModelsTable", 1)[0]
        )
    )
    features = {
        match.group(1).casefold(): match.groups()[1:] for match in feature_matches
    }
    rows = []
    seen: set[str] = set()
    for match in supported_matches:
        name, slug, context_k, output_k = match.groups()
        model_id = slug.strip()
        key = model_id.casefold()
        if not model_id or key in seen:
            continue
        feature = features.get(name.casefold(), ("", "", ""))
        reasoning_label, vision_label, sampling = feature
        vision = vision_label.strip() in {"✓", "✔", "yes", "Yes"}
        context_window = int(context_k) * 1_000
        max_output_tokens = int(output_k) * 1_000
        rows.append(
            {
                "model_id": model_id,
                "display_name": name.strip(),
                "context_window": context_window,
                "max_output_tokens": max_output_tokens,
                "input_modalities": ["text", "image"] if vision else ["text"],
                "output_modalities": ["text"],
                "supports_vision": vision,
                "supports_reasoning": bool(reasoning_label.strip()),
                "supports_function_calling": True,
                "supports_json_mode": True,
                "supports_json_schema": True,
                "supports_streaming": True,
                "supports_chat_completion": True,
                "supports_responses_api": False,
                "sampling_parameters": [
                    item.strip() for item in sampling.split(",") if item.strip()
                ],
            }
        )
        seen.add(key)
    if not rows:
        raise ValueError("Baseten public docs contained no supported model rows")
    return sorted(rows, key=lambda row: row["model_id"].casefold())


def catalog_to_models(
    rows: list[dict[str, Any]], existing: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    old_by_id = {
        str(model.get("model_id", "")).casefold(): model
        for model in (existing or [])
        if isinstance(model, dict) and model.get("model_id")
    }
    by_id: dict[str, dict[str, Any]] = {}
    for snapshot in rows:
        model_id = str(snapshot["model_id"])
        key = model_id.casefold()
        old = old_by_id.get(key, {})
        entry = dict(old)
        entry.update(
            {
                "provider": "baseten",
                "model_id": model_id,
                "display_name": snapshot["display_name"],
                "context_window": snapshot["context_window"],
                "max_output_tokens": snapshot["max_output_tokens"],
                "input_modalities": snapshot["input_modalities"],
                "output_modalities": snapshot["output_modalities"],
                "supports_vision": snapshot["supports_vision"],
                "supports_reasoning": snapshot["supports_reasoning"],
                "supports_function_calling": snapshot["supports_function_calling"],
                "supports_json_mode": snapshot["supports_json_mode"],
                "supports_json_schema": snapshot["supports_json_schema"],
                "supports_streaming": snapshot["supports_streaming"],
                "supports_chat_completion": snapshot["supports_chat_completion"],
                "supports_responses_api": snapshot["supports_responses_api"],
                "deprecated": False,
                "license_type": "api",
            }
        )
        extra = dict(old.get("extra") or {})
        extra.update(
            {
                "source": SOURCE,
                "official_source_checked_at": datetime.now(timezone.utc)
                .date()
                .isoformat(),
                "catalog_source": "official_baseten_public_model_apis_docs",
                "model_family": model_id.split("/", 1)[0],
                "sampling_parameters": snapshot["sampling_parameters"],
                "not_listed_in_current_docs": False,
            }
        )
        entry["extra"] = extra
        by_id[key] = entry
    for old in existing or []:
        if not isinstance(old, dict):
            continue
        key = str(old.get("model_id", "")).casefold()
        if key and key not in by_id:
            row = dict(old)
            extra = dict(row.get("extra") or {})
            extra.update(
                {
                    "official_source_checked_at": datetime.now(timezone.utc)
                    .date()
                    .isoformat(),
                    "not_listed_in_current_docs": True,
                }
            )
            row["extra"] = extra
            by_id[key] = row
    return [by_id[key] for key in sorted(by_id)]


def main() -> None:
    existing_payload = json.loads(DATA.read_text(encoding="utf-8"))
    rows = parse_model_inventory(fetch_docs())
    models = catalog_to_models(rows, existing_payload.get("models", []))
    if not models:
        raise RuntimeError("Baseten public docs returned no usable models")
    DATA.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"baseten.json: {len(rows)} public models scraped; total={len(models)}")


if __name__ == "__main__":
    main()
