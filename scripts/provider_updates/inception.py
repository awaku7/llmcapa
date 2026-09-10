"""Compatibility entry point for the Inception catalog updater.

The canonical updater is ``scripts/_update_inception.py``.  Keep this path
working for callers that use the older provider_updates layout.
"""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "scripts" / "_update_inception.py"


def main() -> None:
    runpy.run_path(str(UPDATER), run_name="__main__")


if __name__ == "__main__":
    main()
