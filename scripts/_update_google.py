"""Update google.json with official Gemini API pricing from Playwright scrape."""
import json, os, shutil

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# Official Google Gemini API pricing (from ai.google.dev)
GOOGLE_PRICES = {
    "gemini-3.5-flash": (1.5, 9.0, 1048576),
    "gemini-3.5-live-translate-preview": (3.5, 21.0, 1048576),
    "gemini-3.1-flash-lite": (0.25, 1.5, 1048576),
    "gemini-omni-flash-preview": (1.5, 9.0, 1048576),
    "gemini-3.1-pro-preview": (2.0, 12.0, 1048576),
    "gemini-3.1-pro-preview-customtools": (2.0, 12.0, 1048576),
    "gemini-3.1-flash-live-preview": (0.75, 4.5, 131072),
    "gemini-3.1-flash-image": (0.5, 3.0, 131072),
    "gemini-3.1-flash-lite-image": (0.25, 1.5, 65536),
    "gemini-3.1-flash-tts-preview": (1.0, 20.0, 131072),
    "gemini-3-flash-preview": (0.5, 3.0, 1048576),
    "gemini-3-pro-image": (2.0, 12.0, 65536),
    "gemini-2.5-pro": (1.25, 10.0, 1048576),
    "gemini-2.5-flash": (0.3, 2.5, 1048576),
    "gemini-2.5-flash-lite": (0.1, 0.4, 1048576),
    "gemini-2.5-flash-lite-preview-09-2025": (0.1, 0.4, 1048576),
    "gemini-2.5-flash-native-audio-preview-12-2025": (0.5, 2.0, 1048576),
    "gemini-2.5-flash-image": (0.3, 2.5, 32768),
    "gemini-2.5-flash-preview-tts": (0.5, 10.0, 32768),
    "gemini-2.5-pro-preview-tts": (1.0, 20.0, 32768),
    "gemini-2.0-flash": (0.1, 0.4, 1048576),
    "gemini-2.0-flash-lite": (0.075, 0.3, 1048576),
    "gemini-1.5-pro": (1.25, 10.0, 2097152),
    "gemini-1.5-flash": (0.075, 0.3, 1048576),
}

path = os.path.join(DATA, "google.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)

updated = 0
for m in data["models"]:
    mid = m["model_id"]
    if mid in GOOGLE_PRICES:
        inp, out, ctx = GOOGLE_PRICES[mid]
        m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
        m["context_window"] = ctx
        m["supports_google_api"] = True
        m["supports_responses_api"] = False
        m["supports_fim"] = False
        updated += 1

# Also fix google_api flag and responses_api for all models
for m in data["models"]:
    m["supports_google_api"] = True
    if "responses_api" not in m:
        m["supports_responses_api"] = False

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

shutil.copy2(path, os.path.join(INSTALLED, "google.json"))
print(f"google.json: {updated} models updated with official pricing ({len(data['models'])} total)", flush=True)
