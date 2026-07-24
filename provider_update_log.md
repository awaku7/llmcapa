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

## OpenAI (2026-07-11)

### Source
- Official OpenAI API Documentation: https://developers.openai.com/api/docs/models
- Pricing page: https://developers.openai.com/api/docs/pricing
- Method: Playwright (headless browser) for JavaScript-rendered pages

### Models Updated
23 models total

### Changes
- Added GPT-5.6 Sol/Terra/Luna (flagship models, context=1.05M, max_output=128K, reasoning effort supported)
- Added GPT-5.5, GPT-5.5 Pro
- Added GPT-5.4, GPT-5.4 Mini, GPT-5.4 Nano, GPT-5.4 Pro
- Added GPT Image 2, GPT-Realtime 2.1/Mini, GPT-4o Transcribe/Mini Transcribe
- Added GPT-5.3 Codex, Sora 2
- Removed: gpt-4o, gpt-4o-mini, gpt-4.1 series (deprecated by OpenAI)
- Pricing updated to latest (2026-07)

## Bulk Update via OpenRouter API (2026-07-11)

### Source
- OpenRouter API: https://openrouter.ai/api/v1/models
- Method: fetch_openrouter(cache_ttl=0) via llmcapa

### Models Updated
- amazon: 21 models
- anthropic: 36 models
- deepseek: 18 models
- google: 71 models
- meta: 2 models
- microsoft: 57 models
- mistral: 15 models
- novita: 115 models
- nvidia: 68 models
- openai: 88 models
- openrouter: 14 models
- qwen: 34 models
- sakana: 2 models
- xai: 5 models
- xiaomi: 5 models

### Notes
- All provider data refreshed from OpenRouter API (accurate pricing, context windows, capabilities)
- Provider parameter is now required for search() to avoid cross-provider ambiguity (historical; made optional again in 0.4.0 — see below)
- Ollama data (1,638 models) preserved as local-only (not available via OpenRouter)
- Japanese domestic providers (NTT, ELYZA, SoftBank, NEC, Fujitsu, PFN) preserved from previous bundled data
- LMStudio catalog preserved from previous bundled data

## Fixes Applied (2026-07-11)

### Source
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing (Playwright)
- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing (Playwright)
- FIM flags: pattern-based for code completion models
- Responses API: restricted to OpenAI/Azure only

### Changes
- **Anthropic**: 9 models updated with official pricing (Fable 5 $10/$50, Opus 4.8 $5/$25, Sonnet 5 $3/$15, Haiku 4.5 $1/$5)
- **DeepSeek**: 2 models updated with official pricing (v4-flash $0.14/$0.28, v4-pro $0.435/$0.87)
- **FIM flags**: 0 models corrected (codegemma, codellama, starcoder2, deepseek-coder, qwen-coder, etc.)
- **Responses API**: 0 non-OpenAI/Azure models set to False
- **Provider names**: meta-llama->meta, x-ai->xai (consolidated)

## 0.4.0 — Provider aliases + search() optional provider (2026-07-18)

### Changes
- **`search(provider=None)`**: `provider` is optional again. When omitted, search runs across all providers via `list_models` / `_by_provider` (not the flat `_models` index), so provider-scoped duplicates (e.g. azure `gpt-4o`) are preserved.
- **Provider aliases** (`Registry._provider_aliases`): common client/SDK/OpenRouter-style names resolve to canonical registry providers:
  - `deepseek` ← `deepseek-ai`
  - `meta` ← `meta-llama`
  - `mistral` ← `mistralai`
  - `xai` ← `x-ai`, `grok`
  - `anthropic` ← `claude`
  - `google` ← `gemini`, `vertexai`, `vertex-ai`
  - `azure-openai` ← `azure`
  - `zhipu` ← `zai`, `z-ai`
  - `moonshotai` ← `moonshot`, `kimi`
  - `amazon` ← `bedrock`
  - `xiaomi` ← `mimo`
  - `huggingface` ← `hf`
  - `qwen` ← `alibaba`, `dashscope`
  - `lmstudio` ← `lm-studio`, `lm_studio`
