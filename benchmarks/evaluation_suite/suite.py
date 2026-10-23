"""One-folder, isolated Kaggle evaluation suite. No production API is started."""
from __future__ import annotations
import argparse,copy,csv,hashlib,json,os,subprocess,sys,threading,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
import yaml
from common import save,read,jsonl,sha,redact,detect_artifact

HERE=Path(__file__).resolve().parent
STAGES=('retrieval','ablation','zalo','vlsp')

def resolve(path,root):
    path=Path(path);return path.resolve() if path.is_absolute() else (root/path).resolve()

def remap(rows,store,fingerprint):
    """Version migration is not approval; changed builds always need re-review."""
    from vn_labor_online.retrieval import as_evidence,temporal_filter
    result=[];changes=[]
    for original in rows:
        row=copy.deepcopy(original);old=row.get('corpus_fingerprint')
        if old!=fingerprint:
            locators=row.get('required_group_locators')
            if not locators:raise ValueError('Changed build and no portable locators: '+row['id'])
            groups=[]
            for group in locators:
                candidates=[]
                for unit in store.units:
                    key={k:str(unit.get(k) or '') for k in ['article_number','clause_number','point_number','level']}
                    key['instrument_number']=str(unit.get('instrument_number') or unit.get('document_number') or '')
                    if any(all(key.get(k)==str(v) for k,v in locator.items()) for locator in group):candidates.append(unit)
                active,_=temporal_filter([as_evidence(u,1,'label_mapping',1) for u in candidates],row['query_date'],strict=False)
                ids=sorted({e.unit_id for e in active})
                if not ids:raise ValueError('Cannot resolve Gold locator: '+row['id'])
                groups.append(ids)
            row.update(required_groups=groups,corpus_fingerprint=fingerprint,review_status='DRAFT',
                reviewer=None,reviewed_at=None,migration='NEW_BUILD_REQUIRES_REVIEW')
            changes.append(row['id'])
        locators=[]
        for group in row['required_groups']:
            values=[]
            for uid in group:
                if uid not in store.units_by_id:raise ValueError('Unknown qrel '+uid)
                unit=store.units_by_id[uid]
                value={k:str(unit.get(k) or '') for k in ['article_number','clause_number','point_number','level']}
                value['instrument_number']=str(unit.get('instrument_number') or unit.get('document_number') or '')
                if value not in values:values.append(value)
            locators.append(values)
        row['required_group_locators']=locators;result.append(row)
    return result,changes

def source_manifest(project):
    paths=list((project/'src/vn_labor_online').glob('*.py'))+list(HERE.glob('*.py'))
    paths+=list(HERE.glob('*_notes.json'))
    return {str(p.relative_to(project)) if project in p.parents else p.name:sha(p) for p in sorted(paths)}

