"""Refresh the mdx.MaaS model catalog from its official public model sheet.

The updater uses the published CSV export of the model list. Capability fields
are populated only when the sheet or the official Chat Completions API docs
provide evidence; unpublished context/output limits and prices remain unset.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "llmcapa" / "data" / "mdx-maas.json"
MODEL_LIST_SOURCE = (
    "https://docs.google.com/spreadsheets/d/"
    "18eMqI3kPDjVVBLRdyHSuinkJ-6ZVQ-Uh-8BWXHNBO0g/export?format=csv&gid=0"
)
MODEL_LIST_PAGE = (
    "https://docs.google.com/spreadsheets/d/"
    "18eMqI3kPDjVVBLRdyHSuinkJ-6ZVQ-Uh-8BWXHNBO0g/edit?gid=0#gid=0"
)
SERVICE_SOURCE = "https://maas.mdx1.jp/"
API_SOURCE = (
    "https://github.com/mdx-jp/mdx-maas-docs/blob/main/"
    "chat_completions_api_document.md"
)
API_BASE_URL = "https://api.maas.mdx1.jp/v1"


def _available(value: str) -> bool:
    return value.strip().lower() in {"〇", "○", "◯", "yes", "true", "available"}


def _fetch_model_rows() -> list[dict[str, str]]:
    request = Request(
        MODEL_LIST_SOURCE,
        headers={"User-Agent": "llmcapa-mdx-maas-catalog-updater/1.0"},
    )
    with urlopen(request, timeout=60) as response:
        text = response.read(2_000_000).decode("utf-8-sig")

    rows = list(csv.reader(io.StringIO(text)))
    header_index = next((i for i, row in enumerate(rows) if "モデル名" in row), None)
    if header_index is None:
        raise ValueError("The official mdx.MaaS model sheet has no モデル名 header")

    header = rows[header_index]
    indexes = {name: header.index(name) for name in header if name}
    required = {"モデル名", "説明", "即時応答API", "Batch API"}
    missing = required - indexes.keys()
    if missing:
        raise ValueError(
            f"The official model sheet is missing columns: {sorted(missing)}"
        )

    result: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        if len(row) <= indexes["モデル名"]:
            continue
        model_id = row[indexes["モデル名"]].strip()
        if not model_id:
            continue
        result.append(
            {
                "model_id": model_id,
                "description": (
                    row[indexes["説明"]].strip() if len(row) > indexes["説明"] else ""
                ),
                "immediate": (
                    row[indexes["即時応答API"]].strip()
                    if len(row) > indexes["即時応答API"]
                    else ""
                ),
                "batch": (
                    row[indexes["Batch API"]].strip()
                    if len(row) > indexes["Batch API"]
                    else ""
                ),
                "cold_start": (
                    row[indexes["起動待ち時間あり※"]].strip()
                    if "起動待ち時間あり※" in indexes
                    and len(row) > indexes["起動待ち時間あり※"]
                    else ""
                ),
            }
        )
    return result


def _record(row: dict[str, str], checked_at: str) -> dict[str, object]:
    model_id = row["model_id"]
    description = row["description"]
    immediate = _available(row["immediate"])
    batch = _available(row["batch"])
    description_lower = description.lower()

    input_modalities = ["text"]
    if "画像" in description or "image" in description_lower:
        input_modalities.append("image")
    if "動画" in description or "video" in description_lower:
        input_modalities.append("video")

    reasoning = any(
        marker in description_lower for marker in ("推論", "thinking", "reasoning")
    )
    function_calling = any(
        marker in description_lower
        for marker in ("ツール呼び出し", "tool calling", "function calling")
    )
    context_window = (
        128000
        if re.search(r"(?<![a-z0-9])128\s*k(?![a-z0-9])", description_lower)
        else 0
    )

    api_availability: dict[str, object] = {
        "immediate": immediate,
        "batch": batch,
    }
    if row["cold_start"] in {"あり", "有", "yes", "true"}:
        api_availability["may_require_cold_start"] = True

    extra: dict[str, object] = {
        "official_source": SERVICE_SOURCE,
        "official_model_list_source": MODEL_LIST_PAGE,
        "official_api_source": API_SOURCE,
        "official_catalog_checked_at": checked_at,
        "protocol": "openai-compatible",
        "api_base_url": API_BASE_URL,
        "supported_endpoints": ["/v1/chat/completions"],
        "api_availability": api_availability,
        "description": description,
    }
    if context_window:
        extra["context_window_basis"] = "mdx-MaaS official model list"
    else:
        extra["context_window_note"] = (
            "The mdx-MaaS model list does not publish a deployment-specific limit."
        )

    return {
        "provider": "mdx-maas",
        "model_id": model_id,
        "display_name": model_id,
        "context_window": context_window,
        "max_output_tokens": 0,
        "input_modalities": input_modalities,
        "output_modalities": ["text"],
        "supports_function_calling": function_calling,
        "supports_json_mode": None,
        "supports_streaming": immediate,
        "supports_vision": "image" in input_modalities,
        "supports_reasoning": reasoning,
        "supports_chat_completion": immediate,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
        "pricing": None,
        "extra": extra,
    }


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    rows = _fetch_model_rows()
    models = [
        _record(row, checked_at)
        for row in rows
        if _available(row["immediate"]) or _available(row["batch"])
    ]
    payload = {"models": models}
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(models)} mdx.MaaS model records to {OUTPUT}")


if __name__ == "__main__":
    main()
