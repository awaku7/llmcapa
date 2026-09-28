"""Explicit Microsoft Foundry Local catalog import.

The normal llmcapa lookup path remains offline. This module performs network I/O
only when :func:`fetch_foundry_local` is called, and it only accepts loopback
endpoints because Foundry Local is a machine-local runtime.
"""

from __future__ import annotations

import ipaddress
import json
import urllib.request
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import Capability
from .registry import Registry, default_registry

_MAX_CATALOG_BYTES = 10 * 1024 * 1024
_CONTEXT_KEYS = (
    "contextWindow",
    "contextLength",
    "maxContextLength",
    "maxSequenceLength",
)
_OUTPUT_KEYS = ("maxOutputTokens", "maxTokens", "maxNewTokens")


def _normalize_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("endpoint must be a non-empty loopback URL")
    parsed = urlsplit(endpoint.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpoint scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("endpoint must not contain credentials")
    host = parsed.hostname
    if not host:
        raise ValueError("endpoint must include a host")
    if host.lower() != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("endpoint host must be loopback") from exc
        if not address.is_loopback:
            raise ValueError("endpoint host must be loopback")
    if parsed.query or parsed.fragment:
        raise ValueError("endpoint must not contain query or fragment")
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    elif path:
        raise ValueError("endpoint path must be empty or /v1")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _model_setting_value(record: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = _positive_int(record.get(key))
        if value is not None:
            return value
    settings = record.get("modelSettings")
    if not isinstance(settings, dict):
        return None
    for key in keys:
        value = _positive_int(settings.get(key))
        if value is not None:
            return value
    parameters = settings.get("parameters")
    if not isinstance(parameters, list):
        return None
    wanted = {key.lower() for key in keys}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name") or "").strip().lower()
        if name not in wanted:
            continue
        for value_key in ("value", "default", "max"):
            value = _positive_int(parameter.get(value_key))
            if value is not None:
                return value
    return None


def _conservative_limit(records: list[dict[str, Any]], keys: tuple[str, ...]) -> int:
    values = [
        value
        for record in records
        if (value := _model_setting_value(record, keys)) is not None
    ]
    return min(values) if values else 0


def _task_modalities(tasks: set[str]) -> tuple[list[str], list[str], bool, bool]:
    normalized = {task.lower().replace("_", "-") for task in tasks}
    chat = any("chat" in task or "text-generation" in task for task in normalized)
    vision = any(
        "vision" in task or "image-to-text" in task or "image-text" in task
        for task in normalized
    )
    audio_markers = (
        "automatic-speech-recognition",
        "speech-recognition",
        "transcription",
        "audio",
    )
    audio_input = any(
        any(marker in task for marker in audio_markers) for task in normalized
    )
    embedding = any("embedding" in task for task in normalized)

    input_modalities: list[str] = []
    output_modalities: list[str] = []
    if chat or vision or embedding:
        input_modalities.append("text")
    if vision:
        input_modalities.append("image")
    if audio_input:
        input_modalities.append("audio")
    if embedding:
        output_modalities.append("embedding")
    elif chat or vision or audio_input:
        output_modalities.append("text")
    if not input_modalities:
        input_modalities.append("text")
    if not output_modalities:
        output_modalities.append("text")
    return input_modalities, output_modalities, chat or vision, vision


def _variant_summary(record: dict[str, Any]) -> dict[str, Any]:
    runtime = record.get("runtime")
    runtime_summary: dict[str, Any] = {}
    if isinstance(runtime, dict):
        if runtime.get("deviceType") is not None:
            runtime_summary["device_type"] = runtime.get("deviceType")
        if runtime.get("executionProvider") is not None:
            runtime_summary["execution_provider"] = runtime.get("executionProvider")
    result: dict[str, Any] = {}
    mappings = (
        ("name", "name"),
        ("displayName", "display_name"),
        ("version", "version"),
        ("modelType", "model_type"),
        ("publisher", "publisher"),
        ("task", "task"),
        ("fileSizeMb", "file_size_mb"),
        ("supportsToolCalling", "supports_tool_calling"),
        ("license", "license"),
        ("uri", "uri"),
        ("parentModelUri", "parent_model_uri"),
    )
    for source, target in mappings:
        if record.get(source) is not None:
            result[target] = record.get(source)
    if runtime_summary:
        result["runtime"] = runtime_summary
    return result


def _build_capability(
    model_id: str, records: list[dict[str, Any]], endpoint: str
) -> Capability:
    first = records[0]
    tasks = {
        str(record.get("task") or "").strip()
        for record in records
        if str(record.get("task") or "").strip()
    }
    input_modalities, output_modalities, supports_chat, supports_vision = (
        _task_modalities(tasks)
    )
    tool_flags = [record.get("supportsToolCalling") for record in records]
    supports_tools = bool(tool_flags) and all(flag is True for flag in tool_flags)

    aliases: list[str] = []
    seen_aliases: set[str] = set()
    for record in records:
        name = str(record.get("name") or "").strip()
        lowered = name.lower()
        if name and lowered != model_id.lower() and lowered not in seen_aliases:
            aliases.append(name)
            seen_aliases.add(lowered)

    licenses = {
        str(record.get("license") or "").strip()
        for record in records
        if str(record.get("license") or "").strip()
    }
    license_type = next(iter(licenses)) if len(licenses) == 1 else "unknown"
    publishers = sorted(
        {
            str(record.get("publisher") or "").strip()
            for record in records
            if str(record.get("publisher") or "").strip()
        }
    )
    display_name = str(
        first.get("displayName") or first.get("alias") or model_id
    ).strip()

    return Capability(
        provider="foundry-local",
        model_id=model_id,
        display_name=display_name,
        context_window=_conservative_limit(records, _CONTEXT_KEYS),
        max_output_tokens=_conservative_limit(records, _OUTPUT_KEYS),
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        supports_function_calling=supports_tools,
        supports_json_mode=None,
        supports_streaming=supports_chat,
        supports_vision=supports_vision,
        supports_chat_completion=supports_chat,
        supports_responses_api=False,
        license_type=license_type,
        aliases=aliases,
        extra={
            "foundry_local": {
                "endpoint": endpoint,
                "tasks": sorted(tasks),
                "publishers": publishers,
                "variants": [_variant_summary(record) for record in records],
            }
        },
    )


def fetch_foundry_local(
    endpoint: str,
    *,
    timeout: float = 5.0,
    registry: Registry | None = None,
) -> int:
    """Fetch and register the machine-local Foundry Local catalog.

    ``endpoint`` is the dynamic Foundry Local service endpoint, for example
    ``http://localhost:5272``. ``.../v1`` is also accepted and normalized to
    the service root before requesting ``/foundry/list``.

    This function is the only Foundry Local network boundary in llmcapa. It
    requires an explicit caller action, accepts loopback hosts only, applies a
    bounded timeout and response size, and never persists machine-local catalog
    records to the bundled model database.
    """
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ValueError("timeout must be a positive number")
    base = _normalize_endpoint(endpoint)
    request = urllib.request.Request(
        f"{base}/foundry/list",
        headers={"Accept": "application/json", "User-Agent": "llmcapa"},
    )
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            raw = response.read(_MAX_CATALOG_BYTES + 1)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch Foundry Local catalog: {exc}") from exc
    if len(raw) > _MAX_CATALOG_BYTES:
        raise RuntimeError("Foundry Local catalog exceeds size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Foundry Local returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise TypeError("Foundry Local catalog must contain a models list")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in payload["models"]:
        if not isinstance(record, dict):
            continue
        alias = str(record.get("alias") or "").strip()
        name = str(record.get("name") or "").strip()
        model_id = alias or name
        if model_id:
            grouped[model_id].append(record)

    target = registry or default_registry()
    target._ensure_loaded()
    count = 0
    for model_id in sorted(grouped, key=str.lower):
        capability = _build_capability(model_id, grouped[model_id], base)
        target._register_refreshed_catalog_record(capability)
        count += 1
    return count
