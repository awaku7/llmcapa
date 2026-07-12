"""Registry: loads bundled capability data and provides lookup/search."""

from __future__ import annotations

import json
import re
import ssl
import urllib.request
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional, Union

from .models import Capability


class ModelNotFoundError(KeyError):
    """Raised when a model id or alias cannot be resolved."""


class Registry:
    """In-memory registry of model capabilities."""

    def __init__(self) -> None:
        self._models: Dict[str, Capability] = {}
        self._alias_index: Dict[str, str] = {}
        # Provider-scoped index: {provider_lower: {model_id_lower: Capability}}
        self._by_provider: Dict[str, Dict[str, Capability]] = {}

        self._loaded = False

    # Provider aliases map: canonical name -> list of equivalent provider names
    # Used by list_models() so that e.g. provider="deepseek" also matches "deepseek-ai"
    _provider_aliases: Dict[str, List[str]] = {
        "deepseek": ["deepseek-ai"],
        "meta": ["meta-llama"],
        "mistral": ["mistralai"],
        "xai": ["x-ai"],
        "amazon": ["bedrock"],
        "bedrock": ["amazon"],
        "xiaomi": ["mimo"],
        "mimo": ["xiaomi"],
        "openai": ["azure-openai", "azure_openai", "azureopenai"],
        "azure-openai": ["openai"],
        "huggingface": ["hf"],
        "hf": ["huggingface"],
    }

    @staticmethod
    def _normalize_provider(name: str) -> str:
        """Normalize provider name: lowercase, unify separators to hyphen."""
        normalized = name.lower().strip()
        normalized = re.sub(r'[_. \t]+', '-', normalized)
        return normalized

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

        # Load local OpenRouter cache if it exists (up to 24h old) to override bundled data with latest updates
        import os
        import time
        home = os.path.expanduser("~")
        cache_file = os.path.join(home, ".llmcapa", "openrouter_cache.json")
        if os.path.exists(cache_file):
            try:
                mtime = os.path.getmtime(cache_file)
                if time.time() - mtime > 86400:
                    return
            except Exception:
                pass
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
        """Register a single Capability.

        The *flat* model_id -> Capability mapping uses **first-registered-wins**
        semantics so that native provider data takes precedence over
        aggregator/reseller data for unqualified lookups.

        Provider-scoped lookups via ``get(..., provider=...)`` always
        find the correct provider's data regardless of registration order.
        """
        key = cap.model_id.lower()
        prov = self._normalize_provider(cap.provider)

        # First-registered-wins for the flat model_id index.
        # Also skip if key is already claimed as an alias for another model.
        if key not in self._models and key not in self._alias_index:
            self._models[key] = cap
            self._alias_index[key] = key
            for alias in cap.aliases:
                if alias.lower() not in self._alias_index:
                    self._alias_index[alias.lower()] = key

        # Provider-scoped index: always register (no first-wins here)
        if prov not in self._by_provider:
            self._by_provider[prov] = {}
        if key not in self._by_provider[prov]:
            self._by_provider[prov][key] = cap

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
        supports_fc = "tools" in supported_params or "function_calling" in supported_params

        # Pricing
        pricing_data = r.get("pricing") or {}
        pricing = None
        if pricing_data.get("prompt") is not None:
            pricing = {
                "input_per_1m": float(pricing_data.get("prompt", 0)) * 1000000,
                "output_per_1m": float(pricing_data.get("completion", 0)) * 1000000,
                "currency": "USD",
            }

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
            supports_streaming=True,
            supports_chat_completion=True,
            supports_vision="image" in input_mods,
            supports_json_mode="json_mode" in supported_params or "response_format" in supported_params,
            supports_reasoning_effort="reasoning" in supported_params or "reasoning_effort" in supported_params,
            supports_thinking_budget="thinking" in supported_params or "thinking_budget" in supported_params,
            knowledge_cutoff=r.get("knowledge_cutoff"),
            pricing=pricing,
            aliases=[model_id.lower()],
        )

    # ------------------------------------------------------------------
    # OpenRouter dynamic fetching
    # ------------------------------------------------------------------
    def fetch_openrouter(
        self,
        cache_ttl: int = 86400,
    ) -> int:
        """Fetch all models dynamically from OpenRouter API and register them.

        This allows users to get the latest models and pricing from OpenRouter
        without bundling them in the static package.

        The response is cached locally
        in ~/.llmcapa/openrouter_cache.json to avoid redundant API requests.
        """
        self._ensure_loaded()

        records = []
        # Try loading from cache first
        if cache_ttl > 0:
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
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                with urllib.request.urlopen(req, context=ctx) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    records = data.get("data", [])
            except Exception as e:
                raise RuntimeError(f"Failed to fetch models from OpenRouter: {e}") from e

            # Cache the response
            if cache_ttl > 0:
                import os
                import time
                home = os.path.expanduser("~")
                cache_dir = os.path.join(home, ".llmcapa")
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, "openrouter_cache.json")
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
    # HuggingFace dynamic fetching
    # ------------------------------------------------------------------
    def _map_huggingface_record(self, r: dict) -> Capability:
        """Map a HuggingFace API record to a Capability."""
        model_id = r.get("modelId", r.get("_id", ""))
        pipeline = r.get("pipeline_tag", "")
        tags = r.get("tags", [])
        card = r.get("cardData", {}) or {}
        config = r.get("config", {}) or {}

        # Provider from model_id prefix (e.g. "deepseek-ai/..." -> "deepseek-ai")
        provider = "huggingface"
        if "/" in model_id:
            provider = model_id.split("/", 1)[0]

        # Determine input modalities from pipeline_tag
        is_vision = pipeline in ("image-text-to-text", "visual-question-answering", "image-feature-extraction")
        input_mods = ["text"]
        if is_vision:
            input_mods.append("image")

        # Context window: try card -> config -> default
        model_data = card.get("model_data", {}) or {}
        ctx_win = (
            model_data.get("context_window")
            or card.get("context_window")
            or card.get("context_length")
            or config.get("max_position_embeddings")
            or config.get("n_positions")
            or config.get("n_ctx")
            or 4096
        )

        max_out = (
            model_data.get("max_output_tokens")
            or card.get("max_output_tokens")
            or 2048
        )

        # Chat completion is supported for text-generation and image-text-to-text
        supports_chat = pipeline in ("text-generation", "image-text-to-text", "conversational")

        return Capability(
            provider=provider,
            model_id=model_id,
            display_name=r.get("modelId", model_id),
            context_window=int(ctx_win) if ctx_win else 4096,
            max_output_tokens=int(max_out) if max_out else 2048,
            input_modalities=input_mods,
            output_modalities=["text"],
            supports_chat_completion=supports_chat,
            supports_streaming=True,
            supports_vision=is_vision,
            supports_function_calling=False,
            supports_json_mode=False,
            aliases=[model_id.lower()],
        )

    def fetch_huggingface(
        self,
        limit: int = 100,
        cache_ttl: Optional[int] = None,
    ) -> int:
        """Fetch top models from HuggingFace API and register them.

        Retrieves the most downloaded text-generation and image-text-to-text models
        from HuggingFace, registers their basic capabilities, and caches the result
        locally in ~/.llmcapa/huggingface_cache.json.

        Args:
            limit: Maximum number of models to fetch per pipeline tag (default 100).
            cache_ttl: Cache lifetime in seconds. If provided, the response is cached
                       to avoid redundant API requests. Pass 0 to force refresh.
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
            cache_file = os.path.join(cache_dir, "huggingface_cache.json")

            if os.path.exists(cache_file):
                mtime = os.path.getmtime(cache_file)
                if time.time() - mtime < cache_ttl:
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            records = json.load(f)
                    except Exception:
                        pass

        if not records:
            ctx = ssl._create_unverified_context()
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            records = []

            # Fetch text-generation models
            for tag in ("text-generation", "image-text-to-text"):
                url = (
                    f"https://huggingface.co/api/models"
                    f"?pipeline_tag={tag}&sort=downloads&direction=-1&limit={limit}"
                )
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                        chunk = json.loads(response.read().decode("utf-8"))
                        for r in chunk:
                            if r.get("modelId") or r.get("_id"):
                                records.append(r)
                except Exception as e:
                    raise RuntimeError(f"Failed to fetch models from HuggingFace ({tag}): {e}") from e

            if cache_file and records:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(records, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        count = 0
        for r in records:
            model_id = r.get("modelId") or r.get("_id")
            if not model_id:
                continue
            try:
                cap = self._map_huggingface_record(r)
                self.register(cap)
                count += 1
            except Exception:
                continue
        return count

    # ------------------------------------------------------------------
    # lookup
    # ------------------------------------------------------------------
    def _lookup_candidates(self, model_id: str) -> list[str]:
        """Return lookup keys including safe suffix normalization.

        Automatically strips known suffixes such as:
          -colon suffix (:free, :beta, etc.)
          -date patterns: YYYY-MM-DD, MM-DD, YYYYMMDD
          -literal suffixes: -latest, -preview, -preview-XX-XX
        Supports separators: -, _, . (e.g. gpt-4o-latest, model_latest,
        claude.latest). Multiple suffixes are stripped iteratively
        (e.g., -preview-05-20 removes -05-20 first, then -preview).

        Also, if model_id contains a provider/ prefix (e.g. "openai/o3-mini"),
        the bare model_id without prefix is added as a candidate.
        """
        key = (model_id or "").strip().lower()
        candidates = [key]

        # 1. Strip colon suffix (e.g., :free, :beta)
        if ":" in key:
            candidates.append(key.split(":")[0])

        # 2. If model_id contains a provider/ prefix, also try bare model_id
        if "/" in key:
            without_prefix = key.split("/", 1)[1]
            if without_prefix not in candidates:
                candidates.append(without_prefix)

        # 3. Progressively strip known trailing patterns
        DatePat = r"[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}-[0-9]{2}|[0-9]{8}"
        suffix_pats = [f"[-_.]({DatePat})$", r"[-_.](latest|preview)$"]

        for base in list(candidates):
            k = base
            changed = True
            while changed:
                changed = False
                # Try date patterns first (longest match)
                m = re.search(suffix_pats[0], k)
                if m:
                    k = k[: m.start()]
                    if k not in candidates:
                        candidates.append(k)
                    changed = True
                    continue
                # Try literal suffixes
                m = re.search(suffix_pats[1], k)
                if m:
                    k = k[: m.start()]
                    if k not in candidates:
                        candidates.append(k)
                    changed = True
                    continue
        return candidates

    def get(self, model_id: str, provider: Optional[str] = None) -> Capability:
        """Resolve a model id or alias to its Capability.

        Args:
            model_id: Model id, alias, or deployment name.
            provider: If given, scope the lookup to models from this
                      provider only. Otherwise, returns the first-registered
                      (native) version.

        Raises:
            ModelNotFoundError: If the model cannot be resolved.
        """
        self._ensure_loaded()
        if provider is not None:
            # Scoped lookup: search only within the given provider
            p = self._normalize_provider(provider)
            # Collect matching provider names (canonical + aliases)
            matching_providers = {p}
            for canonical, aliases in self._provider_aliases.items():
                if p == canonical:
                    matching_providers.update(aliases)
                elif p in aliases:
                    matching_providers.add(canonical)
                    matching_providers.update(a for a in aliases if a != p)
            for prov in matching_providers:
                prov_index = self._by_provider.get(prov)
                if prov_index is not None:
                    for key in self._lookup_candidates(model_id):
                        # Direct model_id match
                        cap = prov_index.get(key)
                        if cap is not None:
                            return cap
                        # Alias resolution: key may point to another model_id
                        resolved = self._alias_index.get(key)
                        if resolved is not None and resolved != key:
                            cap = prov_index.get(resolved)
                            if cap is not None:
                                return cap
            raise ModelNotFoundError(model_id)
        # Unqualified lookup: use alias index (first-registered-wins)
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
        if provider is not None:
            p = self._normalize_provider(provider)
            # Collect matching provider names (canonical + aliases)
            matching_providers = {p}
            for canonical, aliases in self._provider_aliases.items():
                if p == canonical:
                    matching_providers.update(aliases)
                elif p in aliases:
                    matching_providers.add(canonical)
                    matching_providers.update(a for a in aliases if a != p)
            result: List[Capability] = []
            for prov in matching_providers:
                idx = self._by_provider.get(prov)
                if idx:
                    result.extend(idx.values())
        else:
            result = list(self._models.values())
        if not include_deprecated:
            result = [c for c in result if not c.deprecated]
        return sorted(result, key=lambda c: (c.provider, c.model_id))

    def providers(self) -> List[str]:
        """Return the sorted list of known providers."""
        self._ensure_loaded()
        return sorted(self._by_provider.keys())

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

    def find_by_model_id(self, model_id: str) -> List[tuple[str, Capability]]:
        """Find all (provider, Capability) tuples for a given model_id across providers."""
        self._ensure_loaded()
        key = model_id.strip().lower()
        results: List[tuple[str, Capability]] = []
        for prov, caps in self._by_provider.items():
            for lookup_key in [key] + [k for k in self._lookup_candidates(model_id) if k != key]:
                cap = caps.get(lookup_key)
                if cap is not None:
                    results.append((prov, cap))
                    break
                resolved = self._alias_index.get(lookup_key)
                if resolved is not None and resolved != lookup_key:
                    cap = caps.get(resolved)
                    if cap is not None:
                        results.append((prov, cap))
                        break
        return results

    def search(
        self,
        prefix: str,
        provider: str,
        include_deprecated: bool = False,
        limit: Optional[int] = None,
    ) -> List[Capability]:
        """Search models by prefix matching on model_id, display_name, or aliases.

        Case-insensitive prefix search. Results are sorted by (provider, model_id).
        """
        self._ensure_loaded()
        prefix_lower = prefix.strip().lower()
        if not prefix_lower:
            return []

        result = []
        for cap in self._models.values():
            if provider is not None and cap.provider.lower() != provider.lower():
                continue
            if not include_deprecated and cap.deprecated:
                continue
            # Check model_id
            if cap.model_id.lower().startswith(prefix_lower):
                result.append(cap)
                continue
            # Check display_name
            if cap.display_name and cap.display_name.lower().startswith(prefix_lower):
                result.append(cap)
                continue
            # Check aliases
            for alias in cap.aliases:
                if alias.lower().startswith(prefix_lower):
                    result.append(cap)
                    break

        result.sort(key=lambda c: (c.provider, c.model_id))
        if limit is not None:
            result = result[:limit]
        return result


def default_registry() -> Registry:
    """Return the global default registry instance."""
    return _default_registry


_default_registry = Registry()
