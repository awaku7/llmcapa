from __future__ import annotations

import llmcapa
from llmcapa.models import AudioCapability, AudioEndpointCapability, Capability


def test_audio_capability_round_trip_preserves_detailed_fields():
    original = AudioCapability(
        transcription=True,
        accepts_audio_input=True,
        input_formats=("wav", "mp3"),
        sample_rates_hz=(16000,),
        output_formats=("pcm",),
        output_sample_rates_hz=(24000,),
        voice_values=("alloy",),
        endpoints=AudioEndpointCapability(transcription=True, streaming=True),
    )
    restored = AudioCapability.from_dict(original.to_dict())

    assert restored.transcription is True
    assert restored.input_formats == ("wav", "mp3")
    assert restored.sample_rates_hz == (16000,)
    assert restored.output_sample_rates_hz == (24000,)
    assert restored.endpoints is not None
    assert restored.endpoints.streaming is True


def test_openai_audio_catalog_exposes_input_and_output_constraints():
    transcribe = llmcapa.get("gpt-4o-transcribe", provider="openai")
    tts = llmcapa.get("gpt-4o-mini-tts", provider="openai")

    assert transcribe.audio is not None
    assert transcribe.audio.transcription is True
    assert transcribe.audio.accepts_audio_input is True
    assert transcribe.audio.max_input_bytes == 25_000_000
    assert "wav" in transcribe.audio.input_formats

    assert tts.audio is not None
    assert tts.audio.speech_generation is True
    assert tts.audio.speed_min == 0.25
    assert tts.audio.speed_max == 4.0
    assert "mp3" in tts.audio.output_formats
    assert "alloy" in tts.audio.voice_values


def test_audio_capability_is_available_on_capability_serialization():
    capability = llmcapa.get("nova-sonic-v1", provider="amazon")
    payload = capability.to_dict()
    restored = Capability.from_dict(payload)

    assert restored.audio is not None
    assert restored.audio.supports_realtime is True
    assert restored.audio.sample_rates_hz == (16000,)
    assert restored.audio.output_sample_rates_hz == (24000,)
