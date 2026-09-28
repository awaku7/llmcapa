# Microsoft Foundry Local support

`llmcapa` treats Microsoft Foundry Local as a machine-local runtime provider named
`foundry-local`. It is intentionally separate from the cloud `azure_foundry`
catalog.

## Import the local catalog

Foundry Local exposes a dynamic local REST endpoint. Obtain the current endpoint
from Foundry Local itself or its SDK; do not hardcode the port.

```python
import llmcapa

count = llmcapa.fetch_foundry_local("http://localhost:5272")
print(count)

cap = llmcapa.get("phi-4-mini", provider="foundry-local")
print(cap.supports_function_calling)
print(cap.extra["foundry_local"]["variants"])
```

Passing an OpenAI-style base URL ending in `/v1` is also accepted:

```python
llmcapa.fetch_foundry_local("http://localhost:5272/v1")
```

The importer requests the service-root `GET /foundry/list` endpoint.

## Offline and security behavior

Normal `llmcapa` model lookup does not contact Foundry Local. Network access occurs
only after an explicit `fetch_foundry_local(...)` call. The importer:

- accepts only `localhost`, `127.0.0.0/8`, or IPv6 loopback endpoints;
- rejects credentials, query strings, fragments, and unrelated URL paths;
- applies a timeout and a 10 MiB response limit;
- does not persist machine-local catalog records into bundled catalog files.

## Model aliases and hardware variants

Foundry Local can publish multiple hardware variants for one logical model, for
example CPU and CUDA variants. `llmcapa` groups records by the Foundry Local
`alias` and registers the alias as the logical `model_id`.

Variant names are retained as aliases and detailed runtime metadata is available
under:

```python
cap.extra["foundry_local"]["variants"]
```

This keeps application configuration on stable logical aliases such as
`phi-4-mini` while leaving hardware-specific variant selection to Foundry Local.

## Capability mapping

The importer uses only information explicitly exposed by the local catalog.
Unknown values are not guessed.

- `supportsToolCalling` -> `supports_function_calling`
- chat/text-generation task -> chat completions + text input/output
- vision/image-to-text task -> image input + text output
- transcription/speech-recognition task -> audio input + text output
- embedding task -> text input + embedding output
- explicit context/output limits -> `context_window` / `max_output_tokens`
- license, publisher, task, model format, file size, and runtime metadata are
  retained when supplied

When multiple hardware variants expose different numeric limits, the smallest
explicit positive value is used conservatively. Missing limits remain `0`
(unknown).

## Scope

This support imports model capabilities only. It does not download, load, unload,
or run Foundry Local models. Runtime orchestration belongs to applications such as
UAG, which can use the Foundry Local SDK and the OpenAI-compatible local REST
endpoint for inference.
