"""CLI tests: sorting, limits, units, columns, formats, exit codes, find."""

from __future__ import annotations

import json

import llmcapa
from llmcapa import cli

# A prefix that matches both active and deprecated models in the bundled data.
PREFIX = "claude"


def test_units_formatting():
    assert cli._fmt_tokens(0) == "-"
    assert cli._fmt_tokens(None) == "-"
    assert cli._fmt_tokens(512) == "512"
    assert cli._fmt_tokens(4095) == "4.1K"
    assert cli._fmt_tokens(65536) == "65.5K"
    assert cli._fmt_tokens(131072) == "131K"
    assert cli._fmt_tokens(1048576) == "1M"


def test_deprecated_hidden_by_default(capsys):
    rc = cli.main(["search", PREFIX, "--limit", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "claude-3-opus-20240229" not in out
    assert "claude" in out


def test_deprecated_ordered_last_and_flag_column(capsys):
    rc = cli.main(["search", PREFIX, "--all", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    flags = [d["deprecated"] for d in data]
    assert flags == sorted(flags)
    assert False in flags and True in flags


def test_limit_keeps_active_models(capsys):
    rc = cli.main(["search", PREFIX, "--all", "--limit", "5", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 5
    assert not any(d["deprecated"] for d in data)


def test_limit_applied_after_sort(capsys):
    rc = cli.main(
        ["search", PREFIX, "--all", "--limit", "5", "--sort=-ctx", "--format", "json"]
    )
    assert rc == 0
    ctx = [d["context_window"] for d in json.loads(capsys.readouterr().out)]
    assert ctx == sorted(ctx, reverse=True)


def test_sort_desc_suffix(capsys):
    rc = cli.main(
        ["search", PREFIX, "--limit", "5", "--sort", "ctx:desc", "--format", "json"]
    )
    assert rc == 0
    ctx = [d["context_window"] for d in json.loads(capsys.readouterr().out)]
    assert ctx == sorted(ctx, reverse=True)


def test_unknown_sort_key_is_error(capsys):
    assert cli.main(["search", PREFIX, "--sort", "bogus"]) == 2
    assert "bogus" in capsys.readouterr().err


def test_unknown_units_render_dash(capsys):
    rc = cli.main(
        [
            "search",
            "kling",
            "--columns",
            "provider,model_id,ctx",
            "--format",
            "csv",
            "--limit",
            "3",
        ]
    )
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "provider,model_id,ctx"
    assert lines[1].endswith(",-")


def test_machine_formats_use_explicit_deprecated_column(capsys):
    rc = cli.main(["search", PREFIX, "--format", "csv", "--limit", "1"])
    assert rc == 0
    header = capsys.readouterr().out.splitlines()[0]
    assert header.startswith("deprecated,")


def test_columns_csv_and_unknown_column(capsys):
    rc = cli.main(
        [
            "search",
            PREFIX,
            "--columns",
            "provider,model_id",
            "--format",
            "csv",
            "--limit",
            "2",
        ]
    )
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "provider,model_id"
    assert len(lines) == 3
    assert cli.main(["search", PREFIX, "--columns", "bogus"]) == 2


def test_no_match_exit_codes(capsys):
    assert cli.main(["search", "zzzz-no-such-model-prefix"]) == 1
    assert "no models matching" in capsys.readouterr().err
    assert cli.main(["search", "zzzz-no-such-model-prefix", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == []
    assert cli.main(["search", "zzzz-no-such-model-prefix", "--allow-empty"]) == 0
    capsys.readouterr()


def test_list_uses_shared_renderer(capsys):
    rc = cli.main(["list", "--provider", "anthropic", "--limit", "3"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VTRJS" in out
    assert "model_id" in out


def test_no_deprecated_flag_is_accepted(capsys):
    assert cli.main(["list", "--no-deprecated", "--limit", "1"]) == 0
    capsys.readouterr()


def test_markdown_format(capsys):
    rc = cli.main(
        [
            "search",
            PREFIX,
            "--format",
            "md",
            "--columns",
            "provider,model_id",
            "--limit",
            "2",
        ]
    )
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "| provider | model_id |"
    assert set(lines[1].replace("|", "").split()) == {"---"}
    assert len(lines) == 4


def test_width_clipping(capsys):
    rc = cli.main(["search", "gpt", "--limit", "3", "--width", "60"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "..." in out


def test_cap_flag_semantics():
    # A verified decision record reports yes.
    assert cli._cap_flag(llmcapa.get("jev-1.13.0"), "decision") == "yes"
    # Image input without an image record stays unknown, not "yes".
    assert cli._cap_flag(llmcapa.get("claude-fable-5"), "image") == "?"
    # No record and no modality means unsupported.
    assert cli._cap_flag(llmcapa.get("claude-fable-5"), "decision") == "-"


def test_find_decision_models(capsys):
    rc = cli.main(["find", "decision=true", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data and all(d["decision"]["decision"] is True for d in data)
    assert {d["provider"] for d in data} == {
        "openai",
        "typesafe",
        "openrouter",
        "laya",
        "cloudflare-workers-ai",
        "liquid",
        "perplexity",
        "microsoft",
        "google",
    }


def test_find_bare_name_and_min_context(capsys):
    rc = cli.main(["find", "decision", "--min-context", "64000", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data and all(d["context_window"] >= 64000 for d in data)


def test_find_bool_words_and_invalid_value(capsys):
    rc = cli.main(["find", "vision=false", "--limit", "2", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert all(d["supports_vision"] is False for d in data)
    assert cli.main(["find", "decision=maybe"]) == 2
    assert "invalid feature filter" in capsys.readouterr().err


def test_find_no_match_exit_code(capsys):
    assert cli.main(["find", "decision=true", "--provider", "anthropic"]) == 1
    assert "no models matching" in capsys.readouterr().err


def test_find_render_options(capsys):
    rc = cli.main(
        [
            "find",
            "embedding=true",
            "--columns",
            "provider,model_id,embedding",
            "--limit",
            "2",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    header = out.splitlines()[0].split()
    assert header == ["provider", "model_id", "embedding"]


def test_decision_columns(capsys):
    rc = cli.main(
        [
            "find",
            "decision=true",
            "--provider",
            "typesafe",
            "--columns",
            "provider,model_id,decision,q_kinds,pck,state",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "q_kinds" in out and "PCK" in out and "state" in out
    assert "yes" in out and "choice,score,noul" in out and "PCK" in out


def test_wide_columns_include_capability_records(capsys):
    rc = cli.main(["search", "typesafe", "--all", "--wide"])
    out = capsys.readouterr().out
    assert rc == 0
    header = out.splitlines()[0]
    for name in ("decision", "image", "audio", "video"):
        assert name in header


def test_capability_sort_key(capsys):
    assert cli.main(["search", "typesafe", "--all", "--sort", "decision"]) == 0
    capsys.readouterr()
    assert cli.main(["search", "typesafe", "--all", "--sort=-decision"]) == 0
    capsys.readouterr()


def test_show_flattens_nested_records(capsys):
    rc = cli.main(["show", "jev-1.13.0"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "decision.question_kinds" in out
    assert "choice, score, noul" in out
    assert "pricing.input_per_1m" in out
    assert "{" not in out


def test_registry_search_orders_active_first():
    caps = llmcapa.search(PREFIX, include_deprecated=True)
    flags = [c.deprecated for c in caps]
    assert flags == sorted(flags)
    limited = llmcapa.search(PREFIX, include_deprecated=True, limit=5)
    assert limited and not any(c.deprecated for c in limited)


def test_fetch_github_cli_forces_refresh_when_requested(monkeypatch, capsys):
    calls = {}

    class DummyRegistry:
        def fetch_github_catalog(self, **kwargs):
            progress = kwargs.pop("progress_callback")
            progress("Downloading GitHub file 1/1: openai.json")
            calls.update(kwargs)
            return 3

    monkeypatch.setattr(cli, "default_registry", lambda: DummyRegistry())
    assert (
        cli.main(["fetch-github", "--provider", "openai", "--ref", "main", "--refresh"])
        == 0
    )
    assert calls == {"provider": "openai", "ref": "main", "cache_ttl": 0}
    captured = capsys.readouterr()
    assert "registered 3 models" in captured.out.lower()
    assert "downloading github file 1/1" in captured.err.lower()


def test_update_openrouter_and_bare_update(monkeypatch, capsys):
    calls = []

    class DummyRegistry:
        def fetch_openrouter(self, **kwargs):
            progress = kwargs.pop("progress_callback")
            progress("Registered 12 OpenRouter models")
            calls.append(kwargs)
            return 7

    monkeypatch.setattr(cli, "default_registry", lambda: DummyRegistry())
    assert cli.main(["update", "openrouter"]) == 0
    captured = capsys.readouterr()
    assert "registered 12 openrouter models" in captured.err.lower()
    # Keep the former bare `update` invocation working as an OpenRouter alias.
    assert cli.main(["update"]) == 0
    capsys.readouterr()
    assert calls == [{"cache_ttl": 0}, {"cache_ttl": 0}]


def test_update_hf_cli_fetches_all_pages_and_shows_progress(monkeypatch, capsys):
    calls = []

    class DummyRegistry:
        def fetch_huggingface(self, **kwargs):
            progress = kwargs.pop("progress_callback")
            progress("Downloaded 200 HuggingFace models across 2 pages")
            calls.append(kwargs)
            return 200

    monkeypatch.setattr(cli, "default_registry", lambda: DummyRegistry())
    assert cli.main(["update", "hf"]) == 0
    captured = capsys.readouterr()
    assert "registered 200 models" in captured.out.lower()
    assert "downloaded 200 huggingface models across 2 pages" in captured.err.lower()
    # Keep the former flat command working while promoting the nested spelling.
    assert cli.main(["fetch-hf"]) == 0
    assert "registered 200 models" in capsys.readouterr().out.lower()
    assert calls == [{"cache_ttl": 0}] * 2


def test_update_github_cli_forces_refresh_when_requested(monkeypatch, capsys):
    calls = {}

    class DummyRegistry:
        def fetch_github_catalog(self, **kwargs):
            progress = kwargs.pop("progress_callback")
            progress("Downloading GitHub file 1/1: openai.json")
            calls.update(kwargs)
            return 3

    monkeypatch.setattr(cli, "default_registry", lambda: DummyRegistry())
    assert (
        cli.main(["update", "gh", "--provider", "openai", "--ref", "main", "--refresh"])
        == 0
    )
    assert calls == {"provider": "openai", "ref": "main", "cache_ttl": 0}
    captured = capsys.readouterr()
    assert "registered 3 models" in captured.out.lower()
    assert "downloading github file 1/1" in captured.err.lower()


def test_regions_command_lists_known_regions(capsys):
    rc = cli.main(["regions"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "japaneast" in out
    assert "ap-northeast-1" in out


def test_regions_command_provider_filter(capsys):
    rc = cli.main(["regions", "--provider", "azure-foundry"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "japaneast" in out
    assert "ap-northeast-1" not in out


def test_regions_command_global_is_opt_in(capsys):
    # vertex-ai records use the global_endpoint flag (no literal "global"
    # location), so "global" appears only with --global.
    rc = cli.main(["regions", "--provider", "vertex-ai"])
    assert rc == 0
    assert "global" not in capsys.readouterr().out.splitlines()
    rc = cli.main(["regions", "--provider", "vertex-ai", "--global"])
    assert rc == 0
    assert "global" in capsys.readouterr().out.splitlines()


def test_list_region_filter(capsys):
    rc = cli.main(
        [
            "list",
            "--provider",
            "azure-foundry",
            "--region",
            "japaneast",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data
    assert any(d["model_id"] == "gpt-4o" for d in data)
    for entry in data:
        assert entry["provider"] == "azure-foundry"
        assert "japaneast" in entry["regions"]["locations"]


def test_find_region_filter_and_regions_column(capsys):
    rc = cli.main(
        [
            "find",
            "--provider",
            "amazon",
            "--region",
            "ap-northeast-1",
            "--columns",
            "provider,model_id,regions",
            "--format",
            "csv",
            "--limit",
            "5",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    lines = out.strip().splitlines()
    assert lines[0] == "provider,model_id,regions"
    assert len(lines) > 1
    for line in lines[1:]:
        assert "ap-northeast-1" in line


def test_find_region_no_match_is_error(capsys):
    rc = cli.main(["find", "--provider", "amazon", "--region", "japaneast"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "region: japaneast" in captured.err


def test_search_region_filter_narrows_results(capsys):
    rc = cli.main(["search", "claude", "--format", "json"])
    assert rc == 0
    all_hits = json.loads(capsys.readouterr().out)
    rc = cli.main(
        ["search", "claude", "--region", "ap-northeast-1", "--format", "json"]
    )
    assert rc == 0
    region_hits = json.loads(capsys.readouterr().out)
    assert 0 < len(region_hits) < len(all_hits)


def test_search_contains_matches_substring(capsys):
    assert cli.main(["search", "onnet"]) == 1
    capsys.readouterr()
    rc = cli.main(["search", "onnet", "--contains", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data
    assert any("sonnet" in d["model_id"].lower() for d in data)
    for entry in data:
        fields = [entry["model_id"], entry["display_name"] or "", *entry["aliases"]]
        assert any("onnet" in field.lower() for field in fields)


def test_show_provider_option(capsys):
    rc = cli.main(["show", "gpt-4o", "--provider", "azure-foundry", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "azure-foundry"
    assert "japaneast" in data["regions"]["locations"]


def test_show_unknown_model_suggests_near_matches(capsys):
    rc = cli.main(["show", "gpt-4oo"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "model not found: gpt-4oo" in captured.err
    assert "did you mean:" in captured.err
    assert "gpt-4o (azure-foundry)" in captured.err


def test_providers_counts(capsys):
    rc = cli.main(["providers", "--counts"])
    out = capsys.readouterr().out
    assert rc == 0
    lines = {line.split()[0]: line for line in out.strip().splitlines()}
    assert "amazon" in lines
    count = int(lines["amazon"].split()[-1])
    assert count > 100
    rc = cli.main(["providers"])
    plain = capsys.readouterr().out
    assert rc == 0
    assert "amazon" in plain.strip().splitlines()


def test_regions_column_shows_global_endpoint(capsys):
    rc = cli.main(
        [
            "list",
            "--provider",
            "vertex-ai",
            "--region",
            "global",
            "--columns",
            "model_id,regions",
            "--format",
            "csv",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    row = next(
        line for line in out.splitlines() if line.startswith("gemini-3-flash-preview,")
    )
    assert "global" in row


def test_regions_unknown_provider_is_error(capsys):
    rc = cli.main(["regions", "--provider", "bogus-provider"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "unknown provider: bogus-provider" in captured.err


def test_regions_known_provider_without_region_data(capsys):
    rc = cli.main(["regions", "--provider", "huggingface"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""


def test_search_contains_covers_all_providers(capsys):
    rc = cli.main(["search", "gemini-3-flash-preview", "--format", "json"])
    assert rc == 0
    prefix_providers = {d["provider"] for d in json.loads(capsys.readouterr().out)}
    rc = cli.main(
        ["search", "gemini-3-flash-preview", "--contains", "--format", "json"]
    )
    assert rc == 0
    contains_providers = {d["provider"] for d in json.loads(capsys.readouterr().out)}
    # The flat first-registered-wins mapping would hide the vertex-ai and
    # ollama records behind the google one.
    assert contains_providers == prefix_providers
    assert "vertex-ai" in contains_providers


def test_regions_provider_alias_and_case(capsys):
    rc = cli.main(["regions", "--provider", "azure"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "japaneast" in out
    rc = cli.main(["regions", "--provider", "Azure-Foundry"])
    assert rc == 0
    assert "japaneast" in capsys.readouterr().out


def test_help_omits_legacy_commands(capsys):
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "SUPPRESS" not in out
    assert "fetch-hf" not in out
    assert "fetch-github" not in out
