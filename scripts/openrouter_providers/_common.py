"""Shared mechanics for provider-scoped OpenRouter catalog updates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def update_provider(openrouter_provider: str, output_file: str) -> int:
    """Refresh one provider file from OpenRouter, preserving deprecated records."""
    import llmcapa

    llmcapa.fetch_openrouter(cache_ttl=0)
    models = [m for m in llmcapa.list_models(provider=openrouter_provider)]
    path = DATA / output_file
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"models": []}
    entries = [m.to_dict() for m in models]
    current = {m.get("model_id") for m in entries}
    entries.extend(
        m for m in old.get("models", [])
        if m.get("deprecated") and m.get("model_id") not in current
    )
    entries.sort(key=lambda m: m.get("model_id", ""))
    path.write_text(json.dumps({"models": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{output_file}: {len(entries)} models from OpenRouter provider={openrouter_provider}")
    return 0
