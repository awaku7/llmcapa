# API Specification

## Thinking controls

`llmcapa` describes provider-specific reasoning controls without forcing clients to know provider names. Existing fields remain supported.

### Control types

| `thinking_control.kind` | API parameter | Value type | Example |
|---|---|---|---|
| `toggle` | provider-specific | boolean-like mode | MiniMax `enabled` / `disabled` |
| `level` | `thinking_level` | string | `minimal`, `low`, `medium`, `high` |
| `budget` | `thinking_budget` | integer token count | `0`–`24576` |

### Capability fields

```python
cap.supports_reasoning_effort
cap.reasoning_effort_values

cap.supports_thinking_budget
cap.thinking_budget_values

cap.supports_thinking_level
cap.thinking_level_values

cap.thinking_control
```

The convenience methods return copies and are safe to inspect:

```python
cap.get_reasoning_effort_values()   # list[str]
cap.get_thinking_budget_values()    # dict[str, Any]
cap.get_thinking_level_values()     # list[str]
cap.get_thinking_control()          # dict[str, Any]
```

### Examples

#### OpenAI `reasoning_effort`

```python
cap = llmcapa.get("o3", provider="openai")
cap.get_reasoning_effort_values()
# ["low", "medium", "high"]
```

#### Vertex AI Gemini 2.5 budget

```python
cap = llmcapa.get("gemini-2.5-flash", provider="vertex-ai")
cap.get_thinking_control()
# {
#   "kind": "budget",
#   "parameter": "thinking_budget",
#   "type": "token_range",
#   "min": 0,
#   "max": 24576,
# }
```

The application passes an integer such as `8192` to the Vertex API.

#### Vertex AI Gemini 3 level

```python
cap = llmcapa.get("gemini-3-flash-preview", provider="vertex-ai")
cap.get_thinking_control()
# {
#   "kind": "level",
#   "parameter": "thinking_level",
#   "values": ["minimal", "low", "medium", "high"],
# }
```

#### MiniMax toggle

```python
cap = llmcapa.get("MiniMax-M3", provider="minimax")
cap.get_thinking_control()
# {
#   "kind": "toggle",
#   "parameter": "thinking",
#   "values": ["enabled", "disabled"],
#   "encoding": {
#     "enabled": {"type": "enabled"},
#     "disabled": {"type": "disabled"},
#   },
# }
```

### Compatibility

Adding `thinking_level_values` and `thinking_control` is backward-compatible. Existing callers using `reasoning_effort_values` or `thinking_budget_values` continue to work unchanged. Fields with unknown values are omitted from `Capability.to_dict()` when unset.

`llmcapa` reports capability metadata; it does not send provider API requests. Clients should use `thinking_control` to select the provider parameter and validate the value before constructing the request.
