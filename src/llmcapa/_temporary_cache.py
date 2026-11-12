"""Best-effort retention of regenerable user caches, not durable catalogs."""

import json
import math
import re
import stat
import tempfile
import time
from pathlib import Path

from ._user_catalog_cache import override_write_lock

DAY = 86400
LEGACY_RETENTION = 30 * DAY


def _identity(info):
    return [info.st_mtime_ns, info.st_ctime_ns, info.st_size, info.st_ino]


def _expiry_path(path):
    return path.with_suffix(".json.expiry")


def _atomic_text(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_temporary_cache(home, path, payload, ttl):
    """Keep existing JSON formats; publish data and retention metadata together."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with override_write_lock(home):
        _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
        info = path.stat()
        _atomic_text(
            _expiry_path(path),
            json.dumps(
                {
                    "identity": _identity(info),
                    "expires": info.st_mtime + ttl,
                }
            ),
        )


def _expired(path, info, now):
    if not stat.S_ISREG(info.st_mode):
        return False
    # Old releases did not record the caller's potentially custom TTL.
    deadline = info.st_mtime + LEGACY_RETENTION
    metadata = _expiry_path(path)
    try:
        if not stat.S_ISREG(metadata.lstat().st_mode):
            return False
        record = json.loads(metadata.read_text(encoding="utf-8"))
        expires = record["expires"]
        if (
            record["identity"] == _identity(info)
            and isinstance(expires, (int, float))
            and math.isfinite(expires)
            and expires >= info.st_mtime
        ):
            deadline = expires
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return now >= deadline


def _paths(home):
    yield home / "openrouter_cache.json"
    for path in home.glob("huggingface_all_tasks_cache_*.json"):
        if re.fullmatch(
            r"huggingface_all_tasks_cache_(all|limit_[1-9][0-9]*)\.json", path.name
        ):
            yield path
    github = home / "github_catalog_cache"
    if not github.is_symlink():
        for path in github.glob("*.json"):
            if re.fullmatch(r"[0-9a-f]{64}\.json", path.name):
                yield path


def cleanup_temporary_caches(home, now=None):
    """Remove only recognized expired cache files; never delete user overrides."""
    now = time.time() if now is None else now
    try:
        if home.is_symlink() or not home.is_dir():
            return
        for path in _paths(home):
            try:
                info = path.lstat()
                if not _expired(path, info, now):
                    continue
                with override_write_lock(home, timeout=0):
                    current = path.lstat()
                    if _identity(current) != _identity(info):
                        continue
                    if not _expired(path, current, now):
                        continue
                    path.unlink()
                    _expiry_path(path).unlink(missing_ok=True)
            except OSError:
                # Never wait for a publisher; locked files and read-only homes are OK.
                continue
    except OSError:
        return
