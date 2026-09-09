import json

import llmcapa
from llmcapa import (
    Capability,
    ImageAnalysisCapability,
    ImageCapability,
    ImageEndpointCapability,
)


def test_image_capability_is_optional_and_backward_compatible():
    cap = Capability(provider="test", model_id="text-model")

    assert cap.image is None
    assert "image" not in cap.to_dict()


def test_image_capability_round_trip_normalizes_nested_values():
    cap = Capability(
        provider="openai",
        model_id="gpt-image-2.5-flare",
        image=ImageCapability(
            analysis=ImageAnalysisCapability(ocr=False),
            generation=True,
            editing=True,
            inpainting=True,
            accepts_image_input=True,
            max_input_images=16,
            input_formats=("png", "jpeg", "webp"),
            input_mime_types=("image/png", "image/jpeg", "image/webp"),
            max_input_bytes=50_000_000,
            max_input_payload_bytes=60_000_000,
            max_input_width=4096,
            max_input_height=4096,
            max_input_pixels=16_000_000,
            input_fidelity_values=("low", "high"),
            output_formats=("png", "jpeg", "webp"),
            quality_values=("auto", "xhigh", "max"),
            max_outputs=10,
            supports_transparent_background=True,
            background_values=("auto", "transparent"),
            partial_images_max=3,
            endpoints=ImageEndpointCapability(
                image_api_generations=True,
                image_api_edits=True,
                responses_image_tool=True,
                responses_mainline_model_required=True,
                responses_action_values=("auto", "generate", "edit"),
                responses_multi_turn=True,
                responses_image_context=True,
            ),
        ),
    )

    payload = cap.to_dict()
    assert json.loads(json.dumps(payload))["image"]["max_outputs"] == 10
    restored = Capability.from_dict(payload)

    assert restored.image == cap.image
    assert restored.image.output_formats == ("png", "jpeg", "webp")
    assert restored.image.input_formats == ("png", "jpeg", "webp")
    assert restored.image.input_mime_types == ("image/png", "image/jpeg", "image/webp")
    assert restored.image.max_input_bytes == 50_000_000
    assert restored.image.max_input_payload_bytes == 60_000_000
    assert restored.image.max_input_width == 4096
    assert restored.image.max_input_height == 4096
    assert restored.image.max_input_pixels == 16_000_000
    assert restored.image.analysis.ocr is False
    assert restored.image.endpoints.image_api_edits is True
    assert restored.image.endpoints.responses_mainline_model_required is True
    assert restored.image.endpoints.responses_action_values == (
        "auto",
        "generate",
        "edit",
    )
    assert restored.image.endpoints.responses_multi_turn is True
    assert restored.image.endpoints.responses_image_context is True


def test_image_capability_distinguishes_unknown_from_unsupported():
    unknown = ImageCapability()
    unsupported = ImageCapability(generation=False)

    assert unknown.generation is None
    assert unsupported.generation is False


def test_openai_image_catalog_records_expose_image_capability():
    flare = llmcapa.get("gpt-image-2.5-flare", provider="openai")
    sunburst = llmcapa.get("gpt-image-2.5-sunburst", provider="openai")
    gpt_image_1 = llmcapa.get("gpt-image-1", provider="openai")

    assert flare.image is not None
    assert flare.image.max_input_images == 16
    assert flare.image.max_outputs == 10
    assert "webp" in flare.image.output_formats
    assert "xhigh" in flare.image.quality_values
    assert flare.image.partial_images_max == 3
    assert flare.image.endpoints is not None
    assert flare.image.endpoints.image_api_generations is True
    assert flare.image.endpoints.image_api_edits is True
    assert flare.image.endpoints.responses_image_tool is True
    assert flare.image.endpoints.responses_mainline_model_required is True
    assert flare.image.endpoints.responses_action_values == ("auto", "generate", "edit")
    assert flare.image.endpoints.responses_multi_turn is True
    assert flare.image.endpoints.responses_image_context is True
    assert sunburst.image is not None
    assert sunburst.image.source_url.endswith("gpt-image-2.5-sunburst.md")
    assert gpt_image_1.image is not None
    assert gpt_image_1.image.generation is True
    assert gpt_image_1.image.source_url.endswith("gpt-image-1.md")


def test_generation_and_vision_catalogs_are_separate():
    xai_image = llmcapa.get("grok-imagine-image", provider="xai")
    google_image = llmcapa.get("gemini-3-pro-image", provider="google")
    vision_only = llmcapa.get("gpt-4o", provider="openai")

    assert xai_image.image is not None
    assert xai_image.image.generation is True
    assert google_image.image is not None
    assert google_image.image.generation is True
    assert vision_only.supports("image_input") is True
    assert vision_only.image is None


def test_endpoint_extensions_round_trip_through_extra():
    restored = Capability.from_dict(
        {
            "provider": "openai",
            "model_id": "image-model",
            "image": {
                "generation": True,
                "endpoints": {
                    "image_api_generations": True,
                    "future_endpoint_flag": True,
                },
            },
        }
    )

    assert restored.image.endpoints.extra["future_endpoint_flag"] is True
    assert (
        Capability.from_dict(restored.to_dict()).image.endpoints.extra[
            "future_endpoint_flag"
        ]
        is True
    )
