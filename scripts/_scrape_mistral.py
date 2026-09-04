"""Scrape Mistral model cards from docs.mistral.ai (static HTML, no browser).

docs.mistral.ai serves server-rendered HTML to plain HTTP clients, and each
card carries everything _update_mistral.build_row needs: display name, API id,
status badge, dates, replacement, license, version, context, prices, features.

Outputs (same shape as the former Playwright version):
  _scratch_mistral_scrape_full.json
  _scratch_mistral_overview.json

Usage:
  python scripts/_scrape_mistral.py
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "_scratch_mistral_scrape_full.json"
OVERVIEW_OUT = WORKDIR / "_scratch_mistral_overview.json"
BASE = "https://docs.mistral.ai/models/"
OVERVIEW = "https://docs.mistral.ai/models"

UA = "llmcapa-official-updater/1.0"

ID_RE = re.compile(r"[a-z][a-z0-9._-]{2,80}", re.IGNORECASE)
ID_HINT = re.compile(
    r"mistral|ministral|codestral|devstral|voxtral|magistral|leanstral|"
    r"pixtral|mathstral|mixtral|ocr|labs",
    re.IGNORECASE,
)
MONTH_RE = (
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}"
)

FEATURE_NAMES = [
    "Chat Completions", "Function Calling", "Agents & Conversations",
    "Built-In Tools", "Structured Outputs", "Predicted Outputs", "Prefix",
    "OCR", "Document QnA", "FIM", "Embeddings", "Moderations",
    "Transcriptions", "Text to Speech", "Batching",
    "Annotations - Structured", "BBox Extraction", "Chat Moderations",
    "Timestamps",
]


def fetch(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as resp:
        return resp.read(3000000).decode("utf-8", "replace")


def page_text(body):
    text = re.sub(r"<script[\s>].*?</script>", "\n", body, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[\s>].*?</style>", "\n", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = htmlmod.unescape(text)
    return re.sub(r"\n{2,}", "\n", text)


def extract_card(slug, body):
    text = page_text(body)
    h1m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.DOTALL | re.IGNORECASE)
    h1 = htmlmod.unescape(re.sub(r"<[^>]+>", "", h1m.group(1))).strip() if h1m else ""
    tm = re.search(r"<title>(.*?)</title>", body, re.DOTALL | re.IGNORECASE)
    title = htmlmod.unescape(tm.group(1)).strip() if tm else ""
    is404 = bool(re.search(r"404|not found|page not found|Meow", h1 + " " + title, re.IGNORECASE)) or len(text) < 400

    top = text[:2500]
    lic = None
    if re.search(r"\bOPEN\b", top): lic = "open"
    elif re.search(r"\bPREMIER\b", top): lic = "premier"
    elif re.search(r"\bLABS\b", top): lic = "labs"
    verm = re.search(r"\bv([0-9]+(?:\.[0-9]+)*)\b", top)
    ver = verm.group(1) if verm else None
    datem = re.search(MONTH_RE, top)
    date = datem.group(0) if datem else None

    # API id: the copy badge right after H1 ("Click to copy: <id>") is exact.
    # Fall back to bare identifier lines mentioning a Mistral family.
    copy_ids = re.findall(r'title="Click to copy: ([^"]+)"', body)
    copy_ids = [c.strip() for c in copy_ids if c.strip()]
    skip_heads = {"SPEED","PERFORMANCE","MODALITIES","FEATURES","WEIGHTS","DEPRECATION DATE","RETIREMENT DATE","PRICE","CONTEXT"}
    id_cands = []
    if copy_ids:
        id_cands.append(copy_ids[0])
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) > 40: continue
        if ID_RE.fullmatch(line) is None: continue
        if line.upper() in skip_heads: continue
        if ID_HINT.search(line): id_cands.append(line)
    id_cands = list(dict.fromkeys(id_cands))[:10]
    primary = id_cands[0] if id_cands else None

    plusm = re.search(r"^\+(\d+)$", text, re.MULTILINE)
    plus_n = plusm.group(1) if plusm else None

    # Pricing: SSR price spans "$<!-- -->X" between H1 and FEATURES, each
    # followed by a label (Input / Cached input / Output) and unit
    # (/M Tokens, /Min, /1000 Pages...). Nav/flight-data $ noise is excluded
    # because we only look between H1 and FEATURES. Labels matter: a card
    # like "$1.4 Input / $0.14 Cached input / $4.4 Output" must not take the
    # first two values as input/output.
    ip = op = cache_p = None; unit = None
    hi = body.find("<h1")
    fi = body.find("FEATURES", hi if hi >= 0 else 0)
    card_html = body[hi:fi] if hi >= 0 and fi > hi else body[:250000]
    pipe = re.sub(r"<[^>]+>", "|", card_html)
    pipe = re.sub(r"\|+", "|", pipe)
    triples = re.findall(r"\$\|([0-9]+(?:\.[0-9]+)?)(?:\|([^|$]{0,40}?))?\|/([^|$]{0,40})", pipe)
    price_vals = [float(v) for v, _, _ in triples]
    price_units = [u for _, _, u in triples]
    m_tokens_unlabeled: list[float] = []
    min_p = page_p = None
    for v, label, u in triples:
        fv = float(v)
        lab = (label or "").strip().lower()
        ul = u.strip().lower()
        if "page" in ul:
            if page_p is None: page_p = fv
            continue
        if re.search(r"\bmin\b", ul):
            if min_p is None: min_p = fv
            continue
        if lab == "input":
            if ip is None: ip = fv
        elif "cached" in lab:
            if cache_p is None: cache_p = fv
        elif lab == "output":
            if op is None: op = fv
        else:
            m_tokens_unlabeled.append(fv)
    # Fallback for cards without explicit Input/Output labels: positional.
    if ip is None and m_tokens_unlabeled:
        ip = m_tokens_unlabeled.pop(0)
    if op is None and m_tokens_unlabeled:
        op = m_tokens_unlabeled.pop(0)
    if ip is not None or op is not None:
        unit = "per_1m_tokens"
    if ip is None and re.search(r"\$0\b", card_html): ip = 0.0

    card_text = page_text(card_html)
    # Context can be absent (deprecated cards without a header row) or polluted
    # by the weights table ("Context Size (tokens)" 32k). Prefer the header-row
    # value right after CONTEXT. Unit may be k or M (e.g. "1M" -> 1000k).
    # NOTE: the embedded Next.js payload (self.__next_f) contains version
    # strings like "v26.04" ("eyebrow=v26.04"); a bare "v26.04" lookalike must
    # never be read as "26.04M". Require an explicit k/K/M unit letter.
    ctx_k = None
    ctxm = re.search(r"CONTEXT(?:\s*\|?\s*i)?\s*\|?\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmM])(?![A-Za-z0-9.])", card_text, re.IGNORECASE)
    if ctxm:
        ctx_k = float(ctxm.group(1)) * (1000.0 if ctxm.group(2).upper() == "M" else 1.0)
    max_out_k = None
    maxm = re.search(r"MAX OUTPUT(?:\s*\|?\s*i)?\s*\|?\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmM])(?![A-Za-z0-9.])", card_text, re.IGNORECASE)
    if maxm:
        max_out_k = float(maxm.group(1)) * (1000.0 if maxm.group(2).upper() == "M" else 1.0)

    depm = re.search(r"DEPRECATION DATE\s*\n?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.IGNORECASE)
    retm = re.search(r"RETIREMENT DATE\s*\n?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.IGNORECASE)
    replm = re.search(r"REPLACEMENT\s*\n?\s*([^\n]+)", text, re.IGNORECASE)
    repl = replm.group(1).strip() if replm else None
    if repl and len(repl) > 120: repl = None
    dep = depm.group(1) if depm else None
    ret = retm.group(1) if retm else None

    badges = re.findall(r'data-badge-type="[^"]*"[^>]*>\s*([^<]{1,30})', body)
    status = badges[0].strip() if badges else None
    if not status:
        if re.search(r"This model is deprecated", text, re.IGNORECASE): status = "Deprecated"
        elif re.search(r"This model is retired|has been retired", text, re.IGNORECASE): status = "Retired"

    hi2 = body.find("<h1")
    feat0 = body.find("FEATURES", hi2 if hi2 >= 0 else 0)
    feat1 = body.find("Other Models", feat0 if feat0 >= 0 else 0)
    if feat0 >= 0 and feat1 > feat0:
        feat_region = body[feat0:feat1]
    else:
        feat_region = (body[hi2:hi2+250000] if hi2 >= 0 else body[:250000])
    present = set(htmlmod.unescape(x).strip() for x in re.findall(r'LinkItem_title__ZRXu4">([^<]+)</span>', feat_region))
    feats = {name: (name in present) for name in FEATURE_NAMES}
    if not present: feats = dict.fromkeys(FEATURE_NAMES)

    modm = re.search(r"MODALITIES(.{0,200})", text, re.IGNORECASE | re.DOTALL)
    mod_head = (modm.group(1) if modm else "").lower()
    modalities = {
        "text": ("text" in mod_head) or feats.get("Chat Completions") is True,
        "image": bool(re.search(r"image|vision|img", mod_head)),
        "audio": bool(re.search(r"audio|speech|transcri|tts|voxtral", h1 + " " + mod_head, re.IGNORECASE)) or feats.get("Transcriptions") is True or feats.get("Text to Speech") is True,
    }

    description = ""
    title_l = (title or "").strip().lower()
    nav_prefix = ("TRY", "Compare", "Legal", "MODELS", "MODEL", "FEATURES", "WEIGHTS", "OPEN", "PREMIER", "LABS")
    for line in text.split("\n"):
        line = line.strip()
        if len(line) <= 40: continue
        if ID_RE.fullmatch(line) is not None: continue
        if line.startswith("v") and re.fullmatch(r"v[0-9.]+", line): continue
        if line.startswith(tuple(nav_prefix), 0, 0) if False else False: continue
        if any(line.startswith(pref) for pref in ("TRY ", "Compare", "Legal", "MODELS", "MODEL", "FEATURES", "WEIGHTS", "OPEN", "PREMIER", "LABS")): continue
        # standalone date / version / license badges, not descriptions
        if re.fullmatch(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", line): continue
        if re.fullmatch(r"(GA|Public Preview|Deprecated|Retired|Private Preview|Beta)", line, re.IGNORECASE): continue
        if re.fullmatch(r"(Apache 2\.0|MIT|Modified MIT|Premier|Open)", line, re.IGNORECASE): continue
        if re.fullmatch(r"v[0-9.]+", line): continue
        if title_l and line.strip().lower() == title_l: continue
        description = line; break

    speedm = re.search(r"SPEED(.{0,40}?)([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE | re.DOTALL)
    perfm = re.search(r"PERFORMANCE(.{0,40}?)([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE | re.DOTALL)
    dollars = list(price_vals[:8])

    return {"slug": slug, "url": BASE + slug, "h1": h1, "license": lic, "ver": ver, "date": date,
        "primaryCode": primary, "idCandidates": id_cands, "plusN": plus_n,
        "input_price": ip, "output_price": op, "unit": unit, "min_price": min_p, "page_price": page_p,
        "allDollar": dollars[:8], "ctx_k": ctx_k, "max_out_k": max_out_k, "cached_input": cache_p, "deprecation_date": dep, "retirement_date": ret,
        "replacement": repl, "status": status, "features": feats, "modalities": modalities,
        "description": description[:300],
        "speed": float(speedm.group(2)) if speedm else None,
        "perf": float(perfm.group(2)) if perfm else None,
        "text_len": len(text), "is404": is404, "head_text": text[:1800]}


def main():
    prev = {}
    if OUT.exists():
        try: prev = __import__("json").loads(OUT.read_text(encoding="utf-8")).get("models", {})
        except Exception: prev = {}
    print("overview...", flush=True)
    ov_body = fetch(OVERVIEW)
    slugs = list(dict.fromkeys(re.findall(r'href="(/models/[^"]+)"', ov_body)))
    tmp = []
    for s in slugs:
        s = s.split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
        if s and s.lower() not in {"models","overview","model-selection-guide","model-cards","legacy","deprecated","pricing"}:
            tmp.append(s)
    slugs = tmp
    ov_text = page_text(ov_body)
    lines = [l.strip() for l in ov_text.split("\n") if l.strip()]
    idx = next((n for n, l in enumerate(lines) if re.search(r"legacy|deprecated", l, re.IGNORECASE)), -1)
    chunk = lines[idx:idx+400] if idx >= 0 else lines[-200:]
    OVERVIEW_OUT.write_text(__import__("json").dumps({"slugs": slugs, "link_count": len(slugs), "legacy_chunk": chunk, "text_len": len(ov_text)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"overview slugs={len(slugs)}", flush=True)
    for s in slugs: print(" ", s, flush=True)
    ordered = list(dict.fromkeys(slugs + [s for s in prev.keys() if s not in slugs]))
    results = {}; errors = []
    for i, slug in enumerate(ordered, 1):
        print(f"[{i}/{len(ordered)}] {slug}", flush=True)
        try:
            body = fetch(BASE + slug)
            data = extract_card(slug, body)
            data["http_status"] = 200
            results[slug] = data
            print(f"  {data.get('h1')} code={data.get('primaryCode')} ctx={data.get('ctx_k')} in={data.get('input_price')} out={data.get('output_price')} status={data.get('status')} dep={data.get('deprecation_date')} ret={data.get('retirement_date')} 404={data.get('is404')}", flush=True)
        except Exception as e:
            errors.append({"slug": slug, "error": str(e)}); print(f"  ERR {e}", flush=True)
        if i % 8 == 0:
            OUT.write_text(__import__("json").dumps({"scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "models": results, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {"scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "count": len(results), "models": results, "errors": errors, "overview_slugs": slugs}
    OUT.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} models={len(results)} errors={len(errors)}", flush=True)


if __name__ == "__main__":
    main()
