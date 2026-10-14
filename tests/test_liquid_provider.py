"""Bundled Liquid AI decision-model catalog tests."""

import llmcapa

EXPECTED_LIQUID_MODELS = {"d1", "d1-3B", "d1-omni-600M"}


def test_liquid_provider_is_registered_and_queryable():
    assert "liquid" in llmcapa.providers()
    assert llmcapa.list_models(provider="liquid-ai") == llmcapa.list_models(
        provider="liquid"
    )

    models = llmcapa.list_models(provider="liquid")
    assert {model.model_id for model in models} == EXPECTED_LIQUID_MODELS
    assert all(model.provider == "liquid" for model in models)

    for model_id in EXPECTED_LIQUID_MODELS:
        cap = llmcapa.get(model_id, provider="liquid")
        assert cap.provider == "liquid"
        assert cap.model_id == model_id


def test_liquid_models_are_typed_decision_models():
    for model_id in EXPECTED_LIQUID_MODELS:
        cap = llmcapa.get(model_id, provider="liquid")

        assert cap.output_modalities == ["decision"]
        assert cap.supports("decision_output") is True
        assert cap.supports("text_output") is False
        assert cap.supports_chat_completion is False
        assert cap.max_output_tokens == 0
        assert cap.decision is not None
        assert cap.decision.decision is True
        assert cap.decision.question_kinds == ("choice", "score", "noul")
        assert cap.decision.returns_probabilities is True
        assert cap.decision.returns_confidence is True
        assert cap.decision.free_form_text is False
        assert cap.decision.type_errors_possible is False

    hosted = llmcapa.get("d1", provider="liquid")
    assert hosted.decision.extra["client_sdk"] == "typesafe-sdk"
    assert hosted.decision.extra["base_url"] == "https://api.liquid.ai"
    assert hosted.decision.extra["wire_protocol"] == "typesafe-systemone-compatible"
    assert hosted.decision.endpoints == (
        "https://api.liquid.ai/decisions/v1/systemone",
    )


def test_liquid_open_models_have_documented_context_and_modalities():
    d1 = llmcapa.get("d1-3B", provider="liquid")
    omni = llmcapa.get("d1-omni-600M", provider="liquid")

    assert d1.context_window == 32768
    assert d1.input_modalities == ["text", "image"]
    assert d1.supports("vision") is True
    assert d1.decision is not None
    assert d1.decision.calibrated_confidence is True
    assert d1.decision.max_total_tokens == 32768
    assert d1.decision.extra["local_api_method"] == "system_one"
    assert d1.extra["parameters"] == 3_120_000_000
    assert d1.extra["license_name"] == "LFM Open License v1.0"

    assert omni.context_window == 16384
    assert omni.input_modalities == ["text", "image", "audio"]
    assert omni.supports("vision") is True
    assert omni.supports("audio_input") is True
    assert omni.decision is not None
    # Calibration differs by modality, so the aggregate value is unknown.
    assert omni.decision.calibrated_confidence is None
    assert omni.decision.max_total_tokens == 16384
    assert omni.decision.extra["local_api_method"] == "system_one"
    assert omni.extra["parameters"] == 587_000_000
    assert omni.extra["license_name"] == "LFM Open License v1.0"


def test_liquid_huggingface_aliases_resolve():
    assert llmcapa.get("LiquidAI/d1-3B", provider="liquid").model_id == "d1-3B"
    assert (
        llmcapa.get("LiquidAI/d1-omni-600M", provider="liquid").model_id
        == "d1-omni-600M"
    )