- **Normalization**: provider names are lowercased; separators `_. \t` are unified to `-` (e.g. `azure_openai` → `azure-openai`).
- **Docs**: README.md / README.ja.md Listing & Searching examples updated (`search("gpt-4o")` all-providers).
- **Version**: `pyproject.toml` + `__init__.py` → **0.4.0**.

### Tests
- `test_search_provider_optional`, `test_search_provider_scoped_not_flat_index`, and related alias/search tests green; full `tests/` suite green.

## Mistral refresh (2026-07-18)

### Source
- Overview: https://docs.mistral.ai/models/overview (Playwright, 62 card slugs)
- Cards: https://docs.mistral.ai/models/model-cards/<slug>
- Scrape: `_scratch_mistral_scrape_full.json` via `scripts/_scrape_mistral.py`
- Apply: `scripts/_update_mistral.py`

### Result
- mistral.json: **62** models (active=20, deprecated=42, token-priced=12)
- Shape: xai-style with `extra.source`, deprecation/retirement, specialty pricing in extra
- Install copy: site-packages/llmcapa/data/mistral.json
- Feature flags: opacity-30 / cursor-not-allowed = disabled
- Skipped 404 slugs: none

## Mistral refresh (2026-07-18) — quality pass

### Fixes
- Voxtral Mini chat vs pure-transcribe classification (no longer force all non-small Voxtral to transcribe)
- Voxtral Small token pricing: use 3-amount cards as audio/min + input/output token
- Research cards with null feature flags default to chat=True (mathstral/next/mamba/7b)
- pick_model_id accepts open-* ids (e.g. open-codestral-mamba)

### Result
- mistral.json: **62** models (active=20, deprecated=42, token-priced=12)
- Install copy synced
- Skipped 404 slugs: none

## Mistral refresh (2026-07-18) — quality pass

### Fixes
- Voxtral Mini chat vs pure-transcribe classification (no longer force all non-small Voxtral to transcribe)
- Voxtral Small token pricing: use 3-amount cards as audio/min + input/output token
- Research cards with null feature flags default to chat=True (mathstral/next/mamba/7b)
- pick_model_id accepts open-* ids (e.g. open-codestral-mamba)

### Result
- mistral.json: **62** models (active=20, deprecated=42, token-priced=12)
- Install copy synced
- Skipped 404 slugs: none

## xAI refresh (2026-07-18)

### Source
- ListModels: `_scratch_xai_listmodels_parsed.json`
- Docs: https://docs.x.ai/developers/models (+ pricing / Voice / Imagine)
- Apply: `scripts/_update_xai.py`

### Result
- xai.json: **19** models (active=14, deprecated=5, token-priced=11)
- Text: grok-4.5 $2/$6 @500k (cache $0.5, long $4); grok-4.3 / 4.20 family $1.25/$2.5 @1M (cache $0.2, long $2.5)
- Imagine + Voice specialty entries included
- Install copy synced

## Anthropic refresh (2026-07-18)

### Source
- Overview + pricing Playwright: `_scratch_anthropic_overview_live2.html`, `_scratch_anthropic_pricing_live2.html`
- Docs: https://platform.claude.com/docs/en/about-claude/models/overview / https://platform.claude.com/docs/en/about-claude/pricing
- Apply: `scripts/_update_anthropic.py`

### Result
- anthropic.json: **17** models (active=10, deprecated=7, priced=17)
- New: Fable 5 / Mythos 5 $10/$50; Opus 4.8 $5/$25; Sonnet 5 intro $2/$10→$3/$15; Haiku 4.5 $1/$5
- Cache pricing (5m/1h/hit) + batch in extra; OpenRouter aliases deduped
- Install copy synced

