from scripts.provider_updates.siliconflow import (
    build_live_rows,
    extract_model_ids,
    merge_previous,
)


def test_extract_model_ids_uses_model_fields_and_supported_lists_only():
    markdown = '''
# Example
model = "deepseek-ai/DeepSeek-R1"

## 1. Supported models
* **DeepseekVL2 Series**:
* **Qwen Series**:
  * Qwen/Qwen3-32B
  * Wan-AI/Wan2.2-I2V-A14B
  * product-characteristics

## Other details
* fake/provider-9000
{"model_id": "props:children:1:props:pageMetadata"}
'''

    assert extract_model_ids(markdown) == {
        "deepseek-ai/DeepSeek-R1",
        "Qwen/Qwen3-32B",
        "Wan-AI/Wan2.2-I2V-A14B",
    }


def test_live_rows_derive_only_documented_modalities():
    evidence = {
        "qwen/qwen3-32b": {
            "model_id": {"Qwen/Qwen3-32B"},
            "categories": {"vision", "reasoning"},
            "pages": {"https://docs.siliconflow.com/en/userguide/capabilities/vision"},
        },
        "wan-ai/wan2.2-i2v-a14b": {
            "model_id": {"Wan-AI/Wan2.2-I2V-A14B"},
            "categories": {"video_generation"},
            "pages": {"https://docs.siliconflow.com/en/userguide/capabilities/video"},
        },
    }

    rows = {row["model_id"]: row for row in build_live_rows(evidence)}
    assert rows["Qwen/Qwen3-32B"]["input_modalities"] == ["text", "image"]
    assert rows["Qwen/Qwen3-32B"]["supports_reasoning"] is True
    assert rows["Wan-AI/Wan2.2-I2V-A14B"]["input_modalities"] == ["text", "image"]
    assert rows["Wan-AI/Wan2.2-I2V-A14B"]["output_modalities"] == ["video"]


def test_merge_discards_old_mdx_fragments_and_retains_plausible_prior_ids():
    live = [
        {
            "model_id": "deepseek-ai/DeepSeek-R1",
            "extra": {},
        }
    ]
    previous = [
        {"model_id": "DeepSeek-R1", "extra": {}},
        {"model_id": "props:children:1:props:pageMetadata", "extra": {}},
        {"model_id": "Kimi-K2", "extra": {}},
    ]

    result = merge_previous(live, previous)
    by_id = {row["model_id"]: row for row in result}
    assert set(by_id) == {"deepseek-ai/DeepSeek-R1", "Kimi-K2"}
    assert by_id["Kimi-K2"]["extra"]["not_confirmed_by_current_public_docs"] is True
