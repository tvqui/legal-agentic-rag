"""Check external dataset access/schema before spending hours on LLM evaluation."""
import argparse,json
from pathlib import Path
import yaml
from external import prepare_zalo,prepare_vlsp
from common import read,save
from protocol import safe_failure

def check(settings,output,stages):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);result={}
    for name,func in [('zalo',prepare_zalo),('vlsp',prepare_vlsp)]:
        if name not in stages:continue
        print('DATASET_PREFLIGHT '+name,flush=True)
        try:
            func(output,settings);source=read(output/name/'source.json')
            result[name]={'status':'PASS',**{k:v for k,v in source.items() if k in {'revision','queries','corpus','selected','eligible','total','subset','split'}}}
        except Exception as exc:result[name]={'status':'ERROR',**safe_failure(exc)}
        print(json.dumps({name:result[name]}),flush=True)
    save(output/'external_preflight.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--settings',required=True);p.add_argument('--output',required=True)
    p.add_argument('--stages',nargs='+',default=['zalo','vlsp'])
    a=p.parse_args();result=check(yaml.safe_load(Path(a.settings).read_text(encoding='utf-8')),a.output,a.stages)
    raise SystemExit(0 if all(r['status']=='PASS' for r in result.values()) else 1)
