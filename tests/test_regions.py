"""Tests for model regional availability metadata and queries."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llmcapa
from llmcapa import Capability, RegionCapability
from llmcapa.registry import Registry


def _regional_model(provider: str, model_id: str, **regions) -> Capability:
    return Capability.from_dict(
        {
            "provider": provider,
            "model_id": model_id,
            "context_window": 1024,
            "max_output_tokens": 256,
            "regions": regions,
        }
    )


def test_region_capability_round_trip_and_provider_extensions():
    raw = {
        "locations": ["us-east-1", "eu-west-1"],
        "multi_regions": ["us", "eu"],
        "geographic_inference_regions": ["us-east-1"],
        "global_inference_regions": ["us-east-1", "eu-west-1"],
        "inference_profiles": ["us.anthropic.claude-sonnet-4-5-v1:0"],
        "source_url": "https://example.com/regions",
        "checked_at": "2026-03-01",
        "provider_note": "kept",
    }
    cap = Capability.from_dict(
        {
            "provider": "bedrock",
            "model_id": "example-model",
            "regions": raw,
        }
    )

    assert isinstance(cap.regions, RegionCapability)
    assert cap.regions.locations == ("us-east-1", "eu-west-1")
    assert cap.regions.inference_profiles == ("us.anthropic.claude-sonnet-4-5-v1:0",)
    assert cap.to_dict()["regions"] == raw
    assert Capability.from_dict(cap.to_dict()) == cap


def test_registry_list_regions_and_find_by_region_are_scoped_and_offline():
    registry = Registry()
    registry._loaded = True
    registry.register(
        _regional_model(
            "vertex-ai",
            "gemini-test",
            locations=["us-central1", "asia-northeast1"],
            source_url="https://example.com/vertex",
        )
    )
    registry.register(
        _regional_model(
            "google",
            "gemini-api-test",
            locations=["Japan", "United States"],
            scope="country",
            global_endpoint=True,
        )
    )
    registry.register(
        _regional_model(
            "bedrock",
            "claude-test",
            locations=["us-east-1", "eu-west-1"],
            inference_profiles=["global.anthropic.claude-test"],
        )
    )
    registry.register(
        Capability.from_dict(
            {
                "provider": "bedrock",
                "model_id": "no-region-data",
                "context_window": 1024,
                "max_output_tokens": 256,
            }
        )
    )

    assert registry.list_regions(provider="vertex-ai") == [
        "asia-northeast1",
        "us-central1",
    ]
    assert registry.list_regions(provider="google", scope="country") == [
        "Japan",
        "United States",
    ]
    assert registry.list_regions(include_global=True) == [
        "asia-northeast1",
        "eu-west-1",
        "global",
        "Japan",
        "United States",
        "us-central1",
        "us-east-1",
    ]
    assert [cap.model_id for cap in registry.find_by_region("US-EAST-1")] == [
        "claude-test"
    ]
    assert [cap.model_id for cap in registry.find_by_region("global")] == [
        "gemini-api-test"
    ]
    assert [
        cap.model_id
        for cap in registry.find_by_region("Japan", provider="google", scope="country")
    ] == ["gemini-api-test"]
    assert registry.list_regions(model_id="not-a-model") == []
    assert registry.list_regions(
        provider="bedrock", include_inference_regions=True
    ) == ["eu-west-1", "us-east-1"]
    assert [
        cap.model_id
        for cap in registry.find_by_region(
            "us-east-1", provider="bedrock", include_inference_regions=True
        )
    ] == ["claude-test"]


def test_bundled_regional_availability_snapshot_is_queryable():
    registry = Registry()

    countries = registry.list_regions(provider="google", scope="country")
    assert "Japan" in countries
    assert len(countries) > 100

    vertex = registry.get("gemini-2.5-flash", provider="vertex-ai")
    assert "us-central1" in vertex.regions.locations
    assert vertex.regions.global_endpoint is True

    hydrogen = registry.get("gemini-4-hydrogen", provider="vertex-ai")
    assert hydrogen.regions.multi_regions == ("us", "eu")
    assert hydrogen.regions.global_endpoint is True
    assert hydrogen.regions.locations == ()

    nova = registry.get("nova-2-lite-v1", provider="bedrock")
    assert "us-east-1" in nova.regions.geographic_inference_regions
    assert "nova-2-lite-v1" not in [
        cap.model_id for cap in registry.find_by_region("eu-west-2", provider="bedrock")
    ]
    assert "nova-2-lite-v1" in [
        cap.model_id
        for cap in registry.find_by_region(
            "eu-west-2", provider="bedrock", include_inference_regions=True
        )
    ]


def test_top_level_region_helpers_use_default_registry(monkeypatch):
    registry = Registry()
    registry._loaded = True
    registry.register(
        _regional_model("bedrock", "model-a", locations=["ap-northeast-1"])
    )
    monkeypatch.setattr(llmcapa, "default_registry", lambda: registry)

    assert llmcapa.list_regions(provider="bedrock") == ["ap-northeast-1"]
    assert [cap.model_id for cap in llmcapa.find_by_region("ap-northeast-1")] == [
        "model-a"
    ]
