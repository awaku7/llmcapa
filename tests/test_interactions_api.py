"""Interactions API support metadata for Google's Gemini APIs."""

from __future__ import annotations

import sys
from pathlib import Path

import llmcapa
from llmcapa import Capability, Feature

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _update_google as google_updater  # noqa: E402
import _update_vertex_ai as vertex_updater  # noqa: E402


def test_interactions_api_feature_is_tri_state_and_serializable() -> None:
    unknown = Capability(provider="example", model_id="unknown")
    assert unknown.supports(Feature.LLMC_FEAT_INTERACTIONS_API) is None
    assert "supports_interactions_api" not in unknown.to_dict()

    supported = Capability.from_dict(
        {
            "provider": "google",
            "model_id": "gemini-4-carbon",
            "supports_interactions_api": True,
        }
    )
    assert supported.supports("interactions_api") is True
    assert supported.supports(Feature.LLMC_FEAT_INTERACTIONS_API) is True
    assert "interactions_api" in supported.features()
    assert Capability.from_dict(supported.to_dict()) == supported
    replacement = Capability(
        provider="example",
        model_id="no-interactions",
        supports_interactions_api=False,
    )
    assert supported.can_be_replaced_by(replacement) is False


def test_google_interactions_api_status_uses_official_model_list() -> None:
    supported = llmcapa.get("gemini-4-carbon", provider="google")
    unsupported = llmcapa.get("gemini-3.5-flash", provider="google")
    assert supported.supports("interactions_api") is True
    assert unsupported.supports("interactions_api") is False

    rows = [{"model_id": "gemini-4-carbon"}, {"model_id": "gemini-3.5-flash"}]
    for row in rows:
        google_updater.apply_google_interactions_api(row)
    assert [row["supports_interactions_api"] for row in rows] == [True, False]


def test_vertex_interactions_api_status_is_provider_specific() -> None:
    supported = llmcapa.get("gemini-3.8-flash-cyber", provider="vertex-ai")
    unsupported = llmcapa.get("gemini-3.1-flash-image", provider="vertex-ai")
    assert supported.supports(Feature.LLMC_FEAT_INTERACTIONS_API) is True
    assert unsupported.supports("interactions_api") is False

    listed = {"model_id": "gemini-3.8-flash-cyber", "supports_interactions_api": False}
    unlisted = {"model_id": "gemini-3.1-flash-image", "supports_interactions_api": True}
    music = {"model_id": "lyria-3-clip-preview"}
    non_gemini = {
        "model_id": "google/gemma-4-31b-it",
        "supports_interactions_api": True,
    }
    for row in (listed, unlisted, music, non_gemini):
        vertex_updater.apply_vertex_interactions_api(row)
    assert listed["supports_interactions_api"] is True
    assert unlisted["supports_interactions_api"] is False
    assert music["supports_interactions_api"] is True
    assert "supports_interactions_api" not in non_gemini
