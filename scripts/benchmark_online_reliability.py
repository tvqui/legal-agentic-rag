"""Authenticated benchmark connection; never print credential values."""
from pathlib import Path
import argparse,json,os,re,statistics,time,urllib.request,urllib.error,urllib.parse
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]

def read_env(path):
    values={}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line: continue
            key,value=line.split('=',1); values[key.strip()]=value.strip().strip('"\'')
    return values

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class Connection:
    def __init__(self):
        root=read_env(ROOT/'.env'); frontend=read_env(ROOT/'frontend/.env')
        self.target=frontend.get('VITE_BACKEND_TARGET','').rstrip('/')
        parsed=urllib.parse.urlsplit(self.target)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise ValueError('Configure an HTTPS backend target in frontend/.env without credentials in the URL')
        self.host=parsed.hostname
        self.token=frontend.get('BACKEND_PROXY_TOKEN') or root.get('VN_LABOR_API_KEY') or ''
        self.opener=urllib.request.build_opener(NoRedirect())
    def request(self,path,body=None,timeout=30,extra_headers=None):
        headers={'Accept':'application/json','ngrok-skip-browser-warning':'true'}
        if self.token: headers['Authorization']='Bearer '+self.token
        headers.update(extra_headers or {})
        data=None
        if body is not None:
            headers['Content-Type']='application/json'; data=json.dumps(body,ensure_ascii=False).encode('utf-8')
        started=time.monotonic()
        try:
            with self.opener.open(urllib.request.Request(self.target+path,data=data,headers=headers),timeout=timeout) as response:
                status=response.status; payload=response.read().decode('utf-8',errors='replace')
        except urllib.error.HTTPError as exc:
            status=exc.code; payload=exc.read().decode('utf-8',errors='replace')
        except Exception as exc:
            return {'http_status':None,'elapsed_seconds':round(time.monotonic()-started,3),'network_error':type(exc).__name__}
        try: content=json.loads(payload)
        except json.JSONDecodeError: content={'non_json_response':True,'body_excerpt':payload[:500]}
        if not isinstance(content,dict): content={'invalid_json_response_type':type(content).__name__}
        if self.token:
            content=json.loads(json.dumps(content,ensure_ascii=False).replace(self.token,'[REDACTED]'))
        return {'http_status':status,'elapsed_seconds':round(time.monotonic()-started,3),'body':content}

def preflight(connection,out):
    health=[connection.request('/health',timeout=20) for _ in range(3)]
    ready=connection.request('/ready',timeout=60)
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'target_host':connection.host,
      'health':health,'readiness':ready,
      'health_median_seconds':statistics.median(x['elapsed_seconds'] for x in health),
      'frontend_required':False,'credentials_printed':False}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    body=ready.get('body') or {}
    print(json.dumps({'report':str(out),'host':connection.host,
      'health_http':[x['http_status'] for x in health],
      'health_seconds':[x['elapsed_seconds'] for x in health],
      'ready_http':ready['http_status'],'ready':body.get('ready'),
      'components':body.get('components'),'online_features':body.get('online_features'),
      'quality_policy':body.get('quality_policy'),
      'build_id':body.get('compatibility',{}).get('build_id')},ensure_ascii=False))
    return result


from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,secrets,time


QUESTIONS=[
 'Điều 1 Nghị định 145/2020/NĐ-CP quy định gì? Hãy trình bày đầy đủ phạm vi điều chỉnh và dẫn nguồn chính thức.',
 'Ngày 15/12/2020, người lao động làm theo hợp đồng không xác định thời hạn muốn đơn phương nghỉ việc vì lý do cá nhân. Khi đó phải đáp ứng điều kiện gì và báo trước bao lâu? Nêu Điều, Khoản, Điểm có hiệu lực tại ngày này, không dùng quy định bắt đầu có hiệu lực từ năm 2021.',
 'Tôi ký hợp đồng lao động không xác định thời hạn, dự kiến nghỉ ngày 30/09/2026 và chỉ báo trước 20 ngày. Tôi không làm công việc đặc thù, không thuộc trường hợp được nghỉ không cần báo trước và công ty chưa đồng ý cho nghỉ sớm. Việc nghỉ như vậy có đúng không? Tôi có thể phải chịu hậu quả gì? Dẫn Điều, Khoản và nguồn chính thức.',
 'Tôi thử việc cho công việc yêu cầu trình độ cao đẳng. Công ty yêu cầu thử việc 90 ngày và trả 80% mức lương của công việc đó. Hãy đánh giá riêng thời gian thử việc và tiền lương, nêu căn cứ cho từng phần.',
 'Nếu hết thời gian đó mà công ty yêu cầu tôi thử việc thêm một lần nữa cho chính công việc ấy thì có được không?',
]

