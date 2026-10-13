"""Check OFFLINE structured inference before starting the long enrichment job."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from .ai_enrichment import provider_from_config,validate_structured
from .ai_requests import error_details
from .config import load_yaml,resolve_paths
from .integrity import _atomic
from .util import read_jsonl


def probe(cfg):
    provider=provider_from_config(cfg); rows=[]
    schema={'type':'object','additionalProperties':False,'properties':{'quote':{'type':'string'}},'required':['quote']}
    cases=list(read_jsonl(cfg['output_dir']/'03_structure/cases.jsonl'))
    real=next((c.get('facts','') for c in cases if c.get('facts')),None)
    if not real: raise ValueError('No real corpus case available for AI preflight')
    from .ai_requests import source_chunks
    source=next(source_chunks(real,int(cfg['knowledge'].get('ai_chunk_bytes',3500))))[1]
    quote=next((line.strip() for line in source.splitlines() if len(line.strip())>=20),source[:80])
    try:
        for label,context in [('short',quote),('bounded_real_case',source)]:
            started=time.monotonic()
            try:
                response=provider.structured('Copy requested_quote verbatim from source. Return only schema JSON.',
                    json.dumps({'source':context,'requested_quote':quote},ensure_ascii=False),schema)
                validate_structured(response,schema)
                if response['quote']!=quote: raise ValueError('AI_PREFLIGHT_QUOTE_MISMATCH')
                rows.append({'probe':label,'passed':True,'elapsed_seconds':round(time.monotonic()-started,3),
                    'input_bytes':len(context.encode('utf-8'))})
            except Exception as exc:
                rows.append({'probe':label,'passed':False,'elapsed_seconds':round(time.monotonic()-started,3),**error_details(exc)})
                break
    finally:
        close=getattr(provider,'close',None)
        if callable(close): close()
    result={'schema_version':1,'passed':len(rows)==2 and all(r['passed'] for r in rows),
        'probes':rows,'note':'Connectivity/schema/latency smoke only; does not certify full corpus accuracy.'}
    _atomic(cfg['output_dir']/'reports/ai_provider_preflight.json',result)
    print('AI_PREFLIGHT '+json.dumps(result,ensure_ascii=False),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--config',default='config/kaggle.yaml')
    args=parser.parse_args(); path=Path(args.config); return 0 if probe(resolve_paths(load_yaml(path),path))['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
