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

from .models import Capability, ComputerUseCapability, Feature, ReasoningEffort
from .registry import Registry, ModelNotFoundError, default_registry
from .tokenizer import count_tokens, count_messages_tokens

__version__ = "0.5.9"

__all__ = [
    "Capability",
    "ComputerUseCapability",
    "Feature",
    "ReasoningEffort",
    "Registry",
    "ModelNotFoundError",
    "get",
    "list_models",
    "providers",
    "find",
    "search",
    "find_model",
    "load_extra",
    "fetch_openrouter",
    "fetch_huggingface",
    "register",
    "supports_computer_use",
    "get_computer_use_capability",
    "supports_computer_action",
    "supports_computer_environment",
    "default_registry",
    "count_tokens",
    "count_messages_tokens",
    "__version__",
]


def get(model_id: str, provider: Optional[str] = None) -> Capability:
    """Return the Capability for a model id or alias.

    Args:
        model_id: Model id, alias, or deployment name.
        provider: If given, scope the lookup to models from this
                  provider only (e.g. ``provider="novita"``).
    """
    return default_registry().get(model_id, provider)


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


def find_model(model_id: str) -> List[tuple[str, Capability]]:
    """Find all (provider, Capability) tuples for a given model_id across providers.

    Returns a list of (provider, Capability) for every provider that has a model
    matching the given model_id. Useful when the same model is available from
    multiple providers with different specs/pricing.
    """
    return default_registry().find_by_model_id(model_id)


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


def fetch_openrouter(cache_ttl: int = 86400) -> int:
    """Fetch all models dynamically from OpenRouter API and register them.

    Args:
        cache_ttl: Cache lifetime in seconds (default 24 hours). Pass 0 to
                   force a refresh from OpenRouter.
    """
    return default_registry().fetch_openrouter(cache_ttl)


def fetch_huggingface(
    limit: int = 100,
    cache_ttl: Optional[int] = None,
) -> int:
    """Fetch top models from HuggingFace API and register them.

    Retrieves the most downloaded text-generation and image-text-to-text models
    from HuggingFace, registers their basic capabilities, and caches the result
    locally in ~/.llmcapa/huggingface_cache.json.

    Args:
        limit: Maximum number of models to fetch per pipeline tag (default 100).
        cache_ttl: Cache lifetime in seconds. Pass 0 to force refresh.
    """
    return default_registry().fetch_huggingface(limit=limit, cache_ttl=cache_ttl)


def register(cap: Capability) -> None:
    """Register (or override) a Capability in the default registry."""
    default_registry().register(cap)


def get_computer_use_capability(
    model_id: str,
    provider: Optional[str] = None,
) -> Optional[ComputerUseCapability]:
    """Return Computer Use capability, or ``None`` when it is unknown."""
    return get(model_id, provider).computer_use


def supports_computer_use(model_id: str, provider: Optional[str] = None) -> bool:
    """Return whether a model is explicitly registered as supporting CUA."""
    cap = get_computer_use_capability(model_id, provider)
    return bool(cap and cap.supported)


def supports_computer_action(
    model_id: str,
    action: str,
    provider: Optional[str] = None,
) -> bool:
    """Return whether a registered Computer Use capability supports *action*."""
    cap = get_computer_use_capability(model_id, provider)
    return bool(cap and cap.supported and action in cap.actions)


def supports_computer_environment(
    model_id: str,
    environment: str,
    provider: Optional[str] = None,
) -> bool:
    """Return whether a registered capability supports *environment*."""
    cap = get_computer_use_capability(model_id, provider)
    return bool(cap and cap.supported and environment in cap.environments)
