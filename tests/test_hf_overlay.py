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


def test_remote_overlay_refresh_support(tmp_path, monkeypatch):
    import json
    from io import BytesIO

    from llmcapa.registry import Registry

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    registry = Registry()
    registry._ensure_loaded()
    source = _source()
    registry._hf_catalog_source = source
    payload = pack_hf_overlay(source, _local("vllm"), provider="vllm")
    raw = json.dumps(payload).encode("utf-8")
    requests = []

    def fake_urlopen(request, context=None, timeout=None):
        requests.append(request.full_url)
        if request.full_url.endswith("/huggingface.json"):
            return BytesIO(json.dumps(source).encode("utf-8"))
        return BytesIO(raw)

    monkeypatch.setattr("llmcapa.registry.urllib.request.urlopen", fake_urlopen)
    count = registry.fetch_github_catalog("vllm", cache_ttl=0, write_bundled=False)
    assert count == 3
    assert registry.get("local-only", provider="vllm").context_window == 1024
    assert (
        registry.fetch_github_catalog("vllm", cache_ttl=86400, write_bundled=False) == 3
    )
    assert len(requests) == 2


def test_hf_refresh_reconciles_previously_unmatched_model():
    from copy import deepcopy

    old_source = _source()
    original = _local("lmstudio")
    packed = pack_hf_overlay(old_source, original, provider="lmstudio")
    assert len(packed["unmatched"]) == 1

    new_source = deepcopy(old_source)
    new_hf = deepcopy(new_source["models"][0])
    new_hf["model_id"] = "LOCAL-ONLY"
    new_source["models"].append(new_hf)

    expanded = expand_hf_overlay(new_source, packed)
    actual = {model["model_id"].casefold(): model for model in expanded["models"]}
    assert len(actual) == 3
    assert actual["local-only"] == original["models"][-1]
    assert not any(model["model_id"] == "LOCAL-ONLY" for model in expanded["models"])

    rebased = pack_hf_overlay(new_source, expanded, provider="lmstudio")
    assert expand_hf_overlay(new_source, rebased) == expanded


def test_remote_overlay_uses_matching_newer_hf_snapshot(tmp_path, monkeypatch):
    import json
    from copy import deepcopy
    from io import BytesIO

    from llmcapa.registry import Registry

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    old_source = _source()
    new_source = deepcopy(old_source)
    new_model = deepcopy(new_source["models"][0])
    new_model["model_id"] = "org/new-on-remote"
    new_source["models"].append(new_model)
    local = _local("vllm")
    local["models"].append(
        {
            "provider": "vllm",
            "model_id": "org/new-on-remote",
            "display_name": "New remote model",
            "max_output_tokens": 321,
            "context_window": 4096,
            "extra": {"backend": "vllm"},
        }
    )
    remote_overlay = pack_hf_overlay(new_source, local, provider="vllm")
    registry = Registry()
    registry._ensure_loaded()
    registry._hf_catalog_source = old_source

    calls = []

    def fake_urlopen(request, context=None, timeout=None):
        calls.append(request.full_url)
        body = (
            json.dumps(new_source)
            if request.full_url.endswith("/huggingface.json")
            else json.dumps(remote_overlay)
        )
        return BytesIO(body.encode("utf-8"))

    monkeypatch.setattr("llmcapa.registry.urllib.request.urlopen", fake_urlopen)
    count = registry.fetch_github_catalog("vllm")
    assert count == 4
    assert registry.get("org/new-on-remote", provider="vllm").max_output_tokens == 321
    assert len(calls) == 2
    # The installed HF source was not overwritten, and the remote results are
    # durable even if the registry is rebuilt while offline.
    offline = Registry()
    cap = offline.get("org/new-on-remote", provider="vllm")
    assert cap.max_output_tokens == 321
    assert len(calls) == 2


def test_all_catalog_postprocessors_preserve_overlay_format(tmp_path):
    import json
    from copy import deepcopy

    from scripts import (
        _audio_capability_postprocess,
        _image_capability_postprocess,
        _structured_capability_postprocess,
        _video_capability_postprocess,
    )

    source = _source()
    source["models"] = [deepcopy(source["models"][0])]
    hf = source["models"][0]
    hf["model_id"] = "org/image-generator"
    hf["input_modalities"] = ["text", "audio", "video", "file"]
    hf["output_modalities"] = ["image", "audio", "video", "embedding"]
    local = deepcopy(hf)
    local.update({"provider": "vllm", "max_output_tokens": 1024})
    local["extra"] = {"backend": "vllm"}
    packed = pack_hf_overlay(source, {"models": [local]}, provider="vllm")

    (tmp_path / "huggingface.json").write_text(json.dumps(source), encoding="utf-8")
    catalog_path = tmp_path / "vllm.json"
    catalog_path.write_text(json.dumps(packed), encoding="utf-8")

    assert _image_capability_postprocess.audit(tmp_path)["image_output_records"] >= 1
    assert _audio_capability_postprocess.audit(tmp_path).get("vllm", 0) >= 1
    assert _video_capability_postprocess.audit(tmp_path).get("vllm", 0) >= 1
    for module in (
        _image_capability_postprocess,
        _audio_capability_postprocess,
        _video_capability_postprocess,
        _structured_capability_postprocess,
    ):
        module.apply(tmp_path)
        current = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert is_hf_overlay(current)
        assert "models" not in current

    model = expand_hf_overlay(source, current)["models"][0]
    assert model["image"]["generation"] is True
    assert model["audio"]["speech_generation"] is True
    assert model["video"]["generation"] is True
    assert model["document"]["accepts_file"] is True
    assert model["embedding"]["embedding"] is True
    assert model["extra"] == local["extra"]
