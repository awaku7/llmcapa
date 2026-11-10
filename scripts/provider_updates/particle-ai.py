"""Refresh Particle Inference API models from Particle's official docs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.provider_updates._catalog_io import load_json, save_json
    from scripts.provider_updates._http import fetch_text
except ModuleNotFoundError:  # Running this updater directly by path.
    from _catalog_io import load_json, save_json
    from _http import fetch_text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "particle-ai.json"
MODELS_SOURCE = "https://docs.particle.ai/models"
MODELS_URL = MODELS_SOURCE + ".md"
PRICING_SOURCE = "https://docs.particle.ai/usage-billing"
PRICING_URL = PRICING_SOURCE + ".md"
BASE_URL = "https://api.particle.ai/v1"
RESPONSES_URL = "wss://api.particle.ai/v1/responses"

# These are the three production entries in Particle's official model catalog.
# This catalog is scoped to the Particle Inference API, so it may contain
# models also offered by their original labs or other inference services.
MODEL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "model_id": "particle-ai/particle-1",
        "pricing_id": "particle-1",
        "display_name": "Particle-1",
        "aliases": ["particle-1"],
        "reasoning_effort_values": [
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "ultra",
        ],
        "reasoning_can_be_disabled": True,
        "tool_calling_status": "qualified",
        "off_peak_factor": 0.5,
    },
    {
        "model_id": "deepseek-ai/deepseek-v41-flash-1017",
        "pricing_id": "deepseek-v41-flash-1017",
        "display_name": "DeepSeek V4.1 Flash",
        "aliases": [
            "deepseek-v41-flash-1017",
            "deepseek-v4.1-flash",
            "deepseek-v4-flash-0731",
            "deepseek-v4-flash",
            "deepseek-v4.1-flash-1017",
        ],
        "reasoning_effort_values": [
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "ultra",
        ],
        "reasoning_can_be_disabled": True,
        "tool_calling_status": "qualified",
        "off_peak_factor": 0.5,
    },
    {
        "model_id": "glm-5.3-flash",
        "pricing_id": "glm-5.3-flash",
        "display_name": "GLM 5.3 Flash",
        "aliases": ["glm5.3flash"],
        "reasoning_effort_values": ["minimal", "low", "medium", "high", "xhigh", "max"],
        "reasoning_can_be_disabled": False,
        "tool_calling_status": "supported",
        "off_peak_factor": 0.5,
    },
)


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_prices(markdown: str) -> dict[str, dict[str, float]]:
    """Parse Particle's official peak input/cache/output prices."""
    accepted = {str(spec["pricing_id"]) for spec in MODEL_SPECS}
    result: dict[str, dict[str, float]] = {}
    for line in markdown.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _table_cells(line)
        if not cells:
            continue
        model_id = cells[0].strip("`")
        if model_id not in accepted:
            continue
        prices = []
        for cell in cells[1:]:
            match = re.search(r"\\?\$\s*([\d,]+(?:\.\d+)?)", cell)
            if match:
                prices.append(float(match.group(1).replace(",", "")))
        if len(prices) < 3:
            raise ValueError(f"Particle pricing row is incomplete for {model_id}")
        result[model_id] = {
            "input_per_1m": prices[0],
            "cached_input_per_1m": prices[1],
            "output_per_1m": prices[2],
        }
    missing = accepted - result.keys()
    if missing:
        raise ValueError(f"Particle pricing docs are missing models: {sorted(missing)}")
    return result


