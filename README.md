# llmcapa

Lookup capabilities (context window, modalities, supported features) of various LLM models — fully offline by default.

## Features

- **Comprehensive Bundled Data**: Offline capability data for OpenAI, Anthropic, Google (Gemini), Microsoft (Phi), Amazon (Nova/Titan), Meta (Llama), Mistral, Qwen, DeepSeek, xAI (Grok), NVIDIA, MoonshotAI (Kimi), zhipu-ai (GLM), OpenRouter, and Japanese domestic models (NTT tsuzumi, PFN PLaMo, ELYZA, SoftBank, NEC, Fujitsu, etc. adopted by the Digital Agency's "GENNAI" platform).
- **Zero Runtime Dependencies**: Built entirely on the Python standard library.
- **Alias Resolution**: Automatically resolves aliases and provider-specific names (e.g., `gpt-4o-2024-08-06` -> `gpt-4o`, `gemini-1.5-pro-preview-0409` -> `gemini-1.5-pro`).
- **Advanced Feature Queries**: Check support for `vision`, `multimodal`, `chat_completion`, `responses_api`, `reasoning_effort`, `thinking_budget`, and specific input/output modalities (e.g., `image_input`, `image_output`, `audio_input`).
- **High Performance**: Evaluated feature checks are cached internally using memoization to avoid redundant calculations.
- **Cost Estimation**: Estimate API costs based on input and output token counts.
- **Drop-in Replacement Checker**: Check if a model can be safely replaced by another model based on context window and required features.
- **Tokenizer Mapping**: Access tokenizer names (e.g., `o200k_base`) directly from model capabilities.
- **Extendable**: Load your own local JSON model definitions.
- **CLI Included**: Query and list model capabilities directly from your terminal.

## Install

```bash
pip install llmcapa
```

Or from source:

```bash
pip install .
```

## Usage

### Basic Lookup

```python
import llmcapa

# Get model capabilities (case-insensitive, alias-resolved)
cap = llmcapa.get("gpt-4o")
print(cap.context_window)       # 128000
print(cap.max_output_tokens)    # 16384
print(cap.tokenizer_name)       # "o200k_base"

# Check feature support (using strings or Feature enum)
from llmcapa import Feature, ReasoningEffort

print(cap.supports(Feature.LLMC_FEAT_VISION))             # True
print(cap.supports(Feature.LLMC_FEAT_RESPONSES_API))      # True
print(cap.supports(Feature.LLMC_FEAT_REASONING_EFFORT))   # False

# Use ReasoningEffort enum for models supporting reasoning_effort
print(ReasoningEffort.LLMC_EFFORT_HIGH)                   # "high"
# List all supported features
print(cap.features())
# ['chat_completion', 'file', 'file_input', 'function_calling', 'image', 'image_input', 'json_mode', 'multimodal', 'responses_api', 'streaming', 'text', 'text_input', 'text_output', 'vision']
```

### Token & Cost Estimation

Roughly estimate the number of tokens for a given text (supporting 30+ major languages) and calculate API costs:

> [!NOTE]
> Token estimation is a lightweight, offline approximation. For exact token counts, please use the official APIs or dedicated tokenizers from each provider.

```python
gpt = llmcapa.get("gpt-4o")

# Estimate tokens for multilingual text
# If `tiktoken` is installed, it dynamically uses it for exact OpenAI token counts.
# Otherwise, it falls back to a highly-optimized, standard-library-only estimation.
text = "Hello world! こんにちは世界。"
tokens = gpt.estimate_tokens(text)
print(tokens)  # 10 (estimated tokens)

# Estimate API costs based on token counts (returns cost and currency)
res = gpt.estimate_cost(input_tokens=1500, output_tokens=500)
print(res)  # {'cost': 0.00875, 'currency': 'USD'}
```

### Drop-in Replacement Checker

Check if a model can be safely replaced by another model. The replacement model must have a context window at least as large as the target model and support all required features.

```python
gpt4o = llmcapa.get("gpt-4o")
gpt4o_mini = llmcapa.get("gpt-4o-mini")
gemini = llmcapa.get("gemini-3.5-flash")

# gpt-4o-mini has the same context window and supports all the same features
print(gpt4o.can_be_replaced_by(gpt4o_mini))  # True

# gemini-3.5-flash has a larger context window but lacks responses_api (which gpt-4o supports)
print(gpt4o.can_be_replaced_by(gemini))  # False

# If we only require vision and function_calling, gemini-3.5-flash can replace gpt-4o
print(gpt4o.can_be_replaced_by(gemini, required_features=["vision", "function_calling"]))  # True
```

### Modality & Multimodal Checks

You can check specific input/output modalities or general multimodal support using `Feature` enum:

```python
from llmcapa import Feature

gemini = llmcapa.get("gemini-3.5-flash")

print(gemini.supports(Feature.LLMC_FEAT_MULTIMODAL))    # True (supports multiple modalities)
print(gemini.supports(Feature.LLMC_FEAT_AUDIO_INPUT))   # True
print(gemini.supports(Feature.LLMC_FEAT_IMAGE_OUTPUT))  # False
```

### Reasoning & Thinking Checks

Differentiate between OpenAI-style `reasoning_effort` and Anthropic-style `thinking_budget` using `Feature` enum:

```python
from llmcapa import Feature

o1 = llmcapa.get("o1")
print(o1.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # True
print(o1.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # False

claude = llmcapa.get("claude-3-7-sonnet")
print(claude.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # False
print(claude.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # True
```

### Listing & Searching Models

```python
# List all models for a specific provider
for c in llmcapa.list_models(provider="anthropic"):
    print(c.model_id, c.context_window)

# Search models by capability criteria
big_reasoning_models = llmcapa.find(
    supports_reasoning=True,
    min_context_window=200000
)
```

### On-demand OpenRouter Integration (Caching)

To update model data or fetch the latest pricing, you can optionally fetch and register models from the OpenRouter API on-demand using `fetch_openrouter()`. The response is cached locally in `~/.llmcapa/openrouter_cache.json` and automatically loaded on subsequent imports (if the cache is less than 24 hours old), keeping the library fully offline during regular usage.

```python
# Fetch and register OpenRouter models dynamically
count = llmcapa.fetch_openrouter()
print(f"Registered {count} models from OpenRouter!")

# Lookup using OpenRouter model ID
cap = llmcapa.get("meta-llama/llama-3.3-70b-instruct")
print(cap.context_window)  # 131072
print(cap.pricing)         # {'input_per_1m': 0.1, 'output_per_1m': 0.32, 'currency': 'USD'}
```

### On-demand HuggingFace Integration (Caching)

You can also fetch and register popular models from the HuggingFace API on-demand using `fetch_huggingface()`. This retrieves the most downloaded text-generation and image-text-to-text models, registers their basic capabilities, and caches the result locally in `~/.llmcapa/huggingface_cache.json`.

```python
# Fetch and register top 100 HuggingFace models dynamically
count = llmcapa.fetch_huggingface()
print(f"Registered {count} models from HuggingFace!")

# Lookup using HuggingFace model ID
cap = llmcapa.get("deepseek-ai/DeepSeek-V4-Flash")
print(cap.context_window)   # 4096 (estimated; exact value not available via HF API)
print(cap.supports_vision)  # False (text-generation pipeline)

# Fetch a different number of models
count = llmcapa.fetch_huggingface(limit=200)
```

> **Note**: The HuggingFace listing API does not provide context window, pricing, or detailed capability data. The registered models have conservative defaults (4K context, 2K max output). For accurate data, use `fetch_openrouter()` or bundled snapshots.

### Token Counting (Standalone)

Count tokens for a single text or a list of chat messages using the best available tokenizer for a given model.

```python
# Count tokens for a text string
import llmcapa
tokens = llmcapa.count_tokens("Hello, world!", "gpt-4o")
print(tokens)  # exact count if tiktoken is installed, else estimation

# Count tokens for chat messages (includes overhead)
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
]
total = llmcapa.count_messages_tokens(messages, "gpt-4o")
print(total)
```

### Programmatic Registration

Register a Capability directly without a JSON file:

```python
from llmcapa import Capability

cap = Capability(
    provider="local",
    model_id="my-model",
    context_window=4096,
    max_output_tokens=1024,
    supports_function_calling=True,
    aliases=["mm"],
)
llmcapa.register(cap)

print(llmcapa.get("my-model").context_window)  # 4096
```

> **Note**: `llmcapa.get()` raises `ModelNotFoundError` if the model is not found.

### Custom Local Data

Load your own model definitions from a local JSON file:

```python
llmcapa.load_extra("my_models.json")
```

`my_models.json` format:
```json
{
  "models": [
    {
      "provider": "local",
      "model_id": "my-custom-model",
      "context_window": 32768,
      "max_output_tokens": 4096,
      "supports_function_calling": true,
      "aliases": ["my-model-latest"]
    }
  ]
}
```

## Development

For details on how to extend the library, add new providers, or implement new feature flags, please refer to the [DEVELOP.md](DEVELOP.md) guide.

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

# Count tokens for text or messages
llmcapa tokens gpt-4o "Hello, world!"
llmcapa tokens gpt-4o --messages '[{"role":"user","content":"Hi"}]'

# Load extra model data from a local JSON file on startup
llmcapa --extra my_models.json show gpt-4o

# Explicitly fetch and update the OpenRouter models cache (forces cache refresh)
llmcapa update

# Fetch and register popular models from HuggingFace
llmcapa fetch-hf
llmcapa fetch-hf --limit 200
```

## Notes

- **Static Snapshot**: Bundled capability data is a static snapshot. While we strive to keep it updated with the latest models (including GPT-5.5, Claude Fable, Gemini 3.5, DeepSeek V4, etc.), providers change limits and pricing frequently. Use `fetch_openrouter()` or verify with official documentation when absolute accuracy is critical.
- **HuggingFace Data Accuracy**: Models fetched via `fetch_huggingface()` have conservative defaults (4K context, 2K max output) since the HuggingFace listing API does not expose detailed capability data. For accurate specifications, use `fetch_openrouter()` or the bundled data.

## License

Apache License 2.0
