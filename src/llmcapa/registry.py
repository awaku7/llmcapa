"""Registry: loads bundled capability data and provides lookup/search."""

from __future__ import annotations

import json
import re
import ssl
import urllib.request
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from .models import Capability


class ModelNotFoundError(KeyError):
    """Raised when a model id or alias cannot be resolved."""


class Registry:
    """In-memory registry of model capabilities."""

    def __init__(self) -> None:
        self._models: Dict[str, Capability] = {}
        self._alias_index: Dict[str, str] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # loading
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            self._load_bundled()

    def _load_bundled(self) -> None:
        data_pkg = resources.files("llmcapa.data")
        for entry in sorted(data_pkg.iterdir(), key=lambda e: e.name):
            if entry.name.endswith(".json"):
                self._load_json_text(entry.read_text(encoding="utf-8"))

        # Load local OpenRouter cache if it exists to override bundled data with latest updates
        import os
        home = os.path.expanduser("~")
        cache_file = os.path.join(home, ".llmcapa", "openrouter_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
                for r in records:
                    model_id = r.get("id")
                    if not model_id:
                        continue
                    self.register(self._map_openrouter_record(r))
            except Exception:
                pass

    def _load_json_text(self, text: str) -> int:
        payload = json.loads(text)
        if isinstance(payload, dict):
            records = payload.get("models", [])
        else:
            records = payload
        count = 0
        for record in records:
            self.register(Capability.from_dict(record))
            count += 1
        return count

    def load_extra(self, path: Union[str, Path]) -> int:
        """Load user-defined model data from a local JSON file.

        The file may contain either a list of model records or an object
        with a "models" key. Existing entries with the same model_id are
        overridden. Returns the number of records loaded.
        """
        self._ensure_loaded()
        text = Path(path).read_text(encoding="utf-8")
        return self._load_json_text(text)

    def register(self, cap: Capability) -> None:
        """Register (or override) a single Capability."""
        key = cap.model_id.lower()
        self._models[key] = cap
        self._alias_index[key] = key
        for alias in cap.aliases:
            self._alias_index[alias.lower()] = key

    def _map_openrouter_record(self, r: dict) -> Capability:
        model_id = r.get("id", "")
        context_window = int(r.get("context_length") or 0)
        top_provider = r.get("top_provider") or {}
        max_output = int(top_provider.get("max_completion_tokens") or 0)

        # Modalities
        arch = r.get("architecture") or {}
        input_mods = arch.get("input_modalities") or ["text"]
        output_mods = arch.get("output_modalities") or ["text"]

        # Features
        supported_params = r.get("supported_parameters") or []
        supports_fc = "tools" in supported_params or "tool_choice" in supported_params
        supports_json = "structured_outputs" in supported_params or "response_format" in supported_params
        supports_reasoning = "reasoning" in supported_params or "include_reasoning" in supported_params
        supports_reasoning_effort = "reasoning" in supported_params

        # Pricing
        pricing_data = r.get("pricing") or {}
        pricing = None
        if pricing_data:
            try:
                pricing = {
                    "input_per_1m": float(pricing_data.get("prompt", 0)) * 1000000,
                    "output_per_1m": float(pricing_data.get("completion", 0)) * 1000000,
                    "currency": "USD"
                }
            except (ValueError, TypeError):
                pass

        # Determine provider from model_id prefix (e.g. "meta-llama/..." -> "meta-llama")
        provider = "openrouter"
        if "/" in model_id:
            parts = model_id.split("/")
            if not parts[0].startswith("~"):
                provider = parts[0]

        return Capability(
            provider=provider,
            model_id=model_id,
            display_name=r.get("name", model_id),
            context_window=context_window,
            max_output_tokens=max_output,
            input_modalities=input_mods,
            output_modalities=output_mods,
            supports_function_calling=supports_fc,
            supports_json_mode=supports_json,
            supports_streaming=True,
            supports_vision="image" in input_mods,
            supports_reasoning=supports_reasoning,
            supports_reasoning_effort=supports_reasoning_effort,
            supports_chat_completion=True,
            supports_responses_api=False,
            knowledge_cutoff=r.get("knowledge_cutoff"),
            pricing=pricing,
            aliases=[model_id.lower()]
        )

    # ------------------------------------------------------------------
    # OpenRouter dynamic fetching
    # ------------------------------------------------------------------
    def fetch_openrouter(self, cache_ttl: Optional[int] = None) -> int:
        """Fetch all models dynamically from OpenRouter API and register them.

        This allows retrieving capabilities for all 300+ models on OpenRouter
        without bundling them in the static package.

        If cache_ttl (in seconds) is provided, the response is cached locally
        in ~/.llmcapa/openrouter_cache.json to avoid redundant API requests.
        """
        self._ensure_loaded()
        
        records = []
        cache_file = None
        if cache_ttl is not None:
            import os
            import time
            home = os.path.expanduser("~")
            cache_dir = os.path.join(home, ".llmcapa")
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, "openrouter_cache.json")
            
            if os.path.exists(cache_file):
                mtime = os.path.getmtime(cache_file)
                if time.time() - mtime < cache_ttl:
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            records = json.load(f)
                    except Exception:
                        pass

        if not records:
            url = "https://openrouter.ai/api/v1/models"
            ctx = ssl._create_unverified_context()
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, context=ctx) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    records = data.get("data", [])
            except Exception as e:
                raise RuntimeError(f"Failed to fetch models from OpenRouter: {e}") from e

            if cache_file and records:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(records, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        count = 0
        for r in records:
            model_id = r.get("id")
            if not model_id:
                continue

            cap = self._map_openrouter_record(r)
            self.register(cap)
            count += 1
        return count

    # ------------------------------------------------------------------
    # lookup
    # ------------------------------------------------------------------
    def _lookup_candidates(self, model_id: str) -> list[str]:
        """Return lookup keys including safe date-suffix normalization."""
        key = (model_id or "").strip().lower()
        candidates = [key]
        if "-" in key:
            base, suffix = key.rsplit("-", 1)
            if re.fullmatch(r"\d{8}", suffix):
                candidates.append(base)
        return candidates

    def get(self, model_id: str) -> Capability:
        """Resolve a model id or alias to its Capability."""
        self._ensure_loaded()
        for key in self._lookup_candidates(model_id):
            resolved = self._alias_index.get(key)
            if resolved is not None:
                return self._models[resolved]
        raise ModelNotFoundError(model_id)

    def list_models(
        self,
        provider: Optional[str] = None,
        include_deprecated: bool = True,
    ) -> List[Capability]:
        """Return capabilities, optionally filtered by provider."""
        self._ensure_loaded()
        result: Iterable[Capability] = self._models.values()
        if provider is not None:
            p = provider.lower()
            result = (c for c in result if c.provider.lower() == p)
        if not include_deprecated:
            result = (c for c in result if not c.deprecated)
        return sorted(result, key=lambda c: (c.provider, c.model_id))

    def providers(self) -> List[str]:
        """Return the sorted list of known providers."""
        self._ensure_loaded()
        return sorted({c.provider for c in self._models.values()})

    def find(
        self,
        provider: Optional[str] = None,
        min_context_window: int = 0,
        min_max_output_tokens: int = 0,
        include_deprecated: bool = False,
        **feature_flags: bool,
    ) -> List[Capability]:
        """Search models by conditions.

        feature_flags accepts keys like supports_vision=True or
        short forms like vision=True.
        """
        self._ensure_loaded()
        result = []
        for cap in self.list_models(provider, include_deprecated):
            if (cap.context_window or 0) < min_context_window:
                continue
            if (cap.max_output_tokens or 0) < min_max_output_tokens:
                continue
            ok = True
            for key, expected in feature_flags.items():
                feature = key[len("supports_"):] if key.startswith("supports_") else key
                if cap.supports(feature) != bool(expected):
                    ok = False
                    break
            if ok:
                result.append(cap)
        return result


# Module-level default registry
_default = Registry()


def default_registry() -> Registry:
    """Return the shared default Registry instance."""
    return _default
