"""Update endpoint metadata for the xai provider only."""
import json
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"src/llmcapa/data/xai.json"
LOG=ROOT/"provider_update_log.md"
BASE_URL='https://api.x.ai/v1'
SOURCE='https://docs.x.ai/docs'
def main():
 data=json.loads(DATA.read_text(encoding="utf-8")); n=0
 for model in data.get("models",[]):
  model.setdefault("extra",{})["endpoints"]=[{"base_url":BASE_URL,"protocol":"openai-compatible","auth":"bearer","source":SOURCE}]; n+=1
 DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 LOG.write_text(LOG.read_text(encoding="utf-8")+f"\n## xai endpoint metadata refresh ({date.today()})\n\n- Source: {SOURCE}\n- Updated: {n} models.\n",encoding="utf-8")
 print("xai: endpoint metadata updated",n)
if __name__=="__main__": main()
