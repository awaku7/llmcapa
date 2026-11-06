"""Migrate local inference catalogs to lossless Hugging Face overlays.

This is an explicit on-repository data migration, not a network updater.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmcapa.hf_overlay import (
    expand_hf_overlay,
    is_hf_overlay,
    pack_hf_overlay,
)

DATA_DIR = ROOT / "src" / "llmcapa" / "data"


def main() -> None:
    source = json.loads((DATA_DIR / "huggingface.json").read_text(encoding="utf-8"))
    for provider, filename in (
        ("vllm", "vllm.json"),
        ("llama-cpp", "llama_cpp.json"),
        ("lmstudio", "lmstudio.json"),
    ):
        path = DATA_DIR / filename
        previous = json.loads(path.read_text(encoding="utf-8"))
        if is_hf_overlay(previous):
            previous = expand_hf_overlay(source, previous)
        encoded = pack_hf_overlay(source, previous, provider=provider)
        expanded = expand_hf_overlay(source, encoded)
        expected = {row["model_id"].casefold(): row for row in previous["models"]}
        actual = {row["model_id"].casefold(): row for row in expanded["models"]}
        if actual != expected:
            raise AssertionError(f"{provider}: overlay round-trip changed model facts")
        before_size = path.stat().st_size
        path.write_text(
            json.dumps(encoded, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"{provider}: models={len(actual)} "
            f"HF_refs={len(source['models']) - len(encoded['excluded'])} "
            f"overrides={len(encoded['overrides'])} "
            f"unmatched={len(encoded['unmatched'])} "
            f"bytes={before_size}->{path.stat().st_size}",
            flush=True,
        )


if __name__ == "__main__":
    main()
