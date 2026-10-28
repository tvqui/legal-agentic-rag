"""Inspect an existing evaluation archive, without model calls or Gold leakage.

This is a DRAFT-qrels diagnostic, not a legal accuracy score. Candidate IDs in
the trace can be truncated, and an audit PASS is not expert legal approval.
"""
from pathlib import Path
from collections import Counter
from zipfile import ZipFile
import argparse,json,hashlib

def hit(ids,groups):
    found=set(ids)
    return {'any':any(found.intersection(g) for g in groups),
            'all':bool(groups) and all(found.intersection(g) for g in groups)}

def diagnose(archive,variant='full'):
    archive=Path(archive)
    with ZipFile(archive) as z:
        gold={r['id']:r for r in (json.loads(line) for line in z.read('labor_retrieval_gold.jsonl').decode('utf-8-sig').splitlines() if line.strip())}
        records=[json.loads(line) for line in z.read('ablation/responses.jsonl').decode('utf-8-sig').splitlines() if line.strip()]
        names=set(z.namelist());stage_counts={name:Counter() for name in ['seed_candidates_in_trace','auditor_any_pass','selected','public_citations']}
        reasons=Counter();states=Counter();errors=Counter();blocked=[];per_query=[];missing_trace=[];technical=0;eligible=0
        for row in records:
            if row.get('variant')!=variant:continue
            states[row.get('answer_status') or row.get('status','UNKNOWN')]+=1
            if row.get('status')!='OK':technical+=1
            tid=row.get('trace_id');path=f'ablation/traces/{variant}/{tid}.json'
            if path not in names:
                if row.get('id') in gold: missing_trace.append(row['id'])
                continue
            trace=json.loads(z.read(path))
            decisions=[d for event in trace.get('events',[]) if event.get('event')=='applicability_audit' for d in event.get('decisions',[])]
            for d in decisions:reasons.update(d.get('reasons',[]))
            for event in trace.get('events',[]):
                if event.get('event')=='semantic_answer_audit' and event.get('error_code'):errors[event['error_code']]+=1
            if row.get('id') not in gold:continue
            groups=gold[row['id']].get('required_groups',[])
            if not groups:continue
            eligible+=1
            selection=[event for event in trace.get('events',[]) if event.get('event')=='selection']
            stages={
              'seed_candidates_in_trace':[x['unit_id'] for x in trace.get('retrieval_candidates',[])],
              'auditor_any_pass':[d['evidence_id'] for d in decisions if d.get('audit_status')=='PASS'],
              'selected':selection[-1].get('evidence_ids',[]) if selection else [],
              'public_citations':[c['evidence_id'] for c in row.get('citations',[])],
            }
            results={name:hit(ids,groups) for name,ids in stages.items()}
            for name,result in results.items():stage_counts[name].update({k:int(v) for k,v in result.items()})
            if results['selected']['any'] and row.get('answer_status')=='INSUFFICIENT_EVIDENCE':blocked.append(row['id'])
            per_query.append({'id':row['id'],'answer_status':row.get('answer_status'),'matches':results})
        configs={}
        cfg_path=f'ablation/{variant}_config.json'
        if cfg_path in names:
            cfg=json.loads(z.read(cfg_path))
            configs={name:{key:cfg.get(name,{}).get(key) for key in ('mode','provider','model','review_provider','review_model') if key in cfg.get(name,{})} for name in ('researcher','applicability','adjudication')}
        return {'schema_version':1,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'variant':variant,
          'scope':'DRAFT qrels; groups matched by ID, not legal correctness; historical snapshot only',
          'gold_questions':len(gold),'eligible_with_trace':eligible,'technical_errors_all_questions':technical,
          'eligible_missing_trace_ids':missing_trace,'statuses_all_questions':dict(states),
          'stage_matches':{k:dict(v) for k,v in stage_counts.items()},'decision_reason_occurrences':dict(reasons),
          'review_error_occurrences':dict(errors),'selected_any_gold_but_blocked':blocked,'configuration':configs,
          'definitions':{'any':'At least one required group has an ID present.','all':'Every required group has an ID present.',
             'auditor_any_pass':'A PASS anywhere in recorded decisions; not necessarily the final selection.',
             'seed_candidates_in_trace':'Only recorded candidate IDs, possibly truncated; not the full retrieval universe.',
             'errors':'Missing/failed calls do not receive invented zero scores; see counts and denominators.'},
          'per_query':per_query}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--variant',default='full');p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    report=diagnose(a.archive,a.variant);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    compact={k:v for k,v in report.items() if k not in {'per_query','decision_reason_occurrences','definitions'}}
    print(json.dumps(compact,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
