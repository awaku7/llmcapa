"""Update openai.json with scraped data and update provider_update_log.md."""
import json, re
from datetime import date

# ── Parsed OpenAI model data from scraped pages ──

FLAGSHIP_MODELS = {
    "gpt-5.6-sol": {
        "model_id": "gpt-5.6-sol",
        "display_name": "GPT-5.6 Sol",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2026-02-16",
        "aliases": ["gpt-5.6"],
    },
    "gpt-5.6-terra": {
        "model_id": "gpt-5.6-terra",
        "display_name": "GPT-5.6 Terra",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 15.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2026-02-16",
        "aliases": [],
    },
    "gpt-5.6-luna": {
        "model_id": "gpt-5.6-luna",
        "display_name": "GPT-5.6 Luna",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 1.0, "output_per_1m": 6.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2026-02-16",
        "aliases": [],
    },
    "gpt-5.5": {
        "model_id": "gpt-5.5",
        "display_name": "GPT-5.5",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-10-01",
        "aliases": [],
    },
    "gpt-5.5-pro": {
        "model_id": "gpt-5.5-pro",
        "display_name": "GPT-5.5 Pro",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 30.0, "output_per_1m": 180.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-10-01",
        "aliases": [],
    },
    "gpt-5.4": {
        "model_id": "gpt-5.4",
        "display_name": "GPT-5.4",
        "context_window": 1048576,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 15.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
    "gpt-5.4-mini": {
        "model_id": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "context_window": 524288,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 0.75, "output_per_1m": 4.5, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
    "gpt-5.4-nano": {
        "model_id": "gpt-5.4-nano",
        "display_name": "GPT-5.4 Nano",
        "context_window": 262144,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 0.2, "output_per_1m": 1.25, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
    "gpt-5.4-pro": {
        "model_id": "gpt-5.4-pro",
        "display_name": "GPT-5.4 Pro",
        "context_window": 1048576,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 30.0, "output_per_1m": 180.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
}

SPECIALIZED_MODELS = {
    "gpt-realtime-2.1": {
        "model_id": "gpt-realtime-2.1",
        "display_name": "GPT-Realtime 2.1",
        "context_window": 131072,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 4.0, "output_per_1m": 24.0, "currency": "USD"},
        "input_modalities": ["text", "image", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "supports_reasoning": True,
    },
    "gpt-realtime-2.1-mini": {
        "model_id": "gpt-realtime-2.1-mini",
        "display_name": "GPT-Realtime 2.1 Mini",
        "context_window": 131072,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 0.6, "output_per_1m": 2.4, "currency": "USD"},
        "input_modalities": ["text", "image", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "supports_reasoning": True,
    },
    "gpt-4o-transcribe": {
        "model_id": "gpt-4o-transcribe",
        "display_name": "GPT-4o Transcribe",
        "context_window": 32768,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 10.0, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": True,
    },
    "gpt-4o-mini-transcribe": {
        "model_id": "gpt-4o-mini-transcribe",
        "display_name": "GPT-4o Mini Transcribe",
        "context_window": 32768,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 1.25, "output_per_1m": 5.0, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": True,
    },
    "gpt-5.3-codex": {
        "model_id": "gpt-5.3-codex",
        "display_name": "GPT-5.3 Codex",
        "context_window": 131072,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 1.75, "output_per_1m": 14.0, "currency": "USD"},
        "supports_function_calling": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
    },
    "sora-2": {
        "model_id": "sora-2",
        "display_name": "Sora 2",
        "context_window": 0,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "supports_chat_completion": False,
        "supports_streaming": False,
        "supports_vision": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "price_per_second_720p": 0.10,
            "batch_price_per_second_720p": 0.05,
            "billing_unit": "per_second",
        },
    },
    "sora-2-pro": {
        "model_id": "sora-2-pro",
        "display_name": "Sora 2 Pro",
        "context_window": 0,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["video"],
        "supports_chat_completion": False,
        "supports_streaming": False,
        "supports_vision": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "price_per_second_720p": 0.30,
            "price_per_second_1024p": 0.50,
            "price_per_second_1080p": 0.70,
            "batch_price_per_second_720p": 0.15,
            "batch_price_per_second_1024p": 0.25,
            "batch_price_per_second_1080p": 0.35,
            "billing_unit": "per_second",
        },
    },
    "gpt-image-2": {
        "model_id": "gpt-image-2",
        "display_name": "GPT Image 2",
        "context_window": 131072,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text", "image"],
        "supports_vision": True,
        "supports_function_calling": False,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "image_input_per_1m": 8.0,
            "image_cached_input_per_1m": 2.0,
            "image_output_per_1m": 30.0,
            "text_input_per_1m": 5.0,
            "text_cached_input_per_1m": 1.25,
            "batch_image_input_per_1m": 4.0,
            "batch_image_output_per_1m": 15.0,
            "batch_text_input_per_1m": 2.5,
        },
    },
    "gpt-image-1.5": {
        "model_id": "gpt-image-1.5",
        "display_name": "GPT Image 1.5",
        "context_window": 131072,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 10.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text", "image"],
        "supports_vision": True,
        "supports_function_calling": False,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "image_input_per_1m": 8.0,
            "image_cached_input_per_1m": 2.0,
            "image_output_per_1m": 32.0,
            "text_input_per_1m": 5.0,
            "text_cached_input_per_1m": 1.25,
            "text_output_per_1m": 10.0,
            "note": "Text output tokens include model reasoning tokens",
        },
    },
    "gpt-image-1-mini": {
        "model_id": "gpt-image-1-mini",
        "display_name": "GPT Image 1 Mini",
        "context_window": 131072,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 2.0, "output_per_1m": 8.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text", "image"],
        "supports_vision": True,
        "supports_function_calling": False,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "image_input_per_1m": 2.5,
            "image_cached_input_per_1m": 0.25,
            "image_output_per_1m": 8.0,
            "text_input_per_1m": 2.0,
            "text_cached_input_per_1m": 0.2,
        },
    },
    "gpt-image-1": {
        "model_id": "gpt-image-1",
        "display_name": "GPT Image 1",
        "context_window": 131072,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 40.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text", "image"],
        "supports_vision": True,
        "supports_function_calling": False,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "image_input_per_1m": 10.0,
            "image_cached_input_per_1m": 2.5,
            "image_output_per_1m": 40.0,
            "text_input_per_1m": 5.0,
            "text_cached_input_per_1m": 1.25,
        },
    },
    "chatgpt-image-latest": {
        "model_id": "chatgpt-image-latest",
        "display_name": "ChatGPT Image Latest",
        "context_window": 131072,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 10.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text", "image"],
        "supports_vision": True,
        "supports_function_calling": False,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "image_input_per_1m": 8.0,
            "image_cached_input_per_1m": 2.0,
            "image_output_per_1m": 32.0,
            "text_input_per_1m": 5.0,
            "text_cached_input_per_1m": 1.25,
            "text_output_per_1m": 10.0,
        },
    },
    "gpt-realtime-translate": {
        "model_id": "gpt-realtime-translate",
        "display_name": "GPT Realtime Translate",
        "context_window": 0,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["audio"],
        "output_modalities": ["audio"],
        "supports_chat_completion": False,
        "supports_streaming": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "price_per_minute": 0.034,
            "billing_unit": "per_minute",
        },
    },
    "gpt-realtime-whisper": {
        "model_id": "gpt-realtime-whisper",
        "display_name": "GPT Realtime Whisper",
        "context_window": 0,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "price_per_minute": 0.017,
            "billing_unit": "per_minute",
        },
    },
    "gpt-4o-transcribe-diarize": {
        "model_id": "gpt-4o-transcribe-diarize",
        "display_name": "GPT-4o Transcribe Diarize",
        "context_window": 32768,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 10.0, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "estimated_cost_per_minute": 0.006,
            "use_case": "transcription_diarization",
        },
    },
    "chat-latest": {
        "model_id": "chat-latest",
        "display_name": "Chat Latest",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "supports_reasoning": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "cached_input_per_1m": 0.5,
            "category": "chatgpt",
        },
    },
    "gpt-5.4-cyber": {
        "model_id": "gpt-5.4-cyber",
        "display_name": "GPT-5.4 Cyber",
        "context_window": 1048576,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": None, "output_per_1m": None, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "supports_reasoning": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "category": "cyber",
            "note": "Pricing not publicly listed on pricing page",
        },
    },
    "gpt-5.5-cyber": {
        "model_id": "gpt-5.5-cyber",
        "display_name": "GPT-5.5 Cyber",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 12.5, "output_per_1m": 75.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "supports_reasoning": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "cached_input_per_1m": 1.25,
            "category": "cyber",
        },
    },
    "gpt-audio-1.5": {
        "model_id": "gpt-audio-1.5",
        "display_name": "GPT Audio 1.5",
        "context_window": 131072,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 4.0, "output_per_1m": 16.0, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_chat_completion": True,
        "supports_streaming": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "category": "audio",
        },
    },
    "gpt-audio-mini": {
        "model_id": "gpt-audio-mini",
        "display_name": "GPT Audio Mini",
        "context_window": 131072,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 0.6, "output_per_1m": 2.4, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_chat_completion": True,
        "supports_streaming": True,
        "extra": {
            "source": "https://developers.openai.com/api/docs/pricing",
            "category": "audio",
        },
    },
    "text-embedding-3-small": {
        "model_id": "text-embedding-3-small",
        "display_name": "Text Embedding 3 Small",
        "context_window": 8191,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.02, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["text"],
        "output_modalities": ["embedding"],
        "supports_chat_completion": False,
        "supports_streaming": False,
        "supports_function_calling": False,
        "extra": {"source": "https://developers.openai.com/api/docs/pricing", "category": "embedding"},
    },
    "text-embedding-3-large": {
        "model_id": "text-embedding-3-large",
        "display_name": "Text Embedding 3 Large",
        "context_window": 8191,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.13, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["text"],
        "output_modalities": ["embedding"],
        "supports_chat_completion": False,
        "supports_streaming": False,
        "supports_function_calling": False,
        "extra": {"source": "https://developers.openai.com/api/docs/pricing", "category": "embedding"},
    },
    "omni-moderation-latest": {
        "model_id": "omni-moderation-latest",
        "display_name": "Omni Moderation Latest",
        "context_window": 32768,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": False,
        "supports_vision": True,
        "extra": {"source": "https://developers.openai.com/api/docs/pricing", "category": "moderation", "note": "Free"},
    },
}

