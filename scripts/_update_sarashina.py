"""Refresh the Sarashina API catalog from its official documentation pages."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "llmcapa" / "data" / "sarashina.json"
BASE_URL = "https://api.sarashina.ai/v1"
DOCS = {
    "models": "https://docs.sarashina.ai/models",
    "introduction": "https://docs.sarashina.ai/introduction",
    "chat": "https://docs.sarashina.ai/api-reference/chat-completions",
    "embedding": "https://docs.sarashina.ai/api-reference/embeddings",
    "rerank": "https://docs.sarashina.ai/api-reference/rerank",
    "translate": "https://docs.sarashina.ai/api-reference/translate",
    "rate_limits": "https://docs.sarashina.ai/rate-limits",
}
ENDPOINTS = {
    "chat": f"{BASE_URL}/chat/completions",
    "embedding": f"{BASE_URL}/embeddings",
    "rerank": f"{BASE_URL}/rerank",
    "translate": f"{BASE_URL}/translate",
}

CHAT_MODELS = ("sarashina3-mini", "sarashina3-nano", "sarashina3-guard")
ALL_MODELS = CHAT_MODELS + (
    "sarashina3-embedding",
    "sarashina3-rerank",
    "sarashina3-translate",
)


def _plain_text(source: str) -> str:
    """Convert rendered or server-side HTML to searchable plain text."""
    source = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1>", " ", source)
    return html.unescape(re.sub(r"(?s)<[^>]+>", " ", source)).casefold()


def _fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "llmcapa-sarashina-updater/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            return response.read(5_000_000).decode("utf-8", "replace")
    except URLError as exc:
        raise RuntimeError(f"could not fetch official Sarashina documentation: {url}") from exc


def _require_documentation(pages: dict[str, str]) -> None:
    """Fail closed if a required model or API route is absent from current docs."""
    required = {
        "models": (*ALL_MODELS,),
        "introduction": ("bearer",),
        "chat": (*CHAT_MODELS, ENDPOINTS["chat"]),
        "embedding": ("sarashina3-embedding", ENDPOINTS["embedding"]),
        "rerank": ("sarashina3-rerank", ENDPOINTS["rerank"]),
        "translate": ("sarashina3-translate", ENDPOINTS["translate"]),
        "rate_limits": (*ALL_MODELS,),
    }
    missing = []
    for page_name, terms in required.items():
        content = _plain_text(pages.get(page_name, ""))
        for term in terms:
            alternatives = (term.casefold(), term.casefold().replace("-", " "))
            if not any(alternative in content for alternative in alternatives):
                missing.append(f"{page_name}: {term}")
    if missing:
        raise ValueError(
            "official Sarashina documentation is missing expected catalog details: "
            + "; ".join(missing)
        )


def _endpoint(path: str, protocol: str, source: str) -> dict:
    return {
        "base_url": BASE_URL,
        "path": path,
        "protocol": protocol,
        "auth": "bearer",
        "source": source,
    }


def _base_model(
    model_id: str,
    *,
    display_name: str,
    context_window: int,
    max_output_tokens: int,
    input_modalities: list[str],
    output_modalities: list[str],
    endpoint: dict,
    source_pages: list[str],
    checked_at: str,
    supports_chat_completion: bool = False,
    supports_streaming: bool = False,
    supports_function_calling: bool | None = False,
    supports_json_mode: bool | None = False,
    supports_json_schema: bool | None = False,
    supports_reasoning: bool | None = False,
    rpm: int | None = None,
    extra: dict | None = None,
    embedding: dict | None = None,
    rerank: dict | None = None,
) -> dict:
    model_extra = {
        "service": "Sarashina API",
        "developer": "SB Intuitions",
        "source": DOCS["models"],
        "official_source_checked_at": checked_at,
        "official_sources": list(dict.fromkeys([DOCS["introduction"], *source_pages])),
        "endpoints": [endpoint],
        "pricing_status": "zero_jpy_user_confirmed",
        "pricing_source": "user_confirmation",
        "pricing_note": "The user confirmed that Sarashina API usage costs JPY 0; official docs do not publish a numeric price table.",
    }
    if rpm is not None:
        model_extra["requests_per_minute"] = rpm
    model_extra.update(extra or {})
    model = {
        "provider": "sarashina",
        "model_id": model_id,
        "display_name": display_name,
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_function_calling": supports_function_calling,
        "supports_json_mode": supports_json_mode,
        "supports_json_schema": supports_json_schema,
        "supports_streaming": supports_streaming,
        "supports_vision": False,
        "supports_reasoning": supports_reasoning,
        "supports_chat_completion": supports_chat_completion,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_thinking_level": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "JPY"},
        "extra": model_extra,
    }
    if embedding is not None:
        model["embedding"] = embedding
    if rerank is not None:
        model["rerank"] = rerank
    return model


def catalog_from_docs(pages: dict[str, str], checked_at: str | None = None) -> dict:
    """Build the six-model catalog after checking each official docs page."""
    _require_documentation(pages)
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    chat_source = DOCS["chat"]
    embedding_source = DOCS["embedding"]
    rerank_source = DOCS["rerank"]
    translate_source = DOCS["translate"]
    models = [
        _base_model(
            "sarashina3-mini",
            display_name="Sarashina3 mini",
            context_window=128_000,
            max_output_tokens=8_000,
            input_modalities=["text"],
            output_modalities=["text"],
            endpoint=_endpoint("/chat/completions", "openai-compatible", chat_source),
            source_pages=[DOCS["models"], chat_source, DOCS["rate_limits"]],
            checked_at=checked_at,
            supports_chat_completion=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_json_schema=True,
            supports_reasoning=False,
            rpm=6,
            extra={
                "api_max_completion_tokens": 8_000,
                "supported_response_formats": ["text", "json_object", "json_schema"],
                "compatibility_note": "OpenAI Chat Completions subset; undocumented parameters are rejected.",
            },
        ),
        _base_model(
            "sarashina3-nano",
            display_name="Sarashina3 nano",
            context_window=128_000,
            max_output_tokens=8_000,
            input_modalities=["text"],
            output_modalities=["text"],
            endpoint=_endpoint("/chat/completions", "openai-compatible", chat_source),
            source_pages=[DOCS["models"], chat_source, DOCS["rate_limits"]],
            checked_at=checked_at,
            supports_chat_completion=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_json_schema=True,
            supports_reasoning=False,
            rpm=60,
            extra={
                "api_max_completion_tokens": 8_000,
                "supported_response_formats": ["text", "json_object", "json_schema"],
                "compatibility_note": "OpenAI Chat Completions subset; undocumented parameters are rejected.",
            },
        ),
        _base_model(
            "sarashina3-guard",
            display_name="Sarashina3 guard",
            context_window=64_000,
            max_output_tokens=8_000,
            input_modalities=["text"],
            output_modalities=["text"],
            endpoint=_endpoint("/chat/completions", "openai-compatible", chat_source),
            source_pages=[DOCS["models"], chat_source, DOCS["rate_limits"]],
            checked_at=checked_at,
            supports_chat_completion=True,
            supports_streaming=True,
            supports_function_calling=False,
            supports_json_mode=None,
            supports_json_schema=None,
            supports_reasoning=False,
            rpm=6,
            extra={
                "api_max_completion_tokens": 8_000,
                "model_class": "moderation",
                "moderation_categories": [f"T{i}" for i in range(1, 13)],
                "generates_free_form_text": False,
            },
        ),
        _base_model(
            "sarashina3-embedding",
            display_name="Sarashina3 embedding",
            context_window=8_000,
            max_output_tokens=0,
            input_modalities=["text"],
            output_modalities=["embedding"],
            endpoint=_endpoint("/embeddings", "sarashina-embeddings", embedding_source),
            source_pages=[DOCS["models"], embedding_source, DOCS["rate_limits"]],
            checked_at=checked_at,
            rpm=60,
            extra={
                "max_input_texts_per_request": 1,
                "task_types": [
                    "RETRIEVAL_DOCUMENT",
                    "SEMANTIC_SIMILARITY",
                    "RETRIEVAL_QUERY",
                    "QUESTION_ANSWERING",
                    "FACT_VERIFICATION",
                    "CLASSIFICATION",
                    "CLUSTERING",
                ],
            },
            embedding={
                "embedding": True,
                "dimensions": 1_536,
                "max_input_tokens": 8_000,
                "max_input_items": 1,
                "output_formats": ["float"],
                "normalized": False,
                "distance_metrics": ["cosine"],
                "source_url": embedding_source,
                "checked_at": checked_at,
                "status": "documented",
            },
        ),
        _base_model(
            "sarashina3-rerank",
            display_name="Sarashina3 rerank",
            context_window=8_000,
            max_output_tokens=0,
            input_modalities=["text"],
            output_modalities=["rerank"],
            endpoint=_endpoint("/rerank", "sarashina-rerank", rerank_source),
            source_pages=[DOCS["models"], rerank_source, DOCS["rate_limits"]],
            checked_at=checked_at,
            rpm=60,
            extra={
                "max_query_document_pair_tokens": 8_000,
                "task_types": [
                    "GENERAL_RETRIEVAL",
                    "GENERAL_QA",
                    "NEWS_RETRIEVAL",
                    "SEMANTIC_SIMILARITY",
                    "CUSTOMIZE",
                ],
                "customize_requires_query_instruction": True,
                "top_n_filtering_supported": False,
            },
            rerank={
                "rerank": True,
                "max_documents": 20,
                "returns_scores": True,
                "returns_documents": False,
                "score_range": [0.0, 1.0],
                "source_url": rerank_source,
                "checked_at": checked_at,
                "status": "documented",
            },
        ),
        _base_model(
            "sarashina3-translate",
            display_name="Sarashina3 translate",
            context_window=0,
            max_output_tokens=0,
            input_modalities=["text"],
            output_modalities=["text"],
            endpoint=_endpoint("/translate", "sarashina-translate", translate_source),
            source_pages=[DOCS["models"], translate_source, DOCS["rate_limits"]],
            checked_at=checked_at,
            supports_streaming=False,
            rpm=6,
            extra={
                "model_parameter_required": False,
                "input_limit": 5_000,
                "input_limit_unit": "unicode_code_points",
                "source_language_values": ["ja", "en"],
                "target_language_values": ["ja", "en"],
                "same_source_and_target_language_allowed": False,
                "streaming_supported": False,
            },
        ),
    ]
    return {"models": sorted(models, key=lambda model: model["model_id"])}


def main() -> None:
    pages = {name: _fetch(url) for name, url in DOCS.items()}
    payload = catalog_from_docs(pages)
    previous = {}
    if OUT.exists():
        previous = {
            model.get("model_id"): model
            for model in json.loads(OUT.read_text(encoding="utf-8")).get("models", [])
        }
    for model in payload["models"]:
        old = previous.get(model["model_id"], {})
        old_extra = old.get("extra") or {}
        model["extra"] = {**old_extra, **model["extra"]}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    today = datetime.now(timezone.utc).date().isoformat()
    print(f"sarashina.json: {len(payload['models'])} models updated; pricing=JPY 0")


if __name__ == "__main__":
    main()
