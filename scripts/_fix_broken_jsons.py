"""Fix meta.json, xai.json etc. by re-exporting from registry."""
import json, os, shutil
import llmcapa

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# Providers to fix: (json_filename, provider_name_in_file)
FIXES = [
    ("meta.json", ["meta", "meta-llama"]),
    ("xai.json", ["xai", "x-ai"]),
    ("mistral.json", ["mistral", "mistralai", "mistral-ai"]),
    ("qwen.json", ["qwen", "qwen-(alibaba)"]),
]

for fname, prov_names in FIXES:
    all_models = {}
    for pn in prov_names:
        for m in llmcapa.list_models(provider=pn):
            d = m.to_dict()
            d.pop("extra", None)
            d["provider"] = prov_names[0]  # use canonical name
            mid = d["model_id"]
            # Keep model with higher context_window if duplicate
            if mid not in all_models or d.get("context_window",0) > all_models[mid].get("context_window",0):
                all_models[mid] = d
    
    models = sorted(all_models.values(), key=lambda x: x["model_id"])
    path = os.path.join(DATA, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"models": models}, f, ensure_ascii=False, indent=2)
    print(f"{fname}: {len(models)} models (merged {prov_names})", flush=True)

# Also fix azure_foundry.json - it has provider=deepseek which is wrong
# It should be provider=azure-openai
af_path = os.path.join(DATA, "azure_foundry.json")
with open(af_path, encoding="utf-8") as f:
    af = json.load(f)
for m in af.get("models", []):
    m["provider"] = "azure-openai"
with open(af_path, "w", encoding="utf-8") as f:
    json.dump(af, f, ensure_ascii=False, indent=2)
print(f"azure_foundry.json: provider fixed to azure-openai ({len(af.get('models',[]))} models)", flush=True)

# Copy to installed
for fname, _ in FIXES:
    shutil.copy2(os.path.join(DATA, fname), os.path.join(INSTALLED, fname))
shutil.copy2(af_path, os.path.join(INSTALLED, "azure_foundry.json"))
print("Copied to installed package", flush=True)
