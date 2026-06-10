# Developer Guide

This document explains how to develop, extend, and maintain the `llmcapa` library.

---

## Project Structure

```
llmcapa/
├── pyproject.toml          # Build configuration (Hatchling / PEP 621)
├── LICENSE                 # Apache License 2.0
├── README.md               # User documentation
├── DEVELOP.md              # This guide
├── src/llmcapa/
│   ├── __init__.py         # Public API entry point
│   ├── models.py           # Capability dataclass and feature evaluation
│   ├── registry.py         # In-memory registry, loading, and OpenRouter fetching
│   ├── cli.py              # Command-line interface
│   └── data/               # Bundled offline capability data (JSON)
│       ├── __init__.py
│       ├── openai.json
│       ├── anthropic.json
│       └── ...
└── tests/                  # Unit tests (pytest)
    ├── test_registry.py
    ├── test_cache.py
    └── test_advanced.py
```

---

## Design Philosophy

1. **Offline-First**: All core capability data is bundled statically inside the package as JSON files. No network requests are made during standard lookups.
2. **Zero Runtime Dependencies**: The library must run using only the Python standard library. External packages (like `pytest` or `build`) are strictly for development/testing.
3. **Immutability & Performance**: The `Capability` dataclass is `frozen=True`. To avoid redundant calculations during feature checks, evaluation results are cached internally using memoization.

---

## Adding a New Provider

To add a new model provider (e.g., `cohere`):

### 1. Create a Data File
Create a new JSON file under `src/llmcapa/data/<provider_name>.json`.

```json
{
  "models": [
    {
      "provider": "cohere",
      "model_id": "command-r-plus",
      "display_name": "Command R+",
      "context_window": 128000,
      "max_output_tokens": 4000,
      "input_modalities": ["text"],
      "output_modalities": ["text"],
      "supports_chat_completion": true,
      "supports_function_calling": true,
      "supports_json_mode": true,
      "supports_streaming": true,
      "supports_vision": false,
      "supports_reasoning": false,
      "tokenizer_name": "cohere-command",
      "pricing": {
        "input_per_1m": 2.5,
        "output_per_1m": 10.0,
        "currency": "USD"
      },
      "knowledge_cutoff": "2024-01",
      "aliases": ["cohere/command-r-plus"]
    }
  ]
}
```

### 2. Update the Provider Test List
Open `tests/test_registry.py` and add your new provider name to the `expected` set in `test_providers()`:

```python
def test_providers():
    provs = llmcapa.providers()
    expected = {
        "openai", "anthropic", "google",
        "xai", "meta", "mistral", "qwen", "deepseek", "nvidia",
        "microsoft", "amazon", "ntt", "customer-cloud", "elyza",
        "softbank", "nec", "fujitsu", "pfn",
        "cohere",  # Add here
    }
    assert expected <= set(provs)
```

---

## Adding a New Feature Flag

To add a new capability/feature flag (e.g., `supports_structured_outputs`):

### 1. Update the Dataclass
Open `src/llmcapa/models.py` and add the new field to the `Capability` dataclass with a default value:

```python
@dataclass(frozen=True)
class Capability:
    ...
    supports_structured_outputs: bool = False
    ...
```

### 2. Update the Replacement Checker (Optional)
If the new feature is a critical capability that should be verified when checking if one model can replace another, add it to the `features_to_check` list in `can_be_replaced_by()` inside `src/llmcapa/models.py`:

```python
    def can_be_replaced_by(self, other: "Capability", required_features: Optional[List[str]] = None) -> bool:
        ...
        if required_features is None:
            features_to_check = [
                "vision", "function_calling", "json_mode", "streaming",
                "reasoning", "chat_completion", "responses_api",
                "reasoning_effort", "thinking_budget", "image_output",
                "audio_output", "video_output",
                "structured_outputs"  # Add here
            ]
            required_features = [f for f in features_to_check if self.supports(f)]
        ...
```

### 3. Update JSON Data Files
Add the new field to the relevant models in the JSON files under `src/llmcapa/data/`.

### 4. Add Unit Tests
Add test cases in `tests/test_advanced.py` or `tests/test_registry.py` to verify that the new feature flag is correctly parsed, evaluated, and cached.

---

## Development Workflow

### Running Tests
We use `pytest` for testing. Run the following command from the project root directory:

```bash
# Set PYTHONPATH to include the src directory
set "PYTHONPATH=src;%PYTHONPATH%"
python -m pytest -v
```

### Code Verification
Before building or committing, verify that all Python files compile successfully:

```bash
python -m py_compile src/llmcapa/*.py tests/*.py
```

### Building the Package
To build the source distribution (sdist) and wheel binary:

```bash
# Install build dependencies if not already installed
pip install build hatchling

# Build the package
python -m build
```

The built files will be generated under the `dist/` directory.

---

## OpenRouter Mapping Details

When `fetch_openrouter()` is called, it maps the OpenRouter API model schema to our `Capability` dataclass as follows:

| Capability Field | OpenRouter API Field | Mapping Logic / Fallback |
|---|---|---|
| `model_id` | `id` | Exact match |
| `display_name` | `name` | Falls back to `id` if missing |
| `context_window` | `context_length` | Cast to `int`, default `0` |
| `max_output_tokens` | `top_provider.max_completion_tokens` | Cast to `int`, default `0` |
| `input_modalities` | `architecture.input_modalities` | Default `["text"]` |
| `output_modalities` | `architecture.output_modalities` | Default `["text"]` |
| `supports_function_calling` | `supported_parameters` | `True` if `"tools"` or `"tool_choice"` is present |
| `supports_json_mode` | `supported_parameters` | `True` if `"structured_outputs"` or `"response_format"` is present |
| `supports_reasoning` | `supported_parameters` | `True` if `"reasoning"` or `"include_reasoning"` is present |
| `supports_reasoning_effort` | `supported_parameters` | `True` if `"reasoning"` is present |
| `pricing` | `pricing` | Converts `prompt` and `completion` rates to per-1M token rates |
| `aliases` | `id` | Lowercased `id` is added as an alias |
