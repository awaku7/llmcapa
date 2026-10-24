from __future__ import annotations

import json

from scripts.provider_updates._catalog_io import load_json, save_json


def test_catalog_json_io_preserves_unicode_format_and_final_newline(tmp_path):
    path = tmp_path / "catalog.json"
    payload = {"models": [{"model_id": "example/model", "display_name": "日本語モデル"}]}

    save_json(path, payload)

    expected = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    assert path.read_text(encoding="utf-8") == expected
    assert load_json(path) == payload
