"""Capability data model for llmcapa."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


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
    tokenizer_name: str = ""
    knowledge_cutoff: Optional[str] = None
    pricing: Optional[Dict[str, Any]] = None
    deprecated: bool = False
    aliases: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def supports(self, feature: str) -> bool:
        """Return True if the model supports the given feature.

        Accepts short names such as "vision", "json_mode",
        "function_calling", "streaming", "reasoning",
        "chat_completion", "responses_api", "multimodal",
        "reasoning_effort", "thinking_budget",
        or an input modality such as "image", "audio".
        """
        # Use a private cache dictionary to avoid re-evaluating the same feature check.
        # Since Capability is frozen, its state does not change.
        if not hasattr(self, "_supports_cache"):
            # Use object.__setattr__ because the dataclass is frozen=True
            object.__setattr__(self, "_supports_cache", {})
        
        cache = getattr(self, "_supports_cache")
        if feature in cache:
            return cache[feature]

        res = self._eval_supports(feature)
        cache[feature] = res
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
            "reasoning_effort", "thinking_budget"
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
                "reasoning_effort", "thinking_budget", "image_output",
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
        for key, value in data.items():
            if key == "extra":
                continue
            if key in known:
                kwargs[key] = value
            else:
                extra[key] = value
        kwargs["extra"] = extra
        return cls(**kwargs)
