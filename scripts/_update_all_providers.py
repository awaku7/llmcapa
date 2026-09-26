"""Run one provider updater at a time.

Provider data must not be bulk-replaced from OpenRouter.  The actual update
logic lives in provider-specific scripts; this compatibility entry point only
dispatches to one selected script.

Examples:
    python scripts/_update_all_providers.py --list
    python scripts/_update_all_providers.py --provider anthropic
    python scripts/_update_all_providers.py --provider ibm-granite
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

PROVIDER_SCRIPTS = {
    "aion-labs": "_update_aion_labs.py",
    "amazon": "_update_amazon.py",
    "anthropic": "_update_anthropic.py",
    "azure-foundry": "_update_azure_foundry.py",
    "baidu": "_update_baidu.py",
    "bytedance": "_update_bytedance.py",
    "cohere": "_update_cohere.py",
    "deepseek": "_update_deepseek.py",
    "fireworks": "provider_updates/fireworks.py",
    "google": "_update_google.py",
    "ibm-granite": "_update_ibm_granite.py",
    "inception": "_update_inception.py",
    "japanese": "_update_japanese.py",
    "meta": "_update_meta.py",
    "microsoft": "_update_microsoft.py",
    "minimax": "_update_minimax.py",
    "mistral": "_update_mistral.py",
    "moonshot": "_update_moonshot.py",
    "novita": "_update_novita_from_api.py",
    "nvidia": "_update_nvidia.py",
    "ollama": "_update_ollama.py",
    "openai": "_update_openai.py",
    "qwen": "_update_qwen.py",
    "rekaai": "_update_rekaai.py",
    "sakura": "_update_sakura.py",
    "siliconflow": "provider_updates/siliconflow.py",
    "stepfun": "_update_stepfun.py",
    "tencent": "_update_tencent.py",
    "together": "_update_together.py",
    "upstage": "_update_upstage.py",
    "vercel": "_update_vercel.py",
    "xai": "_update_xai.py",
    "xiaomi": "_update_xiaomi.py",
}

ALIASES = {
    "ibm": "ibm-granite",
    "azure": "azure-foundry",
    "kimi": "moonshot",
}

CAPABILITY_FIELDS = (
    "audio",
    "video",
    "image",
    "document",
    "embedding",
    "rerank",
    "spatial",
)


def _read_catalogs() -> dict[Path, dict]:
    catalogs = {}
    for path in sorted((ROOT / "src" / "llmcapa" / "data").glob("*.json")):
        raw = path.read_bytes()
        catalogs[path] = json.loads(raw.decode("utf-8"))
    return catalogs


def _write_catalog(path: Path, data: dict) -> None:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_bytes(payload.replace("\n", newline).encode("utf-8"))


def _preserve_capabilities(before: dict[Path, dict]) -> int:
    """Restore documented capability blocks omitted by a provider refresh."""
    restored = 0
    for path, old_data in before.items():
        if not path.exists():
            continue
        current = json.loads(path.read_text(encoding="utf-8"))
        old_by_id = {
            (str(model.get("provider", "")), str(model.get("model_id", ""))): model
            for model in old_data.get("models", [])
        }
        changed = False
        for model in current.get("models", []):
            key = (str(model.get("provider", "")), str(model.get("model_id", "")))
            old_model = old_by_id.get(key)
            if old_model is None:
                continue
            for field in CAPABILITY_FIELDS:
                if field not in model and field in old_model:
                    model[field] = old_model[field]
                    restored += 1
                    changed = True
        if changed:
            _write_catalog(path, current)
    return restored


def _run_capability_postprocessors() -> int:
    """Rebuild derived capability metadata after a catalog refresh."""
    commands = [
        ("_audio_capability_postprocess.py", []),
        ("_video_capability_postprocess.py", []),
        ("_structured_capability_postprocess.py", []),
        ("_image_capability_postprocess.py", ["--write"]),
    ]
    for name, args in commands:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / name), *args],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="one provider key; required unless --list")
    parser.add_argument("--list", action="store_true", help="list provider keys")
    args = parser.parse_args()

    if args.list:
        for name in sorted(PROVIDER_SCRIPTS):
            print(f"{name}: {PROVIDER_SCRIPTS[name]}")
        return 0

    if not args.provider:
        parser.error("--provider is required; use --list to see available providers")

    provider = ALIASES.get(args.provider.strip().lower(), args.provider.strip().lower())
    script_name = PROVIDER_SCRIPTS.get(provider)
    if script_name is None:
        parser.error(f"unknown provider {args.provider!r}; use --list")

    script = SCRIPTS / script_name
    if not script.exists():
        parser.error(f"provider script not found: {script}")

    print(f"Running provider updater: {provider} ({script_name})", flush=True)
    before = _read_catalogs()
    completed = subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode

    restored = _preserve_capabilities(before)
    if restored:
        print(f"Preserved capability blocks: {restored}", flush=True)
    return _run_capability_postprocessors()


if __name__ == "__main__":
    raise SystemExit(main())
