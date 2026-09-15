from __future__ import annotations

import llmcapa
from llmcapa.models import Capability, VideoCapability, VideoEndpointCapability


def test_video_capability_round_trip_preserves_detailed_fields():
    original = VideoCapability(
        generation=True,
        image_to_video=True,
        input_formats=("mp4", "webm"),
        output_formats=("mp4",),
        duration_values_seconds=(6.0,),
        resolution_values=("1280x720",),
        endpoints=VideoEndpointCapability(generation=True, streaming=True),
    )
    restored = VideoCapability.from_dict(original.to_dict())

    assert restored.generation is True
    assert restored.image_to_video is True
    assert restored.input_formats == ("mp4", "webm")
    assert restored.duration_values_seconds == (6.0,)
    assert restored.endpoints is not None
    assert restored.endpoints.streaming is True


def test_video_catalog_exposes_generation_and_input_constraints():
    sora = llmcapa.get("sora-2", provider="openai")
    nova = llmcapa.get("nova-reel-v1", provider="amazon")

    assert sora.video is not None
    assert sora.video.generation is True
    assert sora.video.text_to_video is True
    assert "mp4" in sora.video.output_formats

    assert nova.video is not None
    assert nova.video.generation is True
    assert nova.video.text_to_video is True
    assert nova.video.image_to_video is True
    assert nova.video.duration_values_seconds == (6.0,)


def test_video_capability_is_available_on_capability_serialization():
    capability = llmcapa.get("grok-imagine-video", provider="xai")
    restored = Capability.from_dict(capability.to_dict())

    assert restored.video is not None
    assert restored.video.video_to_video is True
    assert restored.video.output_mime_types == ("video/mp4",)
