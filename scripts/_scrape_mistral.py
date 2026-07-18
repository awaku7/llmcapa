"""Re-scrape Mistral cards with improved extraction; also pull overview slugs + legacy table."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "_scratch_mistral_scrape_full.json"
OVERVIEW_OUT = WORKDIR / "_scratch_mistral_overview.json"
BASE = "https://docs.mistral.ai/models/model-cards/"
OVERVIEW = "https://docs.mistral.ai/models/overview"

EXTRACT_JS = r"""
() => {
  const text = document.body.innerText || '';
  const h1 = document.querySelector('h1')?.innerText?.trim() || '';
  const title = document.title || '';
  const is404 = /404|not found|page not found|Meow/i.test(h1 + ' ' + title) || text.length < 400;

  let license = null;
  const top = text.slice(0, 2500);
  if (/\bOPEN\b/.test(top)) license = 'open';
  else if (/\bPREMIER\b/.test(top)) license = 'premier';
  else if (/\bLABS\b/.test(top)) license = 'labs';

  const ver = (top.match(/\bv([0-9]+(?:\.[0-9]+)*)\b/) || [])[1] || null;
  const date = (top.match(/(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}/) || [])[0] || null;

  const idCandidates = [];
  const lines = text.split(/\n/).map(l => l.trim()).filter(Boolean);
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^(SPEED|PERFORMANCE|MODALITIES|FEATURES|WEIGHTS|DEPRECATION DATE|RETIREMENT DATE|PRICE|CONTEXT)$/i.test(l)) continue;
    if (/^[a-z][a-z0-9._-]{2,80}$/i.test(l) && /(?:mistral|ministral|codestral|devstral|voxtral|magistral|leanstral|pixtral|mathstral|mixtral|ocr|labs)/i.test(l)) {
      idCandidates.push(l);
    }
  }
  let plusN = null;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^\+(\d+)$/);
    if (m) plusN = m[1];
  }

  let input_price = null, output_price = null, unit = null;
  const priceBlock = (text.match(/PRICE[\s\S]{0,400}/i) || [''])[0];
  const pair = [...priceBlock.matchAll(/\$([0-9]+(?:\.[0-9]+)?)/g)].map(m => parseFloat(m[1]));
  if (pair.length >= 2) { input_price = pair[0]; output_price = pair[1]; unit = 'per_1m_tokens'; }
  else if (pair.length === 1) { input_price = pair[0]; unit = 'per_1m_tokens'; }
  const minP = (text.match(/\$([0-9]+(?:\.[0-9]+)?)\s*\/\s*Min/i) || [])[1];
  const pageP = (text.match(/\$([0-9]+(?:\.[0-9]+)?)\s*\/\s*(?:M\s*)?pages?/i) || [])[1];
  if (/PRICE[\s\S]{0,80}\$0\b/i.test(text) || /Free/i.test(priceBlock)) {
    if (input_price === null) input_price = 0;
  }

  let ctx_k = null;
  const ctxM = text.match(/CONTEXT[\s\S]{0,60}?([0-9]+(?:\.[0-9]+)?)\s*k/i);
  if (ctxM) ctx_k = parseFloat(ctxM[1]);
  if (ctx_k == null) {
    const head = text.slice(0, 3500);
    const m3 = head.match(/CONTEXT[\s\S]{0,80}?([0-9]+)\s*k/i) || head.match(/([0-9]+)\s*k[\s\S]{0,40}CONTEXT/i);
    if (m3) ctx_k = parseFloat(m3[1]);
  }

  const dep = (text.match(/DEPRECATION DATE\s*\n?\s*([0-9]{1,2}\/[0-9]{1,2}\/[0-9]{4})/i) || [])[1] || null;
  const ret = (text.match(/RETIREMENT DATE\s*\n?\s*([0-9]{1,2}\/[0-9]{1,2}\/[0-9]{4})/i) || [])[1] || null;
  const repl = (text.match(/REPLACEMENT\s*\n?\s*([^\n]+)/i) || [])[1] || null;

  const featureNames = [
    'Chat Completions','Function Calling','Agents & Conversations','Built-In Tools',
    'Structured Outputs','Predicted Outputs','Prefix','OCR','Document QnA','FIM',
    'Embeddings','Moderations','Transcriptions','Text to Speech','Batching',
    'Annotations - Structured','BBox Extraction','Chat Moderations','Timestamps'
  ];
  const features = {};
  const all = Array.from(document.querySelectorAll('div,li,a,button,span,p'));
  for (const name of featureNames) {
    const el = all.find(e => e.childNodes.length <= 6 && (e.textContent || '').trim() === name);
    if (!el) { features[name] = null; continue; }
    let node = el; let disabled = false;
    for (let i = 0; i < 10 && node; i++) {
      const cls = (node.className || '').toString();
      if (cls.includes('opacity-30') || cls.includes('cursor-not-allowed')) { disabled = true; break; }
      node = node.parentElement;
    }
    features[name] = !disabled;
  }

  const modHead = (text.match(/MODALITIES[\s\S]{0,200}/i) || [''])[0].toLowerCase();
  const modalities = {
    text: /text/.test(modHead) || features['Chat Completions'] === true,
    image: /image|vision|img/.test(modHead),
    audio: /audio|speech|transcri|tts|voxtral/i.test(h1 + ' ' + modHead) || features['Transcriptions'] === true || features['Text to Speech'] === true,
  };

  let description = '';
  for (const l of lines) {
    if (l.length > 40 && !/^(TRY|Compare|Legal|MODELS|MODEL|FEATURES|WEIGHTS|OPEN|PREMIER|LABS|v[0-9])/i.test(l) && !/^[a-z0-9._-]+$/i.test(l)) {
      description = l;
      break;
    }
  }

  const speed = (text.match(/SPEED[\s\S]{0,40}?([0-9]+(?:\.[0-9]+)?)/i) || [])[1] || null;
  const perf = (text.match(/PERFORMANCE[\s\S]{0,40}?([0-9]+(?:\.[0-9]+)?)/i) || [])[1] || null;
  const allDollar = [...text.slice(0, 4000).matchAll(/\$([0-9]+(?:\.[0-9]+)?)/g)].map(m => parseFloat(m[1]));
  const primaryCode = idCandidates[0] || null;

  return {
    slug: location.pathname.split('/').pop(),
    url: location.href,
    h1, license, ver, date,
    primaryCode,
    idCandidates: idCandidates.slice(0, 10),
    plusN,
    input_price, output_price, unit,
    min_price: minP ? parseFloat(minP) : null,
    page_price: pageP ? parseFloat(pageP) : null,
    allDollar: allDollar.slice(0, 8),
    ctx_k,
    deprecation_date: dep,
    retirement_date: ret,
    replacement: repl ? repl.trim() : null,
    features,
    modalities,
    description: description.slice(0, 300),
    speed, perf,
    text_len: text.length,
    is404,
    head_text: text.slice(0, 1800)
  };
}
"""

OVERVIEW_JS = r"""
() => {
  const text = document.body.innerText || '';
  const links = Array.from(document.querySelectorAll('a[href*="/models/model-cards/"]'))
    .map(a => ({href: a.getAttribute('href'), text: (a.innerText||'').trim()}));
  const slugs = [...new Set(links.map(l => (l.href||'').split('/').filter(Boolean).pop()).filter(Boolean))];
  const lines = text.split(/\n/).map(l => l.trim()).filter(Boolean);
  const idx = lines.findIndex(l => /legacy|deprecated/i.test(l));
  const chunk = idx >= 0 ? lines.slice(idx, idx + 400) : lines.slice(-200);
  return { slugs, link_count: links.length, legacy_chunk: chunk, text_len: text.length };
}
"""


def main() -> None:
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8")).get("models", {})
        except Exception:
            prev = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print("overview...", flush=True)
        page.goto(OVERVIEW, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        ov = page.evaluate(OVERVIEW_JS)
        OVERVIEW_OUT.write_text(json.dumps(ov, ensure_ascii=False, indent=2), encoding="utf-8")
        slugs = ov.get("slugs") or []
        print(f"overview slugs={len(slugs)}", flush=True)
        for s in slugs:
            print(" ", s, flush=True)

        extra = [s for s in prev.keys() if s not in slugs]
        all_slugs = slugs + extra
        seen = set()
        ordered = []
        for s in all_slugs:
            if s not in seen:
                seen.add(s)
                ordered.append(s)

        results = {}
        errors = []
        for i, slug in enumerate(ordered, 1):
            url = BASE + slug
            print(f"[{i}/{len(ordered)}] {slug}", flush=True)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1400)
                data = page.evaluate(EXTRACT_JS)
                data["http_status"] = resp.status if resp else None
                results[slug] = data
                print(
                    f"  {data.get('h1')} code={data.get('primaryCode')} ctx={data.get('ctx_k')} "
                    f"in={data.get('input_price')} out={data.get('output_price')} "
                    f"dep={data.get('deprecation_date')} ret={data.get('retirement_date')} "
                    f"404={data.get('is404')}",
                    flush=True,
                )
            except Exception as e:
                errors.append({"slug": slug, "error": str(e)})
                print(f"  ERR {e}", flush=True)
            if i % 8 == 0:
                OUT.write_text(
                    json.dumps(
                        {
                            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "models": results,
                            "errors": errors,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        browser.close()

    payload = {
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(results),
        "models": results,
        "errors": errors,
        "overview_slugs": slugs,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} models={len(results)} errors={len(errors)}", flush=True)


if __name__ == "__main__":
    main()
