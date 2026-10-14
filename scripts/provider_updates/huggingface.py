"""Compatibility wrapper for the Hugging Face popularity catalog updater."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    updater = ROOT / "scripts" / "_scrape_huggingface.py"
    return subprocess.run([sys.executable, str(updater), "--save"], cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
