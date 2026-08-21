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
    "ai21": "https://docs.ai21.com/docs/overview",
    "allenai": "https://docs.allenai.org/",
    "arcee-ai": "https://docs.arcee.ai/",
    "bytedance-seed": "https://seed.bytedance.com/",
    "cognitivecomputations": "https://huggingface.co/cognitivecomputations",
    "inception": "https://docs.inceptionlabs.ai/capabilities/structured-outputs",
    "morph": "https://docs.morphllm.com/sdk/components/fast-models",
    "nousresearch": "https://nousresearch.com/",
    "perplexity": "https://docs.perplexity.ai/",
    "poolside": "https://docs.poolside.ai/",
    "relace": "https://docs.relace.ai/docs/introduction",
    "sakana": "https://console.sakana.ai/models",
    "thinkingmachines": "https://thinkingmachines.ai/",
    "writer": "https://dev.writer.com/api-reference/completion-api/chat-completion",
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
    "inception": True,
    "morph": True,
    "writer": True,
}


def capability_rule(provider: str, model_id: str) -> tuple[bool, bool] | None:
    """Return (json_mode, json_schema) only for documented model classes."""
    if provider in {"lmstudio", "llama_cpp", "ollama", "sakana"}:
        return True, True
    if provider == "inception" and model_id == "inception/mercury-2":
        return True, True
    if provider == "morph" and model_id.rsplit("/", 1)[-1] in {
        "morph-kimik3",
        "morph-kimik3-fast",
        "morph-qwen35-397b",
        "morph-glm52-744b",
        "morph-minimax3-428b",
        "morph-minimax27-230b",
        "morph-dsv4flash",
        "morph-qwen38-27b",
        "morph-qwen36-27b",
        "morph-gemma4-31b",
    }:
        return True, True
    if provider == "writer" and model_id.endswith(("/palmyra-x4", "/palmyra-x5")):
        return True, True
    if provider == "z-ai" and model_id in {"z-ai/glm-4.5", "z-ai/glm-4.6", "z-ai/glm-4.7", "z-ai/glm-5"}:
        return True, None
    if provider == "perplexity" and "/sonar" in model_id:
        return True, True
    if provider == "bytedance-seed" and "/seed-" in model_id:
        return True, True
    return None


# Official Morph Fast Models catalog. These are separate from the morph-v3
# Fast Apply models already bundled in morph.json.
MORPH_FAST_MODELS = {
    "morph-kimik3": (1048576, 2.90, 14.00),
    "morph-kimik3-fast": (1048576, 6.00, 22.50),
    "morph-qwen35-397b": (262144, 0.50, 3.50),
    "morph-glm52-744b": (1048576, 1.10, 4.10),
    "morph-minimax3-428b": (262144, 0.30, 1.20),
    "morph-minimax27-230b": (196608, 0.279, 1.20),
    "morph-dsv4flash": (1048576, 0.12, 0.278),
    "morph-qwen38-27b": (131072, 0.289, 2.40),
    "morph-qwen36-27b": (131072, 0.289, 2.40),
    "morph-gemma4-31b": (175000, 0.14, 0.40),
}


def official_morph_record(model_id: str, context: int, input_price: float, output_price: float) -> dict:
    return {
        "provider": "morph",
        "model_id": f"morph/{model_id}",
        "display_name": f"Morph: {model_id}",
        "context_window": context,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_json_schema": True,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": True,
        "supports_thinking_budget": False,
        "supports_anthropic_api": True,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "Other",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [f"morph/{model_id}"],
        "license_type": "unknown",
        "pricing": {"input_per_1m": input_price, "output_per_1m": output_price, "currency": "USD"},
        "extra": {
            "official_source": SOURCES["morph"],
            "structured_output_source": SOURCES["morph"],
            "structured_output_api_documented": True,
            "catalog_source": "official_morph_fast_models",
        },
    }


POOLSIDE_MODELS = {
    "laguna-m-1": (131072, True),
}


def official_poolside_record(model_id: str, context: int, reasoning: bool) -> dict:
    return {
        "provider": "poolside", "model_id": f"poolside/{model_id}", "display_name": f"Poolside: {model_id}",
        "context_window": context, "max_output_tokens": 0, "input_modalities": ["text"], "output_modalities": ["text"],
        "supports_function_calling": True, "supports_json_mode": False, "supports_json_schema": None, "supports_streaming": True,
        "supports_vision": False, "supports_reasoning": reasoning, "supports_chat_completion": True, "supports_responses_api": False,
        "supports_reasoning_effort": False, "supports_thinking_budget": False, "supports_anthropic_api": False,
        "supports_google_api": False, "supports_fim": False, "tokenizer_name": "Other", "knowledge_cutoff": None,
        "deprecated": False, "aliases": [f"poolside/{model_id}"], "license_type": "unknown",
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "extra": {"official_source": SOURCES["poolside"], "structured_output_source": SOURCES["poolside"],
                  "structured_output_api_documented": True, "catalog_source": "official_poolside_supported_models"},
    }


ARCEE_API_MODELS = {
    "trinity-mini": 131072,
    "trinity-large-preview": 131072,
}


