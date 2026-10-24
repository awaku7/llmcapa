"""Small standard-library HTTP helpers for provider catalog updaters.

Provider-specific request validation and parsing stay in the individual
updaters; this module centralizes only request construction, bounded reads,
and text decoding.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.request import Request, urlopen


def fetch_bytes(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    max_bytes: int | None = None,
) -> bytes:
    """Fetch a URL using urllib, optionally limiting the response body size."""
    if max_bytes is not None and max_bytes < 0:
        raise ValueError("max_bytes must be non-negative or None")
    request = Request(url, headers=dict(headers or {}))
    with urlopen(request, timeout=timeout) as response:
        return response.read() if max_bytes is None else response.read(max_bytes)


def fetch_text(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    max_bytes: int | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> str:
    """Fetch and decode a URL while preserving urllib's native errors."""
    return fetch_bytes(
        url,
        headers=headers,
        timeout=timeout,
        max_bytes=max_bytes,
    ).decode(encoding, errors)
