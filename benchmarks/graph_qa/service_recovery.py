"""One opt-in, journaled recovery per query pair after explicit provider outages.

Never retry a legal refusal, quota, unknown transport result, or Ollama timeout.
The initial pair and every additional cost remain in the immutable journal.
"""
from pathlib import Path
import time
from protocol import Lock,append,load,write,code_hashes,settings

SERVICE_CODES={'GEMINI_HTTP_500','GEMINI_HTTP_502','GEMINI_HTTP_503','GEMINI_HTTP_504'}

def service_failure(record):
    response=record.get('response') or {}
    if record.get('status')!='OK' or response.get('status')!='INSUFFICIENT_EVIDENCE':return False
    if 'review_service_unavailable' not in response.get('limitations',[]):return False
    steps=(response.get('trace') or {}).get('execution_steps') or []
    codes={s.get('output',{}).get('ma_loi') for s in steps if s.get('status')=='ERROR'
           and s.get('step') in {'model_call','semantic_review'}}
    if codes & {'GEMINI_HTTP_429','OLLAMA_TIMEOUT','GEMINI_TIMEOUT'}:return False
    final_reviews=[step for step in steps if step.get('status')=='ERROR' and step.get('step')=='semantic_review']
    return bool(final_reviews and final_reviews[-1].get('output',{}).get('ma_loi') in SERVICE_CODES)

def recover_services(args,runner):
    run=Path(args.run);s=settings(args.settings)
    with Lock(run):
        if not s['service_recovery_enabled']:raise ValueError('Service recovery was not enabled in frozen settings')
        manifest,jobs=runner.freeze_run(run,s,load(run/'run_manifest.json')['profile'])
        pf=load(run/'preflight.json')
        if pf['settings']!=s or pf['code_sha256']!=code_hashes():raise ValueError('Preflight stale')
        by_key={runner.key(r):r for r in runner.recover_records(run)}
        if set(by_key)!={runner.key(j) for j in jobs}:raise ValueError('Complete the initial paired schedule before service recovery')
        if any(runner.quota_error(r) for r in by_key.values()):raise RuntimeError('Quota failure: service recovery cannot bypass it')
        marker=run/'service_recovery.json';ledger=load(marker) if marker.exists() else {}
        pairs={}
        for job in jobs:pairs.setdefault((job['id'],job['repeat']),[]).append(job)
        worker=None
        try:
            for (qid,repeat),pair in pairs.items():
                token=qid+':'+str(repeat)
                state=ledger.get(token)
                if state is None:
                    if not any(service_failure(by_key[runner.key(j)]) for j in pair):continue
                    # Persist intent BEFORE either arm. A crash never grants a
                    # fresh automatic recovery attempt on a later invocation.
                    state={'status':'STARTED','attempted_arms':[]}
                    ledger[token]=state;write(marker,ledger)
                if state['status']=='DONE':continue
                for job in pair:
                    old=by_key[runner.key(job)]
                    if old.get('service_recovery_pair')==token:continue
                    if job['arm'] in state['attempted_arms'] or (run/'inflight.json').exists():
                        raise RuntimeError('Recovery outcome uncertain: inspect checkpoint; no blind resubmission')
                    if worker is None:
                        worker=runner.Worker(run,run/'worker_state.json')
                        expected=manifest.get('runtime',pf['runtime'])
                        if worker.meta['pins']!=expected['pins'] or worker.meta['environment']!=expected['environment']:
                            raise ValueError('Runtime changed; new run required')
                    state['attempted_arms'].append(job['arm']);write(marker,ledger)
                    write(run/'inflight.json',{**job,'service_recovery_pair':token})
                    started=time.perf_counter()
                    print('Service recovery',qid,job['arm'],'once per pair',flush=True)
                    try:
                        value=worker.ask(job,s['request_timeout_seconds']+15)
                        if value.get('kind')!='answer':raise ValueError('Unexpected worker message')
                        record={**job,**{k:v for k,v in value.items() if k!='kind'}}
                    except Exception as exc:
                        record={**job,'status':'TIMEOUT' if isinstance(exc,TimeoutError) else 'ERROR','error':runner.safe_error(exc)}
                        worker.close();worker=None
                    record['controller_round_trip_ms']=(time.perf_counter()-started)*1000
                    record.setdefault('elapsed_ms',record['controller_round_trip_ms'])
                    record['service_recovery_pair']=token
                    append(run/'retry_history.jsonl',old)
                    append(run/'attempt_journal.jsonl',record)
                    by_key[runner.key(job)]=record;runner.save_records(run,list(by_key.values()))
                    (run/'inflight.json').unlink(missing_ok=True)
                    if record['status']=='TIMEOUT' or 'OLLAMA_TIMEOUT' in runner.canonical(record):
                        raise RuntimeError('Inference timeout: checkpoint saved; stop before overlapping inference')
                    if runner.quota_error(record):raise RuntimeError('Quota exhausted: recovery stopped; no rotation or further retry')
                    if record['status']!='OK':raise RuntimeError('Recovery worker failed: checkpoint saved; inspect owned inference before resume')
                state['status']='DONE';write(marker,ledger)
        finally:
            if worker:worker.close()
            runner.make_report(run)
