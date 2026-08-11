"""Refresh bundled Ollama catalog with the official public tags endpoint.

The endpoint exposes currently featured/current tags rather than the complete
library; existing catalog entries are therefore preserved and live records are
merged in. This avoids deleting historical Ollama models.
"""
from __future__ import annotations
import json, shutil, ssl, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "ollama.json"
INSTALLED = Path(r"F:/Python314/Lib/site-packages/llmcapa/data/ollama.json")
URL = "https://ollama.com/api/tags"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": "llmcapa-updater/1.0"})
    with urllib.request.urlopen(req, timeout=60, context=ssl._create_unverified_context()) as r:
        data = json.load(r)
    return data.get("models", [])


def entry(raw: dict, old: dict | None) -> dict:
    name = raw.get("name") or raw.get("model") or ""
    d = dict(old or {
        "provider": "ollama", "model_id": name, "display_name": name,
        "context_window": 4096, "max_output_tokens": 2048,
        "input_modalities": ["text"], "output_modalities": ["text"],
        "supports_function_calling": False, "supports_json_mode": False,
        "supports_streaming": True, "supports_vision": False,
        "supports_reasoning": False, "supports_chat_completion": True,
        "supports_fim": False, "license_type": "open",
        "aliases": [name.lower()], "deprecated": False,
    })
    d["provider"] = "ollama"
    d["model_id"] = name
    d["display_name"] = d.get("display_name") or name
    details = raw.get("details") or {}
    extra = dict(d.get("extra") or {})
    extra.update({"source": URL, "last_seen": raw.get("modified_at"),
                  "size_bytes": raw.get("size"), "digest": raw.get("digest"),
                  "parameter_size": details.get("parameter_size"),
                  "quantization_level": details.get("quantization_level")})
    d["extra"] = extra
    return d


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    models = {m.get("model_id", "").lower(): m for m in data.get("models", [])}
    live = fetch()
    for raw in live:
        name = (raw.get("name") or raw.get("model") or "").lower()
        if name:
            models[name] = entry(raw, models.get(name))
    result = {"models": sorted(models.values(), key=lambda m: m.get("model_id", "").lower())}
    DATA.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if INSTALLED.parent.exists():
        shutil.copy2(DATA, INSTALLED)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log = ROOT / "provider_update_log.md"
    log.write_text(log.read_text(encoding="utf-8") +
        f"\n## Ollama refresh ({stamp})\n\n"
        f"- Source: {URL}\n- Live tags merged: {len(live)}\n"
        f"- Historical bundled entries preserved: {len(result['models'])}\n",
        encoding="utf-8")
    print(f"ollama.json: {len(result['models'])} models; merged live tags={len(live)}")


if __name__ == "__main__":
    main()
