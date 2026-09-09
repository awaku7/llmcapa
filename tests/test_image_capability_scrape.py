from scripts._scrape_image_capabilities import parse_provider_page


def test_microsoft_parser_extracts_input_format_without_inventing_size():
    parsed = parse_provider_page(
        "microsoft",
        "The image edits API accepts a JPEG or PNG image. Output width and height must be at least 768.",
    )

    assert parsed["input_formats"] == ["jpeg", "png"]
    assert parsed["input_mime_types"] == ["image/jpeg", "image/png"]
    assert "max_input_bytes" not in parsed


def test_meta_parser_extracts_inline_and_file_limits():
    parsed = parse_provider_page(
        "meta",
        "Max filesize per image (inline image_url): 50 MB. "
        "Max filesize per image (input_file via Files API): 1 GiB. PNG and JPEG are supported.",
    )

    assert parsed["max_input_bytes"] == 50_000_000
    assert parsed["max_input_file_bytes"] == 1024**3
    assert parsed["input_formats"] == ["jpeg", "png"]


def test_open_provider_parser_extracts_xai_limits():
    parsed = parse_provider_page(
        "xai",
        "Maximum image size: 20MiB. Supported image file types: jpg/jpeg or png.",
    )

    assert parsed["max_input_bytes"] == 20 * 1024 * 1024
    assert parsed["input_formats"] == ["jpg", "jpeg", "png"]
