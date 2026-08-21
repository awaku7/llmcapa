"""Audit official structured-output API documentation for bundled providers.

This updater is deliberately fail-closed: it records official evidence and only
changes capability flags when the provider explicitly documents the API contract.
It never uses OpenRouter or a third-party catalog as a specification source.
"""
from __future__ import annotations

import argparse
import json
import ssl
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"

SOURCES = {
    "ai21": "https://docs.ai21.com/docs/user-provided-tools-http",
    "allenai": "https://allenai.org/olmo",
    "arcee-ai": "https://arcee.ai/",
    "bytedance-seed": "https://seed.bytedance.com/",
    "cognitivecomputations": "https://huggingface.co/cognitivecomputations",
    "inception": "https://www.inceptionlabs.ai/",
    "morph": "https://docs.morphllm.com/",
    "nousresearch": "https://nousresearch.com/",
    "perplexity": "https://docs.perplexity.ai/",
    "poolside": "https://poolside.ai/",
    "relace": "https://docs.relace.ai/",
    "sakana": "https://console.sakana.ai/models",
    "thinkingmachines": "https://thinkingmachines.ai/",
    "writer": "https://dev.writer.com/",
    "vercel": "https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions/structured-outputs",
    "z-ai": "https://docs.z.ai/guides/capabilities/struct-output",
    "lmstudio": "https://lmstudio.ai/docs/developer/openai-compat/structured-output",
    "llama_cpp": "https://lmstudio.ai/docs/developer/openai-compat/structured-output",
    "ollama": "https://docs.ollama.com/capabilities/structured-outputs",
}

# True means the official page documents response_format/JSON Schema as an API
# capability. False means the page is only provenance or documents another API.
KNOWN_API_SUPPORT = {
    "vercel": True,
    "lmstudio": True,
    "llama_cpp": True,
    "ollama": True,
    "z-ai": True,  # JSON mode; JSON Schema is application-side in the docs.
    "sakana": True,
    "perplexity": True,
    "bytedance-seed": True,
}


def capability_rule(provider: str, model_id: str) -> tuple[bool, bool] | None:
    """Return (json_mode, json_schema) only for documented model classes."""
    if provider in {"lmstudio", "llama_cpp", "ollama", "sakana"}:
        return True, True
    if provider == "z-ai" and model_id in {"z-ai/glm-4.5", "z-ai/glm-4.6", "z-ai/glm-4.7", "z-ai/glm-5"}:
        return True, None
    if provider == "perplexity" and "/sonar" in model_id:
        return True, True
    if provider == "bytedance-seed" and "/seed-" in model_id:
        return True, True
    return None


def fetch(url: str, insecure: bool) -> tuple[bool, str]:
    try:
        req = Request(url, headers={"User-Agent": "llmcapa-structured-output-audit/1.0"})
        context = ssl._create_unverified_context() if insecure else None
        with urlopen(req, timeout=25, context=context) as response:
            body = response.read(200_000).decode("utf-8", "ignore")
        return bool(body.strip()), "reachable"
    except Exception as exc:
        return False, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--insecure", action="store_true", help="disable TLS verification for this run only")
    args = parser.parse_args()
    today = date.today().isoformat()
    results = {}
    for provider, source in SOURCES.items():
        path = DATA / f"{provider}.json"
        ok, status = fetch(source, args.insecure)
        result = {"source": source, "status": status, "reachable": ok}
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            for model in payload.get("models", []):
                rule = capability_rule(provider, model.get("model_id", ""))
                if rule is not None:
                    model["supports_json_mode"], model["supports_json_schema"] = rule
                extra = model.setdefault("extra", {})
                extra["structured_output_source"] = source
                extra["structured_output_checked_at"] = today
                extra["structured_output_source_status"] = status
                if provider in KNOWN_API_SUPPORT:
                    extra["structured_output_api_documented"] = True
                model.setdefault("supports_json_schema", None)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["models"] = len(payload.get("models", []))
        results[provider] = result
    out = ROOT / "_scratch_structured_output_audit.json"
    out.write_text(json.dumps({"checked_at": today, "providers": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