def plan(question_file=None):
    if question_file is not None:
        rows=json.loads(Path(question_file).read_text(encoding='utf-8-sig'))
        if not isinstance(rows,list) or not rows or any(not isinstance(row,dict) or not row.get('id') or not str(row.get('question','')).strip() for row in rows):
            raise ValueError('Question file must contain a nonempty list of question objects with id and question')
        if len({row['id'] for row in rows})!=len(rows): raise ValueError('Duplicate question IDs')
        return rows
    rows=[{'id':f'USER-{i}','question':q,'batch':'USER_5','origin':'USER_QUESTION'} for i,q in enumerate(QUESTIONS,1)]
    rows+=json.loads((ROOT/'artifacts/online_benchmarks/labor_285_v4_20261009T124602Z.questions.json').read_text(encoding='utf-8-sig'))
    assert len(rows)==290 and len({row['id'] for row in rows})==290
    return rows

def run(folder,ids,timeout,resume,question_file=None):
    folder.mkdir(parents=True,exist_ok=True)
    rows=plan(question_file)
    selected=[row for row in rows if not ids or row['id'] in ids]
    planned_path=folder/'questions.json'
    if planned_path.exists() and (folder/'responses.jsonl').exists():
        saved=json.loads(planned_path.read_text(encoding='utf-8-sig'))
        if saved!=selected: raise ValueError('Question plan changed; use a new output folder')
    planned_path.write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
    result_path=folder/'responses.jsonl'
    existing=[json.loads(line) for line in result_path.read_text(encoding='utf-8').splitlines() if line.strip()] if result_path.exists() else []
    if ids-set(row['id'] for row in rows): raise ValueError('Unknown requested question ID')
    if existing and not resume: raise ValueError('Result exists; choose --resume or a new output folder')
    done={row['id'] for row in existing}
    connection=Connection(); capability=secrets.token_hex(32)
    headers={'X-Client-Session':capability}
    print(json.dumps({'stage':'start','selected':len(selected),'already_completed':len(done),'host':connection.host}),flush=True)
    for row in selected:
        if row['id'] in done: continue
        message_id='bench_'+secrets.token_hex(12)
        history=[]
        if row.get('conversation_turns') is not None:
            history=row['conversation_turns']
        elif row.get('batch')=='USER_5':
            index=int(row['id'].split('-')[1])-1
            history=[{'turn_id':f'user_{i}','role':'user','content':q} for i,q in enumerate(QUESTIONS[:index],1)]
        body={'question':row['question'],'conversation_turns':history,
          'conversation_id':'reliability_user5' if history else 'bench_'+secrets.token_hex(8),'message_id':message_id}
        if row.get('query_date'): body['query_date']=row['query_date']
        if row.get('facts'): body['facts']=row['facts']
        started=time.monotonic(); progress=[]; started_at=datetime.now(timezone.utc).isoformat()
        print(json.dumps({'stage':'question','id':row['id'],'question':row['question']},ensure_ascii=False),flush=True)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future=executor.submit(connection.request,'/v1/answer',body,timeout,headers)
            last_poll=0
            while not future.done():
                if time.monotonic()-last_poll>=15:
                    event=connection.request('/v1/requests/'+message_id,timeout=10,extra_headers=headers)
                    value=event.get('body') or {}
                    if event['http_status']==200:
                        progress.append({'elapsed_seconds':round(time.monotonic()-started,2),**value})
                        print(json.dumps({'stage':'progress','id':row['id'],'elapsed_seconds':round(time.monotonic()-started,1),'backend_stage':value.get('stage'),'state':value.get('state')}),flush=True)
                    last_poll=time.monotonic()
                time.sleep(.5)
            response=future.result()
        if response.get('network_error'):
            connection.request('/v1/requests/'+message_id+'/cancel',{},timeout=10,extra_headers=headers)
        value=response.get('body') or {}; trace=value.get('trace') or {}
        record={'id':row['id'],'question':row['question'],'batch':row.get('batch'),
          'started_at':started_at,'finished_at':datetime.now(timezone.utc).isoformat(),'request':body,
          'http_status':response['http_status'],'elapsed_seconds':response['elapsed_seconds'],
          'network_error':response.get('network_error'),'response':value,'progress':progress,
          'quality_review':'PENDING_INDEPENDENT_REVIEW'}
        with result_path.open('a',encoding='utf-8') as stream: stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        print(json.dumps({'stage':'result','id':row['id'],'http':response['http_status'],'seconds':response['elapsed_seconds'],
          'status':value.get('status'),'citations':len(value.get('citations') or []),
          'error_category':value.get('category'),'error_id':value.get('error_id'),
          'trace_id':value.get('trace_id'),'timings_ms':trace.get('timings_ms'),
          'warnings':value.get('warnings')},ensure_ascii=False),flush=True)
        # Avoid hammering a backend that is no longer available.
        if response['http_status'] is None or response['http_status'] in {401,403,429,502,503,504}:
            print(json.dumps({'stage':'paused','reason':'SERVICE_OR_TRANSPORT_FAILURE','id':row['id']}),flush=True)
            return False
        provider_codes=[str(e.get('error_code','')) for e in trace.get('events',[]) if e.get('event')=='semantic_answer_audit']
        provider_codes+=value.get('warnings') or []
        if any('GEMINI_HTTP_429' in code for code in provider_codes):
            print(json.dumps({'stage':'paused','reason':'PROVIDER_RATE_LIMIT','id':row['id']}),flush=True)
            return False
    return True


