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
    "ai21": "provider_updates/ai21.py",
    "aion-labs": "_update_aion_labs.py",
    "amazon": "_update_amazon.py",
    "anthropic": "_update_anthropic.py",
    "anthracite-org": "_update_hf_official_orgs.py",
    "allenai": "_update_hf_official_orgs.py",
    "arcee-ai": "_update_hf_official_orgs.py",
    "baseten": "_update_baseten.py",
    "azure-foundry": "_update_azure_foundry.py",
    "baidu": "_update_baidu.py",
    "bytedance": "_update_bytedance.py",
    "bytedance-seed": "provider_updates/bytedance-seed.py",
    "cohere": "_update_cohere.py",
    "cloudflare-workers-ai": "_update_cloudflare_workers_ai.py",
    "cognitivecomputations": "_update_hf_official_orgs.py",
    "cerebras": "_update_cerebras.py",
    "deepcogito": "_update_hf_official_orgs.py",
    "deepseek": "_update_deepseek.py",
    "deepinfra": "_update_deepinfra.py",
    "fireworks": "provider_updates/fireworks.py",
    "foundry-local": "_update_foundry_local.py",
    "google": "_update_google.py",
    "groq": "provider_updates/groq.py",
    "gryphe": "_update_hf_official_orgs.py",
    "huggingface": "_scrape_huggingface.py",
    "inclusionai": "_update_hf_official_orgs.py",
    "ibm-granite": "_update_ibm_granite.py",
    "inception": "_update_inception.py",
    "japanese": "_update_japanese.py",
    "laya": "_update_laya.py",
    "kwaipilot": "_update_hf_official_orgs.py",
    "llama-cpp": "provider_updates/llama_cpp.py",
    "lmstudio": "provider_updates/lmstudio.py",
    "liquid": "_update_liquid.py",
    "mancer": "_update_hf_official_orgs.py",
    "meta": "_update_meta.py",
    "meituan": "_update_hf_official_orgs.py",
    "modellix": "_update_modellix.py",
    "modellix_media": "_update_modellix_media.py",
    "microsoft": "_update_microsoft.py",
    "minimax": "_update_minimax.py",
    "mistral": "_update_mistral.py",
    "morph": "provider_updates/morph.py",
    "moonshot": "_update_moonshot.py",
    "mdx-maas": "_update_mdx_maas.py",
    "nebius": "_update_nebius.py",
    "novita": "_update_novita_from_api.py",
    "nex-agi": "_update_hf_official_orgs.py",
    "nousresearch": "_update_hf_official_orgs.py",
    "nvidia": "_update_nvidia.py",
    "ollama": "_update_ollama.py",
    "openai": "_update_openai.py",
    "openrouter": "_update_openrouter.py",
    "perceptron": "_update_hf_official_orgs.py",
    "perplexity": "provider_updates/perplexity.py",
    "perplexity-router": "_update_perplexity_router.py",
    "poolside": "provider_updates/poolside.py",
    "qwen": "_update_qwen.py",
    "relace": "provider_updates/relace.py",
    "rekaai": "_update_rekaai.py",
    "sao10k": "_update_hf_official_orgs.py",
    "sakana": "provider_updates/sakana.py",
    "sarashina": "_update_sarashina.py",
    "sakura": "_update_sakura.py",
    "sambanova": "provider_updates/sambanova.py",
    "siliconflow": "provider_updates/siliconflow.py",
    "stepfun": "_update_stepfun.py",
    "tencent": "_update_tencent.py",
    "thaillm": "_update_thaillm.py",
    "thedrummer": "_update_hf_official_orgs.py",
    "thinkingmachines": "provider_updates/thinkingmachines.py",
    "together": "_update_together.py",
    "typesafe": "_update_typesafe.py",
    "upstage": "_update_upstage.py",
    "vercel": "_update_vercel.py",
    "vertex-ai": "_update_vertex_ai.py",
    "xai": "_update_xai.py",
    "xiaomi": "_update_xiaomi.py",
    "undi95": "_update_hf_official_orgs.py",
    "writer": "provider_updates/writer.py",
    "z-ai": "provider_updates/z-ai.py",
}

# The HF organization updater handles several small provider catalogs. Pass a
# single organization so a provider-scoped dispatch never refreshes its peers.
PROVIDER_ARGS = {
    name: ["--provider", name]
    for name in (
        "allenai",
        "arcee-ai",
        "anthracite-org",
        "cognitivecomputations",
        "deepcogito",
        "gryphe",
        "inclusionai",
        "kwaipilot",
        "mancer",
        "meituan",
        "nex-agi",
        "nousresearch",
        "perceptron",
        "sao10k",
        "thedrummer",
        "undi95",
    )
}
PROVIDER_ARGS["huggingface"] = ["--save"]
ALIASES = {
    "ibm": "ibm-granite",
    "azure": "azure-foundry",
    "azure_foundry": "azure-foundry",
    "foundry_local": "foundry-local",
    "llama_cpp": "llama-cpp",
    "kimi": "moonshot",
    "mdx": "mdx-maas",
    "mdxmaas": "mdx-maas",
    "cloudflare": "cloudflare-workers-ai",
    "workers-ai": "cloudflare-workers-ai",
}

# These catalogs currently have no provider-specific refresh implementation.
# Keep them visible rather than substituting OpenRouter or another provider's
# catalog data.
UNSUPPORTED_CATALOGS: dict[str, str] = {
    "vllm": "the available model list is instance-specific; no canonical catalog to refresh",
}

CATALOG_NAME_ALIASES = {
    "azure_foundry": "azure-foundry",
    "foundry_local": "foundry-local",
    "llama_cpp": "llama-cpp",
}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="one provider key; required unless --list")
    parser.add_argument("--list", action="store_true", help="list provider keys")
    args = parser.parse_args()

    if args.list:
        for name in sorted(PROVIDER_SCRIPTS):
            suffix = " " + " ".join(PROVIDER_ARGS[name]) if name in PROVIDER_ARGS else ""
            print(f"{name}: {PROVIDER_SCRIPTS[name]}{suffix}")
        for name, reason in sorted(UNSUPPORTED_CATALOGS.items()):
            print(f"{name}: no updater ({reason})")
        return 0

    if not args.provider:
        parser.error("--provider is required; use --list to see available providers")

    requested_provider = args.provider.strip().lower()
    requested_provider = CATALOG_NAME_ALIASES.get(requested_provider, requested_provider)
    provider = ALIASES.get(requested_provider, requested_provider)
    script_name = PROVIDER_SCRIPTS.get(provider)
    if script_name is None:
        parser.error(f"unknown provider {args.provider!r}; use --list")

    script = SCRIPTS / script_name
    if not script.exists():
        parser.error(f"provider script not found: {script}")

    print(f"Running provider updater: {provider} ({script_name})", flush=True)
    # No shared catalog rewrite/postprocessor: this process only invokes the
    # chosen provider's own update script.
    command = [sys.executable, str(script), *PROVIDER_ARGS.get(provider, [])]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
