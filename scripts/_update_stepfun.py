"""Refresh StepFun models from StepFun's official pricing documentation."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'src/llmcapa/data/stepfun.json'
INSTALLED=Path(r'F:\Python314\Lib\site-packages\llmcapa\data\stepfun.json')
LOG=ROOT/'provider_update_log.md'
SOURCE='https://platform.stepfun.ai/docs/en/guides/pricing/details'
RULES={
 'stepfun/step-3.5-flash': {'input':0.10,'output':0.30,'context':262144,'max_output':65536},
 'stepfun/step-3.7-flash': {'input':0.20,'output':1.15,'context':262144,'max_output':256000},
}

def main():
 req=Request(SOURCE,headers={'User-Agent':'llmcapa-official-updater/1.0'})
 with urlopen(req,timeout=30) as r:
  text=r.read(300000).decode('utf-8','ignore')
 if 'step-3.7-flash' not in text or 'step-3.5-flash' not in text:
  raise RuntimeError('StepFun official pricing page validation failed')
 data=json.loads(DATA.read_text(encoding='utf-8')); today=date.today().isoformat(); updated=0
 for m in data.get('models',[]):
  rule=RULES.get(m.get('model_id'))
  if not rule: continue
  m.update({'context_window':rule['context'],'max_output_tokens':rule['max_output'],'pricing':{'input_per_1m':rule['input'],'output_per_1m':rule['output'],'currency':'USD'}})
  ex=m.setdefault('extra',{}); ex.update({'official_source':SOURCE,'official_source_checked_at':today,'official_spec_refresh':'parsed'})
  updated+=1
 DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 INSTALLED.parent.mkdir(parents=True,exist_ok=True); INSTALLED.write_text(DATA.read_text(encoding='utf-8'),encoding='utf-8')
 LOG.write_text(LOG.read_text(encoding='utf-8')+f'\n## StepFun official refresh ({today})\n\n- Source: {SOURCE}\n- Updated: {updated} models (Step 3.5 Flash and Step 3.7 Flash).\n- OpenRouter was not used.\n',encoding='utf-8')
 print(f'stepfun.json: official_models_updated={updated}')

if __name__=='__main__': main()
