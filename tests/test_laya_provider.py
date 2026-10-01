"""Bundled Laya decision-provider catalog tests."""

import llmcapa


EXPECTED_LAYA_MODELS = {\n    "laya",\n    "laya-multilingual",\n    "laya-typed-decisions",\n}


def test_laya_provider_is_registered_and_queryable():
    assert "laya" in llmcapa.providers()

    models = llmcapa.list_models(provider="laya")
    assert {model.model_id for model in models} == EXPECTED_LAYA_MODELS
    assert all(model.provider == "laya" for model in models)

    for model_id in EXPECTED_LAYA_MODELS:
        cap = llmcapa.get(model_id, provider="laya")
        assert cap.provider == "laya"
        assert cap.model_id == model_id


def test_laya_aliases_resolve_within_provider_scope():
    english = llmcapa.get("english", provider="laya")
    multilingual = llmcapa.get("multilingual", provider="laya")
    typed = llmcapa.get("typed-decisions", provider="laya")

    assert english.model_id == "laya"
    assert multilingual.model_id == "laya-multilingual"
    assert typed.model_id == "laya-typed-decisions"


def test_laya_models_are_decision_only():
    for model_id in EXPECTED_LAYA_MODELS:
        cap = llmcapa.get(model_id, provider="laya")

        assert cap.input_modalities == ["text"]
        assert cap.output_modalities == ["decision"]
        assert cap.supports("decision_output") is True
        assert cap.supports("text_output") is False
        assert cap.supports("chat_completion") is False
        assert cap.supports("responses_api") is False
        assert cap.decision is not None
        assert cap.decision.question_kinds == ("choice", "score", "noul")
        assert cap.decision.returns_probabilities is True
        assert cap.decision.returns_confidence is True
        assert cap.decision.calibrated_confidence is False
        assert cap.decision.parallel_questions is True
        assert cap.decision.free_form_text is False
        assert cap.decision.type_errors_possible is False
        assert cap.decision.deterministic is True
        assert cap.decision.extra["http_endpoint_path"] == "/v1/systemone"
        assert (\n            cap.decision.extra["wire_protocol"] == "typesafe-systemone-compatible"\n        )


def test_laya_checkpoint_context_windows_and_metadata():
    english = llmcapa.get("laya", provider="laya")
    multilingual = llmcapa.get("laya-multilingual", provider="laya")
    typed = llmcapa.get("laya-typed-decisions", provider="laya")

    assert english.context_window == 512
    assert english.extra["checkpoint_key"] == "english"
    assert english.extra["parameters"] == 421000000

    assert multilingual.context_window == 8192
    assert multilingual.extra["default_context_window"] == 1024
    assert multilingual.extra["max_context_window"] == 8192
    assert multilingual.extra["checkpoint_key"] == "multilingual"
    assert multilingual.extra["parameters"] == 322000000

    assert typed.context_window == 1024
    assert typed.extra["checkpoint_key"] == "typed-decisions"
    assert typed.extra["parameters"] == 421000000


def test_laya_is_not_a_text_model_replacement():
    decision = llmcapa.get("laya", provider="laya")
    text = llmcapa.get("gpt-4o", provider="openai")

    assert decision.can_be_replaced_by(text) is False