## Moonshot / Kimi refresh (2026-07-18)

### Source
- Official: https://platform.moonshot.ai/docs/pricing/chat (Playwright `_scratch_kimi_k3_pricing.html`)
- OpenRouter cross-check: `_scratch_openrouter_models_latest.json`
- Apply: `scripts/_update_moonshot.py`

### Result
- moonshot.json: **10** models (active=7, deprecated=3)
- **Kimi K3** added: $3/$15 @1,048,576; cache miss $0.30
- K2.7 Code / K2.6 / K2.5 / K2 family retained
- Install copy synced

## MiniMax refresh (2026-07-18)

### Source
- Models: https://platform.minimax.io/docs/guides/models-intro
- PayGO: https://platform.minimax.io/docs/guides/pricing-paygo
- Chat enum: https://platform.minimax.io/docs/api-reference/text-chat
- Apply: `scripts/_update_minimax.py`

### Result
- minimax.json: **16** models (active=16, token-priced=10)
- Text: MiniMax-M3 $0.30/$1.20 ≤512k (perm 50% off; >512k $0.60/$2.40); M2.7 $0.30/$1.20; highspeed $0.60/$2.40
- Specialty: speech-2.8 (hd $100/M chars, turbo $60), Hailuo 2.3, music-3.0 $0.15/track, image-01 $0.0035
- Install copy synced

## Google refresh (2026-07-18)

### Source
- Pricing: https://ai.google.dev/gemini-api/docs/pricing
- Apply: `scripts/_update_google.py`

### Result
- google.json: **74** models (active=68, token-priced=52)
- Inserted: gemini-3.5-live-translate-preview, gemini-omni-flash-preview, gemini-3.1-flash-tts-preview
- Lyria-3 clip/pro: $0.04 / $0.08 per song (extra)
- Deprecations: gemini-2.0-flash* shut 2026-06-01; Imagen 4 2026-08-17; Veo 3/2 2026-06-30
- Install copy synced

## Qwen / Alibaba Model Studio refresh (2026-07-18)

### Source
- Pricing: https://www.alibabacloud.com/help/en/model-studio/model-pricing
- Apply: `scripts/_update_qwen.py`

### Result
- qwen.json: **158** models (active=154, token-priced=59)
- Added bare Model Studio IDs: qwen3.7-max/plus, qwen3.6-flash/plus/max-preview, qwen3.5-*, qwen-plus/flash/max, qwen3-max
- List prices (intl): qwen3.7-max $2.5/$7.5 (promo $1.25/$3.75); qwen3.7-plus $0.4/$1.6; qwen3.6-flash $0.25/$1.5
- Media: qwen-image-2.0-pro / wan2.7-image-pro $0.075/image; happyhorse-1.1-t2v ~$0.14/s 720p
- OpenRouter `qwen/...` entries kept; alibaba_list_pricing annotated in extra
- Install copy synced

## Qwen / Alibaba Model Studio refresh (2026-07-18)

### Source
- Pricing: https://www.alibabacloud.com/help/en/model-studio/model-pricing
- Apply: `scripts/_update_qwen.py`

### Result
- qwen.json: **158** models (active=154, token-priced=59)
- Added bare Model Studio IDs: qwen3.7-max/plus, qwen3.6-flash/plus/max-preview, qwen3.5-*, qwen-plus/flash/max, qwen3-max
- List prices (intl): qwen3.7-max $2.5/$7.5 (promo $1.25/$3.75); qwen3.7-plus $0.4/$1.6; qwen3.6-flash $0.25/$1.5
- Media: qwen-image-2.0-pro / wan2.7-image-pro $0.075/image; happyhorse-1.1-t2v ~$0.14/s 720p
- OpenRouter `qwen/...` entries kept; alibaba_list_pricing annotated in extra
- Install copy synced

## Anthropic refresh (2026-07-18)

