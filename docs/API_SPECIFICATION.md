# llmcapa API Specification

**Status:** public API specification\
**Scope:** Python package API, capability data model, registry behavior, serialization, token/cost helpers, and CLI.\
**Version:** follows the installed package version (`llmcapa.__version__`).

## 1. Purpose and guarantees

`llmcapa` is an offline-first catalog for querying LLM model capabilities. It reports metadata; it does not send inference requests or construct provider requests automatically. Provider-specific request construction remains the responsibility of the client.

The bundled catalog is loaded lazily. Optional OpenRouter and Hugging Face refresh operations use the network and cache their results locally.

Unknown capability values are represented as unknown where supported (`None`), rather than being silently treated as unsupported. In particular, `supports_json_mode` and `supports_json_schema` are tri-state values.

## 2. Public exports

The package exports:

```python
import llmcapa

llmcapa.Capability
llmcapa.ComputerUseCapability
llmcapa.Feature
llmcapa.ReasoningEffort
llmcapa.Registry
llmcapa.ModelNotFoundError
llmcapa.__version__
```

Top-level functions are:

```python
llmcapa.get(model_id, provider=None)
llmcapa.list_models(provider=None, include_deprecated=True)
llmcapa.providers()
llmcapa.find(**conditions)
llmcapa.find_model(model_id)
llmcapa.search(prefix, provider=None, include_deprecated=False, limit=None)
llmcapa.register(capability)
llmcapa.load_extra(path)
llmcapa.fetch_openrouter(cache_ttl=86400)
llmcapa.fetch_huggingface(limit=100, cache_ttl=None)
llmcapa.count_tokens(text, model_id)
llmcapa.count_messages_tokens(messages, model_id)
llmcapa.supports_json_mode(model_id, provider=None)
llmcapa.supports_json_schema(model_id, provider=None)
llmcapa.get_computer_use_capability(model_id, provider=None)
llmcapa.supports_computer_use(model_id, provider=None)
llmcapa.supports_computer_action(model_id, action, provider=None)
llmcapa.supports_computer_environment(model_id, environment, provider=None)
```

## 3. Lookup and registry behavior

### 3.1 `get`

```python
cap = llmcapa.get("gpt-4o")
cap = llmcapa.get("model-id", provider="openai")
```

`model_id` may be a model ID, alias, or deployment name. Without `provider`, the first-registered/native entry wins when multiple catalogs contain the same model. With `provider`, lookup is provider-scoped.

Provider names are normalized case-insensitively and separators are unified. Common aliases include `grok`/`xai`, `claude`/`anthropic`, `vertexai`/`vertex-ai`, `bedrock`/`amazon`, `hf`/`huggingface`, and `dashscope`/`qwen`.

Numeric model fallback may resolve the closest lower registered numeric variant when an exact variant is absent. Clients requiring strict identity should inspect `cap.model_id` after lookup.

Raises `ModelNotFoundError` when no model can be resolved.

### 3.2 Listing, search, and filtering

- `list_models()` returns sorted capabilities by `(provider, model_id)`.
- `include_deprecated=False` removes deprecated entries.
- `providers()` returns sorted canonical/provider catalog names.
- `search()` performs case-insensitive prefix matching against `model_id`, `display_name`, and aliases. Empty prefixes return no results.
- `find()` supports `provider`, `min_context_window`, `min_max_output_tokens`, `include_deprecated`, and feature flags such as `vision=True` or `supports_function_calling=True`.
- `find_model()` returns every `(provider, Capability)` matching a model ID across providers.

## 4. Feature model

### 4.1 `Feature`

Standard feature values are:

```text
vision, function_calling, json_mode, streaming, reasoning,
chat_completion, responses_api, reasoning_effort, thinking_budget,
thinking_level, multimodal, fim, realtime, file_input,
speech_input, speech_output, embedding_output, rerank,
rerank_output,
text_input, image_input, audio_input, video_input,
text_output, image_output, audio_output, video_output
```

`Capability.supports(feature)` accepts either a `Feature` member or a string. It also accepts modality shorthand such as `image`, `audio`, `video`, `embedding`, and `rerank`.

```python
cap.supports("vision")
cap.supports(Feature.LLMC_FEAT_FUNCTION_CALLING)
cap.features()                 # sorted supported feature names
```

A feature can return `True`, `False`, or `None` when the underlying value is unknown. Custom features may be stored in `extra`.

`multimodal` is inferred when more than one input or output modality is present. `file_input` includes `file` and `pdf` input modalities; `embedding_output` includes `embedding` and `embeddings`.

### 4.2 `ReasoningEffort`

Values:

```text
none, minimal, low, medium, high, xhigh, max
```

## 5. `Capability` schema

`Capability` is a frozen dataclass. Required fields:

```python
Capability(provider: str, model_id: str)
```

Fields and defaults:

| Field | Type | Default / meaning |
|---|---|---|
| `provider` | `str` | required |
| `model_id` | `str` | required |
| `display_name` | `str` | `""` |
| `context_window` | `int` | `0` |
| `max_output_tokens` | `int` | `0` |
| `input_modalities` | `list[str]` | `[`"`text`"`]` |
| `output_modalities` | `list[str]` | `[`"`text`"`]` |
| `supports_function_calling` | `bool` | `False` |
| `supports_json_mode` | `bool \| None` | unknown by default |
| `supports_streaming` | `bool` | `True` |
| `supports_vision` | `bool` | `False` |
| `supports_reasoning` | `bool` | `False` |
| `supports_chat_completion` | `bool` | `True` |
| `supports_responses_api` | `bool` | `False` |
| `supports_reasoning_effort` | `bool` | `False` |
| `supports_thinking_budget` | `bool` | `False` |
| `supports_anthropic_api` | `bool` | `False` |
| `supports_google_api` | `bool` | `False` |
| `supports_fim` | `bool` | `False` |
| `license_type` | `str` | `"unknown"` |
| `tokenizer_name` | `str` | `""` |
| `knowledge_cutoff` | `str \| None` | `None` |
| `pricing` | `dict \| None` | `None` |
| `deprecated` | `bool` | `False` |
| `aliases` | `list[str]` | `[]` |
| `reasoning_effort_values` | `list[str] \| None` | provider defaults when supported |
| `thinking_budget_values` | `dict \| None` | provider defaults when supported |
| `extra` | `dict[str, Any]` | `{}` |
| `supports_realtime` | `bool` | `False` |
| `computer_use` | `ComputerUseCapability \| None` | `None` |
| `supports_json_schema` | `bool \| None` | unknown by default |
| `supports_thinking_level` | `bool` | `False` |
| `thinking_level_values` | `list[str] \| None` | `None` |
| `thinking_control` | `dict \| None` | `None` |

The order of fields is part of positional-constructor compatibility; new fields are appended.

## 6. Capability methods

```python
cap.supports(feature) -> bool | None
cap.features() -> list[str]
cap.estimate_tokens(text) -> int
cap.count_tokens(text) -> int
cap.estimate_cost(input_tokens=0, output_tokens=0) -> dict
cap.can_be_replaced_by(other, required_features=None,
                       required_actions=None, required_environment=None) -> bool
cap.get_reasoning_effort_values() -> list[str]
cap.get_thinking_budget_values() -> dict[str, Any]
cap.get_thinking_level_values() -> list[str]
cap.get_thinking_control() -> dict[str, Any]
cap.to_dict() -> dict
Capability.from_dict(data) -> Capability
```

`estimate_tokens()` uses `tiktoken` when an applicable tokenizer is available, otherwise a multilingual standard-library estimate. `count_tokens()` uses the best available provider/model tokenizer and falls back to estimation.

`estimate_cost()` expects `pricing.input_per_1m`, `pricing.output_per_1m`, and optionally `pricing.currency`. It returns `{"cost": float, "currency": str}`. Missing or unknown rates produce zero cost, not an exception.

`can_be_replaced_by()` requires an equal-or-larger context window and equivalent required capabilities. Computer Use replacement additionally checks provider/API type, tool type, environments, and required actions.

## 7. Reasoning and thinking controls

The normalized `thinking_control` object describes how a client should map a capability to a provider request. It does not perform that request.

Supported control kinds:

| `kind` | Parameter | Value |
|---|---|---|
| `toggle` | provider-specific | enabled/disabled-like values |
| `level` | `thinking_level` | discrete string levels |
| `budget` | `thinking_budget` | integer token range |

Examples:

```python
cap.get_thinking_control()
# {"kind": "budget", "parameter": "thinking_budget",
#  "type": "token_range", "min": 0, "max": 24576}
```

Convenience getters return copies and therefore do not expose mutable internal state.

## 8. Computer Use schema

`ComputerUseCapability` fields:

```text
supported, native, provider, model, api_type, tool_type, tool_version,
status, environments, actions, requires_beta, beta_header, enable_zoom,
source_url, checked_at
```

`environments` and `actions` are immutable `frozenset[str]` values in Python and sorted arrays in serialized JSON. `is_compatible_with()` checks support, native/API/tool type, beta requirements, environment inclusion, and action inclusion.

## 9. Serialization and external data

```python
payload = cap.to_dict()
restored = Capability.from_dict(payload)
```

The output is JSON-compatible. Optional `None` fields, empty `extra`, and internal caches are omitted. Unknown input keys are preserved in `extra`, allowing forward-compatible catalog data. `computer_use` is serialized as a nested object.

`load_extra(path)` accepts either a JSON list of records or an object with a `models` key. Existing entries with the same model ID are overridden. Each record must contain `provider` and `model_id`.

## 10. Dynamic catalogs

```python
llmcapa.fetch_openrouter(cache_ttl=86400)
llmcapa.fetch_huggingface(limit=100, cache_ttl=None)
```

These functions access external APIs, register returned records, and return the number of registered records. `cache_ttl=0` forces refresh. Normal capability lookup remains offline and uses bundled data plus valid local caches.

## 11. CLI

```text
llmcapa --version
llmcapa show MODEL_ID [--json]
llmcapa list [--provider NAME] [--json] [--no-deprecated]
llmcapa providers
llmcapa search PREFIX [--provider NAME] [--json] [--no-deprecated] [--limit N]
llmcapa tokens MODEL_ID [TEXT] [--messages]
llmcapa update
llmcapa fetch-hf [--limit N]
```

Global option:

```text
--extra JSON_FILE    load additional model records before executing the command
```

`show`, `list`, and `search` support JSON output. CLI failures return a non-zero exit status and print an error to stderr. `tokens --messages` expects a JSON array of messages and can also read text from stdin.

## 12. Compatibility and versioning

- Existing fields and methods remain supported unless explicitly marked deprecated.
- New catalog fields are optional and must be safely ignored by older clients.
- `Capability.from_dict()` preserves unknown fields in `extra`.
- `to_dict()` may omit unset optional fields; consumers must not require omitted optional keys.
- `supports_json_mode` and `supports_json_schema` are independent.
- Provider-specific documentation is maintained separately and should be linked from this document rather than duplicated here.

## 13. Related specifications

- [Catalog data sources](catalog_data_sources.md)
- [Structured output provider status](STRUCTURED_OUTPUT_PROVIDER_STATUS.md)