from pathlib import Path
import collections,csv,json,math,statistics

def export(folder):
    rows=[json.loads(line) for line in (folder/'responses.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    fields=['id','batch','question','elapsed_seconds','http_status','answer_status','citation_count','answer','limitations','questions','warnings','trace_id','server_total_ms','quality_review']
    with (folder/'responses.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for row in rows:
            body=row.get('response') or {}; trace=body.get('trace') or {}
            writer.writerow({'id':row['id'],'batch':row.get('batch'),'question':row['question'],
              'elapsed_seconds':row['elapsed_seconds'],'http_status':row['http_status'],'answer_status':body.get('status'),
              'citation_count':len(body.get('citations') or []),'answer':body.get('answer',body.get('message','')),
              'limitations':json.dumps(body.get('limitations',[]),ensure_ascii=False),
              'questions':json.dumps(body.get('questions',[]),ensure_ascii=False),
              'warnings':json.dumps(body.get('warnings',[]),ensure_ascii=False),
              'trace_id':body.get('trace_id'),'server_total_ms':trace.get('timings_ms',{}).get('total'),
              'quality_review':row.get('quality_review','PENDING_INDEPENDENT_REVIEW')})
    success=[row['elapsed_seconds'] for row in rows if row['http_status']==200]
    answer_times=sorted(row['elapsed_seconds'] for row in rows if row['http_status']==200 and row.get('response',{}).get('status') in {'SUFFICIENT','PARTIAL_ALLOWED'})
    planned=json.loads((folder/'questions.json').read_text(encoding='utf-8-sig'))
    summary={'attempted':len(rows),'http_statuses':dict(collections.Counter(str(r['http_status']) for r in rows)),
      'planned':len(planned),'remaining':len({r['id'] for r in planned}-{r['id'] for r in rows}),
      'answer_statuses':dict(collections.Counter(str((r.get('response')or{}).get('status')) for r in rows)),
      'http_200_p50_seconds':statistics.median(success) if success else None,
      'answers_only_p50_seconds':statistics.median(answer_times) if answer_times else None,
      'answers_only_p95_seconds':answer_times[max(0,math.ceil(len(answer_times)*.95)-1)] if answer_times else None,
      'sum_request_seconds':round(sum(r['elapsed_seconds'] for r in rows),3),
      'legal_accuracy':'NOT_CERTIFIED_NO_APPROVED_GOLD','note':'HTTP 200 and citation count are not correctness or completeness.'}
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Kết quả chạy ONLINE thực tế','',
      'Thời gian là thời gian HTTP đo trực tiếp. Trạng thái kỹ thuật không chứng nhận nội dung đúng luật. Trace đầy đủ được giữ trong responses.jsonl.','',
      '| ID | Giây | HTTP | Trạng thái | Citation |','|---|---:|---:|---|---:|']
    for row in rows:
        body=row.get('response') or {}
        lines.append(f"| {row['id']} | {row['elapsed_seconds']:.3f} | {row['http_status']} | {body.get('status')} | {len(body.get('citations')or[])} |")
    for row in rows:
        body=row.get('response') or {}
        lines+=['',f"## {row['id']}",'',row['question'],'',
          f"Thời gian: {row['elapsed_seconds']:.3f} giây; HTTP: {row['http_status']}; trạng thái: {body.get('status')}; trace: {body.get('trace_id','không có')}.",'',
          body.get('answer',body.get('message','Không nhận được câu trả lời hợp lệ.')),'']
        for citation in body.get('citations')or[]:
            label=' · '.join(str(citation[k]) for k in ('document_number','article','clause','point') if citation.get(k))
            lines.append(f"- {label}: {citation.get('official_url') or 'Chưa có URL'} ({citation.get('evidence_id')})")
        if body.get('questions'): lines+=['','Cần bổ sung: '+'; '.join(body['questions'])]
        if body.get('limitations'): lines+=['','Giới hạn: '+', '.join(body['limitations'])]
        if body.get('warnings'): lines+=['','Cảnh báo: '+'; '.join(body['warnings'])]
        lines+=['','Đánh giá pháp lý độc lập: chưa hoàn tất.']
    (folder/'responses.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary



def main():
    parser=argparse.ArgumentParser(description='Sequential Kaggle benchmark, resumable results, no frontend or credential printing.')
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts/online_benchmarks/reliability_20261020/candidate')
    parser.add_argument('--ids',nargs='*'); parser.add_argument('--resume',action='store_true')
    parser.add_argument('--questions',type=Path,help='Optional reviewed question plan JSON; keeps the default 290-question plan unchanged')
    parser.add_argument('--timeout',type=int,default=230)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--require-fixed-backend',action='store_true')
    parser.add_argument('--require-reviewer',choices=['gemini','same'])
    parser.add_argument('--require-taxonomy',help='Require the exact deployed taxonomy version before submitting answers')
    parser.add_argument('--require-feature',action='append',default=[],metavar='KEY=VALUE')
    parser.add_argument('--list',action='store_true')
    args=parser.parse_args()
    if args.list:
        print(json.dumps({'total':len(plan(args.questions)),'rows':[{'id':row['id'],'question':row['question']} for row in plan(args.questions)]},ensure_ascii=False,indent=2)); return 0
    initial=args.out/'preflight.json'
    previous=json.loads(initial.read_text(encoding='utf-8')) if initial.exists() else None
    checked=preflight(Connection(),args.out/'preflight_latest.json')
    ready=checked['readiness'].get('body') or {}
    if checked['readiness']['http_status']!=200 or ready.get('ready') is not True:
        print('Backend is not ready; no answer requests were submitted.'); return 2
    features=ready.get('online_features') or {}
    for expected in args.require_feature:
        if '=' not in expected: parser.error('--require-feature must use KEY=VALUE')
        key,value=expected.split('=',1)
        if not key or not value: parser.error('--require-feature must use nonempty KEY=VALUE')
        if features.get(key)!=value:
            print('Backend feature not deployed: '+key+'; no answer requests were submitted.'); return 2
    if args.require_fixed_backend and (features.get('conversation_context')!='user-turns-v2-short-history' or features.get('literal_source_lookup')!='verified-excerpt-v1'):
        print('Backend has not deployed the verified fix; no answer requests were submitted.'); return 2
    if args.require_reviewer and (ready.get('quality_policy') or {}).get('semantic_review_provider')!=args.require_reviewer:
        print('Backend reviewer differs from the requested comparison; no answer requests were submitted.'); return 2
    if args.require_taxonomy and ready.get('taxonomy_version')!=args.require_taxonomy:
        print('Backend taxonomy differs from the required deployment; no answer requests were submitted.'); return 2
    def signature(report):
        body=report.get('readiness',{}).get('body') or {}
        return {'build':body.get('compatibility',{}).get('build_id'),'taxonomy':body.get('taxonomy_version'),'features':body.get('online_features'),
          'policy':body.get('quality_policy'),
          'models':{key:{k:value.get(k) for k in ('provider','model')} for key,value in (body.get('components') or {}).items() if isinstance(value,dict)}}
    if (args.out/'responses.jsonl').exists() and (previous is None or signature(previous)!=signature(checked)):
        print('Backend deployment changed or initial preflight is missing. Use a new output folder to avoid mixing versions.'); return 2
    if previous is None or not (args.out/'responses.jsonl').exists():
        initial.write_text(json.dumps(checked,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.preflight_only: return 0
    try:
        completed=run(args.out,set(args.ids or []),args.timeout,args.resume,args.questions)
    finally:
        if (args.out/'responses.jsonl').exists():
            print(json.dumps({'summary':export(args.out)},ensure_ascii=False),flush=True)
    return 0 if completed else 3

if __name__=='__main__': raise SystemExit(main())
