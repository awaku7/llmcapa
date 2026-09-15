from __future__ import annotations

import llmcapa
from llmcapa.models import (
    Capability,
    DocumentCapability,
    EmbeddingCapability,
    RerankCapability,
    SpatialCapability,
)


def test_specialized_capabilities_round_trip():
    capability = Capability(
        provider="local",
        model_id="specialized",
        document=DocumentCapability(input_formats=("pdf",)),
        embedding=EmbeddingCapability(dimensions=768),
        rerank=RerankCapability(rerank=True, returns_scores=True),
        spatial=SpatialCapability(spatial=True, kind_values=("geospatial",)),
    )
    restored = Capability.from_dict(capability.to_dict())

    assert restored.document is not None
    assert restored.document.input_formats == ("pdf",)
    assert restored.embedding is not None
    assert restored.embedding.dimensions == 768
    assert restored.rerank is not None
    assert restored.rerank.returns_scores is True
    assert restored.spatial is not None
    assert restored.spatial.kind_values == ("geospatial",)


def test_catalog_specialized_capabilities_are_normalized():
    embedding = llmcapa.get("text-embedding-3-large", provider="openai")
    rerank = llmcapa.get("rerank-v3.5", provider="cohere")

    assert embedding.embedding is not None
    assert embedding.embedding.dimensions == 3072
    assert rerank.rerank is not None
    assert rerank.rerank.rerank is True