### Source
- Overview + pricing Playwright: `_scratch_anthropic_overview_live3.html`, `_scratch_anthropic_pricing_live3.html`
- Docs: https://platform.claude.com/docs/en/about-claude/models/overview / https://platform.claude.com/docs/en/about-claude/pricing
- Apply: `scripts/_update_anthropic.py`

### Result
- anthropic.json: **17** models (active=10, deprecated=7, priced=17)
- New: Fable 5 / Mythos 5 $10/$50; Opus 4.8 $5/$25; Sonnet 5 intro $2/$10→$3/$15; Haiku 4.5 $1/$5
- Cache pricing (5m/1h/hit) + batch in extra; OpenRouter aliases deduped
- Install copy synced

## OpenAI (2026-07-18)

### Source
- Official OpenAI API Documentation: https://developers.openai.com/api/docs/models
- Pricing page: https://developers.openai.com/api/docs/pricing
- Method: Playwright (headless browser) for JavaScript-rendered pages

### Models Updated
106 models total

### Changes
- Flagship: GPT-5.6 Sol/Terra/Luna, GPT-5.5(+Pro), GPT-5.4(+Mini/Nano/Pro)
- Image: gpt-image-2 / 1.5 / 1-mini / 1, chatgpt-image-latest (token pricing + batch)
- Video: sora-2 ($0.10/s 720p), sora-2-pro ($0.30–$0.70/s)
- Realtime: 2.1/mini modality rates; translate $0.034/min; whisper $0.017/min
- Audio: gpt-audio-1.5 / mini; transcribe + diarize
- Specialized: chat-latest, gpt-5.4-cyber, gpt-5.5-cyber ($12.5/$75)
- Embeddings + omni-moderation-latest (free)
- Preserved legacy openai/* OpenRouter-style aliases from prior catalog

## Moonshot / Kimi refresh (2026-07-18)

### Source
- Official: https://platform.kimi.ai/docs/pricing/chat + chat-k27-code / chat-k26 / chat-k25 (Playwright live)
- Apply: `scripts/_update_moonshot.py`

### Result
- moonshot.json: **11** models (active=8, deprecated=3, priced=11)
- **Kimi K3**: $3/$15 @1M; cache hit $0.30 (fixed cache_miss mapping)
- **K2.7 Code**: $0.95/$4.00; cache hit $0.19 (was $1.0/$4.4)
- **K2.7 Code HighSpeed** added: $1.90/$8.00; cache hit $0.38
- **K2.6**: $0.95/$4.00; cache hit $0.16
- **K2.5**: $0.60/$3.00; cache hit $0.10 (was $0.57/$2.85)
- Multimodal (image+video) for K3 / K2.7 Code / K2.6 / K2.5
- Install copy synced

## Xiaomi MiMo refresh (2026-07-18)

### Source
- Models: https://mimo.mi.com/docs/en-US/quick-start/summary/model
- Pricing: https://mimo.mi.com/docs/en-US/price/pay-as-you-go (Playwright live)
- Apply: `scripts/_update_xiaomi.py`

### Result
- xiaomi.json: **11** models (active=7, deprecated=4, priced=7)
- **mimo-v2.5-pro**: $0.435/$0.87; cache hit $0.0036; 1M/128k
- **mimo-v2.5**: $0.14/$0.28 (was $0.105/$0.28); cache hit $0.0028; multimodal
- **mimo-v2.5-asr**: $0.074/hour overseas
- TTS series free limited-time; voiceclone/voicedesign added
- V2 series marked deprecated 2026-06-30
- Model IDs normalized to bare official IDs
- Install copy synced

## Meta Model API refresh (2026-07-18)

### Source
- Models: https://ai.developer.meta.com/docs/getting-started/models
- Pricing: https://ai.developer.meta.com/docs/getting-started/pricing-rate-limits (Playwright live)
- Apply: `scripts/_update_meta.py`

### Result
- meta.json: **32** models (active=32, priced=12)
- **muse-spark-1.1** inserted: $1.25/$4.25; cached input $0.15; 1M ctx
- Multimodal: text/image/video/PDF in → text out
- Web search grounding: $2.50 / 1k queries
- Free tier 60 RPM / 2M TPM; Paid 3k RPM / 4M TPM
- Existing Llama open-weight + OpenRouter-style entries retained
- Install copy synced

## NVIDIA NIM refresh (2026-07-18)

### Source
- Catalog: https://build.nvidia.com/models
- Model pages: nemotron-3-ultra / super / nano (Playwright live)
- Docs: https://docs.api.nvidia.com/nim/reference/llm-apis
- Apply: `scripts/_update_nvidia.py`

### Result
- nvidia.json: **73** models (active=73, priced=20)
- **nemotron-3-ultra-550b-a55b**: $0.50/$2.20 (Deep Infra); partners $0.41–$0.90 in
- **nemotron-3-super-120b-a12b**: $0.20/$0.80 (Bitdeer/CoreWeave)
- **nemotron-3-nano-30b-a3b**: $0.05/$0.20
- Free endpoint twins synced; omni / embed / cosmos3-nano* added
- Free NVIDIA trial endpoints remain available for evaluation
- Install copy synced
- Changes: updated:nvidia/nemotron-3-ultra-550b-a55b, updated:nvidia/nemotron-3-super-120b-a12b, inserted:nvidia/nemotron-3-nano-30b-a3b, inserted:nvidia/nemotron-3-nano-omni-30b-a3b-reasoning, inserted:nvidia/nemotron-3-embed-1b, replaced:nemotron-3.5-content-safety->nvidia/nemotron-3.5-content-safety, inserted:nvidia/cosmos3-nano, inserted:nvidia/cosmos3-nano-reasoner, synced_free:nvidia/nemotron-3-ultra-550b-a55b:free, synced_free:nvidia/nemotron-3-super-120b-a12b:free, synced_free:nvidia/nemotron-3-nano-30b-a3b:free

## Anthropic refresh (2026-07-18)

### Source
- Overview + pricing Playwright: `_scratch_anthropic_overview_live3.html`, `_scratch_anthropic_pricing_live3.html`
- Docs: https://platform.claude.com/docs/en/about-claude/models/overview / https://platform.claude.com/docs/en/about-claude/pricing
- Apply: `scripts/_update_anthropic.py`

### Result
- anthropic.json: **17** models (active=10, deprecated=7, priced=17)
- New: Fable 5 / Mythos 5 $10/$50; Opus 4.8 $5/$25; Sonnet 5 intro $2/$10→$3/$15; Haiku 4.5 $1/$5
- Cache pricing (5m/1h/hit) + batch in extra; OpenRouter aliases deduped
- Install copy synced

## Amazon Nova / Bedrock refresh (2026-07-18)

### Source
- Bedrock pricing: https://aws.amazon.com/bedrock/pricing/
- Nova pricing: https://aws.amazon.com/nova/pricing/
- Metered unit map: https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrock/USD/current/bedrock.json
- Scratch: `_scratch_amazon_nova_pricing_live.html`
- Apply: `scripts/_update_amazon.py`

### Result
- amazon.json: **19** models (active=19, deprecated=0, priced=18)
- Nova 2 Lite Global $0.30/$2.50 (geo $0.33/$2.75); Nova 2 Pro Preview $1.25/$10; Nova 2 Omni Preview $0.30/$2.50
- Nova 1.0: Micro $0.035/$0.14, Lite $0.06/$0.24, Pro $0.80/$3.20 (+latency-opt $1/$4), Premier $2.50/$12.50
- Sonic speech/text dual rates in extra; Canvas/Reel/Embeddings priced
- Titan Lite corrected to $0.15/$0.20; dual aliases amazon/* + amazon.*:0
- Install copy synced

## DeepSeek refresh (2026-07-18)

### Source
- Pricing: https://api-docs.deepseek.com/quick_start/pricing/
- Change log: https://api-docs.deepseek.com/updates/
- Thinking mode: https://api-docs.deepseek.com/guides/thinking_mode/
- Scratch: `_scratch_deepseek_pricing_live.html`
- Apply: `scripts/_update_deepseek.py`

### Result
- deepseek.json: **9** models (active=3, deprecated=6, priced=8)
- Active: V4 Flash $0.14/$0.28 (cache hit $0.0028); V4 Pro $0.435/$0.87 (cache hit $0.003625); 1M ctx / 384K max out
- Legacy deepseek-chat/reasoner → v4-flash until 2026-07-24
- Historical V3.x/R1 kept as deprecated; distill open-weight unpriced
- Removed Azure/NPU catalog pollution from deepseek provider
- Install copy synced

## Microsoft refresh (2026-07-18)

### Source
- Pricing: https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/microsoft/
- Retired: https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/model-lifecycle-retirement
- MAI docs: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai
- Catalog: https://ai.azure.com/catalog/publishers/microsoft
- MAI news: https://microsoft.ai/news/today-were-announcing-3-new-world-class-mai-models-available-in-foundry/
- Scratch: `_scratch_ms_pricing_live2.html`, `_scratch_ms_retired_text.txt`, `_scratch_ms_mai_docs.html`, `_scratch_ms_catalog_publisher.html`
- Apply: `scripts/_update_microsoft.py`

### Result
- microsoft.json: **60** models (active=48, deprecated=12, priced=21, extra=60)
- Phi PAYG corrected: Phi-4 $0.125/$0.50 ctx **16384**; Phi-4-mini $0.075/$0.30; multimodal text+image $0.08/$0.32 (audio $4/$0.32); reasoning $0.125/$0.50 @ 32K
- Phi-3/3.5 family marked deprecated (retired 2025-08-30) with Foundry rates kept
- MAI-DS-R1 Global $1.35/$5.40 deprecated (retired 2026-02-27); MAI-Image-2 $5/$33, Efficient/2e $5/$19.50; Voice/Transcribe unpriced meters
- Added MAI-Thinking-1 (256K) + MAI-Code-1-Flash product surface (unpriced)
- Deduped phi-4 / microsoft/phi-4; modalities fixed on multimodal/vision
- Azure AI services retained as license/unpriced; community forks free
- Install copy synced

## Japanese (multi-vendor) refresh (2026-07-18)

### Source
- PLaMo API: https://plamo.preferredai.jp/api
- PLaMo PR GA: https://www.preferred.jp/ja/news/pr20260622/
- PLaMo blog: https://tech.preferred.jp/ja/blog/plamo-3-0-prime-release/
- Cloud PF Type A: https://www.softbank.jp/biz/services/ai/cloud-pf-type-a/
- Sarashina3 blog: https://www.sbintuitions.co.jp/blog/entry/2026/06/30/sarashina3-mini-nano/
- tsuzumi 2: https://www.nttdata.com/jp/ja/lineup/tsuzumi/
- Azure tsuzumi: https://marketplace.microsoft.com/en-us/product/1681106214127.nttdata-tsuzumi-2-instruct-offer
- GENNAI / 7-model synthesis: https://ai-revolution.co.jp/media/japan-llm-7-comparison/
- Scratch: `_scratch_jp_*.html`, `_scratch_jp_plamo_api3.html`
- Apply: `scripts/_update_japanese.py`

### Result
- japanese.json: **14** models (active=11, deprecated=3, priced=3, extra=14)
- Providers: {'pfn': 3, 'softbank': 6, 'ntt': 1, 'nec': 1, 'elyza': 1, 'fujitsu': 1, 'customer-cloud': 1}
- PFN: plamo-3.0-prime GA 256K, Standard ¥60/¥250 (USD shell $0.4/$1.67); 2.0/2.2 deprecated
- SoftBank: Sarashina3 mini/nano/guard/embedding/rerank on Cloud PF Type A (2026-06-30); sarashina2-mini deprecated
- NTT tsuzumi-2: vision + Azure GPU-hour (~$0.76/h); secondary token $4/$1100
- NEC cotomi-v3 / ELYZA 70B / Fujitsu Takane 32B / CC Gov-LLM: enterprise quote, 源内 selected
- sakura kept separate (sakura.json) — next refresh
- Install copy synced

## Sakura (さくらのAI Engine) refresh (2026-07-18)

### Source
- Product: https://ai.sakura.ad.jp/sakura-ai/ai-engine/
- Closed models manual: https://manual.sakura.ad.jp/cloud/ai-engine/06-closed-model.html
- Playground: https://playground.aipf.sakura.ad.jp/
- Scratch: `_scratch_sakura_ai_engine.html`
- Apply: `scripts/_update_sakura.py`

### Result
- sakura.json: **26** models (active=26, deprecated=0, priced=14, extra=26)
- Tiers: {'standard': 15, 'closed': 2, 'public_preview': 8, 'alias_default': 1}
- Standard chat: gpt-oss-120b ¥0.15/0.75 per 10k (USD shell $0.10/$0.50); Qwen3-Coder 480B/30B; llm-jp-3.1
- Preview: Kimi-K2.6 (Anthropic Messages), Qwen3.6-35B, gemma-4-31B-it (2026-06-30), Phi-4 mini/mm, Qwen3-VL, Qwen3-0.6B-cpu, Qwen3-Embedding-4B
- Closed (application): PLaMo 2.0-31B, cotomi v3
- Also: whisper, e5-large, VOICEVOX×8, RAG document meter
- Free tier 3,000 chat req/mo; tax-included JPY official
- Replaced placeholder sakura-default with full catalog (default alias → gpt-oss-120b)
- Install copy synced

## OpenRouter refresh (2026-07-18)

### Source
- API: `https://openrouter.ai/api/v1/models` (live → `_scratch_openrouter_models.json`)
- Docs: https://openrouter.ai/docs
- Apply: `scripts/_update_openrouter.py`

### Result
- openrouter.json: **344** models (active=344, deprecated=0, priced=316, free=23, dynamic=5, extra=344)
- vision=179, reasoning=210, tools=270, cache_pricing=178
- native providers: 52 (top: [('openai', 67), ('qwen', 49), ('google', 28), ('mistralai', 19), ('anthropic', 15), ('z-ai', 12), ('deepseek', 11), ('meta-llama', 10), ('nvidia', 10), ('minimax', 8)])
- Pricing: API per-token ×1e6 → USD/1M; router prompt=-1 → catalog -1000000.0
- Cache: input_cache_read/write(/1h) in extra when present
- Synthetic `~*/…-latest` aliases retained (9)
- Replaced thin 14-model placeholder catalog
- Install copy synced

## azure_foundry — 2026-07-18 06:38 UTC

- Catalog: chat-completion filter via Playwright paginate (`_scratch_azure_catalog_raw.json`, n=694 unique names=694)
- Pricing: AOAI + Foundry partner pages (`_scratch_azure_pricing_tables.json`), price_keys=125
- Output: n=694 priced=114 maas_or_paygo=179 extra=683
- Providers (top): huggingface=414, foundry-local=91, azure-openai=34, fireworks=26, microsoft=26, azure-foundry=24, meta=16, nvidia=12, mistral=11, deepseek=8, xai=7, moonshot=3
- Sources: https://ai.azure.com/catalog/models ; https://azure.microsoft.com/en-us/pricing/details/azure-openai/ ; https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/*
- Script: `scripts/_update_azure_foundry.py` (+ `scripts/_scrape_azure_foundry_full.py`)
- Installed copy: `F:\Python314\Lib\site-packages\llmcapa\data\azure_foundry.json`

## azure_foundry — 2026-07-18 06:40 UTC

- Catalog: chat-completion filter via Playwright paginate (`_scratch_azure_catalog_raw.json`, n=694 unique names=694)
- Pricing: AOAI + Foundry partner pages (`_scratch_azure_pricing_tables.json`), price_keys=125
- Output: n=694 priced=114 maas_or_paygo=179 extra=683
- Providers (top): huggingface=414, foundry-local=91, azure-openai=34, fireworks=26, microsoft=26, azure-foundry=24, meta=16, nvidia=12, mistral=11, deepseek=8, xai=7, moonshot=3
- Sources: https://ai.azure.com/catalog/models ; https://azure.microsoft.com/en-us/pricing/details/azure-openai/ ; https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/*
- Script: `scripts/_update_azure_foundry.py` (+ `scripts/_scrape_azure_foundry_full.py`)
- Installed copy: `F:\Python314\Lib\site-packages\llmcapa\data\azure_foundry.json`

## azure_foundry — 2026-07-18 06:47 UTC

- Catalog: chat-completion filter via Playwright paginate (`_scratch_azure_catalog_raw.json`, n=694 unique names=694)
- Pricing: AOAI + Foundry partner pages (`_scratch_azure_pricing_tables.json`), price_keys=127
- Output: n=694 priced=94 maas_or_paygo=179 extra=679
- Providers (top): huggingface=414, foundry-local=91, azure-openai=34, fireworks=26, microsoft=26, azure-foundry=24, meta=16, nvidia=12, mistral=11, deepseek=8, xai=7, moonshot=3
- Sources: https://ai.azure.com/catalog/models ; https://azure.microsoft.com/en-us/pricing/details/azure-openai/ ; https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/*
- Script: `scripts/_update_azure_foundry.py` (+ `scripts/_scrape_azure_foundry_full.py`)
- Installed copy: `F:\Python314\Lib\site-packages\llmcapa\data\azure_foundry.json`

## 0.4.1 — Provider data refresh (2026-07-18)

- **Version**: `pyproject.toml` + `__init__.py` → **0.4.1** (data/catalog refresh; no API break).
- Refreshed provider catalogs (browser scrapes + update scripts), including:
  - microsoft, japanese, sakura, openrouter (**344**), azure_foundry (**694**)
  - Prior wave also covered: minimax, google, qwen, openai, moonshot, xiaomi, meta, nvidia, anthropic, amazon, deepseek
- Azure Foundry: chat-completion catalog + AOAI/Foundry partner pricing merge; long-context in `extra`; partner price-match deepen
- Moonshot: **kimi-k3** present (1M ctx; cache hit $0.30 / miss $3.00 / out $15.00; aliases include `kimi-latest`)
- OpenRouter: `moonshotai/kimi-k3` priced $3/$15
- Install data copies under site-packages synced by provider update scripts
- Timestamp: 2026-07-18 06:59 UTC

## OpenRouter refresh (2026-07-24)

### Source
- API: `https://openrouter.ai/api/v1/models` (live → `_scratch_openrouter_models.json`)
- Docs: https://openrouter.ai/docs
- Apply: `scripts/_update_openrouter.py`

### Result
- openrouter.json: **343** models (active=343, deprecated=0, priced=320, free=18, dynamic=5, extra=343)
- vision=181, reasoning=215, tools=272, cache_pricing=182
- native providers: 53 (top: [('openai', 67), ('qwen', 47), ('google', 30), ('mistralai', 19), ('anthropic', 15), ('z-ai', 12), ('deepseek', 11), ('nvidia', 10), ('meta-llama', 8), ('minimax', 8)])
- Pricing: API per-token ×1e6 → USD/1M; router prompt=-1 → catalog -1000000.0
- Cache: input_cache_read/write(/1h) in extra when present
- Synthetic `~*/…-latest` aliases retained (9)
- Replaced thin 14-model placeholder catalog
- Install copy synced
