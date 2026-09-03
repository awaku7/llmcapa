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

from pathlib import Path

from .models import Capability, ComputerUseCapability, Feature, ReasoningEffort
from .registry import ModelNotFoundError, Registry, default_registry
from .tokenizer import count_messages_tokens, count_tokens

__version__ = "0.5.15"

__all__ = [
    "Capability",
    "ComputerUseCapability",
    "Feature",
    "ModelNotFoundError",
    "ReasoningEffort",
    "Registry",
    "__version__",
    "count_messages_tokens",
    "count_tokens",
    "default_registry",
    "fetch_huggingface",
    "fetch_openrouter",
    "find",
    "find_model",
    "get",
    "get_computer_use_capability",
    "list_models",
    "load_extra",
    "providers",
    "register",
    "search",
    "supports_computer_action",
    "supports_computer_environment",
    "supports_computer_use",
    "supports_json_mode",
    "supports_json_schema",
]


def get(model_id: str, provider: str | None = None) -> Capability:
    """Return the Capability for a model id or alias.

    Args:
        model_id: Model id, alias, or deployment name.
        provider: If given, scope the lookup to models from this
                  provider only (e.g. ``provider="novita"``).
    """
    return default_registry().get(model_id, provider)


def list_models(
    provider: str | None = None,
    include_deprecated: bool = True,
) -> list[Capability]:
    """List known models, optionally filtered by provider."""
    return default_registry().list_models(provider, include_deprecated)


def providers() -> list[str]:
    """Return the sorted list of known providers."""
    return default_registry().providers()


def find(**kwargs) -> list[Capability]:
    """Search models by conditions. See Registry.find."""
    return default_registry().find(**kwargs)


def find_model(model_id: str) -> list[tuple[str, Capability]]:
    """Find all (provider, Capability) tuples for a given model_id across providers.

    Returns a list of (provider, Capability) for every provider that has a model
    matching the given model_id. Useful when the same model is available from
    multiple providers with different specs/pricing.
    """
    return default_registry().find_by_model_id(model_id)


def search(
    prefix: str,
    provider: str | None = None,
    include_deprecated: bool = False,
    limit: int | None = None,
) -> list[Capability]:
    """Search models by prefix matching on model_id, display_name, or aliases.

    Case-insensitive prefix search. Results are sorted by (provider, model_id).
    """
    return default_registry().search(prefix, provider, include_deprecated, limit)


def load_extra(path: str | Path) -> int:
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
    cache_ttl: int | None = None,
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


def supports_json_mode(model_id: str, provider: str | None = None) -> bool | None:
    """Return JSON Object mode support for ``provider + model_id``.

    ``None`` means that the catalog has no verified information; it is not
    treated as equivalent to ``False``.
    """
    return get(model_id, provider).supports_json_mode


def supports_json_schema(model_id: str, provider: str | None = None) -> bool | None:
    """Return native JSON Schema support for ``provider + model_id``."""
    return get(model_id, provider).supports_json_schema


def get_computer_use_capability(
    model_id: str,
    provider: str | None = None,
) -> ComputerUseCapability | None:
    """Return Computer Use capability, or ``None`` when it is unknown."""
    return get(model_id, provider).computer_use


def supports_computer_use(model_id: str, provider: str | None = None) -> bool:
    """Return whether a model is explicitly registered as supporting CUA."""
    cap = get_computer_use_capability(model_id, provider)
    return bool(cap and cap.supported)


def supports_computer_action(
    model_id: str,
    action: str,
    provider: str | None = None,
) -> bool:
    """Return whether a registered Computer Use capability supports *action*."""
    cap = get_computer_use_capability(model_id, provider)
    return bool(cap and cap.supported and action in cap.actions)


def supports_computer_environment(
    model_id: str,
    environment: str,
    provider: str | None = None,
) -> bool:
    """Return whether a registered capability supports *environment*."""
    cap = get_computer_use_capability(model_id, provider)
    return bool(cap and cap.supported and environment in cap.environments)
