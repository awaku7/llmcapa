"""Add license_type field to Capability and update all JSON files."""
import json, os, shutil

# 1. Update models.py
models_py = r"F:\KAIHATSU\llmcapa\src\llmcapa\models.py"
with open(models_py, encoding="utf-8") as f:
    content = f.read()

if "license_type" not in content:
    content = content.replace(
        'supports_fim: bool = False',
        'supports_fim: bool = False\n    license_type: str = "unknown"',
    )
    with open(models_py, "w", encoding="utf-8") as f:
        f.write(content)
    print("models.py: license_type field added", flush=True)
else:
    print("models.py: already has license_type", flush=True)

shutil.copy2(models_py, r"F:\Python314\Lib\site-packages\llmcapa\models.py")

# 2. Update all JSON files with license_type
DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

for fname in os.listdir(DATA):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(DATA, fname)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    
    models = data.get("models", [])
    if not models:
        continue
    
    prov = models[0].get("provider", "")
    
    for m in models:
        pricing = m.get("pricing") or {}
        inp = pricing.get("input_per_1m", -1)
        out = pricing.get("output_per_1m", -1)
        
        if prov == "ollama":
            m["license_type"] = "free"
        elif inp == 0.0 and out == 0.0:
            m["license_type"] = "free"
        elif inp > 0 or out > 0:
            m["license_type"] = "api"
        elif not pricing:
            m["license_type"] = "license"
        else:
            m["license_type"] = "unknown"
    
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print(f"All JSON files updated with license_type", flush=True)

# Copy to installed
for fname in os.listdir(DATA):
    if fname.endswith(".json"):
        shutil.copy2(os.path.join(DATA, fname), os.path.join(INSTALLED, fname))
print("Copied to installed package", flush=True)
print("Done", flush=True)
