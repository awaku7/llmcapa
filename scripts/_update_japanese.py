"""Update japanese.json from OpenRouter registry data."""
import llmcapa, json, shutil

jp_providers = ["ntt", "elyza", "nec", "fujitsu", "pfn", "softbank", "customer-cloud"]
models = []
for p in jp_providers:
    for m in llmcapa.list_models(provider=p):
        d = m.to_dict()
        d.pop("extra", None)
        models.append(d)

models.sort(key=lambda x: x["model_id"])

path = r"F:\KAIHATSU\llmcapa\src\llmcapa\data\japanese.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump({"models": models}, f, ensure_ascii=False, indent=2)

shutil.copy2(path, r"F:\Python314\Lib\site-packages\llmcapa\data\japanese.json")
print(f"japanese.json: {len(models)} models updated", flush=True)
