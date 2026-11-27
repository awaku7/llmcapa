"""CLI rendering and sorting for API-surface capability columns."""

from __future__ import annotations

import csv

from llmcapa import cli


def test_api_surface_columns_and_wide(capsys) -> None:
    rc = cli.main(
        [
            "find",
            "interactions_api=true",
            "--provider",
            "google",
            "--columns",
            "provider,model_id,responses_api,interactions_api,google_api,anthropic_api",
            "--limit",
            "1",
            "--format",
            "csv",
        ]
    )
    assert rc == 0
    rows = list(csv.reader(capsys.readouterr().out.splitlines()))
    assert rows[0] == [
        "provider",
        "model_id",
        "responses_api",
        "interactions_api",
        "google_api",
        "anthropic_api",
    ]
    assert rows[1][2:] == ["no", "yes", "yes", "no"]

    rc = cli.main(["list", "--provider", "google", "--wide", "--limit", "1"])
    assert rc == 0
    header = capsys.readouterr().out.splitlines()[0]
    for name in ("responses_api", "interactions_api", "google_api", "anthropic_api"):
        assert name in header


def test_api_surface_sort_keys(capsys) -> None:
    for key in ("responses_api", "interactions_api", "google_api", "anthropic_api"):
        rc = cli.main(
            ["list", "--provider", "google", f"--sort=-{key}", "--limit", "1"]
        )
        assert rc == 0
        capsys.readouterr()
