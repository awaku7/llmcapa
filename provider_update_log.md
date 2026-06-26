# Provider Update Log

## OpenAI (2026-06-15)

### Source
- Official OpenAI API Documentation: https://developers.openai.com/api/docs/models
- Method: Playwright (headless browser) for JavaScript-rendered pages
- Individual model page access for detailed specs (context window, pricing, features, endpoints)

### Models Updated
39 active models (excluding deprecated models):

**Frontier Models (14)**
- gpt-5.5, gpt-5.5-pro (1,050,000 ctx, highest reasoning, $30/$180)
- gpt-5.4, gpt-5.4-pro (1,050,000 ctx, highest reasoning, $30/$180)
- gpt-5.4-mini, gpt-5.4-nano (400,000 ctx, $0.2/$1.25)
- gpt-5.3-codex (400,000 ctx, coding-optimized)
- gpt-5.2, gpt-5.2-pro (400,000 ctx)
- gpt-5.1 (400,000 ctx)
- gpt-5, gpt-5-pro, gpt-5-mini, gpt-5-nano (400,000 ctx)

**Reasoning Models (2)**
- o3-pro, o3 (200,000 ctx, $20/$80, $5/$20)

**Legacy Chat Models (2)**
- gpt-4.1, gpt-4.1-mini (1,047,576 ctx)

**Chat Models (1)**
- gpt-4o-mini (128,000 ctx)

**Image Models (1)**
- gpt-image-2 (image generation, no function calling)

**Realtime & Audio Models (11)**
- gpt-realtime-2, gpt-realtime-translate, gpt-realtime-whisper
- gpt-realtime-1.5, gpt-realtime, gpt-realtime-mini
- gpt-audio-1.5, gpt-audio
- gpt-4o-transcribe, gpt-4o-mini-transcribe, gpt-4o-transcribe-diarize
- tts-1, tts-1-hd

**Open-Weight Models (2)**
- gpt-oss-120b, gpt-oss-20b (131,072 ctx)

**Embedding Models (2)**
- text-embedding-3-large, text-embedding-3-small

**Other (2)**
- chat-latest (dynamic alias, 400,000 ctx)
- omni-moderation (content moderation)

### Capabilities Coverage
- Function calling: 28 models
- JSON mode (Structured outputs): 20 models
- Streaming: 24 models
- Vision: 25 models
- Reasoning: 19 models
- Fine-tuning: 6 models
- Responses API: all chat/reasoning models

### Data Gaps
- Some special models (tts-1, whisper, omni-moderation) lack Features section in official docs
- text-embedding models have no context_window or pricing in model detail pages
- Cached input pricing only available for gpt-5.5-pro

## Anthropic (2026-06-15)

### Source
- Official Claude Platform Docs: https://platform.claude.com/docs/en/about-claude/models/overview
- Pricing page: https://platform.claude.com/docs/en/about-claude/pricing
- Method: Playwright (headless browser) for JavaScript-rendered pages

### Models Updated
16 models total (8 active, 8 deprecated/retired):

**Current Active Models (8)**
- claude-opus-4-8: 1M ctx, 128k out, $5/$25 MTok, batch $2.50/$12.50, fast mode $10/$50
- claude-opus-4-7: 1M ctx, 128k out, $5/$25 MTok, fast mode $30/$150
- claude-opus-4-6: 1M ctx, 128k out, $5/$25 MTok, fast mode $30/$150
- claude-opus-4-5: 1M ctx, 128k out, $5/$25 MTok (NEW - not in previous file)
- claude-sonnet-4-6: 1M ctx, 128k out, $3/$15 MTok (fixed max_output from 64k to 128k)
- claude-sonnet-4-5-20250929: 1M ctx, 128k out, $3/$15 MTok (fixed ctx from 200k to 1M)
- claude-haiku-4-5-20251001: 200k ctx, 64k out, $1/$5 MTok (fixed pricing from $0.25/$1.25)
- claude-mythos-preview: 1M ctx, 128k out, $25/$125 MTok (research preview)

**Suspended (2)**
- claude-fable-5: Suspended June 12, 2026
- claude-mythos-5: Suspended June 12, 2026

