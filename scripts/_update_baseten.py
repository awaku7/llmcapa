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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "baseten.json"
SOURCE = "https://docs.baseten.co/inference/model-apis/overview"

_SUPPORTED_ROW = re.compile(
    r'model:\s*"([^"]+)"\s*,\s*slug:\s*"([^"]+)"\s*,\s*'
    r"context:\s*(\d+)\s*,\s*maxOutput:\s*(\d+)",
    re.S,
)
_FEATURE_ROW = re.compile(
    r'model:\s*"([^"]+)"\s*,\s*reasoning:\s*"([^"]+)"\s*,\s*'
    r'vision:\s*"([^"]+)"\s*,\s*sampling:\s*"([^"]+)"',
    re.S,
)


def fetch_docs() -> str:
    request = Request(
        SOURCE + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            page = response.read(4_000_000).decode("utf-8", "replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Baseten public Model APIs docs could not be fetched: {exc}") from exc
    if "SupportedModelsTable" not in page or "FeatureSupportTable" not in page:
        raise RuntimeError("Baseten public Model APIs docs did not contain the expected catalog tables")
    return page


def parse_model_inventory(markdown: str) -> list[dict[str, Any]]:
    """Parse the public supported-model list and model-specific feature table."""
    supported_section = markdown.split("export const SupportedModelsTable", 1)
    feature_section = markdown.split("export const FeatureSupportTable", 1)
    if len(supported_section) != 2 or len(feature_section) != 2:
        raise ValueError("Baseten docs are missing public model/feature table data")
    supported_matches = list(_SUPPORTED_ROW.finditer(supported_section[1]))
    feature_matches = list(_FEATURE_ROW.finditer(feature_section[1].split("export const SupportedModelsTable", 1)[0]))
    features = {match.group(1).casefold(): match.groups()[1:] for match in feature_matches}
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
                "sampling_parameters": [item.strip() for item in sampling.split(",") if item.strip()],
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
                "official_source_checked_at": datetime.now(timezone.utc).date().isoformat(),
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
                    "official_source_checked_at": datetime.now(timezone.utc).date().isoformat(),
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
    DATA.write_text(json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"baseten.json: {len(rows)} public models scraped; total={len(models)}")


if __name__ == "__main__":
    main()
