from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import _update_all_providers
import _update_sarashina

import llmcapa


def test_sarashina_catalog_is_registered_with_documented_capabilities() -> None:
    assert "sarashina" in llmcapa.providers()
    models = llmcapa.list_models(provider="sarashina")
    assert {model.model_id for model in models} == (
        set(_update_sarashina.ALL_MODELS) | {"sarashina3-translate"}
    )
    assert all(model.provider == "sarashina" for model in models)
    assert all(
        model.pricing
        == {
            "input_per_1m": 0.0,
            "output_per_1m": 0.0,
            "currency": "JPY",
        }
        for model in models
    )

    mini = llmcapa.get("sarashina3-mini", provider="sarashina")
    assert mini.context_window == 128_000
    assert mini.max_output_tokens == 8_000
    assert mini.supports_chat_completion is True
    assert mini.supports_function_calling is True
    assert mini.supports_json_schema is True
    assert mini.extra["endpoints"][0]["path"] == "/chat/completions"
    assert mini.extra["requests_per_minute"] == 30
    guard = llmcapa.get("sarashina3-guard", provider="sarashina")
    assert guard.extra["requests_per_minute"] == 6

    thinking = llmcapa.get(_update_sarashina.THINKING_MODEL, provider="sarashina")
    assert thinking.display_name == "Sarashina3.2 mini thinking"
    assert thinking.context_window == 128_000
    assert thinking.max_output_tokens == 8_000
    assert thinking.supports_reasoning is True
    assert thinking.supports_reasoning_effort is True
    assert thinking.supports_function_calling is True
    assert thinking.extra["reasoning_effort_values"] == ["low", "medium", "high"]

    embedding = llmcapa.get("sarashina3-embedding", provider="sarashina")
    assert embedding.embedding.dimensions == 1_536
    assert embedding.embedding.max_input_tokens == 8_000
    assert embedding.embedding.normalized is False
    assert "RETRIEVAL_QUERY" in embedding.extra["task_types"]

    rerank = llmcapa.get("sarashina3-rerank", provider="sarashina")
    assert rerank.rerank.max_documents == 20
    assert rerank.rerank.score_range == (0.0, 1.0)
    assert rerank.extra["top_n_filtering_supported"] is False

    translate = llmcapa.get("sarashina3.2-translate", provider="sarashina")
    assert translate.display_name == "Sarashina3.2 translate"
    assert translate.supports_chat_completion is False
    assert translate.supports_streaming is False
    assert translate.extra["input_limit"] == 5_000
    assert translate.extra["source_language_values"] == ["ja", "en"]
    assert translate.extra["requests_per_minute"] == 30

    legacy_translate = llmcapa.get("sarashina3-translate", provider="sarashina")
    assert legacy_translate.supports_chat_completion is False
    assert legacy_translate.supports_streaming is False
    assert legacy_translate.extra["input_limit"] == 5_000
    assert legacy_translate.extra["source_language_values"] == ["ja", "en"]
    assert legacy_translate.extra["requests_per_minute"] == 30


def test_sarashina_updater_requires_all_official_model_and_endpoint_docs() -> None:
    pages = {
        "models": " ".join(_update_sarashina.ALL_MODELS),
        "introduction": "Bearer API key authentication",
        "chat": " ".join(_update_sarashina.CHAT_MODELS)
        + " "
        + _update_sarashina.ENDPOINTS["chat"],
        "embedding": "sarashina3-embedding " + _update_sarashina.ENDPOINTS["embedding"],
        "rerank": "sarashina3-rerank " + _update_sarashina.ENDPOINTS["rerank"],
        "translate": "sarashina3.2-translate "
        + _update_sarashina.ENDPOINTS["translate"],
        "rate_limits": " ".join(_update_sarashina.ALL_MODELS),
    }
    catalog = _update_sarashina.catalog_from_docs(pages, checked_at="2026-10-14")
    assert len(catalog["models"]) == 7
    assert all(
        model["pricing"]
        == {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "JPY"}
        for model in catalog["models"]
    )
    assert catalog["models"][0]["extra"]["official_source_checked_at"] == "2026-10-14"

    pages["rerank"] = "model information only"
    with pytest.raises(ValueError, match="rerank"):
        _update_sarashina.catalog_from_docs(pages, checked_at="2026-10-14")


def test_sarashina_fetch_reads_rendered_page_text(monkeypatch) -> None:
    url = "https://docs.sarashina.ai/models"
    calls = []

    class FakeLocator:
        def inner_text(self, **kwargs):
            calls.append(("inner_text", kwargs))
            return "rendered official Sarashina model details"

    class FakePage:
        def goto(self, target, **kwargs):
            calls.append(("goto", target, kwargs))

        def wait_for_function(self, expression, **kwargs):
            calls.append(("wait", expression, kwargs))

        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

    class FakeBrowser:
        def new_page(self, **kwargs):
            calls.append(("new_page", kwargs))
            return FakePage()

        def close(self):
            calls.append(("close",))

    class FakePlaywright:
        chromium = type(
            "FakeChromium",
            (),
            {"launch": staticmethod(lambda **kwargs: FakeBrowser())},
        )()

    class FakeManager:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *_exc):
            pass

    monkeypatch.setattr(_update_sarashina, "sync_playwright", FakeManager)

    assert _update_sarashina._fetch(url) == "rendered official Sarashina model details"
    assert any(call[0] == "goto" and call[1] == url for call in calls)
    assert ("locator", "body") in calls
    assert ("close",) in calls


def test_sarashina_provider_updater_is_registered() -> None:
    assert _update_all_providers.PROVIDER_SCRIPTS["sarashina"] == "_update_sarashina.py"
    assert (ROOT / "scripts" / "_update_sarashina.py").is_file()


def test_sarashina_translate_keeps_character_limit_and_zero_jpy_pricing() -> None:
    translate = llmcapa.get("sarashina3-translate", provider="sarashina")
    assert translate.context_window == 0
    assert translate.pricing == {
        "input_per_1m": 0.0,
        "output_per_1m": 0.0,
        "currency": "JPY",
    }
    assert translate.extra["input_limit_unit"] == "unicode_code_points"
    assert translate.extra["pricing_source"] == "user_confirmation"