**Deprecated/Retained (6)**
- claude-3-7-sonnet, claude-3-5-sonnet, claude-3-5-haiku
- claude-3-opus, claude-3-sonnet, claude-3-haiku

### Key Fixes vs Previous File
- Haiku 4.5 pricing corrected: $0.25/$1.25 -> $1/$5 MTok
- Sonnet 4.5 context_window corrected: 200k -> 1M
- Sonnet 4.6 max_output_tokens corrected: 64k -> 128k
- Added Opus 4.5 model
- Added batch/cache pricing
- Added fast mode pricing for Opus models
- Fable 5 / Mythos 5 marked as suspended

### Next Provider
- Google (pending)

## Google (2026-06-15)

### Source
- Official Gemini API documentation: https://ai.google.dev/gemini-api/docs/models (Playwright scraping)
- Official Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing

### Models (20 total: 14 active + 6 deprecated)

**Active Text/Chat Models (7)**
- gemini-3.5-flash: ctx=1,048,576, out=65,536, $1.50/$9.00 MTok, fc/json/stream/vision/reasoning
- gemini-3.1-flash-lite: ctx=1,048,576, out=65,536, $0.25/$1.50 MTok, fc/json/stream/vision
- gemini-3-flash-preview: ctx=1,048,576, out=65,536, $0.50/$3.00 MTok, fc/json/stream/vision/reasoning
- gemini-3.1-pro-preview: ctx=1,048,576, out=65,536, $2.00/$12.00 MTok, fc/json/stream/vision/reasoning
- gemini-2.5-pro: ctx=1,048,576, out=65,536, $1.25/$10.00 MTok, fc/json/stream/vision/reasoning
- gemini-2.5-flash: ctx=1,048,576, out=65,536, $0.30/$2.50 MTok, fc/json/stream/vision/reasoning
- gemini-2.5-flash-lite: ctx=1,048,576, out=65,536, $0.10/$0.40 MTok, fc/json/stream/vision

**Image Models (3)**
- gemini-2.5-flash-image (Nano Banana): ctx=65,536, out=32,768
- gemini-3.1-flash-image (Nano Banana 2): ctx=131,072, out=32,768
- gemini-3-pro-image (Nano Banana Pro): ctx=65,536, out=32,768

**Live/Audio Models (2)**
- gemini-3.1-flash-live-preview: ctx=131,072, out=65,536, $0.75/$4.50 MTok
- gemini-2.5-flash-native-audio-preview-12-2025: ctx=1,048,576, out=65,536, $0.50/$2.00 MTok

**Embedding Models (2)**
- gemini-embedding-2: ctx=8,192, $0.20/MTok (multimodal)
- gemini-embedding-001: ctx=2,048, $0.15/MTok (text)

**Deprecated (6)**
- gemini-2.0-flash (Shutdown)
- gemini-2.0-flash-lite (Shutdown)
- gemini-1.5-pro (Deprecated)
- gemini-1.5-flash (Deprecated)
- gemini-3-pro-preview (Shutdown)
- multimodal-embedding (Legacy)

### Key Changes vs Previous File (18 -> 20 models)
- Renamed gemini-3-flash -> gemini-3-flash-preview
- Renamed gemini-3.1-pro -> gemini-3.1-pro-preview
- Added gemini-3.5-flash (was missing pricing, now $1.50/$9.00)
- Added gemini-3.1-flash-live-preview (new)
- Added gemini-2.5-flash-native-audio-preview-12-2025 (new)
- Added gemini-embedding-2 (replaces multimodal-embedding)
- Added gemini-embedding-001 (replaces text-embedding)
- Removed gemini-3.5-pro (doesn't exist in official docs)
- Corrected context_window for gemini-2.5-flash-image: 1M -> 65,536
- Corrected context_window for gemini-3.1-flash-image: 1M -> 131,072
- Corrected context_window for gemini-3-pro-image: 1M -> 65,536
- gemini-3-pro-preview marked as deprecated (shutdown)
- Added pricing for all active models

### Next Provider
- (pending)