# ── Read current openai.json ──
path = r"F:\KAIHATSU\llmcapa\src\llmcapa\data\openai.json"
with open(path, encoding="utf-8") as f:
    current = json.load(f)

# ── Build updated model list ──
updated = []
seen_ids = set()

# 1. Add flagship models
for mid, spec in FLAGSHIP_MODELS.items():
    entry = {"provider": "openai", "aliases": [], "deprecated": False, "input_modalities": ["text", "image"], "output_modalities": ["text"]}
    entry.update(spec)
    updated.append(entry)
    seen_ids.add(mid)

# 2. Add specialized models
for mid, spec in SPECIALIZED_MODELS.items():
    entry = {"provider": "openai", "aliases": [], "deprecated": False, "input_modalities": ["text"], "output_modalities": ["text"]}
    entry.update(spec)
    updated.append(entry)
    seen_ids.add(mid)

# 3. Preserve remaining models from current data (deprecated + legacy aliases)
for m in current.get("models", []):
    mid = m.get("model_id")
    if mid and mid not in seen_ids:
        # Enrich realtime extras if present
        if mid == "gpt-realtime-2.1":
            m = dict(m)
            m.setdefault("extra", {})
            m["extra"].update({
                "source": "https://developers.openai.com/api/docs/pricing",
                "audio_input_per_1m": 32.0,
                "audio_cached_input_per_1m": 0.4,
                "audio_output_per_1m": 64.0,
                "text_input_per_1m": 4.0,
                "text_cached_input_per_1m": 0.4,
                "text_output_per_1m": 24.0,
                "image_input_per_1m": 5.0,
                "image_cached_input_per_1m": 0.5,
            })
        if mid == "gpt-realtime-2.1-mini":
            m = dict(m)
            m.setdefault("extra", {})
            m["extra"].update({
                "source": "https://developers.openai.com/api/docs/pricing",
                "audio_input_per_1m": 10.0,
                "audio_cached_input_per_1m": 0.3,
                "audio_output_per_1m": 20.0,
                "text_input_per_1m": 0.6,
                "text_cached_input_per_1m": 0.06,
                "text_output_per_1m": 2.4,
                "image_input_per_1m": 0.8,
                "image_cached_input_per_1m": 0.08,
            })
        if mid in ("gpt-4o-transcribe", "gpt-4o-mini-transcribe"):
            m = dict(m)
            m.setdefault("extra", {})
            if mid == "gpt-4o-transcribe":
                m["extra"].update({"estimated_cost_per_minute": 0.006})
            else:
                m["extra"].update({"estimated_cost_per_minute": 0.003})
        updated.append(m)
        seen_ids.add(mid)

