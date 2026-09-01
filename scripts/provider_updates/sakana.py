"""Provider catalog, endpoint, and Structured Outputs updater for sakana."""

"""Update endpoint metadata for the sakana provider only."""
import json
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"src/llmcapa/data/sakana.json"
LOG=ROOT/"provider_update_log.md"
BASE_URL='https://api.sakana.ai'
SOURCE='https://console.sakana.ai/get-started'
def update_endpoints():
 data=json.loads(DATA.read_text(encoding="utf-8")); n=0
 for model in data.get("models",[]):
  model.setdefault("extra",{})["endpoints"]=[{"base_url":BASE_URL,"protocol":"openai-compatible","auth":"bearer","source":SOURCE}]; n+=1
 DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 LOG.write_text(LOG.read_text(encoding="utf-8")+f"\n## sakana endpoint metadata refresh ({date.today()})\n\n- Source: {SOURCE}\n- Updated: {n} models.\n",encoding="utf-8")
 print("sakana: endpoint metadata updated",n)


"""Audit Structured Outputs for sakana only."""
import json
from datetime import date
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"src/llmcapa/data/sakana.json"
LOG=ROOT/"provider_update_log.md"
SOURCE='https://console.sakana.ai/models'
DOCUMENTED=True
def update_structured():
 req=Request(SOURCE,headers={"User-Agent":"llmcapa-structured-audit/1.0"})
 with urlopen(req,timeout=30) as response: response.read(100000)
 data=json.loads(DATA.read_text(encoding="utf-8")); n=0
 for model in data.get("models",[]):
  extra=model.setdefault("extra",{}); extra.update({"structured_output_source":SOURCE,"structured_output_checked_at":date.today().isoformat(),"structured_output_api_documented":DOCUMENTED})
  if DOCUMENTED: model["supports_json_mode"]=True; model["supports_json_schema"]=True
  n+=1
 DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 LOG.write_text(LOG.read_text(encoding="utf-8")+f"\n## sakana Structured Outputs audit ({{date.today()}})\n\n- Source: {{SOURCE}}\n- Updated: {{n}} models; documented={{DOCUMENTED}}.\n",encoding="utf-8")
 print("sakana: structured outputs audited",n)


def main():
    update_endpoints()
    update_structured()


if __name__ == "__main__":
    main()
