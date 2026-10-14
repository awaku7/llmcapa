"""Refresh TypeSafe Jev metadata from TypeSafe's official model docs.

The public account API lists account-enabled names but the docs provide the
versioned model specifications and aliases. This updater reads that public
source and preserves capability details unless the docs explicitly replace
those fields.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "typesafe.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.typesafe.ai/models"
LEGACY_COMPAT_ALIASES = {
    "jev-1.13.0": ["jev-1.13"],
}


def fetch_models_page() -> str:
    request = Request(
        SOURCE + ".md",
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        text = response.read(1_000_000).decode("utf-8", "replace")
    if "Current models" not in text or "Context length" not in text:
        raise RuntimeError("TypeSafe official model documentation response was incomplete")
    return text


def parse_model_snapshot(markdown: str) -> dict:
    versioned = re.search(r"(?im)^\|\s*Jev\s+([^|]+)\|\s*`(jev-[^`]+)`\s*\|", markdown)
    if not versioned:
        raise ValueError("TypeSafe docs did not publish a versioned Jev model row")
    display_version, model_id = versioned.groups()

    aliases: dict[str, str] = {}
    alias_section = re.split(r"(?im)^##\s+Aliases\s*$", markdown, maxsplit=1)
    if len(alias_section) == 2:
        for line in alias_section[1].splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            alias = re.search(r"`([^`]+)`", cells[0])
            target = re.search(r"`([^`]+)`", cells[1])
            if alias and target and target.group(1) == model_id:
                aliases[alias.group(1)] = target.group(1)

    context_match = re.search(r"(?i)Context length\s*\|\s*([\d,.]+)\s*k\b", markdown)
    state_match = re.search(r"(?i)([\d,.]+)\s*k\s+tokens?\s+for\s+`state`", markdown)
    price_match = re.search(r"(?i)\$\s*([\d.]+)\s*(?:per\s+)?(?:million|m)\s+input\s+tokens?", markdown)
    if not price_match:
        price_match = re.search(
            r"(?im)^\|\s*Price[^|]*\|\s*(?:\\?\$)[\d,.]+\s*/\s*(?:\\?\$)([\d,.]+)",
            markdown,
        )
    limits_match = re.search(r"(?i)([\d,.]+)\s*([kKmM]?)\s*tokens?\s+per\s+second\s*/\s*([\d,]+)\s+requests?\s+per\s+second", markdown)
    if not aliases:
        raise ValueError("TypeSafe docs did not expose aliases pointing to the current version")

    context = int(float(context_match.group(1).replace(",", "")) * 1000) if context_match else 0
    max_state = int(float(state_match.group(1).replace(",", "")) * 1000) if state_match else 0
    price = float(price_match.group(1)) if price_match else None
    rate = None
    if limits_match:
        token_rate = float(limits_match.group(1).replace(",", ""))
        token_suffix = limits_match.group(2).lower()
        rate = {
            "tokens_per_second": int(token_rate * (1_000 if token_suffix == "k" else 1_000_000 if token_suffix == "m" else 1)),
            "requests_per_minute": int(limits_match.group(3).replace(",", "")) * 60,
        }
    return {
        "model_id": model_id,
        "display_name": f"TypeSafe Jev {display_version.strip()}",
        "context_window": context,
        "max_state_tokens": max_state,
        "input_per_1m": price,
        "aliases": sorted(aliases),
        "alias_targets": aliases,
        "rate_limits": rate,
    }


def build_model(snapshot: dict, old: dict | None, checked_at: str) -> dict:
    result = dict(old or {})
    old_aliases = old.get("aliases", []) if old else []
    aliases = list(
        dict.fromkeys([*snapshot["aliases"], *old_aliases, *LEGACY_COMPAT_ALIASES.get(snapshot["model_id"], [])])
    )
    result.update(
        {
            "provider": "typesafe",
            "model_id": snapshot["model_id"],
            "display_name": snapshot["display_name"],
            "context_window": snapshot["context_window"] or result.get("context_window", 0),
            "input_modalities": ["text"],
            "output_modalities": ["decision"],
            "supports_function_calling": False,
            "supports_json_mode": True,
            "supports_json_schema": True,
            "supports_streaming": False,
            "supports_vision": False,
            "supports_chat_completion": False,
            "supports_responses_api": False,
            "supports_anthropic_api": False,
            "supports_google_api": False,
            "deprecated": False,
            "aliases": aliases,
        }
    )
    if snapshot["input_per_1m"] is not None:
        result["pricing"] = {
            "input_per_1m": snapshot["input_per_1m"],
            "output_per_1m": 0.0,
            "currency": "USD",
        }
    decision = dict(result.get("decision") or {})
    decision.update(
        {
            "decision": True,
            "question_kinds": ["choice", "score", "noul"],
            "returns_probabilities": True,
            "returns_confidence": True,
            "free_form_text": False,
            "state_shapes": ["string", "json_object", "text_array"],
            "max_state_tokens": snapshot["max_state_tokens"] or decision.get("max_state_tokens"),
            "max_total_tokens": snapshot["context_window"],
            "output_token_billing": False,
            "endpoints": ["https://api.typesafe.ai/v1/systemone"],
            "source_url": SOURCE,
            "checked_at": checked_at,
            "status": "documented",
        }
    )
    if snapshot["rate_limits"]:
        decision.pop("rate_limit_requests_per_second", None)
        decision["rate_limit_tokens_per_second"] = snapshot["rate_limits"]["tokens_per_second"]
        decision["rate_limit_requests_per_minute"] = snapshot["rate_limits"]["requests_per_minute"]
    result["decision"] = decision
    extra = dict(result.get("extra") or {})
    extra.update(
        {
            "official_source": "https://typesafe.ai/",
            "official_source_checked_at": checked_at,
            "model_docs": SOURCE,
            "api_reference": "https://docs.typesafe.ai/api",
            "aliases_resolved": snapshot["alias_targets"],
        }
    )
    result["extra"] = extra
    return result


def merge_catalog(snapshot: dict, previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    current = build_model(snapshot, old_by_id.get(snapshot["model_id"].casefold()), checked_at)
    result = [current]
    result.extend(
        row for row in previous
        if isinstance(row, dict) and str(row.get("model_id", "")).casefold() != snapshot["model_id"].casefold()
    )
    return result


def update_catalog(snapshot: dict, *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_catalog(snapshot, data.get("models") or [], checked_at)
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    old_log = LOG.read_text(encoding="utf-8")
    heading = f"## TypeSafe official model refresh ({checked_at})"
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" if end < 0 else old_log[:start].rstrip() + "\n" + old_log[end + 1 :]
    LOG.write_text(
        old_log
        + f"\n## TypeSafe official model refresh ({checked_at})\n\n"
        + f"- Source: {SOURCE}\n- Current version: {snapshot['model_id']}\n"
        + f"- Documented aliases: {', '.join(snapshot['aliases'])}\n"
        + "- Context, per-input pricing, and rate limits were read from the official docs; no output price was inferred.\n",
        encoding="utf-8",
    )
    print(f"typesafe.json: refreshed {len(models)} records; current={snapshot['model_id']}")
    return len(models)


def main() -> None:
    snapshot = parse_model_snapshot(fetch_models_page())
    update_catalog(snapshot)


if __name__ == "__main__":
    main()