updated.sort(key=lambda x: x["model_id"])

# ── Write openai.json ──
output = {"models": updated}
with open(path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"openai.json: {len(updated)} models (flagship={len(FLAGSHIP_MODELS)}, specialized={len(SPECIALIZED_MODELS)}, deprecated preserved)", flush=True)

# ── Copy to installed package ──
import shutil
shutil.copy2(path, r"F:\Python314\Lib\site-packages\llmcapa\data\openai.json")
print("Installed package updated", flush=True)

# ── Update provider_update_log.md ──
log_path = r"F:\KAIHATSU\llmcapa\provider_update_log.md"
today = date.today().strftime("%Y-%m-%d")
log_entry = f"""
## OpenAI ({today})

### Source
- Official OpenAI API Documentation: https://developers.openai.com/api/docs/models
- Pricing page: https://developers.openai.com/api/docs/pricing
- Method: Playwright (headless browser) for JavaScript-rendered pages

### Models Updated
{len(updated)} models total

### Changes
- Flagship: GPT-5.6 Sol/Terra/Luna, GPT-5.5(+Pro), GPT-5.4(+Mini/Nano/Pro)
- Image: gpt-image-2 / 1.5 / 1-mini / 1, chatgpt-image-latest (token pricing + batch)
- Video: sora-2 ($0.10/s 720p), sora-2-pro ($0.30–$0.70/s)
- Realtime: 2.1/mini modality rates; translate $0.034/min; whisper $0.017/min
- Audio: gpt-audio-1.5 / mini; transcribe + diarize
- Specialized: chat-latest, gpt-5.4-cyber, gpt-5.5-cyber ($12.5/$75)
- Embeddings + omni-moderation-latest (free)
- Preserved legacy openai/* OpenRouter-style aliases from prior catalog
"""

with open(log_path, "a", encoding="utf-8") as f:
    f.write(log_entry)
print("provider_update_log.md updated", flush=True)

print("Done", flush=True)
