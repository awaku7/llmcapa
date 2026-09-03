"""Shared mechanics for provider-scoped OpenRouter catalog updates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _normalize_provider_ids(
    entries: list[dict], openrouter_provider: str
) -> list[dict]:
    """Remove only an aggregator route prefix from discovered native IDs.

    A slash inside a native model ID is meaningful (for example,
    ``baichuan/baichuan-m2-32b`` on Novita) and must be preserved.  Only a
    first path component equal to the provider/route name is removable.
    """
    accepted = {str(openrouter_provider).casefold()}
    for entry in entries:
        provider = str(entry.get("provider") or "").casefold()
        model_id = str(entry.get("model_id") or "")
        if "/" not in model_id:
            continue
        prefix, bare = model_id.split("/", 1)
        if prefix.casefold() not in accepted and prefix.casefold() != provider:
            continue
        if not bare:
            continue
        entry["model_id"] = bare
        # Keep the native identifier canonical; route-qualified IDs belong to
        # the aggregator catalog, not to the native provider catalog.
    return entries


def _deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Merge duplicate discovered IDs without losing aliases or metadata."""
    merged: dict[str, dict] = {}
    for entry in entries:
        model_id = str(entry.get("model_id") or "")
        if model_id not in merged:
            merged[model_id] = entry
            continue
        current = merged[model_id]
        aliases = list(current.get("aliases") or [])
        for alias in entry.get("aliases") or []:
            if alias not in aliases:
                aliases.append(alias)
        current["aliases"] = aliases
        for key, value in entry.items():
            if key not in current or current[key] in (None, "", [], {}):
                current[key] = value
    return list(merged.values())


def update_provider(openrouter_provider: str, output_file: str) -> int:
    """Refresh one provider file from OpenRouter, preserving deprecated records."""
    import llmcapa

    llmcapa.fetch_openrouter(cache_ttl=0)
    models = [m for m in llmcapa.list_models(provider=openrouter_provider)]
    path = DATA / output_file
    old = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"models": []}
    )
    entries = _normalize_provider_ids(
        [m.to_dict() for m in models], openrouter_provider
    )
    entries = _deduplicate_entries(entries)
    current = {m.get("model_id") for m in entries}
    entries.extend(
        m
        for m in old.get("models", [])
        if m.get("deprecated") and m.get("model_id") not in current
    )
    entries.sort(key=lambda m: m.get("model_id", ""))
    path.write_text(
        json.dumps({"models": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{output_file}: {len(entries)} models from OpenRouter provider={openrouter_provider}"
    )
    return 0
