"""Resume V8.1 artifacts and run bounded, cached OFFLINE AI enrichment."""
from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def configure(config:Path):
    import yaml
    raw=yaml.safe_load(config.read_text(encoding='utf-8'))
    knowledge=raw.setdefault('knowledge',{})
    knowledge.update({'checklist_mode':'hybrid_ai','case_ontology_mode':'ai',
      'ai_provider':os.getenv('VN_LABOR_OFFLINE_AI_PROVIDER','ollama'),
      'ai_url':os.getenv('VN_LABOR_OFFLINE_AI_URL','http://127.0.0.1:11434/api/chat'),
      'ai_model':os.getenv('VN_LABOR_OFFLINE_AI_MODEL','qwen3:8b'),
      'ai_timeout_seconds':int(os.getenv('VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS','300'))})
    config.write_text(yaml.safe_dump(raw,allow_unicode=True,sort_keys=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config',default='config/kaggle.yaml')
    parser.add_argument('--load-aura',action='store_true'); args=parser.parse_args(); config=ROOT/args.config
    if not (ROOT/'artifacts/03_structure/provisions.jsonl').exists():
        raise RuntimeError('Restore the V8.1 checkpoint before enrichment')
    configure(config)
    subprocess.run([sys.executable,'-m','vn_labor_offline.cli','enrich','--config',str(config),'--mode','hybrid_ai'],cwd=ROOT,check=True)
    if args.load_aura: subprocess.run([sys.executable,'kaggle/remote.py','aura'],cwd=ROOT,check=True)
    else: subprocess.run([sys.executable,'kaggle/remote.py','audit'],cwd=ROOT,check=False)
    report={'mode':'hybrid_ai','case_ontology':'ai','aura_loaded':args.load_aura}
    (ROOT/'artifacts/reports/offline_ai_enrichment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    subprocess.run([sys.executable,'kaggle/remote.py','export'],cwd=ROOT,check=True)
if __name__=='__main__': main()
