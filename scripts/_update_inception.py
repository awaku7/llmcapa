"""Refresh the Inception catalog from Inception's official API and docs.

Sources:
- https://api.inceptionlabs.ai/v1/models
- https://docs.inceptionlabs.ai/get-started/models

The models endpoint exposes chat models.  Mercury Edit 2 is documented on the
official models page but is not returned by the chat-model endpoint, so it is
kept as a documented FIM/edit record with its own endpoint metadata.
"""

from __future__ import annotations

import argparse
import json
import shutil
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "inception.json"
LOG = ROOT / "provider_update_log.md"
API_SOURCE = "https://api.inceptionlabs.ai/v1/models"
MODELS_SOURCE = "https://docs.inceptionlabs.ai/get-started/models"
STRUCTURED_OUTPUT_SOURCE = (
    "https://docs.inceptionlabs.ai/capabilities/structured-outputs"
)


def _fetch(url: str, *, json_response: bool = False) -> object:
    """Fetch an official Inception resource, tolerating the local CA issue."""
    request = Request(url, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read(1_000_000)
    except URLError:
        # Some Windows Python installations in the development environment do
        # not trust the certificate chain used by the docs host.  These are
        # public, read-only catalog endpoints; keep the updater usable there.
        with urlopen(
            request, context=ssl._create_unverified_context(), timeout=60
        ) as response:
            raw = response.read(1_000_000)
    text = raw.decode("utf-8", "ignore")
    return json.loads(text) if json_response else text


def _per_million(value: object) -> float:
    return round(float(value) * 1_000_000, 6)


def _pricing(api_pricing: dict[str, object]) -> dict[str, object]:
    pricing: dict[str, object] = {
        "input_per_1m": _per_million(api_pricing["prompt"]),
        "output_per_1m": _per_million(api_pricing["completion"]),
        "currency": "USD",
    }
    if api_pricing.get("input_cache_reads") is not None:
        pricing["cached_input_per_1m"] = _per_million(
            api_pricing["input_cache_reads"]
        )
    return pricing


def _chat_entry(record: dict[str, object], today: str) -> dict[str, object]:
    model_id = str(record["id"])
    features = {str(x) for x in (record.get("supported_features") or [])}
    input_modalities = list(record.get("input_modalities") or ["text"])
    output_modalities = list(record.get("output_modalities") or ["text"])
    reasoning = model_id in {"mercury-2", "mercury-2.5"}
    extra: dict[str, object] = {
        "official_source": MODELS_SOURCE,
        "official_api_source": API_SOURCE,
        "official_source_checked_at": today,
        "official_spec_refresh": "parsed_official_api",
        "structured_output_source": STRUCTURED_OUTPUT_SOURCE,
        "structured_output_checked_at": today,
        "structured_output_api_documented": "structured_outputs" in features,
        "supported_features": sorted(features),
        "supported_endpoints": ["v1/chat/completions"],
    }
    if model_id == "mercury-2.5":
        # The models page currently shows a temporary 80% discount.  The API
        # values above are the currently effective prices; retain the list
        # prices so consumers can distinguish the promotion from the baseline.
        extra["list_pricing"] = {
            "input_per_1m": 0.20,
            "cached_input_per_1m": 0.02,
            "output_per_1m": 0.75,
            "currency": "USD",
        }
        extra["pricing_status"] = "promotional"
    return {
        "provider": "inception",
        "model_id": model_id,
        "display_name": str(record.get("name") or model_id),
        "context_window": int(record.get("context_length") or 0),
        "max_output_tokens": int(record.get("max_output_length") or 0),
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_function_calling": "tools" in features
        or "tool_calling" in features,
        "supports_json_mode": "json_mode" in features
        or "structured_outputs" in features,
        "supports_json_schema": "structured_outputs" in features,
        "supports_streaming": True,
        "supports_vision": "image" in input_modalities,
        "supports_reasoning": reasoning,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": reasoning,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "Other",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "unknown",
        "pricing": _pricing(record.get("pricing") or {}),
        "reasoning_effort_values": ["low", "medium", "high"] if reasoning else None,
        "extra": extra,
    }


def _edit_entry(today: str) -> dict[str, object]:
    return {
        "provider": "inception",
        "model_id": "mercury-edit-2",
        "display_name": "Inception: Mercury Edit 2",
        "context_window": 32768,
        "max_output_tokens": 8192,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_json_schema": False,
        "supports_streaming": False,
        "supports_vision": False,
        "supports_reasoning": False,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": True,
        "tokenizer_name": "Other",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "unknown",
        "pricing": {
            "input_per_1m": 0.25,
            "cached_input_per_1m": 0.025,
            "output_per_1m": 0.75,
            "currency": "USD",
        },
        "extra": {
            "official_source": MODELS_SOURCE,
            "official_source_checked_at": today,
            "official_spec_refresh": "documented_official_page",
            "supported_endpoints": [
                "v1/fim/completions",
                "v1/edit/completions",
            ],
            "context_windows": {"fim": 32768, "next_edit": 32768},
        },
    }


def update_catalog(*, dry_run: bool = False) -> dict[str, int]:
    today = datetime.now(timezone.utc).date().isoformat()
    docs = str(_fetch(MODELS_SOURCE))
    for required in ("Mercury 2.5", "Mercury 2", "Mercury Edit 2"):
        if required.lower() not in docs.lower():
            raise RuntimeError(f"official models page missing {required}")

    payload = _fetch(API_SOURCE, json_response=True)
    records = payload.get("data", []) if isinstance(payload, dict) else []
    if not records:
        raise RuntimeError("Inception models API returned no models")

    old = json.loads(DATA.read_text(encoding="utf-8"))
    old_by_id = {str(row.get("model_id")): row for row in old.get("models", [])}
    rows = [_chat_entry(record, today) for record in records if record.get("id")]
    rows.append(_edit_entry(today))
    official_ids = {str(row["model_id"]) for row in rows}

    # Retain previously known records as deprecated rather than silently
    # deleting them if Inception removes a model from the public endpoint.
    for model_id, previous in old_by_id.items():
        if model_id not in official_ids:
            previous = dict(previous)
            previous["deprecated"] = True
            previous.setdefault("extra", {})["official_spec_refresh"] = (
                "not_returned_by_official_api"
            )
            rows.append(previous)

    rows.sort(key=lambda row: str(row["model_id"]).lower())
    summary = {
        "previous": len(old.get("models", [])),
        "updated": len([r for r in rows if r["model_id"] in old_by_id]),
        "added": len([r for r in rows if r["model_id"] not in old_by_id]),
        "total": len(rows),
    }
    if dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary

    backup = DATA.with_suffix(DATA.suffix + ".org")
    if not backup.exists():
        shutil.copy2(DATA, backup)
    DATA.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log_entry = (
        f"\n## Inception official refresh ({today})\n\n"
        f"- Sources: {API_SOURCE}; {MODELS_SOURCE}\n"
        f"- Updated {summary['updated']} existing records and added "
        f"{summary['added']} records ({summary['total']} total).\n"
        "- Mercury 2.5 pricing uses the current API promotional rates; list "
        "prices are retained in `extra.list_pricing`.\n"
        "- OpenRouter was not used.\n"
    )
    LOG.write_text(LOG.read_text(encoding="utf-8") + log_entry, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    update_catalog(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
