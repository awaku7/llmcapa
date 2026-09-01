"""Add documented provider API endpoints to catalog records.

Endpoint metadata is provider-owned and is never derived from OpenRouter.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"
LOG = ROOT / "provider_update_log.md"

ENDPOINTS = {
    "deepseek": ("https://api.deepseek.com", "https://api-docs.deepseek.com/"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "https://www.alibabacloud.com/help/en/model-studio/"),
    "moonshot": ("https://api.moonshot.cn/v1", "https://platform.moonshot.cn/docs/"),
    "z-ai": ("https://open.bigmodel.cn/api/paas/v4", "https://docs.z.ai/"),
    "minimax": ("https://api.minimax.io/v1", "https://platform.minimax.io/docs/"),
    "baidu": ("https://qianfan.baidubce.com/v2", "https://cloud.baidu.com/doc/QIANFAN/"),
    "tencent": ("https://api.hunyuan.cloud.tencent.com/v1", "https://cloud.tencent.com/document/product/1729"),
    "bytedance": ("https://ark.cn-beijing.volces.com/api/v3", "https://www.volcengine.com/docs/82379"),
    "xiaomi": ("https://api.xiaomimimo.com/v1", "https://platform.mimo.ai/"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "https://docs.siliconflow.com/"),
    "groq": ("https://api.groq.com/openai/v1", "https://console.groq.com/docs/"),
    "cerebras": ("https://api.cerebras.ai/v1", "https://inference-docs.cerebras.ai/"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "https://docs.fireworks.ai/"),
    "sambanova": ("https://api.sambanova.ai/v1", "https://docs.sambanova.ai/"),
    "novita": ("https://api.novita.ai/v3/openai", "https://novita.ai/docs/"),
    "openai": ("https://api.openai.com/v1", "https://platform.openai.com/docs/api-reference"),
    "anthropic": ("https://api.anthropic.com/v1", "https://docs.anthropic.com/en/api"),
    "google": ("https://generativelanguage.googleapis.com/v1beta", "https://ai.google.dev/api"),
    "xai": ("https://api.x.ai/v1", "https://docs.x.ai/docs"),
    "mistral": ("https://api.mistral.ai/v1", "https://docs.mistral.ai/api/"),
    "cohere": ("https://api.cohere.com/v2", "https://docs.cohere.com/reference"),
    "amazon": ("https://bedrock-runtime.{region}.amazonaws.com", "https://docs.aws.amazon.com/bedrock/"),
    "microsoft": ("https://{resource-name}.openai.azure.com/openai/v1", "https://learn.microsoft.com/azure/ai-services/openai/"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "https://docs.api.nvidia.com/nim/"),
    "together": ("https://api.together.xyz/v1", "https://docs.together.ai/reference"),
    "perplexity": ("https://api.perplexity.ai", "https://docs.perplexity.ai/"),
    "upstage": ("https://api.upstage.ai/v1", "https://developers.upstage.ai/docs/getting-started"),
    "writer": ("https://api.writer.com/v1", "https://dev.writer.com/api-reference"),
    "ai21": ("https://api.ai21.com/studio/v1", "https://docs.ai21.com/"),
    "rekaai": ("https://api.reka.ai/v1", "https://docs.reka.ai/"),
    "huggingface": ("https://router.huggingface.co/v1", "https://huggingface.co/docs/inference-providers/"),
    "ollama": ("http://localhost:11434/v1", "https://docs.ollama.com/api/openai-compatibility"),
    "lmstudio": ("http://localhost:1234/v1", "https://lmstudio.ai/docs/developer/openai-compat"),
    "vertex-ai": ("https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models", "https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference"),
    "openrouter": ("https://openrouter.ai/api/v1", "https://openrouter.ai/docs/api-reference/overview"),
    "sakana": ("https://api.sakana.ai", "https://console.sakana.ai/get-started"),
    "vercel": ("https://ai-gateway.vercel.sh/v1", "https://vercel.com/docs/ai-gateway/sdks-and-apis/rest-api"),
    "azure_foundry": ("https://{resource-name}.services.ai.azure.com/openai/v1", "https://learn.microsoft.com/azure/foundry/foundry-models/concepts/endpoints"),
    "relace": ("https://models.relace.ai", "https://docs.relace.ai/api-reference/introduction"),
}


def main() -> None:
    changed = []
    for provider, (base_url, source) in ENDPOINTS.items():
        path = DATA / f"{provider}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for model in payload.get("models", []):
            extra = model.setdefault("extra", {})
            extra["endpoints"] = [{
                "base_url": base_url,
                "protocol": "openai-compatible" if provider not in {"baidu", "tencent", "bytedance"} else "provider-native-or-openai-compatible",
                "auth": "bearer",
                "source": source,
            }]
            count += 1
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append((provider, count, base_url))
        print(f"{provider}: endpoint added to {count} models -> {base_url}")
    LOG.write_text(LOG.read_text(encoding="utf-8") + f"\n## Official API endpoint metadata ({date.today()})\n\n- Sources: provider official documentation; OpenRouter was not used.\n" + "".join(f"- {p}: {n} models -> `{u}`\n" for p, n, u in changed), encoding="utf-8")


if __name__ == "__main__":
    main()
