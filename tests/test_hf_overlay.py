"""Lossless, source-relative local inference catalog representation."""

from __future__ import annotations

from llmcapa.hf_overlay import expand_hf_overlay, is_hf_overlay, pack_hf_overlay


def _source():
    return {
        "models": [
            {
                "provider": "huggingface",
                "model_id": "org/base",
                "display_name": "org/base",
                "aliases": ["base"],
                "license_type": "apache-2.0",
                "context_window": 8192,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supports_vision": False,
                "supports_function_calling": None,
                "supports_chat_completion": None,
                "pipeline_tag": "text-generation",
                "downloads": 12,
                "likes": 3,
            },
            {
                "provider": "huggingface",
                "model_id": "org/vision",
                "display_name": "org/vision",
                "aliases": ["vision"],
                "license_type": "mit",
                "context_window": 0,
                "input_modalities": ["image", "text"],
                "output_modalities": ["text"],
                "supports_vision": True,
                "supports_function_calling": None,
                "supports_chat_completion": None,
                "pipeline_tag": "image-text-to-text",
                "downloads": 4,
                "likes": 2,
            },
        ]
    }


def _local(provider):
    source = _source()
    records = []
    for hf in source["models"]:
        record = {
            "provider": provider,
            "model_id": hf["model_id"],
            "display_name": hf["display_name"],
            "aliases": hf["aliases"],
            "license_type": hf["license_type"],
            "context_window": hf["context_window"],
            "max_output_tokens": 0,
            "input_modalities": hf["input_modalities"],
            "output_modalities": hf["output_modalities"],
            "supports_vision": hf["supports_vision"],
            "supports_function_calling": hf["supports_function_calling"],
            "supports_chat_completion": True,
            "extra": {
                "metadata_source": "huggingface",
                "metadata_source_checked_at": "2026-11-06",
                "huggingface_model_id": hf["model_id"],
                "huggingface_model_url": f"https://huggingface.co/{hf['model_id']}",
                "huggingface_pipeline_tag": hf["pipeline_tag"],
                "huggingface_downloads": hf["downloads"],
                "huggingface_likes": hf["likes"],
                "endpoints": [{"base_url": "http://localhost:8000/v1"}],
            },
        }
        records.append(record)
    records[1]["model_id"] = "ORG/Vision"
    records[1]["supports_vision"] = False
    records[1]["extra"]["evidence"] = {"source": "verified"}
    records.append(
        {
            "provider": provider,
            "model_id": "local-only",
            "display_name": "Installed local model",
            "context_window": 1024,
            "max_output_tokens": 0,
            "extra": {"server": "local"},
        }
    )
    return {"models": records}


def test_all_local_providers_round_trip():
    for provider in ("vllm", "llama-cpp", "lmstudio"):
        expected = _local(provider)
        encoded = pack_hf_overlay(_source(), expected, provider=provider)
        assert is_hf_overlay(encoded)
        expanded = expand_hf_overlay(_source(), encoded)
        assert {m["model_id"]: m for m in expanded["models"]} == {
            m["model_id"]: m for m in expected["models"]
        }
        assert any(row["model_id"] == "local-only" for row in expanded["models"])
        assert len(encoded["unmatched"]) == 1


def test_expanded_overlay_has_no_fabricated_unlisted_hf_models():
    source = _source()
    catalog = _local("vllm")
    catalog["models"] = catalog["models"][:1]
    packed = pack_hf_overlay(source, catalog, provider="vllm")
    assert packed["excluded"] == ["org/vision"]
    expanded = expand_hf_overlay(source, packed)
    assert expanded == catalog
