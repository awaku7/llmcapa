"""Normalize document, embedding, rerank, and spatial metadata."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from _metadata_loader import load_overrides
except ImportError:  # package-style test imports
    from scripts._metadata_loader import load_overrides

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"

DOCUMENT_FORMATS = [
    "pdf",
    "txt",
    "md",
    "csv",
    "json",
    "xml",
    "html",
    "docx",
    "xlsx",
    "pptx",
]
DOCUMENT_MIMES = [
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "text/html",
]

OVERRIDES = load_overrides("structured_overrides.json")


def _source(extra: dict[str, Any]) -> str | None:
    return extra.get("official_source") or extra.get("docs_url")


def _generic(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    result: dict[str, dict[str, Any]] = {}
    source = _source(extra)
    status = "documented" if source else "inferred"

    file_like = inputs & {"file", "pdf", "csv", "json", "code", "data"}
    if file_like or outputs & {"file", "pdf", "csv", "json"}:
        doc: dict[str, Any] = {
            "accepts_file": bool(file_like),
            "input_formats": sorted(file_like) if file_like else DOCUMENT_FORMATS,
            "input_mime_types": DOCUMENT_MIMES,
            "status": status,
        }
        if source:
            doc["source_url"] = source
        if any(x in model_id for x in ("ocr", "document", "layout", "parse", "vision")):
            doc["ocr"] = True
        result["document"] = doc

    if outputs & {"embedding", "embeddings"} or any(
        x in model_id for x in ("embedding", "embed")
    ):
        emb: dict[str, Any] = {
            "embedding": True,
            "output_formats": ["float"],
            "status": status,
        }
        if source:
            emb["source_url"] = source
        result["embedding"] = emb

    if "rerank" in outputs or "rerank" in model_id:
        rr: dict[str, Any] = {
            "rerank": True,
            "returns_scores": True,
            "status": status,
        }
        if source:
            rr["source_url"] = source
        result["rerank"] = rr

    spatial_kinds = inputs | outputs
    if spatial_kinds & {"3d-image", "geospatial"}:
        sp: dict[str, Any] = {
            "spatial": True,
            "kind_values": sorted(spatial_kinds & {"3d-image", "geospatial"}),
            "supports_3d": "3d-image" in spatial_kinds,
            "supports_geospatial": "geospatial" in spatial_kinds,
            "status": status,
        }
        if source:
            sp["source_url"] = source
        result["spatial"] = sp
    return result


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    changed = Counter()
    checked = 0
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        file_changed = False
        for record in data.get("models", []):
            provider = str(record.get("provider", ""))
            model_id = str(record.get("model_id", ""))
            inferred = _generic(record)
            overrides = OVERRIDES.get((provider, model_id), {})
            capabilities = {**inferred}
            for key, value in overrides.items():
                capabilities[key] = {**capabilities.get(key, {}), **value}
            if not capabilities:
                continue
            checked += 1
            for key, value in capabilities.items():
                old = dict(record.get(key) or {})
                merged = {**old, **value}
                merged["checked_at"] = datetime.now(timezone.utc).date().isoformat()
                if merged != old:
                    record[key] = merged
                    changed[provider or path.stem] += 1
                    file_changed = True
        if file_changed:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return {
        "records_checked": checked,
        "records_changed": sum(changed.values()),
        **{f"provider:{k}": v for k, v in sorted(changed.items())},
    }


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    counts = Counter()
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("models", []):
            for key in ("document", "embedding", "rerank", "spatial"):
                if record.get(key):
                    counts[key] += 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(json.dumps({"records_by_capability": audit()}, ensure_ascii=False, indent=2))
