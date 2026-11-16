"""Verify llmcapa's Windows catalog-stamp fix on a real NTFS volume.

Background: the catalog stamp trusts a database when [size, mtime,
change_time, inode] of every source file still match. On Windows,
Python's st_ctime is the *creation* time, so the fix reads the NTFS
ChangeTime via GetFileInformationByHandleEx instead. This script
reproduces the attack the fix defends against:

  1. write a file and record llmcapa's _file_stat() for it,
  2. rewrite it in place with different content of the same length,
  3. restore the original mtime with os.utime (SetFileTime), which
     cannot touch ChangeTime,
  4. check that _file_stat() still changed -- via the ChangeTime slot.

Run on Windows, on an NTFS volume, with llmcapa importable (from a
repo checkout this script picks up ./src automatically):

    python verify_stamp_windows.py

Exit code 0 means every check passed.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

if os.name != "nt":
    sys.exit("This check only means anything on Windows (os.name == 'nt').")

for _candidate in (Path(__file__).parent / "src", Path(__file__).parent.parent / "src"):
    if _candidate.is_dir():
        sys.path.insert(0, str(_candidate))
        break

from llmcapa import _catalog_index

failures = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


with tempfile.TemporaryDirectory() as directory:
    target = Path(directory) / "probe.json"
    target.write_bytes(b'{"models": ["aaaaaaaaaaaaaaaaaaaa"]}')
    before = _catalog_index._file_stat(target)
    change_before = _catalog_index._windows_change_time_ns(target)
    creation_before = target.stat().st_ctime_ns

    check("ChangeTime API returns a value", change_before is not None)

    time.sleep(0.1)
    # Same-length in-place rewrite, then forge the mtime back.
    with target.open("r+b") as handle:
        handle.write(b'{"models": ["bbbbbbbbbbbbbbbbbbbb"]}')
    stat_now = target.stat()
    os.utime(target, ns=(stat_now.st_atime_ns, before[1]))

    after = _catalog_index._file_stat(target)
    change_after = _catalog_index._windows_change_time_ns(target)

    check(
        "attack setup: size and mtime are indistinguishable",
        after[0] == before[0] and after[1] == before[1],
        f"size {before[0]}->{after[0]}, mtime {before[1]}->{after[1]}",
    )
    check(
        "python st_ctime (creation time) is fooled, as expected",
        target.stat().st_ctime_ns == creation_before,
    )
    check(
        "ChangeTime advanced despite the forged mtime",
        change_after is not None
        and change_before is not None
        and change_after > change_before,
        f"{change_before} -> {change_after}",
    )
    check(
        "llmcapa _file_stat differs, so the stamp will not be trusted",
        after != before,
        f"change slot {before[2]} -> {after[2]}",
    )

if failures:
    sys.exit(f"\n{len(failures)} check(s) failed")
print("\nAll checks passed: the stamp fix holds on this machine.")
