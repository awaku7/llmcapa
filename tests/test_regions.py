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


def test_region_queries_without_provider_use_each_providers_own_record():
    registry = Registry()
    registry._loaded = True
    # The Gemini API record is registered first and wins the flat mapping;
    # it carries no region data. The Vertex AI record for the same model
    # ID must still answer unqualified region queries, attributed to
    # vertex-ai rather than to the flat winner.
    registry.register(
        Capability.from_dict(
            {
                "provider": "google",
                "model_id": "shared-model",
                "context_window": 1024,
                "max_output_tokens": 256,
            }
        )
    )
    registry.register(
        _regional_model(
            "vertex-ai",
            "shared-model",
            locations=["asia-northeast1"],
            source_url="https://example.com/vertex",
        )
    )

    assert registry.get("shared-model").provider == "google"
    assert registry.get("shared-model").regions is None
    assert "asia-northeast1" in registry.list_regions()
    assert registry.list_regions(provider="google") == []
    hits = registry.find_by_region("asia-northeast1")
    assert [(cap.provider, cap.model_id) for cap in hits] == [
        ("vertex-ai", "shared-model")
    ]


def test_bundled_regional_availability_snapshot_is_queryable():
    registry = Registry()

    # Bundled region data uses cloud region/location names only. Service
    # availability by country (e.g. the Gemini API country list) is not
    # recorded, so the google provider carries no region metadata.
    assert registry.list_regions(provider="google") == []
    assert registry.list_regions(scope="country") == []
    assert registry.get("gemini-2.5-flash", provider="google").regions is None

    vertex = registry.get("gemini-2.5-flash", provider="vertex-ai")
    assert "us-central1" in vertex.regions.locations
    assert vertex.regions.global_endpoint is True

    hydrogen = registry.get("gemini-4-hydrogen", provider="vertex-ai")
    assert hydrogen.regions.multi_regions == ("us", "eu")
    assert hydrogen.regions.global_endpoint is True
    assert hydrogen.regions.locations == ()

    # Unqualified region queries consider each provider's own record:
    # the Vertex AI locations surface even though the same model IDs also
    # exist in the google catalog without region data.
    assert "asia-northeast1" in registry.list_regions()
    assert "ap-northeast-1" in registry.list_regions()
    unqualified = registry.find_by_region("asia-northeast1")
    assert ("vertex-ai", "gemini-2.5-flash") in [
        (cap.provider, cap.model_id) for cap in unqualified
    ]

    # Coverage scraped from the official Bedrock page: most Bedrock
    # records now carry regions, not only the first hand-written few.
    bedrock_caps = registry.list_models(provider="bedrock")
    assert sum(1 for cap in bedrock_caps if cap.regions is not None) >= 140
    assert len(registry.find_by_region("ap-northeast-1", provider="bedrock")) >= 30
    nova_pro = registry.get("amazon.nova-pro-v1:0", provider="bedrock")
    assert "us-east-1" in nova_pro.regions.locations

    # Vertex coverage from the official locations page.
    flash37 = registry.get("gemini-3.7-flash", provider="vertex-ai")
    assert flash37.regions is not None
    assert flash37.regions.global_endpoint is True

    # Azure's official region table covers 104 catalog rows in total. Ten
    # Microsoft-published entries are registered under ``microsoft`` rather
    # than ``azure-foundry``, leaving 94 host-catalog rows with regions.
    azure_caps = registry.list_models(provider="azure-foundry")
    assert sum(1 for cap in azure_caps if cap.regions is not None) >= 90
    gpt4o = registry.get("gpt-4o", provider="azure-foundry")
    assert "japaneast" in gpt4o.regions.locations
    assert "eastus" in gpt4o.regions.locations
    assert gpt4o.regions.source_url.endswith("region-availability")
    assert ("azure-foundry", "gpt-4o") in [
        (cap.provider, cap.model_id)
        for cap in registry.find_by_region("japaneast", provider="azure-foundry")
    ]
    assert ("azure-foundry", "gpt-4o") in [
        (cap.provider, cap.model_id) for cap in registry.find_by_region("japaneast")
    ]

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