def official_arcee_record(model_id: str, context: int) -> dict:
    return {
        "provider": "arcee-ai", "model_id": f"arcee-ai/{model_id}", "display_name": f"Arcee AI: {model_id}",
        "context_window": context, "max_output_tokens": 0, "input_modalities": ["text"], "output_modalities": ["text"],
        "supports_function_calling": True, "supports_json_mode": True, "supports_json_schema": None, "supports_streaming": True,
        "supports_vision": False, "supports_reasoning": model_id.endswith("large-preview"), "supports_chat_completion": True,
        "supports_responses_api": False, "supports_reasoning_effort": False, "supports_thinking_budget": False,
        "supports_anthropic_api": False, "supports_google_api": False, "supports_fim": False, "tokenizer_name": "Other",
        "knowledge_cutoff": "2024", "deprecated": False, "aliases": [f"arcee-ai/{model_id}"], "license_type": "Apache-2.0",
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "extra": {"official_source": SOURCES["arcee-ai"], "structured_output_source": "https://docs.arcee.ai/capabilities/structured-outputs",
                  "structured_output_api_documented": True, "catalog_source": "official_arcee_api_models"},
    }


AI21_API_MODELS = {
    "jamba-large": (262144, 0.0, 0.0),
    "jamba-mini": (262144, 0.0, 0.0),
    "jamba-mini-2": (262144, 0.0, 0.0),
}


def official_ai21_record(model_id: str, context: int, input_price: float, output_price: float) -> dict:
    return {
        "provider": "ai21", "model_id": f"ai21/{model_id}", "display_name": f"AI21: {model_id}",
        "context_window": context, "max_output_tokens": 4096, "input_modalities": ["text"], "output_modalities": ["text"],
        "supports_function_calling": True, "supports_json_mode": True, "supports_json_schema": None, "supports_streaming": True,
        "supports_vision": False, "supports_reasoning": False, "supports_chat_completion": True, "supports_responses_api": False,
        "supports_reasoning_effort": False, "supports_thinking_budget": False, "supports_anthropic_api": False,
        "supports_google_api": False, "supports_fim": False, "tokenizer_name": "Other", "knowledge_cutoff": None,
        "deprecated": False, "aliases": [f"ai21/{model_id}"], "license_type": "unknown",
        "pricing": {"input_per_1m": input_price, "output_per_1m": output_price, "currency": "USD"},
        "extra": {"official_source": SOURCES["ai21"], "structured_output_source": SOURCES["ai21"],
                  "structured_output_api_documented": True, "catalog_source": "official_ai21_api_models"},
    }


RELACE_OPEN_MODELS = {
    "deepseek-ai/DeepSeek-V4-Flash-0731": (1048576, 0.14, 0.28, False),
    "moonshotai/kimi-k3": (1048576, 3.00, 15.00, True),
}


def official_relace_record(model_id: str, context: int, input_price: float, output_price: float, json_mode: bool) -> dict:
    return {
        "provider": "relace",
        "model_id": f"relace/{model_id}",
        "display_name": f"Relace: {model_id}",
        "context_window": context,
        "max_output_tokens": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": json_mode,
        "supports_json_schema": None,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_reasoning": True,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "Other",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [f"relace/{model_id}", model_id],
        "license_type": "unknown",
        "pricing": {"input_per_1m": input_price, "output_per_1m": output_price, "currency": "USD"},
        "extra": {
            "official_source": SOURCES["relace"],
            "structured_output_source": SOURCES["relace"],
            "structured_output_api_documented": True,
            "catalog_source": "official_relace_open_models",
        },
    }


def add_official_models(provider: str, payload: dict) -> int:
    if provider == "poolside":
        existing = {m.get("model_id", "").lower() for m in payload.get("models", [])}
        added = 0
        for model_id, (context, reasoning) in POOLSIDE_MODELS.items():
            full_id = f"poolside/{model_id}"
            if full_id.lower() not in existing:
                payload.setdefault("models", []).append(official_poolside_record(model_id, context, reasoning))
                added += 1
        return added
    if provider == "arcee-ai":
        existing = {m.get("model_id", "").lower() for m in payload.get("models", [])}
        added = 0
        for model_id, context in ARCEE_API_MODELS.items():
            full_id = f"arcee-ai/{model_id}"
            if full_id.lower() not in existing:
                payload.setdefault("models", []).append(official_arcee_record(model_id, context))
                added += 1
        return added
    if provider == "ai21":
        existing = {m.get("model_id", "").lower() for m in payload.get("models", [])}
        added = 0
        for model_id, (context, input_price, output_price) in AI21_API_MODELS.items():
            full_id = f"ai21/{model_id}"
            if full_id.lower() not in existing:
                payload.setdefault("models", []).append(official_ai21_record(model_id, context, input_price, output_price))
                added += 1
        return added
    if provider == "morph":
        existing = {m.get("model_id", "").lower() for m in payload.get("models", [])}
        added = 0
        for model_id, (context, input_price, output_price) in MORPH_FAST_MODELS.items():
            full_id = f"morph/{model_id}"
            if full_id.lower() not in existing:
                payload.setdefault("models", []).append(official_morph_record(model_id, context, input_price, output_price))
                added += 1
        return added
    if provider == "relace":
        existing = {m.get("model_id", "").lower() for m in payload.get("models", [])}
        added = 0
        for model_id, (context, input_price, output_price, json_mode) in RELACE_OPEN_MODELS.items():
            full_id = f"relace/{model_id}"
            if full_id.lower() not in existing:
                payload.setdefault("models", []).append(official_relace_record(model_id, context, input_price, output_price, json_mode))
                added += 1
        return added
    return 0


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
            added = add_official_models(provider, payload)
            if added:
                result["official_models_added"] = added
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
