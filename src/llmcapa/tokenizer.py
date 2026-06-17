"""Token counting for various LLM providers — offline by default.

Uses provider-specific tokenizers when available:
  - OpenAI / DeepSeek: tiktoken (exact)
  - Google Gemini: google.genai.local_tokenizer.LocalTokenizer (SentencePiece, offline)
  - Anthropic Claude: tiktoken cl100k_base approximation (no local tokenizer available)
  - Others: falls back to Capability.estimate_tokens (character-based heuristic)

``count_messages_tokens`` formats messages in each provider's native chat format
for accurate overhead calculation.

Message format follows the agentcli internal format (unified across providers):
  {"role": "user"|"assistant"|"system"|"tool", "content": str | list,
   "tool_calls": [...] (optional), "tool_call_id": "..." (optional)}
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .registry import default_registry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def count_tokens(text: str, model_id: str) -> int:
    """Count tokens for a single text string using the best available tokenizer.

    Args:
        text: The text to count tokens for.
        model_id: Model identifier (e.g. "gpt-4o", "gemini-2.0-flash").

    Returns:
        Number of tokens.
    """
    if not text:
        return 0
    cap = default_registry().get(model_id)
    return _count_for_cap(text, cap)


def count_messages_tokens(
    messages: List[Dict[str, Any]],
    model_id: str,
) -> int:
    """Count tokens for a list of chat messages using the provider's native format.

    Each message dict must have a "role" and "content" key.
    Content may be a string or a list of content parts (multimodal).
    Optional "tool_calls" (list) and "tool_call_id" (str) keys are handled.

    Args:
        messages: List of message dicts.
        model_id: Model identifier.

    Returns:
        Number of tokens.
    """
    if not messages:
        return 0

    cap = default_registry().get(model_id)
    provider = cap.provider.lower() if hasattr(cap, "provider") else ""

    # --- Google Gemini: convert to Content objects and use LocalTokenizer ---
    if provider == "google" or "gemini" in (cap.model_id or "").lower():
        result = _count_messages_gemini(messages, cap.model_id)
        if result is not None:
            return result

    # --- OpenAI / DeepSeek: format as ChatML and tokenize ---
    if provider in ("openai", "deepseek") or _has_tiktoken_tokenizer(cap):
        result = _count_messages_chatml(messages, cap)
        if result is not None:
            return result

    # --- Anthropic Claude: format as Anthropic messages and approximate ---
    if provider == "anthropic":
        result = _count_messages_anthropic(messages, cap)
        if result is not None:
            return result

    # --- Fallback: simple per-content counting ---
    return _count_messages_fallback(messages, cap)


# ---------------------------------------------------------------------------
# Helpers: extract content text and tool calls from a message
# ---------------------------------------------------------------------------


def _extract_text_content(content: Any) -> str:
    """Extract plain text from a message content (str or list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            t = part.get("text") or ""
            if t:
                texts.append(t)
            # Nested content in tool_result / function_response
            if part.get("type") in ("tool_result", "function_response"):
                inner = part.get("content", "")
                if isinstance(inner, str) and inner:
                    texts.append(inner)
                elif isinstance(inner, list):
                    for p in inner:
                        if isinstance(p, dict) and p.get("type") == "text":
                            texts.append(p.get("text", ""))
        return "\n".join(texts)
    return ""


def _extract_tool_calls_text(msg: Dict[str, Any]) -> str:
    """Extract tool_calls or function_call from a message as JSON text."""
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        return json.dumps(tool_calls, ensure_ascii=False)

    # Legacy single function_call key
    fc = msg.get("function_call")
    if fc:
        if isinstance(fc, dict):
            return json.dumps(fc, ensure_ascii=False)
        return str(fc)

    return ""


def _has_tiktoken_tokenizer(cap: Any) -> bool:
    tokenizer = (cap.tokenizer_name or "").lower() if hasattr(cap, "tokenizer_name") else ""
    return any(k in tokenizer for k in ["o200k", "cl100k", "p50k", "r50k"])


def _get_encoding(cap: Any) -> Any:
    """Return a tiktoken encoding for the given capability, or None."""
    import tiktoken

    tokenizer_name = (cap.tokenizer_name or "").lower() if hasattr(cap, "tokenizer_name") else ""
    model_id = cap.model_id if hasattr(cap, "model_id") else ""

    if tokenizer_name:
        try:
            return tiktoken.get_encoding(tokenizer_name)
        except Exception:
            pass
    try:
        return tiktoken.encoding_for_model(model_id)
    except Exception:
        pass
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OpenAI / DeepSeek: ChatML format
# ---------------------------------------------------------------------------


def _count_messages_chatml(messages: List[Dict[str, Any]], cap: Any) -> Optional[int]:
    """Count tokens by formatting messages in ChatML format and tokenizing.

    Format::
      <|im_start|>role
      content<|im_end|>
      <|im_start|>assistant
      <tool_calls_json><|im_end|>
      <|im_start|>tool
      result<|im_end|>
    """
    try:
        enc = _get_encoding(cap)
        if enc is None:
            return None
    except Exception:
        return None

    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = _extract_text_content(msg.get("content", ""))
        tc_text = _extract_tool_calls_text(msg)

        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            combined = content
            if tool_call_id:
                combined = f"{tool_call_id}: {combined}" if combined else tool_call_id
            parts.append(f"<|im_start|>{role}\n{combined}<|im_end|>")
        elif role == "assistant" and tc_text:
            combined = content
            if combined and tc_text:
                combined = f"{combined}\n{tc_text}"
            elif tc_text:
                combined = tc_text
            parts.append(f"<|im_start|>{role}\n{combined}<|im_end|>")
        else:
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")

    formatted = "\n".join(parts) + "\n"
    return len(enc.encode(formatted))


# ---------------------------------------------------------------------------
# Google Gemini: types.Content format
# ---------------------------------------------------------------------------


def _count_messages_gemini(messages: List[Dict[str, Any]], model_id: str) -> Optional[int]:
    """Count tokens using Google's LocalTokenizer with Content objects.

    Handles both content-list parts and agentcli-style tool_calls/function_call keys.
    """
    try:
        from google.genai import local_tokenizer, types

        tokenizer = local_tokenizer.LocalTokenizer(model_name=model_id)
        contents: List[types.Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            content_raw = msg.get("content", "")
            parts_list: List[types.Part] = []

            # Map role
            gemini_role = "user"
            if role == "assistant":
                gemini_role = "model"
            elif role == "system":
                gemini_role = "user"  # Gemini handles system separately

            # Content as text
            if isinstance(content_raw, str) and content_raw:
                parts_list.append(types.Part(text=content_raw))
            elif isinstance(content_raw, list):
                for part in content_raw:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            parts_list.append(types.Part(text=text))
                    elif part.get("type") == "function_call":
                        fc = part.get("function_call") or part
                        parts_list.append(
                            types.Part(function_call=types.FunctionCall(
                                name=fc.get("name", ""),
                                args=fc.get("arguments", {}),
                            ))
                        )
                    elif part.get("type") == "function_response":
                        fr = part.get("function_response") or part
                        parts_list.append(
                            types.Part(function_response=types.FunctionResponse(
                                name=fr.get("name", ""),
                                response=fr.get("response", {}),
                            ))
                        )

            # Agentcli-style tool_calls on assistant messages
            if role == "assistant" and msg.get("tool_calls"):
                tc_text = json.dumps(msg["tool_calls"], ensure_ascii=False)
                parts_list.append(types.Part(text=tc_text))

            if not parts_list:
                continue

            contents.append(types.Content(role=gemini_role, parts=parts_list))

        if not contents:
            return 0

        result = tokenizer.count_tokens(contents)
        return result.total_tokens
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Anthropic Claude: messages format
# ---------------------------------------------------------------------------


def _count_messages_anthropic(messages: List[Dict[str, Any]], cap: Any) -> Optional[int]:
    """Count tokens by formatting messages in Anthropic's format and approximating
    with tiktoken cl100k_base.

    Anthropic format::
      \\n\\nHuman: ...\\n\\nAssistant: ...\\n\\nSystem: ...
    """
    try:
        enc = _get_encoding(cap)
        if enc is None:
            return None
    except Exception:
        return None

    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = _extract_text_content(msg.get("content", ""))
        tc_text = _extract_tool_calls_text(msg)

        anthropic_role = "Human"
        if role == "assistant":
            anthropic_role = "Assistant"
        elif role == "system":
            anthropic_role = "System"

        combined = content
        if tc_text:
            if combined:
                combined = f"{combined}\n{tc_text}"
            else:
                combined = tc_text

        if combined:
            parts.append(f"\n\n{anthropic_role}: {combined}")

    formatted = "".join(parts)
    return len(enc.encode(formatted))


# ---------------------------------------------------------------------------
# Fallback: simple per-content counting
# ---------------------------------------------------------------------------


def _count_messages_fallback(messages: List[Dict[str, Any]], cap: Any) -> int:
    """Simple fallback: count content tokens individually + overhead."""
    total = len(messages) * 4 + 3
    for msg in messages:
        content = _extract_text_content(msg.get("content", ""))
        if content:
            total += _count_for_cap(content, cap)
        tc_text = _extract_tool_calls_text(msg)
        if tc_text:
            total += _count_for_cap(tc_text, cap)
    return total


# ---------------------------------------------------------------------------
# Single-text token counting (dispatched by provider)
# ---------------------------------------------------------------------------


def _count_for_cap(text: str, cap: Any) -> int:
    """Dispatch to the appropriate token counter based on provider/capability."""
    provider = cap.provider.lower() if hasattr(cap, "provider") else ""
    model_id = cap.model_id if hasattr(cap, "model_id") else ""
    tokenizer = (cap.tokenizer_name or "").lower() if hasattr(cap, "tokenizer_name") else ""

    # Google Gemini
    if provider == "google" or "gemini" in tokenizer or "gemini" in model_id.lower():
        result = _count_gemini(text, model_id)
        if result is not None:
            return result

    # OpenAI / DeepSeek: use tiktoken
    if provider in ("openai", "deepseek") or _has_tiktoken_tokenizer(cap):
        result = _count_tiktoken(text, tokenizer, model_id)
        if result is not None:
            return result

    # Anthropic: use tiktoken cl100k_base as approximation
    if provider == "anthropic":
        result = _count_tiktoken(text, "cl100k_base", model_id)
        if result is not None:
            return result

    # Fallback: character-based estimation
    if hasattr(cap, "estimate_tokens"):
        return cap.estimate_tokens(text)

    return max(1, len(text) // 3)


def _count_gemini(text: str, model_id: str) -> Optional[int]:
    try:
        from google.genai import local_tokenizer

        tz = local_tokenizer.LocalTokenizer(model_name=model_id)
        result = tz.count_tokens(text)
        return result.total_tokens
    except Exception:
        return None


def _count_tiktoken(text: str, tokenizer_name: str, model_id: str) -> Optional[int]:
    try:
        import tiktoken

        enc = None
        if tokenizer_name:
            try:
                enc = tiktoken.get_encoding(tokenizer_name)
            except Exception:
                pass
        if enc is None:
            try:
                enc = tiktoken.encoding_for_model(model_id)
            except Exception:
                pass
        if enc is None:
            return None
        return len(enc.encode(text))
    except Exception:
        return None


__all__ = [
    "count_tokens",
    "count_messages_tokens",
]
