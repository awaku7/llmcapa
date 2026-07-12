"""Capability data model for llmcapa."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Feature(str, Enum):
    """Standard feature flags supported by LLM models."""
    LLMC_FEAT_VISION = "vision"
    LLMC_FEAT_FUNCTION_CALLING = "function_calling"
    LLMC_FEAT_JSON_MODE = "json_mode"
    LLMC_FEAT_STREAMING = "streaming"
    LLMC_FEAT_REASONING = "reasoning"
    LLMC_FEAT_CHAT_COMPLETION = "chat_completion"
    LLMC_FEAT_RESPONSES_API = "responses_api"
    LLMC_FEAT_REASONING_EFFORT = "reasoning_effort"
    LLMC_FEAT_THINKING_BUDGET = "thinking_budget"
    LLMC_FEAT_MULTIMODAL = "multimodal"
    LLMC_FEAT_FIM = "fim"

    # Modalities (Input)
    LLMC_FEAT_TEXT_INPUT = "text_input"
    LLMC_FEAT_IMAGE_INPUT = "image_input"
    LLMC_FEAT_AUDIO_INPUT = "audio_input"
    LLMC_FEAT_VIDEO_INPUT = "video_input"

    # Modalities (Output)
    LLMC_FEAT_TEXT_OUTPUT = "text_output"
    LLMC_FEAT_IMAGE_OUTPUT = "image_output"
    LLMC_FEAT_AUDIO_OUTPUT = "audio_output"
    LLMC_FEAT_VIDEO_OUTPUT = "video_output"



class ReasoningEffort(str, Enum):
    """Standard reasoning effort levels for models supporting reasoning_effort."""
    LLMC_EFFORT_NONE = "none"
    LLMC_EFFORT_MINIMAL = "minimal"
    LLMC_EFFORT_LOW = "low"
    LLMC_EFFORT_MEDIUM = "medium"
    LLMC_EFFORT_HIGH = "high"
    LLMC_EFFORT_XHIGH = "xhigh"


@dataclass(frozen=True)
class Capability:
    """Capability information of a single LLM model."""

    provider: str
    model_id: str
    display_name: str = ""
    context_window: int = 0
    max_output_tokens: int = 0
    input_modalities: List[str] = field(default_factory=lambda: ["text"])
    output_modalities: List[str] = field(default_factory=lambda: ["text"])
    supports_function_calling: bool = False
    supports_json_mode: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_chat_completion: bool = True
    supports_responses_api: bool = False
    supports_reasoning_effort: bool = False
    supports_thinking_budget: bool = False
    supports_anthropic_api: bool = False
    supports_google_api: bool = False
    supports_fim: bool = False
    license_type: str = "unknown"
    tokenizer_name: str = ""
    knowledge_cutoff: Optional[str] = None
    pricing: Optional[Dict[str, Any]] = None
    deprecated: bool = False
    aliases: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def supports(self, feature: Feature | str) -> bool:
        """Return True if the model supports the given feature.

        Accepts short names such as "vision", "json_mode",
        "function_calling", "streaming", "reasoning",
        "chat_completion", "responses_api", "multimodal",
        "reasoning_effort", "thinking_budget", "fim",
        or an input modality such as "image", "audio".

        Also accepts `Feature` enum members (e.g., `Feature.LLMC_FEATURE_VISION`).
        """
        feature_str = feature.value if isinstance(feature, Feature) else feature

        # Use a private cache dictionary to avoid re-evaluating the same feature check.
        # Since Capability is frozen, its state does not change.
        if not hasattr(self, "_supports_cache"):
            # Use object.__setattr__ because the dataclass is frozen=True
            object.__setattr__(self, "_supports_cache", {})
        
        cache = getattr(self, "_supports_cache")
        if feature_str in cache:
            return cache[feature_str]

        res = self._eval_supports(feature_str)
        cache[feature_str] = res
        return res

    def _eval_supports(self, feature: str) -> bool:
        attr = f"supports_{feature}"
        if hasattr(self, attr):
            return bool(getattr(self, attr))
        if feature.endswith("_input"):
            return feature[:-6] in self.input_modalities
        if feature.endswith("_output"):
            return feature[:-7] in self.output_modalities
        if feature == "multimodal":
            return len(self.input_modalities) > 1 or len(self.output_modalities) > 1
        if feature in self.input_modalities:
            return True
        if feature in self.output_modalities:
            return True
        return bool(self.extra.get(attr) or self.extra.get(feature))

    def features(self) -> List[str]:
        """Return a sorted list of all standard and custom features supported by this model."""
        standard_features = [
            "vision", "function_calling", "json_mode", "streaming",
            "reasoning", "chat_completion", "responses_api",
            "reasoning_effort", "thinking_budget", "fim"
        ]
        # Gather input/output modalities
        for mod in self.input_modalities:
            standard_features.append(f"{mod}_input")
            standard_features.append(mod)
        for mod in self.output_modalities:
            standard_features.append(f"{mod}_output")
            standard_features.append(mod)
        if self.supports("multimodal"):
            standard_features.append("multimodal")

        # Gather custom features from extra
        for key in self.extra:
            if key.startswith("supports_"):
                standard_features.append(key[9:])
            else:
                standard_features.append(key)

        # Filter unique and supported features
        supported = set()
        for f in standard_features:
            if self.supports(f):
                supported.add(f)
        return sorted(list(supported))

    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens for the given text.

        If `tiktoken` is installed and the model uses an OpenAI tokenizer (e.g., `o200k_base`,
        `cl100k_base`), it will dynamically import `tiktoken` and return the exact token count.
        Otherwise, it falls back to a highly-optimized, standard-library-only estimation
        supporting 30+ major languages.
        """
        if not text:
            return 0

        t_name = self.tokenizer_name.lower()

        # Try to use tiktoken if installed and applicable
        if t_name and any(k in t_name for k in ["o200k", "cl100k", "p50k", "r50k"]):
            try:
                import tiktoken
                # Get encoding by name or fallback to model_id
                try:
                    enc = tiktoken.get_encoding(self.tokenizer_name)
                except Exception:
                    enc = tiktoken.encoding_for_model(self.model_id)
                return len(enc.encode(text))
            except Exception:
                pass

        # Determine if the model uses a modern, highly-optimized tokenizer
        # Modern tokenizers have much larger vocabularies (100k-250k+) and are
        # highly efficient for non-Latin scripts.
        is_modern = (
            any(k in t_name for k in ["o200k", "llama3", "gemini", "claude3", "gemma", "r1", "deepseek"])
            or self.provider.lower() in ["google", "anthropic", "deepseek"]
        )

        # Multipliers for different character classes: (modern_tokenizer, older_tokenizer)
        # CJK (Chinese, Japanese, Korean)
        cjk_mult = 0.75 if is_modern else 1.3
        # Cyrillic (Russian, Ukrainian, Bulgarian, etc.)
        cyrillic_mult = 0.45 if is_modern else 1.5
        # Arabic / Persian / Urdu
        arabic_mult = 0.55 if is_modern else 2.5
        # Devanagari (Hindi, Marathi, Nepali)
        devanagari_mult = 0.6 if is_modern else 3.0
        # Thai
        thai_mult = 0.7 if is_modern else 3.5
        # Greek
        greek_mult = 0.45 if is_modern else 1.8
        # Hebrew
        hebrew_mult = 0.55 if is_modern else 2.5
        # Other Indic scripts (Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi)
        indic_mult = 0.65 if is_modern else 3.2
        # Other non-Latin scripts (Georgian, Armenian, Burmese, Lao, Tibetan, etc.)
        other_non_latin_mult = 0.8 if is_modern else 2.2

        tokens = 0.0

        for char in text:
            cp = ord(char)
            if cp <= 0x024F or (0x1E00 <= cp <= 0x1EFF):
                # Latin / ASCII / Common punctuation / Latin Extended (Turkish, Vietnamese, etc.)
                # 1 Latin char is roughly 0.25 to 0.3 tokens (4 chars = 1 token)
                tokens += 0.28
            elif (0x4E00 <= cp <= 0x9FFF) or (0x3000 <= cp <= 0x30FF) or (0xAC00 <= cp <= 0xD7AF) or (0xF900 <= cp <= 0xFAFF) or (0xFF00 <= cp <= 0xFFEF):
                # CJK Unified Ideographs, Hiragana/Katakana, Hangul, Fullwidth
                tokens += cjk_mult
            elif 0x0400 <= cp <= 0x052F:
                # Cyrillic
                tokens += cyrillic_mult
            elif 0x0600 <= cp <= 0x077F:
                # Arabic / Persian / Urdu
                tokens += arabic_mult
            elif 0x0900 <= cp <= 0x097F:
                # Devanagari (Hindi)
                tokens += devanagari_mult
            elif 0x0E00 <= cp <= 0x0E7F:
                # Thai
                tokens += thai_mult
            elif 0x0370 <= cp <= 0x03FF:
                # Greek
                tokens += greek_mult
            elif 0x0590 <= cp <= 0x05FF:
                # Hebrew
                tokens += hebrew_mult
            elif 0x0980 <= cp <= 0x0DFF:
                # Other Indic scripts (Bengali, Gurmukhi, Gujarati, Tamil, Telugu, Kannada, Malayalam, Sinhala)
                tokens += indic_mult
            else:
                # Other non-Latin scripts
                tokens += other_non_latin_mult

        # Round up to nearest integer, minimum 1 token if text is not empty
        return max(1, int(round(tokens)))

    def count_tokens(self, text: str) -> int:
        """Count tokens for the given text using the best available tokenizer.

        Uses provider-specific tokenizers when available (tiktoken for OpenAI/DeepSeek,
        LocalTokenizer for Gemini, etc.). Falls back to estimate_tokens otherwise.

        See ``llmcapa.count_tokens(text, model_id)`` for the standalone version.
        """
        if not text:
            return 0
        from .tokenizer import _count_for_cap

        return _count_for_cap(text, self)

    def estimate_cost(self, input_tokens: int = 0, output_tokens: int = 0) -> Dict[str, Any]:
        """Estimate the cost for the given number of input and output tokens.

        Returns a dict with 'cost' (float) and 'currency' (str).
        If pricing is not available, returns cost=0.0 and currency='USD'.
        """
        if not self.pricing:
            return {"cost": 0.0, "currency": "USD"}
        
        in_rate = float(self.pricing.get("input_per_1m", 0.0))
        out_rate = float(self.pricing.get("output_per_1m", 0.0))
        currency = self.pricing.get("currency", "USD")

        cost = ((input_tokens * in_rate) + (output_tokens * out_rate)) / 1000000.0
        return {"cost": cost, "currency": currency}

    def can_be_replaced_by(self, other: "Capability", required_features: Optional[List[str]] = None) -> bool:
        """Check if this model can be replaced by another model.

        The other model must have a context window at least as large as this model,
        and must support all specified required_features (or all features this model supports
        if required_features is None).
        """
        if other.context_window < self.context_window:
            return False

        if required_features is None:
            # Check all standard features supported by this model
            features_to_check = [
                "vision", "function_calling", "json_mode", "streaming",
                "reasoning", "chat_completion", "responses_api",
                "reasoning_effort", "thinking_budget", "fim", "image_output",
                "audio_output", "video_output"
            ]
            required_features = [f for f in features_to_check if self.supports(f)]

        for feature in required_features:
            if not other.supports(feature):
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict representation."""
        d = asdict(self)
        if not d.get("extra"):
            d.pop("extra", None)
        if d.get("pricing") is None:
            d.pop("pricing", None)
        # Exclude internal cache from dict representation
        d.pop("_supports_cache", None)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        """Create a Capability from a dict, keeping unknown keys in `extra`."""
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs: Dict[str, Any] = {}
        extra: Dict[str, Any] = dict(data.get("extra") or {})
        _list_fields = {"aliases", "input_modalities", "output_modalities"}
        for key, value in data.items():
            if key == "extra":
                continue
            if key in known:
                # Normalize None to empty list for list-typed fields
                if key in _list_fields and value is None:
                    kwargs[key] = []
                else:
                    kwargs[key] = value
            else:
                extra[key] = value
        kwargs["extra"] = extra
        return cls(**kwargs)