def prepare(output,settings,project):
    from vn_labor_online.config import OnlineConfig
    from vn_labor_online.artifact_store import ArtifactStore
    import labor_retrieval as labor
    artifact=detect_artifact(settings['input_root']) if settings['artifact']=='auto' else resolve(settings['artifact'],project)
    if not artifact.exists():raise FileNotFoundError('Artifact is absent')
    settings['artifact']=str(artifact)
    settings['cache']=str(resolve(settings.get('cache','.cache/evaluation_suite'),project))
    base=resolve(settings['base_config'],project)
    raw=yaml.safe_load(base.read_text(encoding='utf-8'));values=dict(raw.get('online',raw))
    values.update(artifact_source=str(artifact),cache_dir=settings['cache'],expected_archive_sha256=None,
        expected_build_id=None,expected_retrieval_unit_fingerprint=None,expected_dense_fingerprint=None)
    store=ArtifactStore(OnlineConfig.model_validate(values))
    report=store.report
    values.update(expected_archive_sha256=store.archive_sha256,expected_build_id=report.build_id,
        expected_retrieval_unit_fingerprint=report.retrieval_unit_fingerprint,expected_dense_fingerprint=report.dense_fingerprint,
        corpus_snapshot_as_of=report.corpus_snapshot_as_of,embedding_device=settings['device'])
    if 'reranker' in values:values['reranker']={**values['reranker'],'device':settings['device']}
    # Base YAML should not contain secrets; fail instead of writing them to output.
    if redact(values)!=values:raise ValueError('Remove API credentials from base YAML; use environment/secrets')
    (output/'online_pinned.yaml').write_text(yaml.safe_dump({'online':values},allow_unicode=True,sort_keys=False),encoding='utf-8')
    files=['06_indexes/retrieval_units.jsonl','05_graph/nodes.jsonl','05_graph/edges.jsonl']
    hashes={name:sha(store.path(name)) for name in files}
    import hashlib
    fp=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    source=settings.get('labor_gold')
    if source:
        source=resolve(source,project)
        if source.suffix.lower()=='.zip':
            from gold import import_candidate
            rows,validation=import_candidate(source,store,fp)
            save(output/'gold_import_validation.json',validation)
        else:
            rows=jsonl(source)
            if rows and 'question_id' in rows[0] and 'id' not in rows[0]:
                raise ValueError('Raw Gold JSONL has another schema: use original candidate ZIP, or portable labor_gold.jsonl exported by this suite')
    else:
        seed=output/'seed_generated.jsonl'
        labor.prepare(argparse.Namespace(artifact=str(artifact),cache=settings['cache'],device=settings['device'],date=settings['labor_seed_date'],gold=str(seed)))
        rows=jsonl(seed)
    rows,changes=remap(rows,store,fp);labor.validate_gold(rows,store,fp)
    from gold import select_rows
    all_rows=rows;rows=select_rows(rows,settings.get('labor_limit'))
    retrieval=[r for r in rows if r.get('retrieval_eligible',True)]
    if not retrieval:raise ValueError('No positive answerable retrieval questions selected')
    (output/'labor_gold.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    (output/'labor_retrieval_gold.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in retrieval),encoding='utf-8')
    save(output/'gold_selection.json',{'available_questions':len(all_rows),'selected_questions':len(rows),
        'selected_ids':[r['id'] for r in rows],'excluded_by_limit_ids':[r['id'] for r in all_rows if r not in rows],
        'retrieval_questions':len(retrieval),'retrieval_ids':[r['id'] for r in retrieval],
        'qa_only_ids':[r['id'] for r in rows if not r.get('retrieval_eligible',True)],
        'selection':'ALL' if settings.get('labor_limit') is None else 'STRATIFIED_SMOKE_NOT_ALL_GOLD'})
    save(output/'gold_migration.json',{'remapped_query_ids':changes,'needs_review':bool(changes) or any(r.get('review_status')!='APPROVED' for r in rows)})
    save(output/'compatibility.json',report.model_dump(mode='json'))
    return settings,fp

def archive_run(output):
    # Always include the run folder name: Path.with_suffix would collide for
    # arbitrary dotted output-directory names.
    archive=output.parent/(output.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(output))
    return archive

def retain_previous_attempt(output,stage):
    folders={'retrieval':['retrieval'],'ablation':['ablation'],'zalo':['zalo'],'vlsp':['vlsp','vlsp_qa']}[stage]
    for name in folders:
        source=(output/name).resolve()
        if not source.exists():continue
        destination=(output/'attempt_history'/(name+'_'+str(time.time_ns()))).resolve()
        if output.resolve() not in source.parents or output.resolve() not in destination.parents:raise ValueError('Unsafe attempt path')
        destination.parent.mkdir(parents=True,exist_ok=True)
        source.rename(destination)

