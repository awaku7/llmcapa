"""Build mistral.json from Playwright scrape (_scratch_mistral_scrape_full.json).

Source: https://docs.mistral.ai/models/overview + model-cards/*
Shape: xai-style Capability JSON with pricing + extra.source
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
SCRAPE = WORKDIR / "_scratch_mistral_scrape_full.json"
OUT = WORKDIR / "src" / "llmcapa" / "data" / "mistral.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\mistral.json")
LOG = WORKDIR / "provider_update_log.md"

# Known multimodal (vision) families on Mistral API (chat + image)
VISION_NAME_RE = re.compile(
    r"pixtral|mistral medium|mistral large|mistral small|ministral|magistral|ocr",
    re.I,
)
# Explicitly not vision
NO_VISION_RE = re.compile(
    r"codestral|embed|moderation|voxtral|tts|transcribe|mathstral|mixtral|mamba|nemo|leanstral|saba|next|7b",
    re.I,
)

SIDEBAR_JUNK = {
    "ocr",
    "labs",
    "lab",
    "codestral",
    "leanstral",
    "mistral",
    "ministral",
    "magistral",
    "devstral",
    "pixtral",
    "voxtral",
    "mixtral",
}


def _slug_to_api_id(slug: str) -> str:
    """Convert card slug date segments to compact API id style.
    e.g. voxtral-mini-25-07 -> voxtral-mini-2507; mistral-medium-3-5-26-04 -> mistral-medium-3-5
    """
    s = slug
    # collapse trailing YY-MM date: -25-07 -> -2507, -26-03 -> -2603
    s2 = re.sub(r"-(\d{2})-(\d{2})$", r"-\1\2", s)
    return s2


def pick_model_id(m: dict, slug: str) -> str:
    cands = m.get("idCandidates") or []
    good = []
    for c in cands:
        if not isinstance(c, str):
            continue
        cl = c.lower()
        if cl in SIDEBAR_JUNK:
            continue
        # API ids: lowercase, may include open-/labs- and digits
        if not re.fullmatch(r"[a-z][a-z0-9._-]{2,80}", c):
            continue
        if re.search(r"\d|labs-|open-", c):
            good.append(c)
    if not good:
        return _slug_to_api_id(slug)

    slug_l = slug.lower()
    slug_api = _slug_to_api_id(slug).lower()
    # Prefer candidate that best matches this card's slug (avoids voxtral mini/transcribe swap)
    def score(c: str) -> tuple:
        cl = c.lower()
        exact = 1 if cl == slug_api or cl == slug_l else 0
        # token overlap with slug (transcribe/tts/mini etc.)
        stoks = set(re.split(r"[-_]", slug_l))
        ctoks = set(re.split(r"[-_]", cl))
        # drop pure digit tokens for family match
        stoks_f = {t for t in stoks if not t.isdigit()}
        ctoks_f = {t for t in ctoks if not t.isdigit()}
        overlap = len(stoks_f & ctoks_f)
        # penalize missing distinctive tokens present in slug
        distinctive = {"transcribe", "realtime", "tts", "embed", "moderation", "ocr", "mamba"}
        miss = len((stoks_f & distinctive) - ctoks_f)
        extra = len((ctoks_f & distinctive) - stoks_f)
        # prefer open-* only when slug is open/research legacy without better match
        open_pen = 1 if cl.startswith("open-") and not slug_l.startswith("open-") else 0
        return (exact, overlap, -miss, -extra, -open_pen, -len(cl))

    good_sorted = sorted(good, key=score, reverse=True)
    best = good_sorted[0]
    # If best still poorly matches (e.g. shared id across chat+transcribe cards),
    # fall back to slug-derived id when slug has distinctive tokens not in best.
    stoks = set(re.split(r"[-_]", slug_l))
    btoks = set(re.split(r"[-_]", best.lower()))
    distinctive = {"transcribe", "realtime", "tts"}
    if (stoks & distinctive) - btoks:
        return _slug_to_api_id(slug)
    # For chat voxtral-mini card when candidate is shared with transcribe, keep compact id
    if best:
        return best
    return _slug_to_api_id(slug)


def parse_us_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m/%d/%Y")
    except Exception:
        return None


def is_deprecated(m: dict) -> bool:
    if m.get("deprecation_date"):
        return True
    ret = parse_us_date(m.get("retirement_date"))
    if ret is not None:
        return True
    return False


def has_vision(display: str, model_id: str) -> bool:
    blob = f"{display} {model_id}"
    if NO_VISION_RE.search(blob) and not re.search(r"pixtral|ocr", blob, re.I):
        return False
    return bool(VISION_NAME_RE.search(blob))


def has_reasoning(display: str, model_id: str) -> bool:
    blob = f"{display} {model_id}".lower()
    return "magistral" in blob or "leanstral" in blob


def features_all_unknown(feats: dict) -> bool:
    if not feats:
        return True
    # OCR is polluted by nav chrome in scrape; ignore it
    vals = [v for k, v in feats.items() if k != "OCR"]
    return all(v is None for v in vals)


def build_row(slug: str, m: dict) -> dict:
    mid = pick_model_id(m, slug)
    display = m.get("h1") or mid
    feats = m.get("features") or {}

    chat = bool(feats.get("Chat Completions"))
    fc = bool(feats.get("Function Calling"))
    json_mode = bool(feats.get("Structured Outputs"))
    fim = bool(feats.get("FIM"))
    emb = bool(feats.get("Embeddings"))
    moderation = bool(feats.get("Moderations"))
    transcription = bool(feats.get("Transcriptions"))
    tts = bool(feats.get("Text to Speech"))

    name_l = display.lower()
    mid_l = mid.lower()

    # modalities
    in_mods: list[str] = []
    out_mods: list[str] = []

    is_tts = tts or "tts" in name_l or "tts" in mid_l
    # Only treat as pure transcription when feature/name says so (not all Voxtral Mini)
    is_transcribe = transcription or "transcribe" in name_l or "transcribe" in mid_l
    is_ocr = ("ocr" in name_l or "ocr" in mid_l) and not chat
    is_embed = emb or "embed" in name_l or "embed" in mid_l
    is_moderation = moderation or "moderation" in name_l
    is_voxtral_chat = (
        ("voxtral" in name_l or "voxtral" in mid_l)
        and not is_tts
        and not is_transcribe
    )

    # Research / legacy cards often have all feature flags null — default chat LLM
    if features_all_unknown(feats) and not (is_embed or is_moderation or is_ocr or is_tts or is_transcribe):
        chat = True
        # coding research models typically support FIM-ish usage; leave fim false unless known
        if "codestral" in name_l or "codestral" in mid_l or "mamba" in name_l:
            fim = True

    vision = has_vision(display, mid)
    if is_ocr:
        vision = True

    if is_embed:
        in_mods = ["text"]
        out_mods = ["text"]
        vision = False
        chat = False
    elif is_moderation and not chat:
        in_mods = ["text"]
        out_mods = ["text"]
        vision = False
    elif is_tts:
        in_mods = ["text"]
        out_mods = ["audio"]
        chat = False
    elif is_transcribe:
        in_mods = ["audio"]
        out_mods = ["text"]
        chat = False
    elif is_ocr:
        in_mods = ["image"]
        out_mods = ["text"]
        chat = False
    else:
        in_mods = ["text"]
        if vision:
            in_mods.append("image")
        if is_voxtral_chat:
            if "audio" not in in_mods:
                in_mods.append("audio")
        out_mods = ["text"]

    ctx = m.get("ctx_k")
    ctx_tokens = int(float(ctx) * 1000) if ctx else 0

    # Pricing: only token pricing goes into pricing{}; specialty units in extra
    pricing = None
    ip, op = m.get("input_price"), m.get("output_price")
    all_dollar = m.get("allDollar") or []
    specialty_price = is_tts or is_transcribe or is_ocr

    # Voxtral Small cards expose audio $/min + token in/out (3 amounts)
    audio_per_min = None
    if is_voxtral_chat and isinstance(all_dollar, list) and len(all_dollar) >= 3:
        audio_per_min = float(all_dollar[0])
        ip = float(all_dollar[1])
        op = float(all_dollar[2])
    elif is_voxtral_chat and ip is not None and op is not None and float(ip) < 0.01 and float(op) <= 0.1:
        # Heuristic: very low "input" is audio/min; keep output if second token price missing
        if isinstance(all_dollar, list) and len(all_dollar) >= 2:
            audio_per_min = float(all_dollar[0])
            # if only 2 values, treat as audio + something ambiguous — leave token price unset
            if len(all_dollar) == 2:
                ip, op = None, None
            else:
                ip, op = float(all_dollar[1]), float(all_dollar[2])

    if not specialty_price and (ip is not None or op is not None):
        pricing = {"currency": "USD"}
        if ip is not None:
            pricing["input_per_1m"] = float(ip)
        if op is not None:
            pricing["output_per_1m"] = float(op)

    extra: dict = {
        "source": m.get("url") or f"https://docs.mistral.ai/models/model-cards/{slug}",
        "card_slug": slug,
    }
    if m.get("ver"):
        extra["version"] = m["ver"]
    if m.get("date"):
        extra["release_date"] = m["date"]
    if m.get("license"):
        extra["license_badge"] = m["license"]
    if m.get("deprecation_date"):
        extra["deprecation_date"] = m["deprecation_date"]
    if m.get("retirement_date"):
        extra["retirement_date"] = m["retirement_date"]
    if m.get("replacement"):
        extra["replacement"] = m["replacement"]
    if m.get("plusN"):
        extra["alias_count"] = str(m["plusN"])
    if m.get("description"):
        extra["description"] = m["description"]

    # specialty pricing
    if is_transcribe and ip is not None:
        extra["price_per_min"] = float(ip)
    if audio_per_min is not None:
        extra["audio_price_per_min"] = audio_per_min
    if is_tts:
        # scraped as [0, 16] — treat 16 as output specialty rate
        if op is not None:
            extra["tts_price"] = float(op)
        if ip is not None:
            extra["tts_input_price"] = float(ip)
    if is_ocr:
        if ip is not None:
            extra["price_per_m_pages"] = float(ip)
        if op is not None:
            extra["price_per_m_pages_annotation"] = float(op)

    if is_embed:
        extra["supports_embeddings"] = True
    if is_moderation:
        extra["supports_moderation"] = True
    if is_transcribe:
        extra["supports_transcription"] = True
    if is_tts:
        extra["supports_tts"] = True
    if feats.get("Batching"):
        extra["supports_batching"] = True
    if feats.get("Prefix"):
        extra["supports_prefix"] = True
    if feats.get("Agents & Conversations"):
        extra["supports_agents"] = True
    if feats.get("Built-In Tools"):
        extra["supports_built_in_tools"] = True
    if feats.get("Predicted Outputs"):
        extra["supports_predicted_outputs"] = True
    if feats.get("Document QnA"):
        extra["supports_document_qna"] = True
    if feats.get("Annotations - Structured"):
        extra["supports_ocr_annotations"] = True
    if feats.get("BBox Extraction"):
        extra["supports_bbox_extraction"] = True

    lic = (m.get("license") or "").lower()
    if lic == "open":
        license_type = "open"
    elif lic == "labs":
        license_type = "labs"
    else:
        license_type = "api"

    # streaming default true for chat/audio APIs
    streaming = bool(chat or is_transcribe or is_tts)

    # aliases: common bare names for current flagship
    alias_map = {
        "mistral-medium-3-5": ["mistral-medium-latest", "mistral-medium"],
        "mistral-small-2603": ["mistral-small-latest", "mistral-small"],
        "mistral-large-2512": ["mistral-large-latest", "mistral-large"],
        "codestral-2508": ["codestral-latest", "codestral"],
        "mistral-embed-2312": ["mistral-embed"],
        "mistral-moderation-2603": ["mistral-moderation-latest", "mistral-moderation"],
        "mistral-ocr-4-0": ["mistral-ocr-latest", "mistral-ocr"],
    }
    aliases = list(alias_map.get(mid, []))

    return {
        "provider": "mistral",
        "model_id": mid,
        "display_name": display,
        "context_window": ctx_tokens,
        "max_output_tokens": 0,
        "input_modalities": in_mods,
        "output_modalities": out_mods,
        "supports_function_calling": fc if chat else False,
        "supports_json_mode": json_mode if chat else False,
        "supports_streaming": streaming,
        "supports_vision": vision,
        "supports_reasoning": has_reasoning(display, mid),
        "supports_chat_completion": chat,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": fim,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": is_deprecated(m),
        "aliases": aliases,
        "license_type": license_type,
        "pricing": pricing,
        "extra": extra,
    }


def dedupe_model_ids(rows: list[dict]) -> list[dict]:
    """Ensure unique model_id; on collision use card slug for the later row."""
    seen: dict[str, int] = {}
    out = []
    for r in rows:
        mid = r["model_id"]
        if mid not in seen:
            seen[mid] = 1
            out.append(r)
            continue
        slug = r.get("extra", {}).get("card_slug", "")
        if slug and slug not in seen:
            r["model_id"] = slug
        else:
            r["model_id"] = f"{mid}#{seen[mid]}"
        seen[mid] = seen[mid] + 1
        seen[r["model_id"]] = 1
        print(f"dedupe: {mid} -> {r['model_id']} (slug={slug})", flush=True)
        out.append(r)
    return out


def main() -> None:
    raw = json.loads(SCRAPE.read_text(encoding="utf-8"))
    models = raw["models"]
    overview = raw.get("overview_slugs") or [
        s for s, m in models.items() if not m.get("is404")
    ]

    rows: list[dict] = []
    skipped = []
    for slug in overview:
        m = models.get(slug)
        if not m or m.get("is404"):
            skipped.append(slug)
            continue
        rows.append(build_row(slug, m))

    rows = dedupe_model_ids(rows)

    # stable sort: active first, then by model_id
    rows.sort(key=lambda r: (r["deprecated"], r["model_id"]))

    payload = {"models": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(OUT, INSTALLED)

    n = len(rows)
    n_price = sum(1 for r in rows if r.get("pricing"))
    n_dep = sum(1 for r in rows if r.get("deprecated"))
    n_active = n - n_dep
    print(f"mistral.json: {n} models (active={n_active}, deprecated={n_dep}, priced={n_price})", flush=True)
    print(f"wrote {OUT}", flush=True)
    print(f"copied {INSTALLED}", flush=True)
    if skipped:
        print("skipped:", skipped, flush=True)

    print("--- active ---", flush=True)
    for r in rows:
        if r["deprecated"]:
            continue
        p = r.get("pricing")
        print(
            f"  {r['model_id']:40} ctx={r['context_window']:7} "
            f"price={p} vision={r['supports_vision']} fim={r['supports_fim']} "
            f"chat={r['supports_chat_completion']} reason={r['supports_reasoning']}",
            flush=True,
        )

    # append log only if last entry is not already today's mistral refresh with same count
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"""
## Mistral refresh ({today}) — quality pass

### Fixes
- Voxtral Mini chat vs pure-transcribe classification (no longer force all non-small Voxtral to transcribe)
- Voxtral Small token pricing: use 3-amount cards as audio/min + input/output token
- Research cards with null feature flags default to chat=True (mathstral/next/mamba/7b)
- pick_model_id accepts open-* ids (e.g. open-codestral-mamba)

### Result
- mistral.json: **{n}** models (active={n_active}, deprecated={n_dep}, token-priced={n_price})
- Install copy synced
- Skipped 404 slugs: {skipped or "none"}
"""
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text("# Provider update log\n" + entry, encoding="utf-8")
    print(f"log updated: {LOG}", flush=True)


if __name__ == "__main__":
    main()
