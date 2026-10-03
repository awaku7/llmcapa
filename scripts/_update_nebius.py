"""Refresh the Nebius Token Factory model catalog from its public official API.

Source: https://tokenfactory.nebius.com/api/public/models_info
Run with: python scripts/_update_all_providers.py --provider nebius
"""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "nebius.json"
SOURCE = "https://tokenfactory.nebius.com/api/public/models_info"

# These are the model kinds represented by llmcapa's input/output modalities.
_TYPE_MODALITIES = {
    "text2text": (["text"], ["text"], True),
    "image2text": (["text", "image"], ["text"], True),
    "embedding": (["text"], ["embedding"], False),
    "rerank": (["text"], ["rerank"], False),
    "text2image": (["text"], ["image"], False),
    "image2image": (["image"], ["image"], False),
    "text2video": (["text"], ["video"], False),
    "image2video": (["text", "image"], ["video"], False),
    "text2speech": (["text"], ["audio"], False),
    "speech2text": (["audio"], ["text"], False),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_catalog() -> Any:
    request = urllib.request.Request(
        SOURCE,
        headers={"User-Agent": "llmcapa provider catalog updater"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Nebius public model catalog must be a JSON list")
    return payload


def catalog_to_models(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for model in payload:
        if not isinstance(model, dict):
            continue
        status = str(model.get("status", "active")).lower()
        if status not in {"active", "available", ""}:
            continue
        model_type = str(model.get("type", "")).lower()
        modality_info = _TYPE_MODALITIES.get(model_type)
        if modality_info is None:
            continue
        input_modalities, output_modalities, is_chat = modality_info
        use_cases = [str(x).lower() for x in (model.get("use_cases") or [])]
        tags = [str(x).lower() for x in (model.get("tags") or [])]

        for flavor in model.get("flavors") or []:
            if not isinstance(flavor, dict):
                continue
            model_id = str(flavor.get("model_id", "")).strip()
            if not model_id:
                continue
            context = flavor.get("max_model_len")
            if not isinstance(context, int) or context < 0:
                context_k = flavor.get("context_window_k", model.get("context_window_k"))
                context = int(float(context_k) * 1000) if _number(context_k) is not None else 0

            input_price = _number(flavor.get("input_price_per_million_tokens"))
            output_price = _number(flavor.get("output_price_per_million_tokens"))
            pricing = None
            if input_price is not None and output_price is not None:
                pricing = {
                    "input_per_1m": input_price,
                    "output_per_1m": output_price,
                    "currency": "USD",
                }

            region_names = sorted(
                str(region.get("name", ""))
                for region in (flavor.get("regions") or [])
                if isinstance(region, dict) and region.get("name")
            )
            entry = {
                "provider": "nebius",
                "model_id": model_id,
                "display_name": flavor.get("model_name") or model.get("name") or model_id,
                "context_window": context,
                # The public catalog reports context length, not a separate output cap.
                "max_output_tokens": 0,
                "input_modalities": list(input_modalities),
                "output_modalities": list(output_modalities),
                "supports_chat_completion": is_chat,
                "supports_streaming": None,
                "supports_function_calling": True if {"function_calling", "tools"} & set(use_cases + tags) else None,
                "supports_json_mode": True if {"json mode", "json_mode", "json"} & set(use_cases + tags) else None,
                "supports_vision": "image" in input_modalities,
                "supports_reasoning": True if "reasoning" in use_cases + tags else None,
                "supports_responses_api": True if "responses_api" in use_cases + tags else None,
                "pricing": pricing,
                "deprecated": False,
                "aliases": [],
                "license_type": "api",
                "extra": {
                    "source": SOURCE,
                    "vendor": model.get("vendor"),
                    "model_type": model_type,
                    "regions": region_names,
                    "use_cases": sorted(set(use_cases)),
                    "tags": sorted(set(tags)),
                    "external_provider": flavor.get("external_provider"),
                },
            }
            old = by_id.get(model_id)
            if old is None:
                by_id[model_id] = entry
                continue

            # A model can be offered in several regions/flavors. Do not claim
            # one region's price as universal when the official API differs.
            previous_regions = list(old["extra"].get("regions", []))
            old_regions = set(previous_regions)
            old_regions.update(region_names)
            old["extra"]["regions"] = sorted(old_regions)
            old_pricing = old.get("pricing")
            if old_pricing != pricing:
                flavors = old["extra"].setdefault("regional_pricing", [])
                for regions, candidate_pricing in (
                    (previous_regions, old_pricing),
                    (region_names, pricing),
                ):
                    if candidate_pricing:
                        variant = {"regions": regions, **candidate_pricing}
                        if variant not in flavors:
                            flavors.append(variant)
                old["pricing"] = None

    return [by_id[key] for key in sorted(by_id)]


def main() -> None:
    models = catalog_to_models(fetch_catalog())
    if not models:
        raise RuntimeError("Nebius API returned no supported public models")
    DATA.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"nebius.json: {len(models)} models refreshed from official public catalog")


if __name__ == "__main__":
    main()
