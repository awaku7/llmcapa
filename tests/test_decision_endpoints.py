"""Decision API endpoint and protocol metadata tests."""

import importlib.util
import json
from pathlib import Path

import llmcapa
from llmcapa import Capability

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"
SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
UPDATER_SPEC = importlib.util.spec_from_file_location(
    "_update_openrouter_for_tests", Path(SCRIPTS) / "_update_openrouter.py"
)
assert UPDATER_SPEC is not None and UPDATER_SPEC.loader is not None
openrouter_updater = importlib.util.module_from_spec(UPDATER_SPEC)
UPDATER_SPEC.loader.exec_module(openrouter_updater)


PERPLEXITY_DECIDER = "pplx-decider-v1.1-27b"
OPENROUTER_ALPHA_DECISION_MODELS = {
    "cloudflare/clef",
    "cloudflare/clef-flash",
    "inception/mercury-decide",
    "jaredpalmer/kev-4b",
    "liquid/d1",
    "openai/gpt-6-luna-decisions",
    "perplexity/pplx-decider-v1.1-27b",
    "respan/span-01",
    "respan/span-01-lite",
    "upstage/solar-decide",
    "upstage/solar-decide-flash",
}


def test_perplexity_decision_model_has_explicit_endpoint_and_schema_metadata():
    cap = llmcapa.get(PERPLEXITY_DECIDER, provider="perplexity")

    assert cap.output_modalities == ["decision"]
    assert cap.supports("decision_output") is True
    assert cap.decision is not None
    assert cap.decision.decision is True
    assert cap.decision.question_kinds == ("noul", "choice", "score")
    assert cap.decision.endpoints == (
        "https://api.perplexity.ai/v1/decisions",
    )
    assert cap.decision.extra["endpoint_protocol"] == "perplexity-decisions-v1"
    assert cap.decision.extra["systemone_schema_compatible"] is True
    assert cap.decision.extra["typesafe_sdk_compatibility"] == "not-documented"


def test_openrouter_decision_routes_have_explicit_gateway_endpoints():
    payload = json.loads((DATA_DIR / "openrouter.json").read_text(encoding="utf-8"))
    models = {
        record["model_id"]: Capability.from_dict(record)
        for record in payload["models"]
        if record["model_id"] in OPENROUTER_ALPHA_DECISION_MODELS
    }

    assert set(models) == OPENROUTER_ALPHA_DECISION_MODELS
    for cap in models.values():
        assert cap.output_modalities == ["decision"]
        assert cap.supports("decision_output") is True
        assert cap.decision is not None
        assert cap.decision.decision is True
        assert cap.decision.endpoints == (
            "https://openrouter.ai/api/alpha/decisions",
        )
        assert (
            cap.decision.extra["endpoint_protocol"]
            == "openrouter-alpha-decisions"
        )


def test_openai_native_decisions_api_endpoint_is_distinguished():
    payload = json.loads((DATA_DIR / "openai.json").read_text(encoding="utf-8"))
    record = next(
        item for item in payload["models"] if item["model_id"] == "gpt-6-luna"
    )
    cap = Capability.from_dict(record)

    assert cap.decision.endpoints == ("https://api.openai.com/v1/decisions",)
    assert cap.decision.extra["endpoint_protocol"] == "openai-decisions-v1"
    assert cap.decision.extra["systemone_schema_compatible"] is False


def test_openrouter_jev_exposes_both_documented_api_surfaces():
    payload = json.loads((DATA_DIR / "openrouter.json").read_text(encoding="utf-8"))
    record = next(
        item for item in payload["models"] if item["model_id"] == "typesafe/jev-1.13"
    )
    cap = Capability.from_dict(record)

    assert cap.decision.endpoints == (
        "https://openrouter.ai/api/alpha/decisions",
        "https://openrouter.ai/api/v1/systemone",
    )
    assert cap.decision.extra["typesafe_sdk_compatibility"] is True


def test_openrouter_updater_preserves_decision_endpoint_metadata():
    raw = {
        "id": "perplexity/pplx-decider-v1.1-27b",
        "name": "Perplexity Decider",
        "context_length": 262144,
        "architecture": {
            "input_modalities": ["text", "image"],
            "output_modalities": ["decisions"],
        },
        "supported_parameters": [],
        "top_provider": {"context_length": 262144, "max_completion_tokens": 0},
        "pricing": {"prompt": 0.00000002, "completion": 0.0},
    }

    cap = Capability.from_dict(openrouter_updater.map_model(raw))
    assert cap.output_modalities == ["decision"]
    assert cap.decision is not None
    assert cap.decision.endpoints == (
        "https://openrouter.ai/api/alpha/decisions",
    )
    assert cap.decision.extra["upstream_endpoint"] == (
        "https://api.perplexity.ai/v1/decisions"
    )


def test_together_tev1_is_marked_as_chat_completion_not_decisions_api():
    payload = json.loads((DATA_DIR / "openrouter.json").read_text(encoding="utf-8"))
    record = next(
        item
        for item in payload["models"]
        if item["model_id"] == "togethercomputer/tev1-4b-experimental"
    )
    cap = Capability.from_dict(record)

    assert cap.output_modalities == ["decision"]
    assert cap.decision is not None
    assert cap.decision.decision is True
    assert cap.decision.extra["endpoint_protocol"] == "openai-compatible-chat-completions"
    assert cap.decision.endpoints == (
        "https://openrouter.ai/api/v1/chat/completions",
    )
    assert cap.decision.extra["systemone_schema_compatible"] is False