def parse_inventory(
    models_markdown: str,
    pricing_markdown: str,
    *,
    checked_at: str | None = None,
) -> list[dict[str, Any]]:
    """Combine the official model catalog and billing table into records."""
    required_ids = {str(spec["model_id"]) for spec in MODEL_SPECS}
    if any(model_id not in models_markdown for model_id in required_ids):
        raise ValueError("Particle model catalog is missing an expected public model ID")
    if "1,048,576" not in models_markdown or "131,072" not in models_markdown:
        raise ValueError("Particle model catalog no longer documents token limits")
    prices = parse_prices(pricing_markdown)
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()

    records = []
    for spec in MODEL_SPECS:
        price = prices[str(spec["pricing_id"])]
        off_peak_factor = float(spec["off_peak_factor"])
        model_id = str(spec["model_id"])
        records.append(
            {
                "provider": "particle-ai",
                "model_id": model_id,
                "display_name": str(spec["display_name"]),
                "context_window": 1_048_576,
                "max_output_tokens": 131_072,
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
                "supports_function_calling": True,
                "supports_json_mode": True,
                "supports_json_schema": False,
                "supports_streaming": True,
                "supports_vision": True,
                "supports_reasoning": True,
                "supports_chat_completion": True,
                "supports_responses_api": True,
                "supports_reasoning_effort": True,
                "reasoning_effort_values": list(spec["reasoning_effort_values"]),
                "supports_thinking_budget": False,
                "deprecated": False,
                "aliases": list(spec["aliases"]),
                "license_type": "api",
                "pricing": {
                    "input_per_1m": price["input_per_1m"],
                    "output_per_1m": price["output_per_1m"],
                    "currency": "USD",
                },
                "extra": {
                    "source": MODELS_SOURCE,
                    "pricing_source": PRICING_SOURCE,
                    "official_source_checked_at": checked_at,
                    "base_url": BASE_URL,
                    "responses_websocket_url": RESPONSES_URL,
                    "auth": "bearer",
                    "protocol": "openai-compatible",
                    "default_output_tokens": 32_000,
                    "cached_input_per_1m": price["cached_input_per_1m"],
                    "off_peak_pricing": {
                        "input_per_1m": price["input_per_1m"] * off_peak_factor,
                        "cached_input_per_1m": price["cached_input_per_1m"]
                        * off_peak_factor,
                        "output_per_1m": price["output_per_1m"] * off_peak_factor,
                        "currency": "USD",
                    },
                    "off_peak_period": "20:30-04:00 America/New_York",
                    "reasoning_default_effort": "high",
                    "reasoning_can_be_disabled": spec[
                        "reasoning_can_be_disabled"
                    ],
                    "tool_calling_status": spec["tool_calling_status"],
                    "structured_outputs_status": "json_schema_best_effort_no_guarantee",
                    "prompt_and_completion_share_context": True,
                    "not_listed_in_current_docs": False,
                },
            }
        )
    return records


def merge_inventory(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    *,
    checked_at: str,
) -> list[dict[str, Any]]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fresh in current:
        model_id = str(fresh["model_id"])
        key = model_id.casefold()
        row = dict(old_by_id.get(key) or {})
        row.update(fresh)
        extra = dict(old_by_id.get(key, {}).get("extra") or {})
        extra.update(fresh.get("extra") or {})
        extra["official_source_checked_at"] = checked_at
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
                    "official_source_checked_at": checked_at,
                    "not_listed_in_current_docs": True,
                }
            )
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(
    models_markdown: str | None = None,
    pricing_markdown: str | None = None,
    *,
    checked_at: str | None = None,
) -> list[dict[str, Any]]:
    """Refresh the Particle provider catalog using only its official docs."""
    if models_markdown is None:
        models_markdown = fetch_text(
            MODELS_URL,
            headers={
                "Accept": "text/markdown,text/plain,*/*",
                "User-Agent": "llmcapa-provider-updater/1.0",
            },
            timeout=30,
            max_bytes=2_000_000,
        )
    if pricing_markdown is None:
        pricing_markdown = fetch_text(
            PRICING_URL,
            headers={
                "Accept": "text/markdown,text/plain,*/*",
                "User-Agent": "llmcapa-provider-updater/1.0",
            },
            timeout=30,
            max_bytes=2_000_000,
        )
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    current = parse_inventory(
        models_markdown, pricing_markdown, checked_at=checked_at
    )
    data = load_json(DATA) if DATA.exists() else {"models": []}
    merged = merge_inventory(current, data.get("models") or [], checked_at=checked_at)
    save_json(DATA, {**data, "models": merged})
    print(f"particle-ai.json: refreshed {len(current)} official models; total={len(merged)}")
    return merged


def main() -> None:
    update_catalog()


if __name__ == "__main__":
    main()
