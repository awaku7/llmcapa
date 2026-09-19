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
        ["search", "kling", "--columns", "provider,model_id,ctx", "--format", "csv", "--limit", "3"]
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
        ["search", PREFIX, "--columns", "provider,model_id", "--format", "csv", "--limit", "2"]
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
        ["search", PREFIX, "--format", "md", "--columns", "provider,model_id", "--limit", "2"]
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
    assert {d["provider"] for d in data} == {"typesafe", "openrouter"}


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
    rc = cli.main(["find", "embedding=true", "--columns", "provider,model_id,embedding", "--limit", "2"])
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
