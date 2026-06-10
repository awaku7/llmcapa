# llmcapa Requirements Specification

## Purpose
Provide a Python library that offers a unified API to retrieve the capabilities and constraints (context window, modalities, supported features, pricing, etc.) of various LLM models.
The library is distributed as a pip-installable package.

## Core Principles
- **Offline-First**: Capability data is bundled statically inside the package as JSON files, allowing standard lookups to run fully offline without any network connection.
- **Separation of Data and Logic**: Model definitions are stored in JSON files, making it easy to add or update models without changing the core Python code.
- **Zero Runtime Dependencies**: Built entirely on the Python standard library to ensure high compatibility and lightweight installation.

## Supported Providers
- **Bundled Static Data**: OpenAI, Anthropic, Google (Gemini), Meta (Llama), Mistral, Qwen, DeepSeek, NVIDIA, Microsoft (Phi), Amazon (Nova/Titan), and Japanese domestic models (NTT tsuzumi, PFN PLaMo, ELYZA, etc.).
- **Dynamic Integration**: Supports fetching and registering all 300+ models dynamically from the OpenRouter API.

## Capability Schema
| Field | Type | Description / Example |
|---|---|---|
| `provider` | `str` | Name of the provider (e.g., `"openai"`) |
| `model_id` | `str` | Unique model identifier (e.g., `"gpt-4o"`) |
| `display_name` | `str` | Human-readable name (e.g., `"GPT-4o"`) |
| `context_window` | `int` | Maximum context length in tokens (e.g., `128000`) |
| `max_output_tokens` | `int` | Maximum completion tokens (e.g., `16384`) |
| `input_modalities` | `list[str]` | Supported input modalities (e.g., `["text", "image"]`) |
| `output_modalities` | `list[str]` | Supported output modalities (e.g., `["text"]`) |
| `supports_function_calling` | `bool` | Whether function calling/tool use is supported |
| `supports_json_mode` | `bool` | Whether JSON mode or structured outputs are supported |
| `supports_streaming` | `bool` | Whether streaming responses are supported |
| `supports_vision` | `bool` | Whether image input is supported |
| `supports_reasoning` | `bool` | Whether reasoning/thinking is supported |
| `supports_chat_completion` | `bool` | Whether standard chat completion API is supported |
| `supports_responses_api` | `bool` | Whether OpenAI-style Responses API is supported |
| `supports_reasoning_effort` | `bool` | Whether reasoning effort parameter is supported |
| `supports_thinking_budget` | `bool` | Whether thinking budget parameter is supported |
| `tokenizer_name` | `str` | Name of the tokenizer used (e.g., `"o200k_base"`) |
| `knowledge_cutoff` | `str` | Knowledge cutoff date (e.g., `"2023-10"`) |
| `pricing` | `dict` | Pricing rates per 1M tokens (e.g., `{"input_per_1m": 2.5, "output_per_1m": 10.0, "currency": "USD"}`) |
| `deprecated` | `bool` | Whether the model is deprecated |
| `aliases` | `list[str]` | Alternative names or specific versions (e.g., `["gpt-4o-2024-08-06"]`) |
| `extra` | `dict` | Custom provider-specific fields |

## Public API
```python
import llmcapa

# Retrieve capabilities for a single model (case-insensitive, alias-resolved)
cap = llmcapa.get("gpt-4o")
print(cap.context_window)       # 128000
print(cap.supports("vision"))    # True

# List all supported features as a sorted list
print(cap.features())            # ['chat_completion', 'function_calling', ...]

# Estimate API costs based on token counts
cost_info = cap.estimate_cost(input_tokens=1500, output_tokens=500)

# Check if a model can be safely replaced by another model
gpt4o = llmcapa.get("gpt-4o")
gemini = llmcapa.get("gemini-3.5-flash")
can_replace = gpt4o.can_be_replaced_by(gemini, required_features=["vision", "function_calling"])

# List models
llmcapa.list_models()                      # All models
llmcapa.list_models(provider="anthropic")  # Filtered by provider

# Search models by capability criteria
llmcapa.find(supports_vision=True, min_context_window=100000)

# Load custom user-defined model data from a local JSON file
llmcapa.load_extra("my_models.json")

# Fetch and register OpenRouter models dynamically with a TTL cache
llmcapa.fetch_openrouter(cache_ttl=86400)
```

## CLI
```bash
# Show capabilities of a specific model
llmcapa show gpt-4o
llmcapa show gpt-4o --json

# List all known models
llmcapa list
llmcapa list --provider google
llmcapa list --json --no-deprecated

# List all known providers
llmcapa providers

# Explicitly fetch and update the OpenRouter models cache
llmcapa update

# Clear local OpenRouter cache file
llmcapa --clear-cache
```

## Package Structure
```
llmcapa/
├── pyproject.toml        # Build configuration (Hatchling / PEP 621)
├── README.md             # User documentation
├── DEVELOP.md            # Developer guide
├── REQUIREMENTS.md       # Requirements specification (this document)
├── LICENSE               # Apache License 2.0
├── src/llmcapa/
│   ├── __init__.py       # Public API entry point
│   ├── models.py         # Capability dataclass and feature evaluation
│   ├── registry.py       # In-memory registry, loading, and OpenRouter fetching
│   ├── cli.py            # Command-line interface
│   └── data/             # Bundled offline capability data (JSON)
│       ├── __init__.py
│       ├── openai.json
│       ├── anthropic.json
│       ├── google.json
│       ├── openrouter.json
│       └── ...
└── tests/                # Unit tests (pytest)
    ├── test_registry.py
    ├── test_cache.py
    └── test_advanced.py
```

## Distribution & Requirements
- **Build Backend**: Hatchling (PEP 621 compliant)
- **Installation**: `pip install llmcapa` / `pip install .`
- **Python Compatibility**: Python >= 3.9
- **Runtime Dependencies**: None (Standard library only)
- **License**: Apache License 2.0

## Testing
- Unit tests using `pytest`
- Schema validation tests for all bundled JSON data files
