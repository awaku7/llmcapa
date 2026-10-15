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
LEGACY_COMPAT_ALIASES = {"jev-1.13.0": ["jev-1.13"]}


def fetch_models_page() -> str:
    request = Request(
        SOURCE + ".md",
        headers={
            "Accept": "text/markdown,text/plain,*/*",
            "User-Agent": "llmcapa-provider-updater/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        text = response.read(1_000_000).decode("utf-8", "replace")
    if "Current models" not in text or "Context length" not in text:
        raise RuntimeError("TypeSafe official model documentation response was incomplete")
    return text


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _read_aliases(markdown: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    parts = re.split(r"(?im)^##\s+Aliases\s*$", markdown, maxsplit=1)
    if len(parts) != 2:
        return aliases
    for line in parts[1].splitlines():
        cells = _cells(line) if line.strip().startswith("|") else []
        if len(cells) < 2:
            continue
        alias = re.search(r"`([^`]+)`", cells[0])
        target = re.search(r"`([^`]+)`", cells[1])
        if alias and target:
            aliases[alias.group(1)] = target.group(1)
    return aliases


def _parse_context(value: str) -> tuple[int, int]:
    found = re.findall(r"([\d,.]+)\s*([kKmM])(?:\s|\b)", value)
    numbers = [
        int(float(amount.replace(",", "")) * (1_000 if suffix.lower() == "k" else 1_000_000))
        for amount, suffix in found
    ]
    return (numbers[0], numbers[1] if len(numbers) > 1 else 0) if numbers else (0, 0)


def _parse_price(value: str) -> float | None:
    # The official table labels this as per Btok / per Mtok: the second amount
    # is therefore USD per one million input tokens.
    amounts = re.findall(r"\\?\$\s*([\d,.]+)", value)
    if amounts:
        return float(amounts[-1].replace(",", ""))
    match = re.search(
        r"(?i)([\d,.]+)\s*(?:per\s+)?(?:million|m)\s+input\s+tokens?",
        value,
    )
    return float(match.group(1).replace(",", "")) if match else None


def parse_model_snapshots(markdown: str) -> list[dict]:
    """Parse every version in the official Current models table."""
    section_match = re.search(
        r"(?ims)^##\s+Current models\s*\n(.*?)(?=^##\s+|\Z)", markdown
    )
    section = section_match.group(1) if section_match else markdown
    rows = [
        _cells(line)
        for line in section.splitlines()
        if line.strip().startswith("|")
    ]

    # Current docs use a wide table: the header names versions and the Model ID
    # row supplies their IDs in matching columns.
    header_index = next(
        (
            i
            for i, row in enumerate(rows)
            if any(re.search(r"(?i)\bJev\s+[\d.]+", cell) for cell in row)
        ),
        None,
    )
    versions: dict[int, str] = {}
    model_ids: dict[int, str] = {}
    if header_index is not None:
        for column, cell in enumerate(rows[header_index]):
            version = re.search(r"(?i)\bJev\s+([\d.]+)", cell)
            if version:
                versions[column] = version.group(1)
        for row in rows[header_index + 1 :]:
            if row and re.search(r"(?i)^\s*Model\s+ID\s*$", row[0]):
                for column, cell in enumerate(row[1:], start=1):
                    match = re.search(r"`(jev-[^`]+)`", cell)
                    if match:
                        model_ids[column] = match.group(1)
                break

    # Compatibility with the previous two-column docs/test-fixture format.
    if not model_ids:
        for row in rows:
            if len(row) < 2:
                continue
            version = re.search(r"(?i)\bJev\s+([\d.]+)", row[0])
            model = re.search(r"`(jev-[^`]+)`", row[1])
            if version and model:
                versions[1] = version.group(1)
                model_ids[1] = model.group(1)
                break
    if not model_ids:
        raise ValueError("TypeSafe docs did not publish a versioned Jev model row")

    aliases = _read_aliases(markdown)
    price_row = next(
        (row for row in rows if row and re.search(r"(?i)^\s*Price\b", row[0])),
        None,
    )
    context_row = next(
        (
            row
            for row in rows
            if row and re.search(r"(?i)^\s*Context\s+length\b", row[0])
        ),
        None,
    )
    # Older pages placed the same metadata in prose rather than table cells.
    if price_row is None:
        price_row = ["Price", markdown]
    if context_row is None:
        context_row = ["Context length", markdown]

    limits_match = re.search(
        r"(?i)([\d,.]+)\s*([kKmM]?)\s*tokens?\s+per\s+second\s*/\s*"
        r"([\d,]+)\s+requests?\s+per\s+second",
        markdown,
    )
    rate = None
    if limits_match:
        token_rate = float(limits_match.group(1).replace(",", ""))
        suffix = limits_match.group(2).lower()
        rate = {
            "tokens_per_second": int(
                token_rate
                * (1_000 if suffix == "k" else 1_000_000 if suffix == "m" else 1)
            ),
            "requests_per_minute": int(limits_match.group(3).replace(",", "")) * 60,
        }

    snapshots = []
    for column, model_id in sorted(model_ids.items()):
        price_value = price_row[column] if column < len(price_row) else ""
        context_value = context_row[column] if column < len(context_row) else ""
        context, max_state = _parse_context(context_value)
        model_aliases = {
            alias: target for alias, target in aliases.items() if target == model_id
        }
        snapshots.append(
            {
                "model_id": model_id,
                "display_name": f"TypeSafe Jev {versions.get(column, model_id.removeprefix('jev-'))}",
                "context_window": context,
                "max_state_tokens": max_state,
                "input_per_1m": _parse_price(price_value),
                "aliases": sorted(model_aliases),
                "alias_targets": model_aliases,
                "rate_limits": rate,
            }
        )
    return snapshots


def parse_model_snapshot(markdown: str) -> dict:
    """Compatibility helper returning the first/latest version in the docs."""
    return parse_model_snapshots(markdown)[0]


def build_model(snapshot: dict, old: dict | None, checked_at: str) -> dict:
    result = dict(old or {})
    aliases = list(
        dict.fromkeys(
            [
                *snapshot["aliases"],
                *LEGACY_COMPAT_ALIASES.get(snapshot["model_id"], []),
            ]
        )
    )
    result.update(
        {
            "provider": "typesafe",
            "model_id": snapshot["model_id"],
            "display_name": snapshot["display_name"],
            "max_output_tokens": result.get("max_output_tokens", 0),
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
            "max_total_tokens": snapshot["context_window"] or decision.get("max_total_tokens"),
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
    else:
        # The current docs say limits are organization-specific and dynamic.
        decision.pop("rate_limit_tokens_per_second", None)
        decision.pop("rate_limit_requests_per_minute", None)
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


def merge_catalog(snapshot: dict | list[dict], previous: list[dict], checked_at: str) -> list[dict]:
    snapshots = snapshot if isinstance(snapshot, list) else [snapshot]
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    current_ids = {item["model_id"].casefold() for item in snapshots}
    result = [
        build_model(item, old_by_id.get(item["model_id"].casefold()), checked_at)
        for item in snapshots
    ]
    # Keep previously cataloged versions not present in the source as historical
    # records; never discard curated capability data silently.
    result.extend(
        row
        for row in previous
        if isinstance(row, dict)
        and str(row.get("model_id", "")).casefold() not in current_ids
    )
    return result


def update_catalog(snapshot: dict | list[dict], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    snapshots = snapshot if isinstance(snapshot, list) else [snapshot]
    models = merge_catalog(snapshots, data.get("models") or [], checked_at)
    DATA.write_text(
        json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    old_log = LOG.read_text(encoding="utf-8")
    heading = f"## TypeSafe official model refresh ({checked_at})"
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = (
            old_log[:start].rstrip() + "\n"
            if end < 0
            else old_log[:start].rstrip() + "\n" + old_log[end + 1 :]
        )
    version_ids = ", ".join(item["model_id"] for item in snapshots)
    documented_aliases = ", ".join(
        alias for item in snapshots for alias in item["aliases"]
    )
    LOG.write_text(
        old_log
        + f"\n## TypeSafe official model refresh ({checked_at})\n\n"
        + f"- Source: {SOURCE}\n- Documented versions: {version_ids}\n"
        + f"- Documented aliases: {documented_aliases}\n"
        + "- Context and per-input pricing were read from the official docs; no output price was inferred. Rate limits are organization-specific and dynamic.\n",
        encoding="utf-8",
    )
    print(f"typesafe.json: refreshed {len(models)} records; documented={len(snapshots)}")
    return len(models)


def main() -> None:
    update_catalog(parse_model_snapshots(fetch_models_page()))


if __name__ == "__main__":
    main()
