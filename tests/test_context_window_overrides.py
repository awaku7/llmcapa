from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _metadata_loader  # noqa: E402


def test_context_window_fallback_fills_unknown_with_provenance() -> None:
    row = {"provider": "moonshot", "model_id": "kimi-k3", "context_window": 0}

    applied = _metadata_loader.apply_context_window_overrides([row])

    override = _metadata_loader.context_window_override("moonshot", "kimi-k3")
    assert override is not None
    assert applied == 1
    assert row["context_window"] == override["context_window"]
    assert row["extra"]["context_window_source"] == override["source"]


def test_context_window_fallback_does_not_replace_live_value() -> None:
    row = {"provider": "moonshot", "model_id": "kimi-k3", "context_window": 123456}

    applied = _metadata_loader.apply_context_window_overrides([row])

    assert applied == 0
    assert row["context_window"] == 123456


def test_context_window_fallback_leaves_unknown_models_unknown() -> None:
    row = {"provider": "unknown-provider", "model_id": "unknown-model", "context_window": 0}

    applied = _metadata_loader.apply_context_window_overrides([row])

    assert applied == 0
    assert row["context_window"] == 0
    assert "extra" not in row


def test_moonshot_updater_reads_context_from_metadata() -> None:
    import _update_moonshot

    rows = _update_moonshot.build()
    by_id = {row["model_id"]: row for row in rows}
    for model_id in ("kimi-k3", "moonshot-v1-8k", "moonshot-v1-32k"):
        override = _metadata_loader.context_window_override("moonshot", model_id)
        assert override is not None
        assert by_id[model_id]["context_window"] == override["context_window"]


def test_static_provider_updaters_load_contexts_from_metadata() -> None:
    import _update_minimax
    import _update_nvidia
    import _update_qwen

    minimax = {row["model_id"]: row for row in _update_minimax.build_models()}
    nvidia = {row["model_id"]: row for row in _update_nvidia.UPSERTS}
    qwen_spec = _update_qwen.FLAGSHIP_TEXT["qwen3.7-max"]
    assert "context_window" not in qwen_spec
    qwen = _update_qwen.make_text_model("qwen3.7-max", qwen_spec)
    _metadata_loader.apply_context_window_overrides([qwen])

    for provider, rows in (
        ("minimax", minimax),
        ("nvidia", nvidia),
        ("qwen", {"qwen3.7-max": qwen}),
    ):
        model_id = {
            "minimax": "MiniMax-M3",
            "nvidia": "nemotron-3-ultra-550b-a55b",
            "qwen": "qwen3.7-max",
        }[provider]
        override = _metadata_loader.context_window_override(provider, model_id)
        assert override is not None
        assert rows[model_id]["context_window"] == override["context_window"]


def test_microsoft_base_uses_documented_context_and_unknown_service_stays_zero() -> None:
    import _update_microsoft

    model = _update_microsoft.base(
        model_id="Phi-4",
        display="Phi-4",
        ctx=999999,
        max_out=16384,
        pricing=None,
    )
    service = _update_microsoft.service(
        "Azure-AI-Content-Safety", "Azure AI Content Safety"
    )

    assert model["context_window"] == 16384
    assert model["extra"]["context_window_source"].startswith("https://")
    assert service["context_window"] == 0


def test_anthropic_template_uses_metadata_instead_of_name_guess() -> None:
    import _update_anthropic

    template = _update_anthropic._template(
        {
            "name": "Claude Opus 4.6",
            "input": 1.0,
            "output": 2.0,
            "cache_5m": None,
            "cache_1h": None,
            "cache_hit": None,
            "deprecated": False,
        }
    )
    assert template["context_window"] == 0

    _metadata_loader.apply_context_window_overrides([template])
    override = _metadata_loader.context_window_override(
        "anthropic", template["model_id"]
    )
    assert override is not None
    assert template["context_window"] == override["context_window"]


def test_granite_base_and_long_context_are_distinct_metadata() -> None:
    override = _metadata_loader.context_window_override(
        "ibm-granite", "granite-4.2-30b"
    )

    assert override is not None
    assert override["context_window"] == 128000
    assert override["long_context_window"] == 512000


def test_cohere_context_parser_accepts_documented_suffixes() -> None:
    from _update_cohere import _parse_token_count

    assert _parse_token_count(r"Context Window:", "Context Window: 256K") == 256000
    assert _parse_token_count(r"Max Output Tokens:", "Max Output Tokens: 8,000") == 8000
