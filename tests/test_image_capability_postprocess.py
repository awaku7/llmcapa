from scripts._image_capability_postprocess import (
    known_analysis_capability,
    minimal_image_capability,
    parse_image_input_constraints,
)


def test_image_input_only_is_not_classified_as_generation():
    record = {
        "model_id": "gpt-4o",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
    }

    assert minimal_image_capability(record) is None


def test_image_generation_record_gets_only_conservative_metadata():
    record = {
        "provider": "xai",
        "model_id": "grok-imagine-image",
        "input_modalities": ["text", "image"],
        "output_modalities": ["image"],
        "extra": {"source": "https://docs.x.ai/developers/models"},
    }

    assert minimal_image_capability(record) == {
        "generation": True,
        "accepts_text_prompt": True,
        "accepts_image_input": True,
        "status": "documented",
        "source_url": "https://docs.x.ai/developers/model-capabilities/images/understanding",
        "input_formats": ["jpg", "jpeg", "png"],
        "input_mime_types": ["image/jpeg", "image/png"],
        "max_input_bytes": 20 * 1024 * 1024,
    }


def test_parse_explicit_input_constraints():
    text = """
    Accepted input formats: PNG, JPEG, WebP
    Maximum input size: 50 MB
    Maximum input dimensions: 4096x4096
    Maximum input pixels: 16 MP
    """

    assert parse_image_input_constraints(text) == {
        "input_formats": ["png", "jpeg", "webp"],
        "max_input_bytes": 50 * 1024 * 1024,
        "max_input_width": 4096,
        "max_input_height": 4096,
        "max_input_pixels": 16_000_000,
    }


def test_image_analysis_output_is_not_classified_as_generation():
    record = {
        "model_id": "MedImageParse",
        "input_modalities": ["image", "text"],
        "output_modalities": ["image"],
    }

    assert minimal_image_capability(record) is None


def test_known_analysis_capability_is_not_treated_as_generation():
    capability = known_analysis_capability(
        {
            "provider": "microsoft",
            "model_id": "MedImageParse",
            "input_modalities": ["image", "text"],
            "output_modalities": ["image"],
        }
    )

    assert capability["analysis"]["segmentation"] is True
    assert capability["analysis"]["object_detection"] is True
    assert capability["status"] == "documented"