def report(output):
    output=Path(output);status=read(output/'state.json');rows=[]
    for folder in ['ablation','vlsp_qa']:
        path=output/folder/'responses.jsonl'
        if path.exists():
            responses=jsonl(path)
            fields=['id','variant','repeat','question','query_date','expected_status','answer_status','status',
                'elapsed_ms','draft_disposition_match','gold_citation_group_recall','answer','reference_answer','error_type']
            with (path.parent/'answers.csv').open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(responses)
            text=['# Câu hỏi, câu trả lời và thời gian đo','', '> Nhãn DRAFT; tham khảo JSONL và trace để thẩm định nguồn.','']
            for r in responses:
                text += [f"## {r['id']} — {r['variant']} — lần {r['repeat']}",'',r['question'],'',
                    f"Thời gian: {r.get('elapsed_ms')} ms. Trạng thái: {r.get('answer_status',r['status'])}.",'',
                    r.get('answer') or r.get('error_type','Chưa có câu trả lời'),'',
                    '**Đáp án tham khảo (DRAFT):** '+str(r.get('reference_answer') or 'Xem nguồn trong JSONL'), '']
            (path.parent/'answers.md').write_text('\n'.join(text),encoding='utf-8')
    def add(section,variant,scope,labels,metrics):
        rows.append({'section':section,'variant':variant,'scope':scope,'labels':labels,**metrics})
    p=output/'retrieval/summary.json'
    if p.exists():
        data=read(p)
        for name,m in data['variants'].items():add('1 Labour retrieval',name,'retrieval; fixed graph',data['label_status'],m)
    for section,folder in [('2 Ablation','ablation'),('4 VLSP adapted QA','vlsp_qa')]:
        p=output/folder/'summary.json'
        if p.exists():
            data=read(p)
            for name,m in data['variants'].items():add(section,name,data['scope'],data['label_status'],m)
    p=output/'zalo/summary.json'
    if p.exists():
        data=read(p)
        for name,m in data['methods'].items():add('3 Zalo retrieval',name,data['scope'],'EXTERNAL_QRELS',m)
    fields=sorted({key for r in rows for key in r}) if rows else ['section','variant','scope','labels']
    with (output/'comparison_tables.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    lines=['# Bảng đánh giá Pháp Điển AI','',
      '> Bốn phép đo có phạm vi và nhãn khác nhau. Không gộp thành một “độ chính xác chung”.',
      '> AI-judge là điểm mô hình chấm, không phải chứng nhận pháp lý. N/A nghĩa là chưa đo/không áp dụng.',
      '', '| Nhóm | Trạng thái thực thi |', '|---|---|']
    for name in STAGES:lines.append(f"| {name} | {status['stages'].get(name,{}).get('status','NOT_RUN')} |")
    specs=[('1 Labour retrieval',['group_recall_at_k','mrr_at_k','group_ndcg_at_k','mean_ms','successful_attempts','errors']),
      ('2 Ablation',['ai_correctness','ai_completeness','ai_evidence_support','ai_judged','draft_disposition_match_rate','gold_citation_group_recall','content_answers','mean_ms','errors']),
      ('3 Zalo retrieval',['recall_at_k','precision_at_k','mrr_at_k','ndcg_at_k','elapsed_ms','attempts']),
      ('4 VLSP adapted QA',['ai_correctness','ai_completeness','ai_judged','content_answers','mean_ms','errors'])]
    for section,keys in specs:
        lines+=['','## '+section,'','| Cấu hình | Nhãn | '+' | '.join(keys)+' |','|---|---|'+'---:|'*len(keys)]
        subset=[r for r in rows if r['section']==section]
        for row in subset:
            def fmt(value):return 'N/A' if value is None else f'{value:.4f}' if isinstance(value,float) else str(value)
            lines.append('| '+row['variant']+' | '+row['labels']+' | '+' | '.join(fmt(row.get(k)) for k in keys)+' |')
        if not subset:lines.append('| Chưa có kết quả | NOT_EVALUATED | '+' | '.join('N/A' for _ in keys)+' |')
    lines+=['','Lưu ý khi đưa vào báo cáo:',
      '- Gold candidate 100 vẫn là DRAFT. Khớp trạng thái chỉ là nhãn tham khảo; không chứng minh câu trả lời đúng luật.',
      '- Xem gold_import_validation.json và gold_selection.json: 85 câu có đáp án để đo truy xuất, 100 câu để đo QA khi không giới hạn.',
      '- DRAFT/seed sáu câu chỉ kiểm tra công cụ, không đại diện chất lượng luật lao động.',
      '- Labour Graph là mở rộng cố định; ablation là pipeline đầy đủ có tắt từng thành phần trong tiến trình đo riêng.',
      '- Zalo chạy trên corpus riêng; không gộp điểm với corpus lao động.',
      '- VLSP là QA thích nghi, lọc từ khóa lao động và giả định ngày; không phải giao thức/bảng xếp hạng chính thức.',
      '- Đọc số lượt chấm AI, lỗi, câu có nội dung, câu từ chối và các trace trước khi diễn giải điểm.',
      '- Độ trễ QA không gồm thời gian AI judge; không phải thời gian frontend.',
      '- OFFLINE mới có thể làm Gold mất hiệu lực: migration luôn hạ về DRAFT, cần rà soát lại.']
    (output/'comparison_tables.md').write_text('\n'.join(lines),encoding='utf-8')
    save(output/'comparison_tables.json',{'stages':status['stages'],'rows':rows})

