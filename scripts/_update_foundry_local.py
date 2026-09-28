"""Refresh the bundled Foundry Local catalog from Microsoft's public catalog API.

This updater intentionally runs only at catalog-maintenance time. Runtime llmcapa
lookups remain offline and consume the generated ``foundry_local.json`` file.

The request shape and public catalog endpoint mirror Microsoft's Foundry Local
implementation in microsoft/Foundry-Local.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "llmcapa" / "data" / "foundry_local.json"
LOG = ROOT / "provider_update_log.md"

REGION_PROBE_URL = "https://api.catalog.azureml.ms/asset-gallery/v1.0/models"
DEFAULT_REGION = "centralus"
CATALOG_URL_TEMPLATE = "https://ai.azure.com/api/{region}/ux/v1.0/entities/crossRegion"
SOURCE_DOCS = (
    "https://learn.microsoft.com/en-us/azure/foundry-local/reference/reference-rest"
)
SOURCE_IMPL = "https://github.com/microsoft/Foundry-Local"
USER_AGENT = "AzureAiStudio"
PAGE_SIZE = 50


def _post_json(url: str, payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=90) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw), response.headers


def _detect_region() -> str:
    try:
        _, headers = _post_json(REGION_PROBE_URL, {"filters": [], "pageSize": 1})
        served_by = str(headers.get("azureml-served-by-cluster", "") or "")
        match = re.search(r"vienna-([a-z0-9]+)-\d+", served_by, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    except (OSError, TypeError, ValueError):
        return DEFAULT_REGION
    return DEFAULT_REGION


def _filter(field: str, values: list[str]) -> dict[str, Any]:
    return {"field": field, "operator": "eq", "values": values}


def _catalog_request(
    *, skip: int | None = None, continuation_token: str | None = None
) -> dict[str, Any]:
    index_request: dict[str, Any] = {
        "filters": [
            _filter("type", ["models"]),
            _filter("kind", ["Versioned"]),
            _filter("labels", ["latest"]),
            _filter("annotations/tags/foundryLocal", [""]),
        ],
        "pageSize": PAGE_SIZE,
    }
    if skip is not None:
        index_request["skip"] = skip
    if continuation_token:
        index_request["continuationToken"] = continuation_token
    return {
        "resourceIds": [{"resourceId": "azureml", "entityContainerType": "Registry"}],
        "indexEntitiesRequest": index_request,
    }


def fetch_catalog() -> tuple[str, list[dict[str, Any]]]:
    region = _detect_region()
    url = CATALOG_URL_TEMPLATE.format(region=region)
    rows: list[dict[str, Any]] = []
    skip: int | None = None
    continuation: str | None = None
    seen_pages: set[tuple[int | None, str | None]] = set()

    for _ in range(200):
        key = (skip, continuation)
        if key in seen_pages:
            raise RuntimeError("Foundry Local catalog pagination loop detected")
        seen_pages.add(key)

        payload, _headers = _post_json(
            url,
            _catalog_request(skip=skip, continuation_token=continuation),
        )
        response = payload.get("indexEntitiesResponse")
        if not isinstance(response, dict):
            raise TypeError(
                "Foundry Local catalog response has no indexEntitiesResponse"
            )
        page = response.get("value")
        if not isinstance(page, list):
            raise TypeError("Foundry Local catalog response has no value list")
        rows.extend(item for item in page if isinstance(item, dict))

        next_skip = response.get("nextSkip")
        next_token = response.get("continuationToken")
        next_skip = next_skip if isinstance(next_skip, int) and next_skip > 0 else None
        next_token = str(next_token).strip() if next_token else None
        if not next_skip and not next_token:
            break
        skip = next_skip
        continuation = next_token
    else:
        raise RuntimeError("Foundry Local catalog pagination exceeded safety limit")

    if not rows:
        raise RuntimeError("Foundry Local catalog returned no models")
    return region, rows


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _tri_state(values: list[bool | None]) -> bool | None:
    explicit = {value for value in values if value is not None}
    if len(explicit) == 1:
        return explicit.pop()
    return None


def _task_modalities(tasks: set[str]) -> tuple[list[str], list[str], bool]:
    normalized = {task.lower().strip() for task in tasks if task}
    inputs: set[str] = set()
    outputs: set[str] = set()
    chat = False

    for task in normalized:
        if "speech" in task or "transcription" in task or "audio" in task:
            inputs.add("audio")
            outputs.add("text")
            continue
        if "embedding" in task:
            inputs.add("text")
            outputs.add("embedding")
            continue
        if "image" in task or "vision" in task or "multimodal" in task:
            inputs.update({"text", "image"})
            outputs.add("text")
            chat = True
            continue
        inputs.add("text")
        outputs.add("text")
        if "chat" in task or "generation" in task or "completion" in task:
            chat = True

    if not inputs:
        inputs.add("text")
    if not outputs:
        outputs.add("text")
    return sorted(inputs), sorted(outputs), chat


def _variant(item: dict[str, Any]) -> dict[str, Any] | None:
    annotations = (
        item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
    )
    tags = annotations.get("tags") if isinstance(annotations.get("tags"), dict) else {}
    system = (
        annotations.get("systemCatalogData")
        if isinstance(annotations.get("systemCatalogData"), dict)
        else {}
    )
    properties = (
        item.get("properties") if isinstance(item.get("properties"), dict) else {}
    )
    variant_info = (
        properties.get("variantInfo")
        if isinstance(properties.get("variantInfo"), dict)
        else {}
    )
    metadata = (
        variant_info.get("variantMetadata")
        if isinstance(variant_info.get("variantMetadata"), dict)
        else {}
    )
    device = str(metadata.get("device") or "").strip()
    execution_provider = str(metadata.get("executionProvider") or "").strip()
    if not metadata or not device or not execution_provider:
        return None

    name = str(properties.get("name") or "").strip()
    entity_id = str(item.get("entityId") or "").strip()
    if not name or not entity_id:
        return None

    alias = str(tags.get("alias") or "").strip()
    if not alias:
        parents = (
            variant_info.get("parents")
            if isinstance(variant_info.get("parents"), list)
            else []
        )
        parent_asset = ""
        if parents and isinstance(parents[0], dict):
            parent_asset = str(parents[0].get("assetId") or "")
        match = re.search(r"/models/([^/]+)", parent_asset)
        alias = match.group(1) if match else name

    context_window = (
        _as_int(system.get("textContextWindow"))
        or _as_int(system.get("maxInputTokens"))
        or _as_int(tags.get("contextLength"))
        or _as_int(tags.get("maxInputTokens"))
    )
    max_output = _as_int(system.get("maxOutputTokens")) or _as_int(
        tags.get("maxOutputTokens")
    )
    return {
        "alias": alias,
        "name": name,
        "entity_id": entity_id,
        "display_name": str(system.get("displayName") or alias).strip(),
        "publisher": str(system.get("publisher") or "").strip(),
        "task": str(tags.get("task") or "").strip(),
        "license": str(tags.get("license") or "").strip(),
        "supports_tool_calling": _as_bool(tags.get("supportsToolCalling")),
        "supports_reasoning": _as_bool(tags.get("supportsReasoning")),
        "context_window": context_window,
        "max_output_tokens": max_output,
        "uri": str(item.get("assetId") or "").strip(),
        "version": properties.get("version"),
        "min_foundry_local_version": str(properties.get("minFLVersion") or "").strip(),
        "model_type": str(metadata.get("modelType") or "ONNX").strip(),
        "device": str(metadata.get("device") or "").strip().upper(),
        "execution_provider": str(metadata.get("executionProvider") or "").strip(),
        "file_size_bytes": _as_int(metadata.get("fileSizeBytes")),
    }


def build_models(raw_rows: list[dict[str, Any]], region: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in raw_rows:
        parsed = _variant(item)
        if parsed is None:
            continue
        grouped[parsed["alias"].lower()].append(parsed)

    models: list[dict[str, Any]] = []
    for model_id in sorted(grouped):
        variants = sorted(grouped[model_id], key=lambda row: row["entity_id"].lower())
        tasks = {str(row["task"]) for row in variants if row.get("task")}
        publishers = sorted(
            {str(row["publisher"]) for row in variants if row.get("publisher")}
        )
        licenses = sorted(
            {str(row["license"]) for row in variants if row.get("license")}
        )
        input_modalities, output_modalities, chat = _task_modalities(tasks)
        context_windows = [
            int(row["context_window"])
            for row in variants
            if isinstance(row.get("context_window"), int)
            and int(row["context_window"]) > 0
        ]
        max_outputs = [
            int(row["max_output_tokens"])
            for row in variants
            if isinstance(row.get("max_output_tokens"), int)
            and int(row["max_output_tokens"]) > 0
        ]
        official_alias = str(variants[0]["alias"])
        aliases = {str(row["name"]) for row in variants if row.get("name")} | {
            str(row["entity_id"]) for row in variants if row.get("entity_id")
        }
        if official_alias.lower() != model_id:
            aliases.add(official_alias)

        models.append(
            {
                "provider": "foundry-local",
                "model_id": model_id,
                "display_name": str(variants[0].get("display_name") or official_alias),
                "context_window": min(context_windows) if context_windows else 0,
                "max_output_tokens": min(max_outputs) if max_outputs else 0,
                "input_modalities": input_modalities,
                "output_modalities": output_modalities,
                "supports_chat_completion": chat,
                "supports_streaming": chat,
                "supports_function_calling": _tri_state(
                    [row.get("supports_tool_calling") for row in variants]
                ),
                "supports_json_mode": None,
                "supports_vision": "image" in input_modalities,
                "supports_reasoning": _tri_state(
                    [row.get("supports_reasoning") for row in variants]
                ),
                "supports_responses_api": False,
                "license_type": licenses[0] if len(licenses) == 1 else "unknown",
                "pricing": None,
                "deprecated": False,
                "aliases": sorted(aliases, key=str.lower),
                "extra": {
                    "source": CATALOG_URL_TEMPLATE.format(region=region),
                    "source_docs": SOURCE_DOCS,
                    "source_implementation": SOURCE_IMPL,
                    "source_type": "official_foundry_local_catalog_api",
                    "catalog_region": region,
                    "tasks": sorted(tasks),
                    "publishers": publishers,
                    "licenses": licenses,
                    "variants": variants,
                },
            }
        )

    if not models:
        raise RuntimeError("Foundry Local catalog contained no usable models")
    return models


def main() -> None:
    region, raw_rows = fetch_catalog()
    models = build_models(raw_rows, region)
    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Foundry Local refresh ({datetime.now(timezone.utc).date()})\n\n"
        + f"- Source: {CATALOG_URL_TEMPLATE.format(region=region)}\n"
        + f"- Official implementation: {SOURCE_IMPL}\n"
        + f"- Result: {len(models)} logical models from {len(raw_rows)} variants.\n",
        encoding="utf-8",
    )
    print(
        f"foundry_local.json: {len(models)} logical models "
        f"from {len(raw_rows)} variants ({region})"
    )


if __name__ == "__main__":
    main()
