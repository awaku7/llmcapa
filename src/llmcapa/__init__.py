"""llmcapa: lookup capabilities of various LLM models, fully offline.

Example:
    >>> import llmcapa
    >>> cap = llmcapa.get("gpt-4o")
    >>> cap.context_window
    128000
    >>> cap.supports("vision")
    True
"""

from __future__ import annotations

from typing import List, Optional, Union
from pathlib import Path

from .models import Capability, Feature, ReasoningEffort
from .registry import Registry, ModelNotFoundError, default_registry
from .tokenizer import count_tokens, count_messages_tokens

__version__ = "0.2.6"

__all__ = [
    "Capability",
    "Feature",
    "ReasoningEffort",
    "Registry",
    "ModelNotFoundError",
    "get",
    "list_models",
    "providers",
    "find",
    "search",
    "load_extra",
    "fetch_openrouter",
    "register",
    "default_registry",
    "count_tokens",
    "count_messages_tokens",
    "__version__",
]


def get(model_id: str) -> Capability:
    """Return the Capability for a model id or alias."""
    return default_registry().get(model_id)


def list_models(
    provider: Optional[str] = None,
    include_deprecated: bool = True,
) -> List[Capability]:
    """List known models, optionally filtered by provider."""
    return default_registry().list_models(provider, include_deprecated)


def providers() -> List[str]:
    """Return the sorted list of known providers."""
    return default_registry().providers()


def find(**kwargs) -> List[Capability]:
    """Search models by conditions. See Registry.find."""
    return default_registry().find(**kwargs)


def search(
    prefix: str,
    provider: Optional[str] = None,
    include_deprecated: bool = False,
    limit: Optional[int] = None,
) -> List[Capability]:
    """Search models by prefix matching on model_id, display_name, or aliases.

    Case-insensitive prefix search. Results are sorted by (provider, model_id).
    """
    return default_registry().search(prefix, provider, include_deprecated, limit)


def load_extra(path: Union[str, Path]) -> int:
    """Load user-defined model data from a local JSON file."""
    return default_registry().load_extra(path)


def fetch_openrouter(cache_ttl: Optional[int] = None) -> int:
    """Fetch all models dynamically from OpenRouter API and register them."""
    return default_registry().fetch_openrouter(cache_ttl)


def register(cap: Capability) -> None:
    """Register (or override) a Capability in the default registry."""
    default_registry().register(cap)