def worker(stage,output):
    settings=read(output/'settings_resolved.json')
    if stage=='retrieval':
        import labor_retrieval as labor
        return labor.run(argparse.Namespace(artifact=settings['artifact'],cache=settings['cache'],device=settings['device'],
          gold=str(output/'labor_retrieval_gold.jsonl'),out=str(output/'retrieval'),methods=settings['retrieval_methods'],
          repeats=settings['repeats'],k=settings['k']))
    if stage=='ablation':
        from qa import evaluate
        result=evaluate(output,settings)
        return 0 if result.get('complete') and all(v['errors']==0 for v in result['variants'].values()) else 1
    if stage=='zalo':
        from external import prepare_zalo,run_zalo
        prepare_zalo(output,settings);run_zalo(output,settings);return 0
    if stage=='vlsp':
        from external import prepare_vlsp
        from qa import evaluate
        prepare_vlsp(output,settings);result=evaluate(output,settings,vlsp=True)
        return 0 if result.get('complete') and result['variants']['full']['errors']==0 else 1
    raise ValueError(stage)

def execute(stage,output,timeout):
    log=output/'logs'/(stage+'.log');log.parent.mkdir(exist_ok=True)
    env=dict(os.environ);env['PYTHONUNBUFFERED']='1'
    # Do not let notebook deployment overrides silently select another artifact.
    env.pop('VN_LABOR_ARTIFACT_SOURCE',None)
    process=subprocess.Popen([sys.executable,'-u',str(HERE/'suite.py'),'_worker','--worker-stage',stage,'--output',str(output)],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,
        start_new_session=os.name!='nt')
    started=time.monotonic()
    with log.open('w',encoding='utf-8') as f:
        def drain():
            for line in process.stdout:
                f.write(line);f.flush();print(line.rstrip(),flush=True)
        reader=threading.Thread(target=drain,daemon=True);reader.start()
        try:
            while process.poll() is None:
                if time.monotonic()-started>timeout:raise TimeoutError(stage)
                remaining=timeout-(time.monotonic()-started)
                try:process.wait(timeout=max(.1,min(15,remaining)))
                except subprocess.TimeoutExpired:print(f'HEARTBEAT {stage} {int(time.monotonic()-started)}s',flush=True)
            reader.join(timeout=10)
        except BaseException:
            if process.poll() is None:
                if os.name!='nt':
                    import signal
                    os.killpg(process.pid,signal.SIGTERM)
                else:process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            reader.join(timeout=5);raise
    return process.returncode,time.monotonic()-started

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','prepare','report','_worker'])
    parser.add_argument('--settings',default=str(HERE/'settings.yaml'))
    parser.add_argument('--artifact');parser.add_argument('--device');parser.add_argument('--resume',action='store_true')
    parser.add_argument('--output',required=True);parser.add_argument('--project',default=str(HERE.parents[1]))
    parser.add_argument('--stages',nargs='+',choices=STAGES,default=list(STAGES))
    parser.add_argument('--worker-stage',choices=STAGES)
    args=parser.parse_args();output=Path(args.output).resolve();project=Path(args.project).resolve()
    if args.action=='report':report(output);return 0
    if args.action=='_worker':
        try:return worker(args.worker_stage,output)
        except Exception as exc:
            # Avoid printing raw provider exceptions with URLs/keys.
            import traceback
            frames=traceback.extract_tb(exc.__traceback__)
            print('STAGE_ERROR '+type(exc).__name__,flush=True)
            for frame in frames[-4:]:print(f'  {Path(frame.filename).name}:{frame.lineno} {frame.name}',flush=True)
            return 1
    if output.exists() and any(output.iterdir()) and not args.resume:raise FileExistsError('Use new output or --resume')
    output.mkdir(parents=True,exist_ok=True)
    settings=yaml.safe_load(Path(args.settings).read_text(encoding='utf-8'))
    if args.artifact:settings['artifact']=args.artifact
    if args.device:settings['device']=args.device
    if settings['repeats']<1 or settings['k']<1:raise ValueError('Positive repeats and k required')
    if type(settings.get('qa_repeats',settings['repeats'])) is not int or settings.get('qa_repeats',settings['repeats'])<1:raise ValueError('Positive qa_repeats required')
    methods=settings['retrieval_methods']
    if not methods or len(methods)!=len(set(methods)) or set(methods)-{'bm25','dense','hybrid','hybrid_graph'}:raise ValueError('Invalid retrieval methods')
    sources=source_manifest(project)
    if args.resume:
        previous=read(output/'settings_resolved.json')
        if read(output/'source_manifest.json')!=sources:raise ValueError('Code changed: start a new run, do not mix versions')
        old=read(output/'state.json');state=old
        frozen=read(output/'run_info.json')['frozen_files']
        old_gold_sha=read(output/'run_info.json').get('source_gold_sha256')
        if old_gold_sha and (not settings.get('labor_gold') or sha(resolve(settings['labor_gold'],project))!=old_gold_sha):
            raise ValueError('Source Gold changed: start a new run')
        if any(sha(output/name)!=value for name,value in frozen.items()):raise ValueError('Frozen run inputs were modified')
        # Resolve the input again; changing data cannot reuse completed stages.
        candidate=detect_artifact(settings['input_root']) if settings['artifact']=='auto' else resolve(settings['artifact'],project)
        if str(candidate.resolve())!=previous['artifact']:raise ValueError('Artifact path changed: new run required')
        settings['artifact']=previous['artifact'];settings['cache']=previous['cache']
        if settings!=previous:raise ValueError('Settings changed: start a new run')
        from vn_labor_online.artifact_store import ArtifactStore
        from vn_labor_online.config import OnlineConfig
        store=ArtifactStore(OnlineConfig.model_validate(yaml.safe_load((output/'online_pinned.yaml').read_text(encoding='utf-8'))['online']))
        if store.report.build_id!=read(output/'compatibility.json')['build_id']:raise ValueError('Artifact build changed')
        hashes={name:sha(store.path(name)) for name in ['06_indexes/retrieval_units.jsonl','05_graph/nodes.jsonl','05_graph/edges.jsonl']}
        fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
        if fingerprint!=read(output/'run_info.json')['corpus_fingerprint']:raise ValueError('Artifact content changed: start a new run')
        del store
    else:
        settings,fp=prepare(output,settings,project)
        save(output/'settings_resolved.json',settings);save(output/'source_manifest.json',sources)
        commit=subprocess.run(['git','rev-parse','HEAD'],cwd=project,capture_output=True,text=True)
        save(output/'run_info.json',{'commit':commit.stdout.strip() if commit.returncode==0 else None,
          'source_gold_sha256':sha(resolve(settings['labor_gold'],project)) if settings.get('labor_gold') else None,
          'corpus_fingerprint':fp,'started_at':datetime.now(timezone.utc).isoformat(),'python':sys.version,
          'frozen_files':{name:sha(output/name) for name in ['online_pinned.yaml','labor_gold.jsonl','labor_retrieval_gold.jsonl','gold_selection.json','settings_resolved.json']}})
        state={'stages':{}}
    save(output/'state.json',state)
    if args.action=='prepare':
        report(output);archive_run(output)
        print('PREPARATION_ONLY: no models/API evaluation was run',flush=True)
        return 0
    started=time.monotonic()
    try:
        for stage in args.stages:
            if args.resume and state['stages'].get(stage,{}).get('status')=='COMPLETE':continue
            if args.resume:retain_previous_attempt(output,stage)
            state['stages'][stage]={'status':'RUNNING'};save(output/'state.json',state)
            print('START '+stage,flush=True)
            try:
                remaining=settings['total_timeout_seconds']-(time.monotonic()-started)
                if remaining<=0:
                    state['stages'][stage]={'status':'NOT_RUN','reason':'TOTAL_BUDGET_EXHAUSTED'}
                    save(output/'state.json',state);break
                code,seconds=execute(stage,output,min(settings['stage_timeout_seconds'],remaining))
                state['stages'][stage]={'status':'COMPLETE' if code==0 else 'ERROR','exit_code':code,'seconds':seconds}
            except Exception as exc:state['stages'][stage]={'status':'ERROR','error_type':type(exc).__name__}
            save(output/'state.json',state);report(output)
    finally:
        report(output)
        archive=archive_run(output)
        print('REPORT '+str(output/'comparison_tables.md'),flush=True)
        print('ARCHIVE '+str(archive),flush=True)
    return 0 if all(state['stages'].get(s,{}).get('status')=='COMPLETE' for s in args.stages) else 1

if __name__=='__main__':sys.exit(main())
