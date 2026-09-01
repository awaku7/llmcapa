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
    "google": "_update_google.py",
    "ibm-granite": "_update_ibm_granite.py",
    "japanese": "_update_japanese.py",
    "meta": "_update_meta.py",
    "microsoft": "_update_microsoft.py",
    "minimax": "_update_minimax.py",
    "mistral": "_update_mistral.py",
    "moonshot": "_update_moonshot.py",
    "novita": "_update_novita_from_api.py",
    "nvidia": "_update_nvidia.py",
    "ollama": "_update_ollama.py",
    "qwen": "_update_qwen.py",
    "rekaai": "_update_rekaai.py",
    "sakura": "_update_sakura.py",
    "stepfun": "_update_stepfun.py",
    "structured-output": "_update_structured_output_providers.py",
    "tencent": "_update_tencent.py",
    "together": "_update_together.py",
    "uncovered-official": "_update_uncovered_official.py",
    "unresolved-catalogs": "_update_unresolved_catalogs.py",
    "upstage": "_update_upstage.py",
    "xai": "_update_xai.py",
    "xiaomi": "_update_xiaomi.py",
}

ALIASES = {
    "ibm": "ibm-granite",
    "hf-official": "uncovered-official",
    "huggingface-official": "uncovered-official",
    "azure": "azure-foundry",
    "kimi": "moonshot",
}


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
    completed = subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
