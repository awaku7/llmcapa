"""Refresh static local-inference model metadata from the bundled HF snapshot.

No local server is contacted. vLLM, llama.cpp, and LM Studio catalogs derive
model facts from the same offline Hugging Face model snapshot. Provider-specific
API capabilities are overlaid on model metadata; unmatched prior IDs are retained.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
HUGGINGFACE_DATA = ROOT / "src" / "llmcapa" / "data" / "huggingface.json"
HUGGINGFACE_MODEL_URL = "https://huggingface.co/{}"
_VLLM_REASONING_EVIDENCE = (
    ROOT / "src" / "llmcapa" / "data" / "_vllm_verified_reasoning.meta"
)
_VLLM_REASONING_FIELDS = (
    "supports_reasoning",
    "supports_reasoning_effort",
    "reasoning_effort_values",
    "supports_thinking_budget",
    "thinking_budget_values",
    "thinking_control",
)
_OPENAI_COMPAT_CHAT_PIPELINES = {
    "text-generation",
    "text2text-generation",
    "image-text-to-text",
    "visual-question-answering",
    "image-to-text",
    "audio-text-to-text",
    "audio-to-text",
    "video-text-to-text",
}
_BACKEND_CHAT_API_OVERRIDES = {
    "vllm": {
        "supports_chat_completion": True,
        "supports_streaming": True,
        "supports_responses_api": True,
        "supports_json_mode": True,
        "supports_json_schema": True,
    },
    "lmstudio": {
        "supports_chat_completion": True,
        "supports_streaming": True,
        "supports_responses_api": True,
        "supports_json_mode": True,
        "supports_json_schema": True,
    },
}
PROVIDER_CONFIG = {
    "vllm": {
        "filename": "vllm.json",
        "base_url": "http://localhost:8000/v1",
        "source": "https://docs.vllm.ai/en/stable/serving/openai_compatible_server.html",
        "all_hf_models": True,
    },
    "llama-cpp": {
        "filename": "llama_cpp.json",
        "base_url": "http://localhost:8080/v1",
        "source": "https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md",
        "all_hf_models": True,
    },
    "lmstudio": {
        "filename": "lmstudio.json",
        "base_url": "http://localhost:1234/v1",
        "source": "https://lmstudio.ai/docs/developer/openai-compat",
        "all_hf_models": True,
    },
}

# These fields described a past local server snapshot, not static model metadata.
_LOCAL_INVENTORY_FIELDS = {
    "inventory_scope",
    "model_server_base_url",
    "not_listed_in_current_installation",
    "not_listed_in_current_server",
    "local_model_type",
    "publisher",
    "server_model_created",
    "last_seen",
    "size_bytes",
    "digest",
    "quantization_level",
    "official_catalog_status",
}


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _list_union(current: Any, previous: Any, default: list[str]) -> list[str]:
    current_values = current if isinstance(current, list) else default
    previous_values = previous if isinstance(previous, list) else []
    return list(dict.fromkeys([*current_values, *previous_values]))


def build_catalog(
    source: dict[str, Any],
    previous: list[dict[str, Any]] | None = None,
    *,
    provider: str = "vllm",
) -> dict[str, list[dict[str, Any]]]:
    """Build provider rows from HF facts without querying runtime inventory."""
    if provider not in PROVIDER_CONFIG:
        raise ValueError(f"unsupported static HF provider: {provider}")
    config = PROVIDER_CONFIG[provider]
    previous = previous or []
    verified_vllm = (
        json.loads(_VLLM_REASONING_EVIDENCE.read_text(encoding="utf-8"))["models"]
        if provider == "vllm"
        else {}
    )
    old_by_id = {
        str(row.get("model_id", "")): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    old_by_id_casefold = {
        model_id.casefold(): row for model_id, row in old_by_id.items()
    }
    rows: dict[str, dict[str, Any]] = {}
    checked_at = datetime.now(timezone.utc).date().isoformat()

    for hf_row in source.get("models", []):
        if not isinstance(hf_row, dict) or not hf_row.get("model_id"):
            continue

        hf_model_id = str(hf_row["model_id"]).strip()
        if not hf_model_id:
            continue
        old = old_by_id.get(hf_model_id) or old_by_id_casefold.get(
            hf_model_id.casefold(), {}
        )
        if not config["all_hf_models"] and not old:
            # Keep the existing local-runtime model set; enrich only exact HF IDs.
            continue
        # Preserve the provider's prior spelling when it differs only by case.
        model_id = str(old.get("model_id") or hf_model_id)

        raw_extra = old.get("extra")
        extra = dict(raw_extra) if isinstance(raw_extra, dict) else {}
        for field in _LOCAL_INVENTORY_FIELDS:
            extra.pop(field, None)
        extra.update(
            {
                "metadata_source": "huggingface",
                "metadata_source_checked_at": checked_at,
                "huggingface_model_id": hf_model_id,
                "huggingface_model_url": HUGGINGFACE_MODEL_URL.format(
                    quote(hf_model_id, safe="/")
                ),
                "huggingface_pipeline_tag": hf_row.get("pipeline_tag"),
                "huggingface_downloads": hf_row.get("downloads"),
                "huggingface_likes": hf_row.get("likes"),
                "endpoints": extra.get(
                    "endpoints",
                    [
                        {
                            "base_url": config["base_url"],
                            "protocol": "openai-compatible",
                            "auth": "bearer",
                            "source": config["source"],
                        }
                    ],
                ),
            }
        )
        input_modalities = _list_union(
            hf_row.get("input_modalities"), old.get("input_modalities"), []
        )
        output_modalities = _list_union(
            hf_row.get("output_modalities"), old.get("output_modalities"), []
        )
        old_vision = old.get("supports_vision")
        supports_vision = (
            True
            if "image" in input_modalities or old_vision is True
            else hf_row.get("supports_vision")
        )
        row = dict(old)
        row.update(
            {
                "provider": provider,
                "model_id": model_id,
                "display_name": str(
                    old.get("display_name") or hf_row.get("display_name") or model_id
                ),
                "aliases": _list_union(hf_row.get("aliases"), old.get("aliases"), []),
                "license_type": str(
                    hf_row.get("license_type") or old.get("license_type") or "unknown"
                ),
                "context_window": _nonnegative_int(hf_row.get("context_window"))
                or _nonnegative_int(old.get("context_window")),
                # HF's generic scraper default is not a model-specific output limit.
                "max_output_tokens": _nonnegative_int(old.get("max_output_tokens")),
                "input_modalities": input_modalities,
                "output_modalities": output_modalities,
                "supports_vision": supports_vision,
                "extra": extra,
            }
        )
        for field in (
            "supports_function_calling",
            "supports_json_mode",
            "supports_json_schema",
            "supports_streaming",
            "supports_reasoning",
            "supports_chat_completion",
            "supports_responses_api",
        ):
            row.setdefault(field, None)
        row.setdefault("knowledge_cutoff", None)
        row.setdefault("pricing", None)
        row.setdefault("deprecated", False)
        row.setdefault("aliases", [])
        row.setdefault("license_type", "unknown")
        pipeline_tag = str(hf_row.get("pipeline_tag", "")).casefold()
        backend_overrides = _BACKEND_CHAT_API_OVERRIDES.get(provider)
        if backend_overrides and pipeline_tag in _OPENAI_COMPAT_CHAT_PIPELINES:
            # These flags describe backend endpoints, not model-repository facts.
            # Function calling remains model/template-specific.
            row.update(backend_overrides)
            if provider == "lmstudio":
                extra["responses_api_source"] = (
                    "https://lmstudio.ai/docs/developer/openai-compat/responses"
                )
                extra["responses_api_stateful"] = True
                extra["structured_output_source"] = (
                    "https://lmstudio.ai/docs/developer/openai-compat/structured-output"
                )
                extra["structured_output_model_dependent"] = True
        # Only reviewed, exact model IDs receive reasoning controls. A model
        # name substring, derivative, or another provider's API flags are not
        # evidence that the vLLM renderer supports the same effort values.
        verified = verified_vllm.get(model_id)
        if isinstance(verified, dict):
            for field in _VLLM_REASONING_FIELDS:
                if field in verified:
                    row[field] = verified[field]
            extra["vllm_reasoning_evidence"] = {
                "source": verified["evidence_url"],
                "checked_at": verified["checked_at"],
                "note": verified.get("note", ""),
                "verification": "documentation_only",
            }
        rows[model_id] = row

    # Keep historical/local IDs with no exact HF repository match, but strip
    # stale server-inventory fields so the file no longer claims live presence.
    for old in previous:
        if not isinstance(old, dict) or not old.get("model_id"):
            continue
        model_id = str(old["model_id"])
        if model_id in rows:
            continue
        row = dict(old)
        raw_extra = row.get("extra")
        extra = dict(raw_extra) if isinstance(raw_extra, dict) else {}
        for field in _LOCAL_INVENTORY_FIELDS:
            extra.pop(field, None)
        extra["metadata_source"] = "previous_catalog_no_exact_hf_match"
        extra["not_listed_in_huggingface_snapshot"] = True
        row["provider"] = provider
        row["extra"] = extra
        rows[model_id] = row

    if not rows:
        raise ValueError(f"HF snapshot contains no model records for {provider}")
    return {"models": [rows[model_id] for model_id in sorted(rows, key=str.casefold)]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=sorted(PROVIDER_CONFIG), default="vllm")
    provider = parser.parse_args().provider
    data_path = (
        ROOT / "src" / "llmcapa" / "data" / PROVIDER_CONFIG[provider]["filename"]
    )
    source = json.loads(HUGGINGFACE_DATA.read_text(encoding="utf-8"))
    previous_data = (
        json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}
    )
    catalog = build_catalog(source, previous_data.get("models", []), provider=provider)
    data_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{provider}: {len(catalog['models'])} static HF-derived metadata records")


if __name__ == "__main__":
    main()
