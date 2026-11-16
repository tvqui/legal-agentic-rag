"""Bounded recovery of saved infrastructure errors; never retry legal verdicts."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

TRANSIENT_CODES = tuple(prefix+suffix for prefix in ('OLLAMA','GEMINI','HTTP_JSON')
    for suffix in ('_TIMEOUT','_CONNECTION_ERROR','_HTTP_500','_HTTP_502','_HTTP_503','_HTTP_504')) + ('COMPONENT_TIME_BUDGET_EXHAUSTED',)
BLOCKING_CODES = {'GEMINI_HTTP_429','GEMINI_HTTP_400','GEMINI_HTTP_401','GEMINI_HTTP_403','GEMINI_HTTP_404'}

def policy(rounds=2, delay=10):
    if type(rounds) is not int or not 0<=rounds<=3:
        raise ValueError('AUTO_RETRY_ROUNDS must be an integer from 0 to 3')
    if type(delay) not in (int,float) or not 0<=delay<=60:
        raise ValueError('RETRY_BACKOFF_SECONDS must be between 0 and 60')
    return {'version':'saved-errors-v1','max_rounds':rounds,'backoff_seconds':delay,
            'retry_codes':list(TRANSIENT_CODES),'preserve_first_pass':True}

def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []

def dump(path, value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(path)

def error_for(row, stage):
    if stage=='generation':return (row.get('error') or {}) if row.get('status')=='ERROR' else None
    judgment=row.get('judge',{})
    return judgment.get('error',{}) if row.get('status')=='OK' and judgment.get('status')=='ERROR' else None

def retry_failed(run, command, invoke, initial_result, *, stage='generation',
                 max_rounds=2, backoff_seconds=10, before_retry=None):
    frozen=policy(max_rounds,backoff_seconds)
    if stage not in {'generation','judge'}:raise ValueError('Invalid retry stage')
    run=Path(run);records_file=run/'responses.jsonl'
    if not run.exists():return initial_result
    state_file=run/f'{stage}_retry_state.json'
    state=read(state_file,{'policy':frozen,'rounds_started':0,'events':[]})
    if state['policy']!=frozen:raise ValueError('Retry policy changed; use a new run')
    result=initial_result
    def refresh():
        records=rows(records_file);failed=[]
        for r in records:
            error=error_for(r,stage)
            if error is None:continue
            code=error.get('error_code')
            failed.append({'id':r['id'],'method':r['method'],'repeat':r['repeat'],
                'question':r.get('question'),'error':error,'retryable':code in TRANSIENT_CODES})
        dump(run/('failed_questions.json' if stage=='generation' else 'failed_judgments.json'),failed)
        if stage=='generation':
            history=rows(run/'attempt_history.jsonl')
            dump(run/'retry_costs.json',{'note':'Generation elapsed includes original failed attempts; startup/backoff is separate in retry state.',
                'all_attempts':len(history)+len(records),
                'total_generation_ms':sum(r.get('elapsed_ms',0) for r in history+records),
                'final_saved_attempts':len(records),'historical_failed_attempts':len(history),
                'first_pass_file':'first_pass_generation.jsonl'})
        return records,failed
    lock=run/'.retry_controller.lock'
    try:lock_fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        raise RuntimeError('A retry controller already owns this run; inspect its process before removing a stale lock') from None
    os.write(lock_fd,json.dumps({'pid':os.getpid(),'stage':stage}).encode())
    try:
        while True:
            records,failed=refresh()
            progress=read(run/('progress.json' if stage=='generation' else 'judge_progress.json'),{})
            scheduled=(type(progress.get('expected')) is int and progress['expected']>0
                and progress.get('saved')==progress['expected']) if stage=='generation' else bool(records)
            first=run/f'first_pass_{stage}.jsonl'
            if scheduled and records and not first.exists():shutil.copyfile(records_file,first)
            if not scheduled or progress.get('paused'):
                state['stop_reason']='PAUSED_OR_INCOMPLETE_SCHEDULE';break
            if result.returncode not in (0,2):
                state['stop_reason']='FATAL_EXIT';break
            if any(f['error'].get('error_code') in BLOCKING_CODES for f in failed):
                state['stop_reason']='QUOTA_OR_CONFIGURATION';break
            pending=[f for f in failed if f['retryable']]
            if not pending:
                state['stop_reason']='NO_RETRYABLE_ERRORS';break
            if state['rounds_started']>=max_rounds:
                state['stop_reason']='RETRY_LIMIT';break
            if before_retry:
                try:before_retry(pending)
                except Exception as exc:
                    state['stop_reason']='RETRY_PRECHECK_FAILED'
                    state['precheck_error_type']=type(exc).__name__
                    print('Retry deferred; keep failed list and checkpoint:',type(exc).__name__,flush=True)
                    break
            elif any(f['error'].get('error_code')=='OLLAMA_TIMEOUT' for f in pending):
                state['stop_reason']='OWNED_OLLAMA_RESTART_REQUIRED';break
            state['rounds_started']+=1
            event={'round':state['rounds_started'],'pending':[{k:f[k] for k in ('id','method','repeat')} for f in pending]}
            state['events'].append(event);dump(state_file,state)
            print(stage,'retry round',event['round'],'pending',len(pending),flush=True)
            started=time.monotonic()
            time.sleep(backoff_seconds)
            args=[str(v) for v in command if str(v) not in {'--resume','--retry-errors'}]
            if stage=='generation':args+=['--resume','--retry-errors']
            args+=['--retry-error-codes',*TRANSIENT_CODES]
            if stage=='judge':
                keys={(f['id'],f['method'],f['repeat']) for f in pending}
                with (run/'judge_attempt_history.jsonl').open('a',encoding='utf-8') as log:
                    for row in records:
                        if (row['id'],row['method'],row['repeat']) in keys:
                            log.write(json.dumps({k:row.get(k) for k in ('id','method','repeat','judge','judge_ms')},ensure_ascii=False)+'\n')
            result=invoke(args)
            event['wall_ms']=(time.monotonic()-started)*1000
            event['exit']=result.returncode
            dump(state_file,state)
    finally:
        try:
            refresh();dump(state_file,state)
        finally:
            os.close(lock_fd);lock.unlink()
    return result

def restart_owned_ollama(scope, failed):
    """Restart only the notebook's owned server before retrying ambiguous timeouts."""
    if not any(f['error'].get('error_code')=='OLLAMA_TIMEOUT' for f in failed):return
    process=scope.get('OWN_OLLAMA');log=scope.get('OLLAMA_LOG')
    if process is None or log is None or log.closed:
        raise RuntimeError('No owned Ollama server; restart the session before retrying timeouts')
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=10)
    environment=dict(os.environ);environment['CUDA_VISIBLE_DEVICES']='1'
    scope['OWN_OLLAMA']=subprocess.Popen(['ollama','serve'],env=environment,stdout=log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+120
    while True:
        if scope['OWN_OLLAMA'].poll() is not None:raise RuntimeError('Owned Ollama exited')
        try:
            with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3):break
        except Exception:
            if time.monotonic()>=deadline:raise RuntimeError('Ollama restart deadline exceeded') from None
            time.sleep(1)
    body={'model':'qwen3:8b','stream':False,'think':False,'keep_alive':'15m',
        'format':{'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready']},
        'options':{'temperature':0,'num_ctx':32768,'num_predict':32},
        'messages':[{'role':'user','content':'Return a JSON object with ready equal to true.'}]}
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as response:reply=json.load(response)
    if not reply.get('done') or reply.get('done_reason')=='length' or json.loads(reply.get('message',{}).get('content','{}'))!={'ready':True}:
        raise RuntimeError('Ollama retry warmup failed; no generation retry was submitted')
