"""Registry: loads bundled capability data and provides lookup/search."""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import stat
import tempfile
import time
import urllib.request
import warnings
from importlib import resources
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

from .models import Capability


class ModelNotFoundError(KeyError):
    """Raised when a model id or alias cannot be resolved."""


class Registry:
    """In-memory registry of model capabilities."""

    def __init__(self) -> None:
        self._models: dict[str, Capability] = {}
        self._alias_index: dict[str, str] = {}
        # Provider-scoped index: {provider_lower: {model_id_lower: Capability}}
        self._by_provider: dict[str, dict[str, Capability]] = {}
        # Provider-to-bundled-file index used by the optional GitHub catalog
        # fetcher. Some providers (for example Modellix) have multiple files.
        self._catalog_files_by_provider: dict[str, set[str]] = {}
        # Auto-refresh at most once per provider in this Registry instance.
        self._github_auto_refresh_attempted: set[str] = set()

        self._loaded = False

    # Provider aliases map: canonical name -> list of equivalent provider names
    # Used by list_models() so that e.g. provider="deepseek" also matches "deepseek-ai"
    _provider_aliases: ClassVar[dict[str, list[str]]] = {
        "deepseek": ["deepseek-ai"],
        "meta": ["meta-llama"],
        "mistral": ["mistralai"],
        # Product / SDK / OpenRouter-style names commonly used by clients
        "openai": ["open-ai"],
        "xai": ["x-ai", "grok"],
        "anthropic": ["claude"],
        "google": ["google-ai", "gemini"],
        "vertex-ai": ["vertexai"],
        "azure-openai": ["azure"],
        "zhipu": ["zai", "z-ai"],
        "moonshotai": ["moonshot", "kimi"],
        "amazon": ["bedrock", "aws-bedrock", "aws"],
        "xiaomi": ["mimo"],
        "huggingface": ["hf"],
        "qwen": ["alibaba", "dashscope"],
        "lmstudio": ["lm-studio", "lm_studio"],
        "together": ["together-ai", "togethercomputer"],
        "vercel": ["vercel-ai-gateway", "vercel-gateway", "ai-gateway"],
        # Modellix is a gateway with its own provider/name model IDs.
        "modellix": ["modellix-ai"],
        # llama.cpp is a local inference backend, kept distinct from Ollama.
        "llama-cpp": ["llama", "llama_cpp"],
    }

    @staticmethod
    def _normalize_provider(name: str) -> str:
        """Normalize provider name: lowercase, unify separators to hyphen."""
        normalized = name.lower().strip()
        normalized = re.sub(r"[_. \t]+", "-", normalized)
        return normalized

    def _matching_providers(self, provider: str) -> set:
        """Return the set of provider names equivalent to *provider*.

        Includes the normalized input, the canonical registry name, and all
        configured aliases (e.g. ``grok`` / ``x-ai`` → ``xai``).
        """
        p = self._normalize_provider(provider)
        matching = {p}
        for canonical, aliases in self._provider_aliases.items():
            if p == canonical or p in aliases:
                matching.add(canonical)
                matching.update(aliases)
        return matching

    # ------------------------------------------------------------------
    # loading
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            self._load_bundled()

    def _load_bundled(self) -> None:
        data_pkg = resources.files("llmcapa.data")
        # Aggregator/reseller files are loaded last so native provider data
        # takes precedence via first-registered-wins.
        aggregators = {
            "openrouter.json",
            "novita.json",
            "azure_foundry.json",
            "lmstudio.json",
            "ollama.json",
            "modellix.json",
            "modellix_media.json",
        }
        regular = []
        agg = []
        for entry in sorted(data_pkg.iterdir(), key=lambda e: e.name):
            if entry.name.endswith(".json"):
                if entry.name in aggregators:
                    agg.append(entry)
                else:
                    regular.append(entry)
        for entry in regular + agg:
            self._load_json_text(
                entry.read_text(encoding="utf-8"), catalog_name=entry.name
            )

        # Reuse explicitly fetched GitHub snapshots without networking.
        self._load_github_catalog_caches()
        # Persistent user catalogs take precedence over the bundled snapshots.
        self._load_persistent_github_catalogs()

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
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
                for r in records:
                    model_id = r.get("id")
                    if not model_id:
                        continue
                    self.register(self._map_openrouter_record(r), overwrite=False)
            except Exception:  # noqa: BLE001, S110
                pass

    def _load_github_catalog_caches(self) -> None:
        """Load fresh main-branch GitHub snapshots from the local cache only."""
        cache_dir = Path.home() / ".llmcapa" / "github_catalog_cache"
        try:
            cache_paths = sorted(
                cache_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return

        seen: set[tuple[str, str]] = set()
        now = time.time()
        for cache_path in cache_paths:
            try:
                if now - cache_path.stat().st_mtime >= 86400:
                    continue
                cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(cache_data, dict)
                    or cache_data.get("ref") != "main"
                ):
                    continue
                providers = cache_data.get("providers")
                files = cache_data.get("files")
                if (
                    not isinstance(providers, list)
                    or not isinstance(files, dict)
                    or not all(isinstance(name, str) for name in providers)
                ):
                    continue
                provider_set = {
                    self._normalize_provider(name) for name in providers
                }
                for text in files.values():
                    if not isinstance(text, str):
                        continue
                    payload = json.loads(text)
                    records = (
                        payload.get("models", [])
                        if isinstance(payload, dict)
                        else payload
                    )
                    if not isinstance(records, list):
                        continue
                    for record in records:
                        try:
                            cap = Capability.from_dict(record)
                            provider = self._normalize_provider(cap.provider)
                            if (
                                provider not in provider_set
                                or provider not in self._catalog_files_by_provider
                            ):
                                continue
                            identity = (provider, cap.model_id.lower())
                            if identity in seen:
                                continue
                            seen.add(identity)
                            self._register_refreshed_catalog_record(cap)
                        except (TypeError, ValueError, KeyError):
                            continue
            except (OSError, ValueError, TypeError):
                continue

    def _load_persistent_github_catalogs(self) -> None:
        """Load durable user-owned GitHub catalog overrides, newest first."""
        override_dir = Path.home() / ".llmcapa" / "catalogs" / "github"
        try:
            override_paths = sorted(
                override_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return

        seen: set[tuple[str, str]] = set()
        for override_path in override_paths:
            try:
                payload = json.loads(override_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("source") != "https://github.com/awaku7/llmcapa"
                ):
                    continue
                providers = payload.get("providers")
                records = payload.get("models")
                if (
                    not isinstance(providers, list)
                    or not isinstance(records, list)
                    or not all(isinstance(name, str) for name in providers)
                ):
                    continue
                provider_set = {
                    self._normalize_provider(name) for name in providers
                }
                for record in records:
                    try:
                        cap = Capability.from_dict(record)
                        provider = self._normalize_provider(cap.provider)
                        if (
                            provider not in provider_set
                            or provider not in self._catalog_files_by_provider
                        ):
                            continue
                        identity = (provider, cap.model_id.lower())
                        if identity in seen:
                            continue
                        seen.add(identity)
                        self._register_refreshed_catalog_record(cap)
                    except (TypeError, ValueError, KeyError):
                        continue
            except (OSError, ValueError, TypeError):
                continue

    def _load_json_text(self, text: str, catalog_name: str | None = None) -> int:
        payload = json.loads(text)
        if isinstance(payload, dict):
            records = payload.get("models", [])
        else:
            records = payload
        count = 0
        for record in records:
            cap = Capability.from_dict(record)
            if catalog_name:
                provider = self._normalize_provider(cap.provider)
                self._catalog_files_by_provider.setdefault(provider, set()).add(
                    catalog_name
                )
            self.register(cap)
            count += 1
        return count

    def load_extra(self, path: str | Path) -> int:
        """Load user-defined model data from a local JSON file.

        The file may contain either a list of model records or an object
        with a "models" key. Existing entries with the same model_id are
        overridden. Returns the number of records loaded.
        """
        self._ensure_loaded()
        text = Path(path).read_text(encoding="utf-8")
        return self._load_json_text(text)

    def register(self, cap: Capability, overwrite: bool = False) -> None:
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
        aggregators = {
            "openrouter",
            "novita",
            "azure-foundry",
            "lmstudio",
            "ollama",
            "modellix",
        }
        existing = self._models.get(key)
        existing_provider = (
            self._normalize_provider(existing.provider) if existing is not None else ""
        )
        replace_with_native = (
            existing is not None
            and existing_provider in aggregators
            and prov not in aggregators
        )
        prefer_openrouter = (
            existing is not None
            and existing_provider == "novita"
            and prov == "openrouter"
        )
        if (
            overwrite
            or replace_with_native
            or prefer_openrouter
            or (key not in self._models and key not in self._alias_index)
        ):
            self._models[key] = cap
            self._alias_index[key] = key
            for alias in cap.aliases:
                if alias.lower() not in self._alias_index:
                    self._alias_index[alias.lower()] = key

        # Provider-scoped index: always register (no first-wins here)
        if prov not in self._by_provider:
            self._by_provider[prov] = {}
        if overwrite or key not in self._by_provider[prov]:
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
        supports_fc = (
            "tools" in supported_params or "function_calling" in supported_params
        )

        # Pricing
        pricing_data = r.get("pricing") or {}
        pricing = None
        if pricing_data.get("prompt") is not None:
            prompt_rate = float(pricing_data.get("prompt") or 0)
            completion_rate = float(pricing_data.get("completion") or 0)
            pricing = {
                "input_per_1m": prompt_rate * 1000000,
                "output_per_1m": completion_rate * 1000000,
                "currency": "USD",
            }

        return Capability(
            # OpenRouter route IDs belong to the OpenRouter catalog.  The
            # route's upstream namespace is part of model_id, not a native
            # provider registration.
            provider="openrouter",
            model_id=model_id,
            display_name=r.get("name", model_id),
            context_window=context_window,
            max_output_tokens=max_output,
            input_modalities=input_mods,
            output_modalities=output_mods,
            supports_function_calling=supports_fc,
            supports_streaming=True,
            supports_chat_completion=True,
            # Gateway-wide transport capability: OpenRouter serves
            # POST /api/v1/responses (stateless) for every route.  This flag
            # does not imply a model-native Responses API.
            supports_responses_api=True,
            supports_reasoning=bool(r.get("reasoning")),
            supports_vision="image" in input_mods,
            supports_json_mode=(
                "json_mode" in supported_params
                or "response_format" in supported_params
                or "structured_outputs" in supported_params
            ),
            supports_json_schema=(
                True if "structured_outputs" in supported_params else None
            ),
            supports_reasoning_effort="reasoning" in supported_params
            or "reasoning_effort" in supported_params,
            supports_thinking_budget="thinking" in supported_params
            or "thinking_budget" in supported_params,
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
                    except Exception:  # noqa: BLE001, S110
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
                raise RuntimeError(
                    f"Failed to fetch models from OpenRouter: {e}"
                ) from e

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
                except Exception:  # noqa: BLE001, S110
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
        r.get("tags", [])
        card = r.get("cardData", {}) or {}
        config = r.get("config", {}) or {}

        # Provider from model_id prefix (e.g. "deepseek-ai/..." -> "deepseek-ai")
        provider = "huggingface"
        if "/" in model_id:
            provider = model_id.split("/", 1)[0]

        # Determine input modalities from pipeline_tag
        is_vision = pipeline in (
            "image-text-to-text",
            "visual-question-answering",
            "image-feature-extraction",
        )
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
            model_data.get("max_output_tokens") or card.get("max_output_tokens") or 2048
        )

        # Chat completion is supported for text-generation and image-text-to-text
        supports_chat = pipeline in (
            "text-generation",
            "image-text-to-text",
            "conversational",
        )

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
        cache_ttl: int | None = None,
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
                    except Exception:  # noqa: BLE001, S110
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
                    with urllib.request.urlopen(
                        req, context=ctx, timeout=30
                    ) as response:
                        chunk = json.loads(response.read().decode("utf-8"))
                        for r in chunk:
                            if r.get("modelId") or r.get("_id"):
                                records.append(r)
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to fetch models from HuggingFace ({tag}): {e}"
                    ) from e

            if cache_file and records:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(records, f, ensure_ascii=False, indent=2)
                except Exception:  # noqa: BLE001, S110
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
            except Exception:  # noqa: BLE001, S112
                continue
        return count

    # ------------------------------------------------------------------
    # lookup
    # ------------------------------------------------------------------
    def _register_refreshed_catalog_record(self, cap: Capability) -> None:
        """Upsert a fetched record without changing cross-provider precedence."""
        key = cap.model_id.lower()
        provider = self._normalize_provider(cap.provider)
        provider_models = self._by_provider.get(provider, {})
        if key not in provider_models:
            self.register(cap)
            return

        # Refresh the provider-scoped entry. Only replace the flat lookup entry
        # when it already belongs to this provider; another provider may own it.
        provider_models[key] = cap
        current = self._models.get(key)
        if current is not None and self._normalize_provider(current.provider) == provider:
            self._models[key] = cap
        for alias in cap.aliases:
            self._alias_index.setdefault(alias.lower(), key)

    def _write_bundled_catalog_files(
        self,
        files: dict[str, str],
        backup_dir: Path | None = None,
    ) -> bool:
        """Back up and atomically replace bundled JSON snapshots when writable."""
        data_package = resources.files("llmcapa.data")
        backup_root = backup_dir or (
            Path.home() / ".llmcapa" / "github_catalog_backups"
        )
        success = True
        for filename, text in files.items():
            destination = data_package / filename
            if not isinstance(destination, Path):
                success = False
                warnings.warn(
                    f"Cannot rewrite bundled catalog {filename}: package resources are read-only; "
                    "the GitHub cache will be used instead.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue

            temporary_path: Path | None = None
            try:
                old_content = destination.read_bytes()
                if old_content.decode("utf-8") == text:
                    continue
                mode = stat.S_IMODE(destination.stat().st_mode)
                backup_root.mkdir(parents=True, exist_ok=True)
                backup_path = backup_root / f"{filename}.{time.time_ns()}.bak"
                backup_path.write_bytes(old_content)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary_file:
                    temporary_file.write(text)
                    temporary_path = Path(temporary_file.name)
                os.chmod(temporary_path, mode)
                os.replace(temporary_path, destination)
            except OSError as exc:
                success = False
                warnings.warn(
                    f"Could not rewrite bundled catalog {filename}: {exc}; "
                    "the GitHub cache will be used instead.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        return success

    def _write_user_catalog_override(
        self,
        cache_key: str,
        ref: str,
        providers: set[str],
        capabilities: list[Capability],
    ) -> None:
        """Persist a fetched catalog under the user's home directory."""
        override_dir = Path.home() / ".llmcapa" / "catalogs" / "github"
        override_key = hashlib.sha256(
            (cache_key + "\0" + ",".join(sorted(providers))).encode("utf-8")
        ).hexdigest()
        override_path = override_dir / f"{override_key}.json"
        payload = {
            "source": "https://github.com/awaku7/llmcapa",
            "ref": ref,
            "updated_at": time.time(),
            "providers": sorted(providers),
            "models": [cap.to_dict() for cap in capabilities],
        }
        temporary_path: Path | None = None
        try:
            override_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=override_dir,
                prefix=f".{cache_key}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write(chr(10))
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, override_path)
        except OSError as exc:
            warnings.warn(
                f"Could not persist GitHub catalog under {override_dir}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def fetch_github_catalog(
        self,
        provider: str,
        cache_ttl: int = 86400,
        ref: str = "main",
        write_bundled: bool = True,
    ) -> int:
        """Fetch this project's bundled catalog for one provider from GitHub.

        The download source is the public ``awaku7/llmcapa`` repository. The
        provider-to-file mapping is derived from the bundled catalogs, so
        providers backed by multiple files are handled as well. By default,
        fetched JSON files replace the corresponding bundled files when the
        package directory is writable; fetched records are also upserted into
        this registry and cached under ``~/.llmcapa``. If the package is
        read-only, a durable user catalog is saved under
        ``~/.llmcapa/catalogs/github``. Set ``write_bundled`` to False to use
        that user catalog instead of changing the bundled files.

        Provider-scoped lookup misses call this method once per provider per
        registry instance, then retry the lookup once.

        Args:
            provider: Provider name or one of its configured aliases.
            cache_ttl: Cache lifetime in seconds (default 24 hours). Pass 0 to
                force a network refresh.
            ref: Git branch, tag, or commit (default ``main``).
            write_bundled: Replace the package's source JSON files when writable.

        Returns:
            Number of matching model records registered.

        Raises:
            ValueError: If provider/ref is invalid or no bundled catalog exists.
            RuntimeError: If GitHub cannot be reached or its catalog is invalid.
        """
        self._ensure_loaded()
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("provider must be a non-empty string")
        if cache_ttl < 0:
            raise ValueError("cache_ttl must be non-negative")
        if (
            not isinstance(ref, str)
            or not re.fullmatch(r"[A-Za-z0-9._/-]+", ref)
            or any(part in ("", ".", "..") for part in ref.split("/"))
        ):
            raise ValueError("ref must be a valid branch, tag, or commit name")

        target_providers = {
            self._normalize_provider(name) for name in self._matching_providers(provider)
        }
        catalog_files = sorted(
            {
                filename
                for catalog_provider, filenames in self._catalog_files_by_provider.items()
                if catalog_provider in target_providers
                for filename in filenames
            }
        )
        if not catalog_files:
            raise ValueError(f"No bundled GitHub catalog found for provider: {provider}")

        # Key the cache by the actual remote files so aliases share one copy.
        cache_key = hashlib.sha256(
            (ref + "\0" + ",".join(catalog_files)).encode("utf-8")
        ).hexdigest()
        cache_path = (
            Path.home()
            / ".llmcapa"
            / "github_catalog_cache"
            / f"{cache_key}.json"
        )
        cached_files: dict[str, str] | None = None
        if cache_ttl > 0 and cache_path.is_file():
            try:
                if time.time() - cache_path.stat().st_mtime < cache_ttl:
                    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
                    files = cache_data.get("files") if isinstance(cache_data, dict) else None
                    if (
                        isinstance(files, dict)
                        and all(
                            filename in files and isinstance(files[filename], str)
                            for filename in catalog_files
                        )
                    ):
                        cached_files = {name: files[name] for name in catalog_files}
            except (OSError, ValueError, TypeError):
                cached_files = None

        downloaded_files: dict[str, str] = cached_files or {}
        if cached_files is None:
            raw_ref = quote(ref, safe="/")
            context = ssl.create_default_context()
            for filename in catalog_files:
                url = (
                    "https://raw.githubusercontent.com/awaku7/llmcapa/"
                    f"{raw_ref}/src/llmcapa/data/{quote(filename, safe='')}"
                )
                request = urllib.request.Request(
                    url, headers={"User-Agent": "llmcapa"}
                )
                try:
                    with urllib.request.urlopen(
                        request, context=context, timeout=30
                    ) as response:
                        content = response.read(25 * 1024 * 1024 + 1)
                    if len(content) > 25 * 1024 * 1024:
                        raise RuntimeError(f"GitHub catalog is too large: {filename}")
                    downloaded_files[filename] = content.decode("utf-8")
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"Failed to fetch GitHub catalog {filename} at {ref}: {exc}"
                    ) from exc

        capabilities: list[Capability] = []
        try:
            for filename, text in downloaded_files.items():
                payload = json.loads(text)
                records = (
                    payload.get("models", []) if isinstance(payload, dict) else payload
                )
                if not isinstance(records, list):
                    raise ValueError(f"catalog {filename} must contain a models list")
                for record in records:
                    if not isinstance(record, dict):
                        raise ValueError(
                            f"catalog {filename} contains a non-object record"
                        )
                    cap = Capability.from_dict(record)
                    if self._normalize_provider(cap.provider) in target_providers:
                        capabilities.append(cap)
        except (TypeError, ValueError, KeyError) as exc:
            raise RuntimeError(
                f"Invalid GitHub catalog for {provider}: {exc}"
            ) from exc

        if not capabilities:
            raise RuntimeError(
                f"GitHub catalog contains no models for provider: {provider}"
            )

        bundled_updated = False
        if write_bundled:
            bundled_updated = self._write_bundled_catalog_files(downloaded_files)
        if not bundled_updated:
            self._write_user_catalog_override(
                cache_key, ref, target_providers, capabilities
            )

        if cached_files is None:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(
                        {
                            "ref": ref,
                            "providers": sorted(target_providers),
                            "files": downloaded_files,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except OSError:
                pass

        for cap in capabilities:
            self._register_refreshed_catalog_record(cap)
        return len(capabilities)

    def _lookup_candidates(self, model_id: str) -> list[str]:
        """Return lookup keys including safe suffix normalization.

        Automatically strips known suffixes such as:
          -colon suffix (:free, :beta, etc.)
          -date patterns: YYYY-MM-DD, MM-DD, YYYYMMDD
          -literal suffixes: -latest, -preview, -preview-XX-XX
        Supports separators: -, _, . (e.g. gpt-4o-latest, model_latest,
        claude.latest). Multiple suffixes are stripped iteratively
        (e.g., -preview-05-20 removes -05-20 first, then -preview).

        """
        key = (model_id or "").strip().lower()
        candidates = [key]

        # 1. Strip colon suffix (e.g., :free, :beta)
        if ":" in key:
            candidates.append(key.split(":")[0])

        # 2. Progressively strip known trailing patterns
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

    @staticmethod
    def _numeric_fallback(
        requested: str, capabilities: list[Capability]
    ) -> Capability | None:
        """Return the closest lower numeric variant of a missing model ID.

        A fallback is considered only when the requested ID and a registered
        model/alias have the same non-numeric shape. For example,
        ``grok-4.7`` may fall back to ``grok-4.6`` but not to ``grok-3`` or
        ``gpt-4.6``. Exact IDs and normal aliases are resolved before this
        conservative fallback is attempted.
        """
        version_re = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)+|\d+)(?![A-Za-z])")

        def parse(value: str) -> tuple[str, tuple[int, ...]] | None:
            text = value.strip().lower()
            match = version_re.search(text)
            if not match:
                return None
            version = tuple(int(part) for part in match.group(1).split("."))
            shape = text[: match.start()] + "<version>" + text[match.end() :]
            return shape, version

        wanted = parse(requested)
        if wanted is None:
            return None
        wanted_shape, wanted_version = wanted
        best: tuple[tuple[int, ...], Capability] | None = None
        for capability in capabilities:
            names = [capability.model_id, *(capability.aliases or [])]
            for name in names:
                parsed = parse(str(name))
                if parsed is None:
                    continue
                shape, version = parsed
                # Never cross a major model generation during numeric
                # fallback.  For example, gemini-3-flash must not resolve to
                # gemini-2.5-flash; the two generations use different
                # thinking controls. Minor/patch fallback within the same
                # major generation remains supported (grok-4.7 -> grok-4.6).
                if (
                    shape != wanted_shape
                    or version >= wanted_version
                    or version[0] != wanted_version[0]
                ):
                    continue
                if best is None or version > best[0]:
                    best = (version, capability)
        return best[1] if best else None

    def _refresh_provider_catalog_on_miss(self, provider: str) -> bool:
        """Try one cached/remote GitHub refresh per provider per registry."""
        provider_key = "\0".join(
            sorted(
                self._normalize_provider(name)
                for name in self._matching_providers(provider)
            )
        )
        if provider_key in self._github_auto_refresh_attempted:
            return False
        self._github_auto_refresh_attempted.add(provider_key)
        try:
            return self.fetch_github_catalog(provider, cache_ttl=86400) > 0
        except (RuntimeError, ValueError):
            # Preserve the normal not-found behavior if GitHub is unavailable
            # or this provider has no published llmcapa catalog.
            return False

    def get(self, model_id: str, provider: str | None = None) -> Capability:
        """Resolve a model, refreshing a provider catalog once after a miss.

        When a provider is supplied and the local lookup misses, the matching
        llmcapa GitHub catalog is fetched (using its 24-hour cache) once per
        provider for this registry, then the lookup is retried once. Unscoped
        lookups and successful local lookups never trigger a fetch.
        """
        self._ensure_loaded()
        try:
            return self._get_local(model_id, provider)
        except ModelNotFoundError:
            if provider is None or not self._refresh_provider_catalog_on_miss(provider):
                raise
            return self._get_local(model_id, provider)

    def _get_local(self, model_id: str, provider: str | None = None) -> Capability:
        """Resolve a model id or alias to its Capability.

        Args:
            model_id: Model id, alias, or deployment name.
            provider: If given, normalize and resolve this provider alias,
                      then search only that single provider catalog. No other
                      provider is used as a fallback. Otherwise, returns the
                      first-registered (native) version.

        Raises:
            ModelNotFoundError: If the model cannot be resolved.
        """
        self._ensure_loaded()
        if provider is not None:
            # Scoped lookup: search only within the given provider
            normalized_provider = self._normalize_provider(provider)
            matching_providers = self._matching_providers(provider)
            # If the requested name is an actual provider, use that catalog
            # only. Otherwise resolve the name through its aliases. This
            # prevents alias queries such as provider="qwen" from combining
            # qwen and alibaba catalogs and returning duplicate model IDs.
            canonical_provider = next(
                (
                    canonical
                    for canonical, aliases in self._provider_aliases.items()
                    if normalized_provider == canonical
                    or normalized_provider in aliases
                ),
                normalized_provider,
            )
            ordered_providers = (
                [normalized_provider]
                if normalized_provider in self._by_provider
                else (
                    [canonical_provider]
                    if canonical_provider in self._by_provider
                    else sorted(matching_providers)
                )
            )
            for prov in ordered_providers:
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
                        # The global alias index may point to another
                        # provider when the same fallback alias is shared by
                        # multiple catalogs. Prefer an alias owned by this
                        # provider before giving up.
                        for candidate in prov_index.values():
                            if key in {
                                str(alias).strip().lower()
                                for alias in (candidate.aliases or [])
                            }:
                                return candidate
            fallback = self._numeric_fallback(
                model_id,
                [
                    cap
                    for prov in ordered_providers
                    for cap in self._by_provider.get(prov, {}).values()
                ],
            )
            if fallback is not None:
                return fallback
            raise ModelNotFoundError(model_id)
        # Unqualified lookup: use alias index (first-registered-wins).
        for key in self._lookup_candidates(model_id):
            resolved = self._alias_index.get(key)
            if resolved is not None:
                return self._models[resolved]
        fallback = self._numeric_fallback(model_id, list(self._models.values()))
        if fallback is not None:
            return fallback
        raise ModelNotFoundError(model_id)

    def list_models(
        self,
        provider: str | None = None,
        include_deprecated: bool = True,
    ) -> list[Capability]:
        """Return capabilities, optionally filtered to one provider catalog.

        A provider argument is normalized and resolved through the same alias
        map as :meth:`get`; it never combines catalogs or falls back to
        another provider.
        """
        self._ensure_loaded()
        if provider is not None:
            normalized_provider = self._normalize_provider(provider)
            matching_providers = self._matching_providers(provider)
            # Prefer an exact provider catalog when it exists. Alias names
            # such as "bedrock" still fall back to their canonical provider.
            canonical_provider = next(
                (
                    canonical
                    for canonical, aliases in self._provider_aliases.items()
                    if normalized_provider == canonical
                    or normalized_provider in aliases
                ),
                normalized_provider,
            )
            providers_to_list = (
                [normalized_provider]
                if normalized_provider in self._by_provider
                else (
                    [canonical_provider]
                    if canonical_provider in self._by_provider
                    else sorted(matching_providers)
                )
            )
            result: list[Capability] = []
            for prov in providers_to_list:
                idx = self._by_provider.get(prov)
                if idx:
                    result.extend(idx.values())
        else:
            result = list(self._models.values())
        if not include_deprecated:
            result = [c for c in result if not c.deprecated]
        return sorted(result, key=lambda c: (c.provider, c.model_id))

    def providers(self) -> list[str]:
        """Return the sorted list of known providers."""
        self._ensure_loaded()
        return sorted(self._by_provider.keys())

    def find(
        self,
        provider: str | None = None,
        min_context_window: int = 0,
        min_max_output_tokens: int = 0,
        include_deprecated: bool = False,
        **feature_flags: bool,
    ) -> list[Capability]:
        """Search models by conditions, optionally limited to one provider catalog.

        When *provider* is supplied, it follows the normalized provider alias
        contract used by :meth:`get` and :meth:`list_models`; no other catalog
        is consulted. ``feature_flags`` accepts keys like
        ``supports_vision=True`` or short forms like ``vision=True``.
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
                feature = key.removeprefix("supports_")
                if cap.supports(feature) != bool(expected):
                    ok = False
                    break
            if ok:
                result.append(cap)
        return result

    def find_by_model_id(self, model_id: str) -> list[tuple[str, Capability]]:
        """Find all (provider, Capability) tuples for a given model_id across providers."""
        self._ensure_loaded()
        key = model_id.strip().lower()
        results: list[tuple[str, Capability]] = []
        for prov, caps in self._by_provider.items():
            for lookup_key in [key] + [
                k for k in self._lookup_candidates(model_id) if k != key
            ]:
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
        provider: str | None = None,
        include_deprecated: bool = False,
        limit: int | None = None,
    ) -> list[Capability]:
        """Search locally, refreshing once if a provider-scoped query misses."""
        self._ensure_loaded()
        result = self._search_local(prefix, provider, include_deprecated, limit)
        if (
            result
            or provider is None
            or not prefix.strip()
            or limit == 0
            or not self._refresh_provider_catalog_on_miss(provider)
        ):
            return result
        return self._search_local(prefix, provider, include_deprecated, limit)

    def _search_local(
        self,
        prefix: str,
        provider: str | None = None,
        include_deprecated: bool = False,
        limit: int | None = None,
    ) -> list[Capability]:
        """Search models by prefix matching on model_id, display_name, or aliases.

        Case-insensitive prefix search. Results are sorted by
        ``(deprecated, provider, model_id)``, so non-deprecated models always
        precede deprecated ones and ``limit`` keeps the active entries.
        When *provider* is given, uses only that provider catalog and the
        same alias resolution as ``list_models`` / ``get``. With no provider,
        all provider catalogs are searched.
        """
        self._ensure_loaded()
        prefix_lower = prefix.strip().lower()
        if not prefix_lower:
            return []

        # Provider-scoped candidates via list_models so first-registered-wins
        # flat index does not hide same-id models under other providers.
        if provider is None:
            # Search must inspect every provider-scoped index.  The flat index
            # intentionally uses first-registered-wins for lookups, but that
            # would hide an OpenRouter route when a native catalog has the same
            # alias (for example ``meta/muse-spark-1.3``).
            candidates = [
                cap
                for prov in sorted(self._by_provider)
                for cap in self._by_provider[prov].values()
                if include_deprecated or not cap.deprecated
            ]
        else:
            candidates = self.list_models(
                provider=provider,
                include_deprecated=include_deprecated,
            )
        result = []
        for cap in candidates:
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

        # Active models first so that ``limit`` never truncates a result set
        # down to deprecated entries only.
        result.sort(key=lambda c: (c.deprecated, c.provider, c.model_id))
        if limit is not None:
            result = result[:limit]
        return result


def default_registry() -> Registry:
    """Return the global default registry instance."""
    return _default_registry


_default_registry = Registry()
