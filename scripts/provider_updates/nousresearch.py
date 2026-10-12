"""Compatibility wrapper for the provider-scoped NousResearch HF inventory updater."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    updater = ROOT / "scripts" / "_update_hf_official_orgs.py"
    return subprocess.run(
        [sys.executable, str(updater), "--provider", "nousresearch"],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
