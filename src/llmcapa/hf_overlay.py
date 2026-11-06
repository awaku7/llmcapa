"""Lossless Hugging Face overlays for bundled local inference catalogs.

Only facts differing from Hugging Face are stored per model.  The provider
catalog is materialized at load time, preserving the normal Capability API.
"""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from typing import Any
from urllib.parse import quote

FORMAT = "hf-model-overlay-v1"
PROVIDERS = frozenset({"vllm", "llama-cpp", "lmstudio"})
INHERITED_FIELDS = (
    "model_id",
    "display_name",
    "aliases",
    "license_type",
    "context_window",
    "input_modalities",
    "output_modalities",
    "supports_vision",
    "supports_function_calling",
    "supports_json_mode",
    "supports_streaming",
    "supports_chat_completion",
    "supports_responses_api",
)
DYNAMIC_EXTRA = frozenset(
    {
        "huggingface_model_id",
        "huggingface_model_url",
        "huggingface_pipeline_tag",
        "huggingface_downloads",
        "huggingface_likes",
    }
)


def is_hf_overlay(payload: Any) -> bool:
    """Identify the explicit compact format; ordinary catalogs are untouched."""
    return isinstance(payload, dict) and payload.get("_format") == FORMAT


def _default_fields(
    matched: list[dict[str, Any]], *, excluded: frozenset[str]
) -> dict[str, Any]:
    """Hoist prevalent fields without assuming every record has those values."""
    if not matched:
        return {}
    sample = matched[:: max(1, len(matched) // 512)]
    keys = set().union(*(row.keys() for row in sample)) - excluded
    result: dict[str, Any] = {}
    for key in sorted(keys):
        serialized = [
            json.dumps(
                row[key], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            for row in sample
            if key in row
        ]
        if len(serialized) < len(sample) * 0.9:
            continue
        value, frequency = Counter(serialized).most_common(1)[0]
        if frequency >= len(sample) * 0.6:
            result[key] = json.loads(value)
    return result


def _baseline(hf_model: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    row = {key: deepcopy(hf_model[key]) for key in INHERITED_FIELDS if key in hf_model}
    row.update(deepcopy(overlay["defaults"]))
    row["provider"] = overlay["provider"]
    row["model_id"] = hf_model["model_id"]
    extra = deepcopy(overlay["extra_defaults"])
    model_id = hf_model["model_id"]
    extra.update(
        {
            "huggingface_model_id": model_id,
            "huggingface_model_url": "https://huggingface.co/"
            + quote(model_id, safe="/"),
            "huggingface_pipeline_tag": hf_model.get("pipeline_tag"),
            "huggingface_downloads": hf_model.get("downloads"),
            "huggingface_likes": hf_model.get("likes"),
        }
    )
    row["extra"] = extra
    return row


def _patch(target: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    set_values = {
        key: deepcopy(value)
        for key, value in target.items()
        if key != "extra" and (key not in base or value != base[key])
    }
    unset = sorted(key for key in base if key != "extra" and key not in target)
    if set_values:
        delta["set"] = set_values
    if unset:
        delta["unset"] = unset

    actual_extra = target.get("extra")
    base_extra = base["extra"]
    if isinstance(actual_extra, dict):
        extra_set = {
            key: deepcopy(value)
            for key, value in actual_extra.items()
            if key not in base_extra or value != base_extra[key]
        }
        extra_unset = sorted(key for key in base_extra if key not in actual_extra)
        if extra_set:
            delta["extra_set"] = extra_set
        if extra_unset:
            delta["extra_unset"] = extra_unset
    elif "extra" in target:
        delta["extra_replace"] = deepcopy(actual_extra)
    else:
        delta["extra_remove"] = True
    return delta


def pack_hf_overlay(
    source: dict[str, Any], catalog: dict[str, Any], *, provider: str
) -> dict[str, Any]:
    """Create a sparse overlay; no model or provider-specific fact is dropped."""
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported Hugging Face overlay provider: {provider}")
    hf_rows = source["models"]
    hf_by_id = {str(row["model_id"]).casefold(): row for row in hf_rows}
    if len(hf_by_id) != len(hf_rows):
        raise ValueError("duplicate Hugging Face model ID")
    models = catalog["models"]
    by_id = {str(row["model_id"]).casefold(): row for row in models}
    if len(by_id) != len(models):
        raise ValueError(f"duplicate model ID in {provider} catalog")
    matched = [
        (hf_row, by_id[hf_row["model_id"].casefold()])
        for hf_row in hf_rows
        if hf_row["model_id"].casefold() in by_id
    ]
    if not matched:
        raise ValueError(f"no Hugging Face models in {provider} catalog")
    rows = [row for _, row in matched]
    defaults = _default_fields(rows, excluded=frozenset(INHERITED_FIELDS) | {"extra"})
    extra_defaults = _default_fields(
        [row.get("extra", {}) for row in rows],
        excluded=DYNAMIC_EXTRA,
    )
    overlay: dict[str, Any] = {
        "_format": FORMAT,
        "provider": provider,
        "source": "huggingface.json",
        "defaults": defaults,
        "extra_defaults": extra_defaults,
        "overrides": {},
        "excluded": [],
        "unmatched": [],
    }
    overrides = overlay["overrides"]
    for hf_row in hf_rows:
        model_id = hf_row["model_id"]
        target = by_id.get(model_id.casefold())
        if target is None:
            overlay["excluded"].append(model_id)
            continue
        delta = _patch(target, _baseline(hf_row, overlay))
        if delta:
            overrides[model_id] = delta
    overlay["unmatched"] = [
        deepcopy(row) for row in models if row["model_id"].casefold() not in hf_by_id
    ]
    return overlay


def expand_hf_overlay(
    source: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Expand a compact catalog into original model records without network I/O."""
    if not is_hf_overlay(overlay):
        raise ValueError("not an hf-model-overlay-v1 catalog")
    if overlay.get("provider") not in PROVIDERS:
        raise ValueError("unsupported overlay provider")
    if overlay.get("source") != "huggingface.json":
        raise ValueError("unsupported overlay source")
    excluded = set(overlay.get("excluded", []))
    overrides = overlay.get("overrides", {})
    source_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for hf_row in source["models"]:
        model_id = hf_row["model_id"]
        source_ids.add(model_id)
        if model_id in excluded:
            continue
        row = _baseline(hf_row, overlay)
        delta = overrides.get(model_id, {})
        for key in delta.get("unset", []):
            row.pop(key, None)
        row.update(deepcopy(delta.get("set", {})))
        if delta.get("extra_remove"):
            row.pop("extra", None)
        elif "extra_replace" in delta:
            row["extra"] = deepcopy(delta["extra_replace"])
        else:
            extra = row["extra"]
            for key in delta.get("extra_unset", []):
                extra.pop(key, None)
            extra.update(deepcopy(delta.get("extra_set", {})))
        rows.append(row)
    if not set(overrides).issubset(source_ids):
        raise ValueError("overlay refers to missing Hugging Face model IDs")
    rows.extend(deepcopy(overlay.get("unmatched", [])))
    if len({row["model_id"].casefold() for row in rows}) != len(rows):
        raise ValueError("duplicate model IDs in expanded overlay")
    rows.sort(key=lambda row: row["model_id"].casefold())
    return {"models": rows}
