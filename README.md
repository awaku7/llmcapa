# llmcapa

Lookup capabilities (context window, modalities, supported features) of various LLM models — fully offline by default.

## Features

- **Comprehensive Bundled Data**: Offline capability data for OpenAI, Anthropic, Google (Gemini), Microsoft (Phi), Amazon (Nova/Titan), Meta (Llama), Mistral, Qwen, DeepSeek, xAI (Grok), NVIDIA, MoonshotAI (Kimi), zhipu-ai (GLM), Sakana AI (Fugu), **Azure AI Foundry**, Novita AI, OpenRouter, **HuggingFace (2,675 popular models)**, and Japanese domestic models (NTT tsuzumi, PFN PLaMo, ELYZA, SoftBank, NEC, Fujitsu, etc. adopted by the Digital Agency's "GENNAI" platform).
- **Zero Runtime Dependencies**: Built entirely on the Python standard library.
- **Alias Resolution**: Automatically resolves aliases and provider-specific names (e.g., `gpt-4o-2024-08-06` -> `gpt-4o`, `gemini-1.5-pro-preview-0409` -> `gemini-1.5-pro`).
- **Advanced Feature Queries**: Check support for `vision`, `multimodal`, `chat_completion`, `responses_api`, `reasoning_effort`, `thinking_budget`, and specific input/output modalities (e.g., `image_input`, `image_output`, `audio_input`).
- **High Performance**: Evaluated feature checks are cached internally using memoization to avoid redundant calculations.
- **Cost Estimation**: Estimate API costs based on input and output token counts.
- **Drop-in Replacement Checker**: Check if a model can be safely replaced by another model based on context window and required features.
- **Tokenizer Mapping**: Access tokenizer names (e.g., `o200k_base`) directly from model capabilities.
- **Extendable**: Load your own local JSON model definitions.
- **Ollama & HuggingFace Support**: Full capability data for **1,638 Ollama models** and **2,675 popular HuggingFace models** across 236 base models with all size variants (codegemma, llama, qwen, mistral, deepseek, gemma, phi, etc.). Zero-cost local inference models included.
- **FIM (Fill-in-the-Middle) Support**: Check if a model supports code infilling via `cap.supports('fim')`. Supported for codegemma, codellama, starcoder2, deepseek-coder, qwen2.5-coder, and more.
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

### Reasoning Effort Values

Retrieve the list of valid `reasoning_effort` values supported by a specific model:

```python
cap = llmcapa.get("gpt-5.5")
print(cap.get_reasoning_effort_values())
# ['none', 'minimal', 'low', 'medium', 'high', 'xhigh']

cap2 = llmcapa.get("o1")
print(cap2.get_reasoning_effort_values())
# ['none', 'low', 'medium', 'high']

# Models without reasoning_effort support return an empty list
cap3 = llmcapa.get("gpt-4o")
print(cap3.get_reasoning_effort_values())
# []
```

### Thinking Budget Values

Retrieve information about valid `thinking_budget` values for models that support it:

```python
cap = llmcapa.get("claude-sonnet-4-20250501")
print(cap.get_thinking_budget_values())
# {'type': 'token_range', 'min': 1024, 'max': 128000}

cap2 = llmcapa.get("deepseek-r1")
print(cap2.get_thinking_budget_values())
# {'type': 'token_range', 'min': 1024, 'max': 8192}

# Models without thinking_budget support return an empty dict
cap3 = llmcapa.get("gpt-4o")
print(cap3.get_thinking_budget_values())
# {}
```

### Sakana Fugu (Multi-Agent Orchestration)

Sakana AI's Fugu is a multi-agent orchestration system presented as a single model. It dynamically coordinates frontier models to tackle complex tasks. llmcapa bundles capability data for both Fugu and Fugu Ultra.

```python
import llmcapa

# Look up Fugu models (case-insensitive, alias-resolved)
fugu = llmcapa.get("fugu")
print(fugu.context_window)       # 272000
print(fugu.max_output_tokens)    # 128000
print(fugu.supports("vision"))   # True (text+image input)
print(fugu.pricing)              # {'input_per_1m': 5.0, 'output_per_1m': 30.0, ...}

fugu_ultra = llmcapa.get("fugu-ultra")
print(fugu_ultra.context_window) # 1000000 (1M tokens)
print(fugu_ultra.pricing)        # {'input_per_1m': 5.0, 'output_per_1m': 30.0, ...}

# List all Sakana models
for cap in llmcapa.list_models(provider="sakana"):
    print(cap.model_id, cap.context_window)
```


### FIM (Fill-in-the-Middle) Support

Check if a model supports code infilling / Fill-in-the-Middle completion:

```python
import llmcapa

cap = llmcapa.get("codegemma:2b", provider="ollama")
print(cap.supports("fim"))       # True
print(cap.supports("vision"))    # False
print("fim" in cap.features())   # True

cap2 = llmcapa.get("llama3.1", provider="ollama")
print(cap2.supports("fim"))      # False
```

The `fim` feature is available as a `Feature` enum member:

```python
from llmcapa import Feature
cap = llmcapa.get("starcoder2", provider="ollama")
print(cap.supports(Feature.LLMC_FEAT_FIM))  # True
```

### Listing & Searching Models

```python
# List all models for a specific provider
for c in llmcapa.list_models(provider="anthropic"):
    print(c.model_id, c.context_window)

# Search models (provider is required)
search_results = llmcapa.search("codegemma", provider="ollama")
big_reasoning_models = llmcapa.find(
    supports_reasoning=True,
    min_context_window=200000
)
```

### Novita AI (Bundled Provider)

Novita AI is a cloud platform offering 200+ open-source and proprietary models via a single API. llmcapa bundles capability data for 137 Novita AI models, including DeepSeek, Qwen, Meta Llama, GLM, Gemini, and many more, with Novita-specific pricing.

Models are accessed using the `novita/` prefix to avoid conflicts with official provider data:

```python
import llmcapa

# Look up Novita AI models
cap = llmcapa.get("novita/deepseek-v3.2")
print(cap.context_window)  # 163840
print(cap.pricing)         # {'input_per_1m': 0.269, 'output_per_1m': 0.4, 'currency': 'USD'}

cap = llmcapa.get("novita/qwen3.7-max")
print(cap.context_window)  # 1000000

# List all Novita AI models
for c in llmcapa.list_models(provider="novita"):
    print(c.model_id, c.context_window, c.pricing)

# List all providers including Novita
print(llmcapa.providers())
# ['...', 'novita', '...']
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

> **Note**: The HuggingFace listing API does not provide context window, pricing, or detailed capability data. The registered models have estimated context windows based on their model family (e.g., Llama 3: 8K, Qwen3: 128K). The bundled `huggingface.json` includes 2,675 popular text-generation models with improved context window estimates. For exact specifications, use `fetch_openrouter()` or official model cards.

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

- **Static Snapshot**: Bundled capability data is a static snapshot. See [docs/catalog_data_sources.md](docs/catalog_data_sources.md) for details on each provider's data source and known SSR limitations (Azure AI Catalog). While we strive to keep it updated with the latest models (including GPT-5.5, Claude Fable, Gemini 3.5, DeepSeek V4, Sakana Fugu, etc.), providers change limits and pricing frequently. Use `fetch_openrouter()` or verify with official documentation when absolute accuracy is critical.
- **HuggingFace Data Accuracy**: The bundled `huggingface.json` includes 2,675 popular text-generation models with context windows estimated from model families. Models fetched via `fetch_huggingface()` at runtime have estimated defaults. For exact specifications, consult official model cards.

## License

Apache License 2.0
