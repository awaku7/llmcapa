from __future__ import annotations

import json

from llmcapa._catalog_format import dump_catalog


def test_dump_catalog_keeps_every_field_one_record_per_line():
    payload = {
        "models": [
            {
                "provider": "example",
                "model_id": "model-1",
                "context_window": 0,
                "max_output_tokens": 0,
                "deprecated": False,
                "aliases": [],
            },
            {
                "provider": "example",
                "model_id": "model-2",
                "context_window": 4096,
            },
        ]
    }
    text = dump_catalog(payload)
    # The compact form parses back to exactly the same payload: no field
    # is dropped or altered, including default-valued ones.
    assert json.loads(text) == payload
    lines = text.splitlines()
    assert lines[0] == "{"
    assert lines[1] == '"models": ['
    assert lines[-2] == "]"
    assert lines[-1] == "}"
    assert len(lines) == 6  # header, two record lines, footer
    assert lines[2].endswith(",")
    assert json.loads(lines[2].rstrip(",")) == payload["models"][0]
    assert json.loads(lines[3]) == payload["models"][1]


def test_dump_catalog_falls_back_for_other_shapes():
    payload = {"_format": "hf-model-overlay-v1", "overrides": {"a": {}}}
    assert json.loads(dump_catalog(payload)) == payload
