#!/usr/bin/env python3
"""
Scrape LM Studio model catalog from https://lmstudio.ai/models

Usage: python _scrape_lmstudio.py [--save]
"""

import json
import os
import re
import sys
from playwright.sync_api import sync_playwright

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "src", "llmcapa", "data", "lmstudio.json")
BASE_URL = "https://lmstudio.ai"


def extract_model_data(page, slug):
    """Extract all model data from a single LM Studio model detail page."""
    page.goto(f"{BASE_URL}{slug}", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    main = page.query_selector("main") or page.query_selector("body")
    text = main.inner_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Find the content section by locating "← All Models"
    start_idx = None
    for i, line in enumerate(lines):
        if "All Models" in line and ("←" in line or "<-" in line):
            start_idx = i
            break
    if start_idx is None:
        return []

    # -- Extract name (line after ← All Models) --
    name = lines[start_idx + 1] if start_idx + 1 < len(lines) else ""

    # -- Extract downloads --
    downloads = ""
    if start_idx + 2 < len(lines):
        m = re.search(r"([\d.]+[KMB]?)\s*Downloads", lines[start_idx + 2])
        if m:
            downloads = m.group(1)

    # -- Find where model variants start (after "Models" heading, looking for "Updated X") --
    variant_start = None
    variant_end = None
    for i in range(start_idx, len(lines)):
        if lines[i] == "Models" and variant_start is None:
            # Check if "Updated" appears within next 5 lines
            for j in range(i + 1, min(i + 5, len(lines))):
                if "Updated" in lines[j]:
                    variant_start = i
                    break
        if variant_start is not None and lines[i] in ("Memory Requirements", "Capabilities"):
            variant_end = i
            break

    if variant_start is None:
        # Fallback: find "Models" heading by looking for model_id patterns
        for i in range(start_idx, len(lines)):
            if "/" in lines[i] and i + 3 < len(lines) and lines[i + 1].endswith("GB"):
                variant_start = i - 1  # Approx
                break

    # -- Extract model variants --
    variants = []
    if variant_start is not None:
        i = variant_start + 1
        while i < len(lines) and (variant_end is None or i < variant_end):
            line = lines[i]
            if "Updated" in line:
                i += 1
                continue
            if "/" in line and not line.startswith("To run"):
                model_id = line
                size = ""
                dl_count = ""
                if i + 1 < len(lines) and "GB" in lines[i + 1]:
                    size = lines[i + 1]
                    if i + 2 < len(lines) and lines[i + 2].isdigit():
                        dl_count = lines[i + 2]
                if model_id:
                    variants.append({
                        "model_id": model_id,
                        "size_gb": size,
                        "downloads": dl_count,
                    })
                # Skip ahead (model_id, size, dl_count, "Get")
                if i + 3 < len(lines) and lines[i + 3] == "Get":
                    i += 4
                    continue
            i += 1

    # -- Collect all content text for context/capability extraction --
    # Grab everything from after "← All Models" to "Product"
    content_lines = []
    if start_idx is not None:
        for i in range(start_idx + 1, len(lines)):
            if lines[i] in ("Product",):
                break
            content_lines.append(lines[i])
    full_text = " ".join(content_lines)

    # -- Extract capabilities from full text --
    full_text_lower = full_text.lower()
    supports_vision = any(w in full_text_lower for w in ["vision", "image understanding", "object detection",
                                                          "multimodal", "video understanding", "ocr",
                                                          "chart comprehension", "document/", "visual"])
    supports_reasoning = any(w in full_text_lower for w in ["reasoning", "thinking", "step-by-step",
                                                            "think step", "think before"])
    supports_function_calling = any(w in full_text_lower for w in ["tool use", "function calling", "tools",
                                                                    "function-calling", "tool usage",
                                                                    "agentic"])

    input_modalities = ["text"]
    if supports_vision:
        input_modalities.append("image")
    # Check for specific modality mentions
    if re.search(r'\b(?:video|audio)\b', full_text_lower):
        for w in ["video", "audio"]:
            if re.search(r'\b' + w + r'\b', full_text_lower):
                if w not in input_modalities:
                    input_modalities.append(w)

    output_modalities = ["text"]

    # -- Extract context window --
    context_window = 0
    # Pattern 1: "256K-token" or "128K tokens" or "256K token"
    ctx_matches = re.findall(r'(\d+)\s*[Kk]\s*-?\s*[Tt]oken', full_text)
    if ctx_matches:
        context_window = max(int(m) * 1024 for m in ctx_matches)
    if not context_window:
        # Pattern 2: "context window of up to 256K" or "context length 128K"
        ctx_matches = re.findall(r'context\s*(?:window|length)?\s*(?:of\s*)?(?:up\s*to\s*)?(\d+)\s*[Kk]', full_text)
        if ctx_matches:
            context_window = max(int(m) * 1024 for m in ctx_matches)
    if not context_window:
        # Pattern 3: "256K context" or "128K context"
        ctx_matches = re.findall(r'(\d+)\s*[Kk]\s*context', full_text)
        if ctx_matches:
            context_window = max(int(m) * 1024 for m in ctx_matches)
    if not context_window:
        # Pattern 4: "1M tokens"
        ctx_matches = re.findall(r'(1)\s*[Mm](?:\s|[-])(?:token|context)', full_text)
        if ctx_matches:
            context_window = max(int(m) * 1024 * 1024 for m in ctx_matches)

    # -- Extract max output tokens --
    max_output = 0
    out_matches = re.findall(r'(\d+)\s*[Kk]\s*output', full_text)
    if out_matches:
        max_output = max(int(m) * 1024 for m in out_matches)

    # -- Extract license --
    license_type = "free"
    for i, line in enumerate(lines):
        if line == "License" and i + 1 < len(lines):
            lic_text = lines[i + 1].lower()
            if "apache" in lic_text:
                license_type = "apache-2.0"
            elif "mit" in lic_text:
                license_type = "mit"
            elif "cc by" in lic_text or "cc-by" in lic_text:
                license_type = "cc-by"
            elif "proprietary" in lic_text or "commercial" in lic_text:
                license_type = "proprietary"
            elif "community" in lic_text:
                license_type = "community"
            break

    # -- Build entries for each variant --
    result_variants = []
    seen_ids = set()
    for v in variants:
        mid = v["model_id"]
        if not mid or mid in seen_ids:
            continue
        seen_ids.add(mid)
        parts = mid.rsplit("/", 1)
        display = parts[-1] if len(parts) > 1 else mid

        entry = {
            "provider": "lmstudio",
            "model_id": mid,
            "display_name": display,
            "context_window": context_window,
            "max_output_tokens": max_output if max_output else 8192,
            "input_modalities": list(input_modalities),
            "output_modalities": list(output_modalities),
            "supports_function_calling": supports_function_calling,
            "supports_json_mode": True,
            "supports_streaming": True,
            "supports_vision": supports_vision,
            "supports_reasoning": supports_reasoning,
            "knowledge_cutoff": "2024-01-01",
            "pricing": {
                "input_per_1m": 0.0,
                "output_per_1m": 0.0,
                "currency": "USD"
            },
            "aliases": [],
            "deprecated": False,
            "supports_fim": False,
            "license_type": license_type,
        }
        result_variants.append(entry)

    return result_variants


def main():
    save = "--save" in sys.argv

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Get all model family links
        print("Fetching model list from main page...")
        page.goto(f"{BASE_URL}/models", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        slugs = page.evaluate("""() => {
            const links = document.querySelectorAll('a');
            const modelLinks = new Set();
            for (const link of links) {
                const href = link.getAttribute('href');
                if (href && href.startsWith('/models/') && href !== '/models') {
                    modelLinks.add(href);
                }
            }
            return Array.from(modelLinks);
        }""")
        print(f"Found {len(slugs)} model families: {slugs}")
        page.close()

        # Scrape each model family page
        all_models = []
        seen_model_ids = set()
        for idx, slug in enumerate(slugs):
            print(f"\n[{idx + 1}/{len(slugs)}] {slug}...", end="")
            try:
                spage = browser.new_page()
                variants = extract_model_data(spage, slug)
                spage.close()
                print(f" {len(variants)} vars")
                for v in variants:
                    mid = v["model_id"]
                    if mid not in seen_model_ids:
                        seen_model_ids.add(mid)
                        all_models.append(v)
            except Exception as e:
                print(f" ERROR: {e}")

        browser.close()

    all_models.sort(key=lambda m: m["model_id"])
    print(f"\nTotal unique model entries: {len(all_models)}")

    output_data = {"models": all_models}

    if save:
        os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Saved to {OUTPUT}")
    else:
        print(f"\nSample entries:")
        for m in all_models[:10]:
            print(f"  {m['model_id']:50s} | ctx={m['context_window']:>6d} | vision={str(m['supports_vision']):5s} | tools={str(m['supports_function_calling']):5s} | reasoning={str(m['supports_reasoning']):5s}")
        print(f"\nRun with --save to write to {OUTPUT}")


if __name__ == "__main__":
    main()
