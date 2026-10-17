"""Refresh Liquid AI decision-model metadata from Liquid's official docs.

The catalog intentionally covers Liquid's typed-decision models, not every
local LFM language model. The updater discovers that family from the official
model matrix and reads numeric specs only from the linked model pages.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "liquid.json"
LOG = ROOT / "provider_update_log.md"
LIBRARY_URL = "https://docs.liquid.ai/lfm/models/complete-library.md"
DECISION_URL = "https://docs.liquid.ai/lfm/models/decision-models.md"
SOURCE = "https://docs.liquid.ai/lfm/models/decision-models"


def fetch_text(url: str, limit: int = 2_000_000) -> str:
    request = Request(
        url,
        headers={"Accept": "text/markdown,text/plain,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read(limit).decode("utf-8", "replace")


def _clean_markdown(text: str) -> str:
    return text.replace(r"\|", "|")


def parse_decision_models(markdown: str) -> list[dict[str, str]]:
    """Read only model rows under the official Decision Models table."""
    text = _clean_markdown(markdown)
    section_match = re.search(r"(?im)^\s*\|?\s*\*\*Decision Models\*\*", text)
    if not section_match:
        raise ValueError("Liquid model matrix has no Decision Models section")
    section = text[section_match.end() :]
    section = re.split(r"(?im)^\s*#{1,3}\s+|^Looking for an older model", section, maxsplit=1)[0]

    found: list[dict[str, str]] = []
    for line in section.splitlines():
        if "|" not in line or "[" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        name_match = re.match(r"\[([^]]+)\]\(([^)]+)\)", cells[0])
        if not name_match:
            continue
        model_id, docs_path = name_match.groups()
        if not model_id.casefold().startswith("d1"):
            continue
        hf_match = re.search(r"https://huggingface\.co/[^)\s]+", " ".join(cells[2:]))
        found.append(
            {
                "model_id": model_id,
                "model_docs_url": urljoin("https://docs.liquid.ai", docs_path),
                "huggingface_model": hf_match.group(0).rstrip(".,") if hf_match else "",
                "hosted_api": any(
                    re.search(r"\bAPI\b", cell, re.IGNORECASE)
                    for cell in cells[1:3]
                ) and hf_match is None,
            }
        )
    if not found:
        raise ValueError("Liquid Decision Models table had no recognizable rows")
    # Keep source order while removing duplicate links/rows.
    unique: dict[str, dict[str, str]] = {}
    for row in found:
        unique[row["model_id"].casefold()] = row
    return list(unique.values())


def parse_model_specs(markdown: str) -> dict[str, object]:
    """Extract only the explicitly labeled context and parameter specs."""
    result: dict[str, object] = {}
    context = re.search(r"(?im)^\|\s*Context Length\s*\|\s*([^|]+)", markdown)
    if context:
        amount = re.search(r"([\d,.]+)\s*([kKmM]?)", context.group(1))
        if amount:
            value = float(amount.group(1).replace(",", ""))
            suffix = amount.group(2).lower()
            result["context_window"] = int(value * (1_024 if suffix == "k" else 1_048_576 if suffix == "m" else 1))
    parameters = re.search(r"(?im)^\|\s*Parameters\s*\|\s*([\d,.]+)\s*([kKmMbB]?)", markdown)
    if parameters:
        value = float(parameters.group(1).replace(",", ""))
        suffix = parameters.group(2).lower()
        result["parameters"] = int(value * (1_000 if suffix == "k" else 1_000_000 if suffix == "m" else 1_000_000_000 if suffix == "b" else 1))
    audio_duration = re.search(r"(?i)audio[^\n]{0,100}?up to\s*([\d.]+)\s*s", markdown)
    if audio_duration:
        result["audio_max_duration_seconds"] = float(audio_duration.group(1))
    return result


def _inputs(model: dict[str, str], detail: str) -> list[str]:
    text = (model["model_id"] + " " + detail[:5000]).casefold()
    modalities = ["text"]
    if "image" in text:
        modalities.append("image")
    if "audio" in text:
        modalities.append("audio")
    return modalities


def build_entry(model: dict[str, str], detail: str, checked_at: str) -> dict:
    specs = parse_model_specs(detail)
    modalities = _inputs(model, detail)
    is_hosted = bool(model.get("hosted_api"))
    model_id = model["model_id"]
    repo = model.get("huggingface_model") or ""
    return {
        "provider": "liquid",
        "model_id": model_id,
        "display_name": f"Liquid AI {model_id}",
        "context_window": int(specs.get("context_window", 0)),
        "max_output_tokens": 0,
        "input_modalities": modalities,
        "output_modalities": ["decision"],
        "supports_function_calling": False,
        "supports_json_mode": False,
        "supports_json_schema": False,
        "supports_streaming": False,
        "supports_vision": "image" in modalities,
        "supports_reasoning": False,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "license_type": "api" if is_hosted else "open",
        "deprecated": False,
        "aliases": [repo] if repo else [],
        "pricing": None,
        "decision": {
            "decision": True,
            "question_kinds": ["choice", "score", "noul"],
            "answer_fields": ["choice", "score", "noul", "confidence", "probabilities", "legend"],
            "returns_probabilities": True,
            "returns_confidence": True,
            "calibrated_confidence": None,
            "parallel_questions": True,
            "free_form_text": False,
            "type_errors_possible": False,
            "state_shapes": ["string", "json_object"] + [x for x in modalities if x != "text"],
            "max_state_tokens": None,
            "max_total_tokens": int(specs.get("context_window", 0)) or None,
            "output_token_billing": False,
            "language_values": [],
            "endpoints": ["https://api.liquid.ai/decisions/v1/systemone"] if is_hosted else [],
            "source_url": model["model_docs_url"],
            "checked_at": checked_at,
            "status": "documented",
            "extra": {
                "base_url": "https://api.liquid.ai" if is_hosted else None,
                "deployment": "hosted-liquid-api" if is_hosted else "local-open-weights",
                **({"parameters": specs["parameters"]} if "parameters" in specs else {}),
                **({"audio_max_duration_seconds": specs["audio_max_duration_seconds"]} if "audio_max_duration_seconds" in specs else {}),
            },
        },
        "extra": {
            "official_source": model["model_docs_url"],
            "official_source_checked_at": checked_at,
            "docs": SOURCE,
            **({"model_card": repo} if repo else {}),
            "model_family": "d1",
            "not_a_language_model": True,
            **({"parameters": specs["parameters"]} if "parameters" in specs else {}),
        },
    }


def merge_models(discovered: list[dict[str, str]], details: dict[str, str], previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(model.get("model_id", "")).casefold(): model
        for model in previous
        if isinstance(model, dict) and model.get("model_id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for source_model in discovered:
        key = source_model["model_id"].casefold()
        base = build_entry(source_model, details.get(key, ""), checked_at)
        old = old_by_id.get(key)
        if old:
            result = dict(old)
            old_decision = old.get("decision") or {}
            old_exact_context = old_decision.get("max_total_tokens") if isinstance(old_decision, dict) else None
            # Preserve curated capability, aliases, pricing, and provider-specific
            # details; refresh only facts the official source explicitly lists.
            result["display_name"] = old.get("display_name") or base["display_name"]
            result["context_window"] = old_exact_context or old.get("context_window", 0) or base["context_window"]
            result["input_modalities"] = base["input_modalities"]
            result["output_modalities"] = base["output_modalities"]
            result["supports_vision"] = base["supports_vision"]
            result["license_type"] = base["license_type"]
            result_extra = dict(old.get("extra") or {})
            result_extra.update(base["extra"])
            result_extra["catalog_listed"] = True
            result["extra"] = result_extra
            decision = dict(old.get("decision") or {})
            decision["source_url"] = source_model["model_docs_url"]
            decision["checked_at"] = checked_at
            decision["endpoints"] = base["decision"]["endpoints"]
            decision_extra = dict(decision.get("extra") or {})
            decision_extra.update(base["decision"]["extra"])
            decision["extra"] = decision_extra
            result["decision"] = decision
        else:
            result = base
            result["extra"]["catalog_listed"] = True
        merged.append(result)
        seen.add(key)

    # Keep previously curated/historical models not present in this pass. The
    # docs page is a discovery source, not grounds to delete old model records.
    for model in previous:
        if not isinstance(model, dict):
            continue
        key = str(model.get("model_id", "")).casefold()
        if key and key not in seen:
            merged.append(model)
    return merged


def update_catalog(discovered: list[dict[str, str]], details: dict[str, str], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    previous = data.get("models") or []
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_models(discovered, details, previous, checked_at)
    if not models:
        raise ValueError("refusing to write an empty Liquid catalog")
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    entry = (
        f"\n## Liquid decision-model documentation refresh ({checked_at})\n\n"
        f"- Sources: {LIBRARY_URL}; {DECISION_URL}\n"
        f"- Decision models listed by Liquid: {len(discovered)}\n"
        "- Context lengths/parameter counts were refreshed only from explicitly labeled model-page specifications.\n"
        "- Historical records absent from the current index were retained.\n"
    )
    old_log = LOG.read_text(encoding="utf-8")
    heading = f"## Liquid decision-model documentation refresh ({checked_at})"
    if heading in old_log:
        start = old_log.index(heading)
        end = old_log.find("\n## ", start + len(heading))
        old_log = old_log[:start].rstrip() + "\n" if end < 0 else old_log[:start].rstrip() + "\n" + old_log[end + 1 :]
    LOG.write_text(old_log + entry, encoding="utf-8")
    print(f"liquid.json: {len(discovered)} current decision-model rows; total={len(models)}")
    return len(discovered)


def main() -> None:
    library = fetch_text(LIBRARY_URL)
    decision_page = fetch_text(DECISION_URL)
    discovered = parse_decision_models(library)
    details = {row["model_id"].casefold(): fetch_text(row["model_docs_url"]) for row in discovered}
    # The overview establishes the shared primitives; it is not a source for
    # numeric limits, which are taken from individual model pages only.
    if "Noul" not in decision_page and "Choice" not in decision_page:
        raise ValueError("Liquid decision-model documentation is not recognizable")
    update_catalog(discovered, details)


if __name__ == "__main__":
    main()
