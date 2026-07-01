# Provider Update Log

## OpenAI (2026-06-15)

### Source
- Official OpenAI API Documentation: https://developers.openai.com/api/docs/models
- Method: Playwright (headless browser) for JavaScript-rendered pages
- Individual model page access for detailed specs (context window, pricing, features, endpoints)

### Models Updated
39 active models (excluding deprecated models)

### Data Gaps
- gpt-4o (legacy) not in bundled data; available via OpenRouter fetch

## Anthropic (2026-06-15)

### Source
- Official Claude Platform Docs: https://platform.claude.com/docs/en/about-claude/models/overview
- Pricing page: https://platform.claude.com/docs/en/about-claude/pricing

### Models Updated
16 models total (8 active, 8 deprecated/retired)

## Google (2026-06-15)

### Source
- Official Gemini API documentation: https://ai.google.dev/gemini-api/docs/models
- Official Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing

### Models Updated
20 models total (14 active + 6 deprecated)

## DeepSeek (2026-07-01)

### Source
- Official DeepSeek API Docs: https://api-docs.deepseek.com/quick_start/pricing (Playwright)
- OpenRouter API comparison

### Models Updated (8 total)
- deepseek-v4-pro: max_output 131K -> 384K, added cache hit pricing
- deepseek-v4-flash: max_output 65K -> 384K, added cache hit pricing
- deepseek-v3.2, v3.1: preserved
- deepseek-v3: ctx=131K, deprecated (deepseek-chat deprecated 2026/07/24)
- deepseek-v3.2-speciale: added (new model)
- deepseek-r1-0528: preserved
- deepseek-r1: deprecated (deepseek-reasoner deprecated 2026/07/24)

## Meta (2026-07-01)

### Source
- OpenRouter API pricing data, official Llama website

### Models Updated (11 total)
- Added pricing from OpenRouter for all major models
- Added Llama 3.2 1B/3B Instruct, Llama Guard 3/4
- Updated context_window: 128K -> 131K (Llama 3.x series)

## Mistral (2026-07-01)

### Source
- Official Mistral docs, OpenRouter API pricing

### Models Updated (13 total)
- Added: mistral-medium-3.5, mistral-large-3, mistral-small-24b, ministral-3, codestral, devstral-2, mistral-nemo
- Deprecated: mistral-small (legacy), mistral-medium-3.1, magistral, mistral-7b, mixtral-8x7b

## xAI / Grok (2026-07-01)

### Source
- OpenRouter API comparison

### Models Updated (8 total)
- Consolidated grok-4.20 variants, added multi-agent model
- Context windows: grok-4.3 1M, grok-4.20 2M, grok-build-0.1 256K

## Qwen (2026-07-01)

### Source
- OpenRouter API data

### Models Updated (12 total)
- Added: qwen3.6, qwen3.5, qwen3, qwen3-2504, qwen3-vl, qwen3-coder, qwen3-coder-next, qwen3-next
- Deprecated: qwen2.5 series, qwq-32b

## MoonshotAI / Kimi (2026-07-01)

### Source
- OpenRouter API pricing data

### Models Updated (9 total)
- Major pricing corrections across all Kimi models (prices increased 50-400%)
- max_output_tokens corrected to 262K for all models
- Added kimi-k2.7-code, kimi-k2.6 variants

## Xiaomi (2026-07-01)

### Source
- OpenRouter API comparison

### Models Updated (5 total)
- mimo-v2.5: input pricing corrected $0.14 -> $0.105

## Sakana (2026-07-01)

### Models Verified (2 total)
- fugu, fugu-ultra: no changes needed

## Remaining Providers (2026-07-01)

### Amazon (Nova)
- 11 Titan/Nova models preserved (Titan series are Bedrock-specific)

### NVIDIA
- 5 main Nemotron models verified, pricing aligned with OpenRouter
- Azure NIM microservices (58 models) are catalog entries; preserved

### Microsoft (Phi)
- Main Phi-3/Phi-4 models preserved
- Azure AI services are catalog entries; preserved

### Japanese Providers
- NTT tsuzumi-2, ELYZA, SoftBank Sarashina2, NEC cotomi-v3, Fujitsu Takane, PFN PLaMo
- customer-cloud cc-gov-llm
- All preserved (source: GENNAI platform; no OpenRouter overlap)

### LMStudio Catalog
- Preserved as-is (community catalog of open-weight models)
