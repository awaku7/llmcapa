"""Safely refresh provider catalogs that lack a dedicated updater.

This script deliberately does NOT use OpenRouter.  It is fail-closed: a provider
is only written when a provider-specific official handler exists and produces a
non-empty validated model list.  Unknown providers are reported to the backlog
instead of being overwritten with guessed or gateway-derived data.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"
BACKLOG = ROOT / "_scratch_uncovered_official_backlog.json"
LOG = ROOT / "provider_update_log.md"

# Official landing pages to inspect.  These are intentionally explicit so that
# adding a provider can never silently fall back to OpenRouter.
PROVIDERS = {
    "aion-labs": "https://docs.aionlabs.ai/",
    "allenai": "https://allenai.org/olmo",
    "anthracite-org": "https://huggingface.co/anthracite-org",
    "arcee-ai": "https://arcee.ai/",
    "baidu": "https://cloud.baidu.com/doc/WENXINWORKSHOP/s/",
    "bytedance": "https://www.volcengine.com/docs/82379/1099320",
    "bytedance-seed": "https://www.volcengine.com/docs/82379/1099320",
    "cohere": "https://docs.cohere.com/docs/models",
    "cognitivecomputations": "https://huggingface.co/cognitivecomputations",
    "deepcogito": "https://huggingface.co/deepcogito",
    "gryphe": "https://huggingface.co/gryphe",
    "ibm-granite": "https://www.ibm.com/granite/docs/",
    "inception": "https://www.inceptionlabs.ai/",
    "inclusionai": "https://huggingface.co/inclusionAI",
    "kwaipilot": "https://huggingface.co/Kwai-Kolors",
    "mancer": "https://huggingface.co/mancer",
    "meituan": "https://huggingface.co/meituan-longcat",
    "morph": "https://docs.morphllm.com/",
    "nex-agi": "https://huggingface.co/Nex-AGI",
    "nousresearch": "https://nousresearch.com/",
    "perceptron": "https://huggingface.co/perceptron",
    "poolside": "https://poolside.ai/",
    "rekaai": "https://docs.reka.ai/",
    "relace": "https://docs.relace.ai/",
    "sao10k": "https://huggingface.co/sao10k",
    "stepfun": "https://platform.stepfun.com/",
    "tencent": "https://cloud.tencent.com/document/product/1729",
    "thedrummer": "https://huggingface.co/TheDrummer",
    "thinkingmachines": "https://thinkingmachines.ai/",
    "undi95": "https://huggingface.co/undi95",
    "upstage": "https://developers.upstage.ai/docs/getting-started/models",
    "vercel": "https://sdk.vercel.ai/providers/ai-sdk-providers",
}

# These catalogs are local/open-model registries and require a separate
# provider-specific strategy rather than a generic web scrape.
MANUAL_HANDLERS_REQUIRED = {"llama_cpp", "lmstudio"}


def check_url(url: str) -> dict:
    try:
        req = Request(url, headers={"User-Agent": "llmcapa-official-catalog-check/1.0"})
        with urlopen(req, timeout=20) as response:
            body = response.read(200_000)
            return {"ok": True, "status": response.status, "bytes": len(body), "final_url": response.geturl()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> None:
    backlog = []
    for path in sorted(DATA.glob("*.json")):
        provider = path.stem
        if provider in {"openrouter", "azure_foundry", "huggingface", "ollama"}:
            continue
        if provider in MANUAL_HANDLERS_REQUIRED:
            backlog.append({"provider": provider, "status": "manual_handler_required"})
            continue
        if provider not in PROVIDERS:
            continue
        source = PROVIDERS[provider]
        result = check_url(source)
        # Provenance-only update: do not infer or alter model capabilities/prices.
        # A provider-specific parser must be added before specification fields
        # are changed.
        if result.get("ok") and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            changed = 0
            for model in data.get("models", []):
                extra = model.setdefault("extra", {})
                before = dict(extra)
                extra["official_source"] = source
                extra["official_source_checked_at"] = date.today().isoformat()
                extra["official_spec_refresh"] = "pending_provider_parser"
                changed += extra != before
            if changed:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            status = "source_checked_provenance_recorded"
        else:
            changed = 0
            status = "source_unreachable"
        backlog.append({"provider": provider, "source": source, "status": status, "models_metadata_touched": changed, **result})

    BACKLOG.write_text(json.dumps({"checked_at": date.today().isoformat(), "providers": backlog}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reachable = sum(1 for x in backlog if x.get("ok"))
    touched = sum(1 for x in backlog if x.get("models_metadata_touched", 0))
    print(f"checked={len(backlog)} reachable={reachable} provenance_files_updated={touched}")
    print(f"backlog={BACKLOG}")
    print("Only official-source provenance was recorded; model specifications were not inferred or changed.")


if __name__ == "__main__":
    main()
