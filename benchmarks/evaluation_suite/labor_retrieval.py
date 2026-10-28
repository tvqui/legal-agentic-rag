"""Reproducible retrieval-only comparison; no generative API calls."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,statistics,sys,time
from datetime import date,datetime,timezone
from pathlib import Path

METHODS=('bm25','dense','hybrid','hybrid_rerank','hybrid_graph','hybrid_graph_rerank')
from protocol import VERSION,DEFAULT_KS,context_metrics,validate_annotation,query_macro,bootstrap_ci,paired_delta

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def load_rows(path):
    rows=[json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    ids=[r['id'] for r in rows]
    if not rows or len(ids)!=len(set(ids)): raise ValueError('Empty Gold or duplicate query IDs')
    return rows

def validate_gold(rows,store,fingerprint):
    for row in rows:
        if row.get('corpus_fingerprint')!=fingerprint: raise ValueError('Gold/corpus mismatch: '+row['id'])
        if not row.get('question') or not row.get('query_date'):raise ValueError('Missing question/date')
        date.fromisoformat(row['query_date'])
        groups=row.get('required_groups')
        if not groups or any(not group for group in groups):raise ValueError('Missing qrels: '+row['id'])
        flat=[uid for group in groups for uid in group]
        if set(flat)-set(store.units_by_id):raise ValueError('Unknown evidence ID: '+row['id'])
        if len(flat)!=len(set(flat)):raise ValueError('Overlapping relevance groups: '+row['id'])

def metrics(ids,groups,k):
    """Each requirement has interchangeable evidence IDs; duplicates add no gain."""
    seen=set();gains=[];first=None
    mapping={uid:i for i,group in enumerate(groups) for uid in group}
    for rank,uid in enumerate(ids[:k],1):
        group=mapping.get(uid);hit=group is not None and group not in seen
        gains.append(int(hit))
        if hit:
            seen.add(group)
            if first is None:first=rank
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(groups))))
    dcg=sum(gain/math.log2(i+2) for i,gain in enumerate(gains))
    return {'group_recall_at_k':len(seen)/len(groups),
      'novel_group_precision_at_k':len(seen)/k,'mrr_at_k':1/first if first else 0,
      'group_ndcg_at_k':dcg/ideal if ideal else 0,'all_groups_found':len(seen)==len(groups)}

def runtime(artifact,cache,device):
    from vn_labor_online.config import OnlineConfig
    from vn_labor_online.artifact_store import ArtifactStore
    from vn_labor_online.retrieval import Retriever
    cfg=OnlineConfig(artifact_source=str(Path(artifact).resolve()),cache_dir=str(Path(cache).resolve()),
        embedding_device=device,embedding_use_fp16=device!='cpu')
    cfg.retrieval.profile_fast_path=False;cfg.retrieval.exact_lookup=False
    cfg.retrieval.issue_anchor_enabled=False;cfg.retrieval.case_law_enabled=False
    cfg.retrieval.community_enabled=False;cfg.reranker.enabled=False
    cfg.retrieval.bm25_top_k=30;cfg.retrieval.dense_top_k=30;cfg.retrieval.fusion_top_k=60
    # Fixed graph isolates structural expansion, not the full adaptive/LLM pipeline.
    cfg.graph.mode='fixed';cfg.graph.max_hops=2;cfg.graph.max_rounds=2
    cfg.graph.max_nodes=50;cfg.graph.max_edges=150;cfg.graph.wall_clock_ms=1500
    print('LOAD_ARTIFACT: kiểm tra và nạp dữ liệu, chưa tải embedding model',flush=True)
    store=ArtifactStore(cfg)
    files=['06_indexes/retrieval_units.jsonl','05_graph/nodes.jsonl','05_graph/edges.jsonl']
    hashes={name:digest(store.path(name)) for name in files}
    fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return cfg,store,Retriever(store,cfg),fingerprint,hashes

def prepare(args):
    date.fromisoformat(args.date)
    cfg,store,retriever,fp,hashes=runtime(args.artifact,args.cache,args.device)
    specs=[
      ('retain_degree','Công ty có được giữ bản chính bằng tốt nghiệp của người lao động để bảo đảm làm việc không?', [('17','1','')]),
      ('annual_leave','Người lao động 30 tuổi, không khuyết tật, làm đủ 12 tháng trong điều kiện bình thường được nghỉ hằng năm hưởng lương bao nhiêu ngày?', [('113','1','a')]),
      ('two_independent_tasks','Tôi 30 tuổi, không khuyết tật, làm đủ 12 tháng trong điều kiện bình thường. Công ty giữ bản chính bằng tốt nghiệp và chỉ cho tổng cộng 6 ngày phép năm có lương. Hãy đánh giá riêng việc giữ bằng và số ngày nghỉ phép.', [('17','1',''),('113','1','a')]),
      ('probation_duration_wage','Công việc yêu cầu trình độ cao đẳng. Công ty yêu cầu thử việc 90 ngày, trả 80% lương công việc. Đánh giá riêng thời hạn và tiền lương thử việc.', [('25','2',''),('26','','')]),
      ('employee_notice_consequences','Hợp đồng không xác định thời hạn, công việc không đặc thù, không thuộc ngoại lệ nghỉ ngay, công ty không đồng ý nghỉ sớm. Tôi báo trước 20 ngày rồi nghỉ. Thời hạn báo trước và hậu quả pháp lý là gì?', [('35','1','a'),('39','',''),('40','1',''),('40','2',''),('40','3','')]),
      ('personal_leave','Người lao động kết hôn được nghỉ việc riêng hưởng lương bao nhiêu ngày và có phải thông báo cho công ty không?', [('115','1','a')]),
    ]
    from vn_labor_online.retrieval import as_evidence,temporal_filter
    rows=[]
    for uid,question,locators in specs:
        groups=[]
        for article,clause,point in locators:
            units=[u for u in store.units if (u.get('instrument_number') or u.get('document_number'))=='45/2019/QH14'
              and str(u.get('article_number') or '')==article
              and str(u.get('clause_number') or '')==clause and str(u.get('point_number') or '')==point]
            active,_=temporal_filter([as_evidence(u,1,'gold_candidate',1) for u in units],args.date,strict=False)
            group=[e.unit_id for e in active]
            if not group:raise ValueError('Cannot resolve seed locator: '+str((article,clause,point)))
            groups.append(group)
        rows.append({'id':uid,'question':question,'query_date':args.date,'required_groups':groups,
            'review_status':'DRAFT','reviewer':None,'reviewed_at':None,'corpus_fingerprint':fp,
            'note':'Minimal seed qrels resolved by locator, NOT human-approved or exhaustive legal support.'})
    out=Path(args.gold)
    if out.exists():raise FileExistsError('Refusing to overwrite Gold: '+str(out))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    print(json.dumps({'gold':str(out),'queries':len(rows),'status':'DRAFT_SMOKE_ONLY','corpus_fingerprint':fp},ensure_ascii=False))

def retrieve(method,row,retriever,graph,cfg):
    from vn_labor_online.retrieval import temporal_filter,authority_filter
    query=row['question'];channels=[]
    if method=='bm25' or method.startswith('hybrid'):channels.append(retriever.bm25(query))
    if method=='dense' or method.startswith('hybrid'):channels.append(retriever.dense(query))
    items=channels[0] if len(channels)==1 else retriever.fusion(channels)
    def filter_items(values):
        values,_=temporal_filter(values,row['query_date'],strict=False)
        values,_=authority_filter(values,strict=False)
        return values
    items=filter_items(items);stats={}
    if method.startswith('hybrid_graph'):
        seeds=items[:5]
        added,stats=graph.expand(seeds,[],query)
        items=retriever.fusion([items,filter_items(added)]) if added else items
        stats['new_candidate_ids']=[e.unit_id for e in added]
    if method.endswith('_rerank'):
        cfg.reranker.enabled=True
        items=retriever.neural_rerank(items,query)
    return items,stats

def summarize(output,manifest,records):
    report={**manifest,'variants':{}}
    for method in manifest['methods']:
        rows=[r for r in records if r['method']==method];good=[r for r in rows if r['status']=='OK']
        values=[r['elapsed_ms'] for r in good]
        summary={'attempts':len(rows),'successful_attempts':len(good),'errors':len(rows)-len(good)}
        for key in ['group_recall_at_k','novel_group_precision_at_k','mrr_at_k','group_ndcg_at_k','all_groups_found']:
            summary[key]=statistics.mean(query_macro(good,lambda r:r['metrics'][key]).values()) if good else None
        for key,fn in [('min_ms',min),('max_ms',max),('mean_ms',statistics.mean),('median_ms',statistics.median)]:
            summary[key]=fn(values) if values else None
        summary['p95_ms']=sorted(values)[math.ceil(.95*len(values))-1] if values else None
        report['variants'][method]=summary
    report['complete']=len(records)==manifest['queries']*manifest['repeats']*len(manifest['methods'])
    report['all_attempts_succeeded']=report['complete'] and all(r['status']=='OK' for r in records)
    cutoffs=manifest.get('cutoffs',[manifest.get('k',10)])
    multi={}
    def interval(values):
        values=list(values)
        if report['complete']:return bootstrap_ci(values)
        return {'mean':statistics.mean(values) if values else None,'n_queries':len(values),'ci95_low':None,'ci95_high':None}
    for method in manifest['methods']:
        good=[r for r in records if r['method']==method and r['status']=='OK']
        report['variants'][method]['unique_queries']=len({r['id'] for r in good})
        report['variants'][method]['context_annotation_queries']=len({r['id'] for r in good if r.get('context',{}).get('fact_coverage') is not None})
        for key in ('context_units','context_chars','estimated_context_tokens','fact_coverage','evidence_precision'):
            vals=query_macro(good,lambda r:r.get('context',{}).get(key))
            report['variants'][method][key]=statistics.mean(vals.values()) if vals else None
        multi[method]={}
        for k in cutoffs:
            multi[method][str(k)]={key:interval(query_macro(good,lambda r:r.get('metrics_by_k',{}).get(str(k),r.get('metrics',{}) if k==manifest.get('k') else {}).get(key)).values())
                for key in ('group_recall_at_k','novel_group_precision_at_k','mrr_at_k','group_ndcg_at_k','all_groups_found')}
        report['variants'][method]['recall_query_ci95']=multi[method].get(str(manifest.get('k',10)),{}).get('group_recall_at_k')
    report['metrics_by_k']=multi
    report['paired_deltas_vs_hybrid']={method:paired_delta(records,method,'hybrid',lambda r:r.get('metrics',{}).get('group_recall_at_k'),'method')
        for method in manifest['methods'] if method!='hybrid'} if report['complete'] and 'hybrid' in manifest['methods'] else {}
    write(output/'summary.json',report)
    lines=['# So sánh truy xuất','',f"Trạng thái nhãn: {manifest['label_status']}",
       'Phạm vi: chỉ truy xuất; không chấm độ đúng pháp lý của câu trả lời.','',
       '| Phương pháp | Lượt OK/tổng | Recall nhóm@k | MRR@k | nDCG nhóm@k | Trung bình ms | p95 ms |',
       '|---|---:|---:|---:|---:|---:|---:|']
    for method,s in report['variants'].items():
        fmt=lambda v:f'{v:.4f}' if v is not None else 'N/A'
        lines.append(f"| {method} | {s['successful_attempts']}/{s['attempts']} | "+' | '.join(fmt(s[k]) for k in ['group_recall_at_k','mrr_at_k','group_ndcg_at_k','mean_ms','p95_ms'])+' |')
    lines+=['','Lỗi được ghi riêng trong responses.jsonl; không được che bằng trung bình các lượt thành công.',
       'Kết quả seed DRAFT chỉ là smoke test; không dùng chọn phương pháp thắng hoặc công bố chính xác.']
    (output/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    with (output/'per_question.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['id','question','method','repeat','status','elapsed_ms','group_recall_at_k','mrr_at_k','group_ndcg_at_k','error']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in records:writer.writerow({k:v for k,v in {**row,**row.get('metrics',{})}.items() if k in fields})
    return report

def sync_device(device):
    if str(device).startswith('cuda'):
        import torch
        torch.cuda.synchronize(device)


def pin_models(cfg,store,methods,cache):
    from huggingface_hub import HfApi,snapshot_download
    pins={}
    if any(m!='bm25' for m in methods):
        repo=store.dense_report.get('model') or cfg.embedding_model
        revision=store.dense_report.get('model_revision')
        if not revision:raise ValueError('Dense artifact missing model_revision; cannot ensure matching embeddings')
        cfg.embedding_model=repo
        cfg.embedding_model_path=snapshot_download(repo,revision=revision,cache_dir=str(Path(cache)/'model_pins'))
        pins['embedding']={'repo':repo,'revision':revision}
    if any(m.endswith('_rerank') for m in methods):
        repo=cfg.reranker.model
        from external import pin_model_revision
        revision=pin_model_revision(repo,cache)
        cfg.reranker.model_path=snapshot_download(repo,revision=revision,cache_dir=str(Path(cache)/'model_pins'))
        cfg.reranker.device=cfg.embedding_device;cfg.reranker.use_fp16=cfg.embedding_use_fp16
        cfg.reranker.top_n=60
        pins['reranker']={'repo':repo,'revision':revision}
    return pins


def run(args):
    cfg,store,retriever,fp,hashes=runtime(args.artifact,args.cache,args.device)
    gold=load_rows(args.gold);validate_gold(gold,store,fp)
    ks=sorted(set(getattr(args,'ks',None) or [args.k]))
    if args.k not in ks:ks.append(args.k);ks.sort()
    if min(ks)<1 or max(ks)>30:raise ValueError('Cutoffs must be 1..30 within fixed candidate pool')
    annotations={}
    annotation_path=getattr(args,'evidence_annotations',None)
    if annotation_path:
        for annotation in load_rows(annotation_path):
            validate_annotation(annotation,store.units_by_id,fp)
            annotations[annotation['id']]=annotation
        if set(annotations)-{r['id'] for r in gold}:raise ValueError('Evidence annotations contain unknown query IDs')

    from vn_labor_online.graph import GraphExplorer
    from vn_labor_online.runtime import request_budget
    graph=GraphExplorer(store,cfg.graph)
    out=Path(args.out)
    if out.exists() and any(out.iterdir()):raise FileExistsError('Use an empty output folder')
    out.mkdir(parents=True,exist_ok=True)
    approved=all(r.get('review_status')=='APPROVED' and r.get('reviewer') and r.get('reviewed_at') for r in gold)
    manifest={'label_status':'REVIEWED_LABELS' if approved else 'PROVISIONAL_DRAFT_GOLD',
        'scope':'retrieval_only_optional_cross_encoder_no_llm_no_gold_at_inference',
        'protocol_version':VERSION,'cutoffs':ks,
        'annotation_queries':len(annotations),'annotation_status':'PARTIAL' if annotations and len(annotations)<len(gold) else 'AVAILABLE' if annotations else 'NOT_ANNOTATED',
        'token_estimator':'ceil(sum(context_source_chars)/4); NOT tokenizer tokens',
        'methods':args.methods,'queries':len(gold),'repeats':args.repeats,'k':args.k,
        'corpus_fingerprint':fp,'file_hashes':hashes,'archive_sha256':store.archive_sha256,
        'gold_sha256':digest(args.gold),'runner_sha256':digest(__file__),
        'compatibility':store.report.model_dump(mode='json'),
        'device':args.device,'config':cfg.model_dump(mode='json'),
        'graph_protocol':'fixed 2 hops; first 5 eligible hybrid seeds; RRF union; same temporal/authority filters',
        'warmup':{},'created_at':datetime.now(timezone.utc).isoformat()}
    import vn_labor_online,importlib.metadata
    source_root=Path(vn_labor_online.__file__).parent
    manifest['online_source_hashes']={p.name:digest(p) for p in sorted(source_root.glob('*.py'))}
    manifest['python']=sys.version
    manifest['dependencies']={}
    for name in ['bm25s','numpy','faiss-cpu','faiss-gpu','FlagEmbedding','torch']:
        try:manifest['dependencies'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    manifest['model_pins']=pin_models(cfg,store,args.methods,args.cache)
    records=[];write(out/'manifest.json',manifest)
    try:
        # Warm up every selected variant; errors stop, never silently drop Dense.
        for method in args.methods:
            started=time.perf_counter()
            print('WARMUP '+method,flush=True)
            with request_budget(600):retrieve(method,gold[0],retriever,graph,cfg)
            manifest['warmup'][method]={'elapsed_ms':(time.perf_counter()-started)*1000}
            write(out/'manifest.json',manifest)
        with (out/'responses.jsonl').open('w',encoding='utf-8') as f:
            for repeat in range(args.repeats):
                for index,row in enumerate(gold):
                    # Rotate method order to reduce persistent order bias.
                    offset=(repeat+index)%len(args.methods)
                    order=args.methods[offset:]+args.methods[:offset]
                    for method in order:
                        result={'id':row['id'],'question':row['question'],'query_date':row['query_date'],
                            'method':method,'repeat':repeat+1,'status':'OK'}
                        sync_device(args.device)
                        started=time.perf_counter()
                        try:
                            with request_budget(180):items,stats=retrieve(method,row,retriever,graph,cfg)
                            sync_device(args.device)
                            result['elapsed_ms']=round((time.perf_counter()-started)*1000,3)
                            ids=[item.unit_id for item in items[:args.k]]
                            result.update(candidate_ids=[item.unit_id for item in items[:max(ks)]],graph_stats=stats,
                                metrics=metrics(ids,row['required_groups'],args.k),
                                metrics_by_k={str(k):metrics([item.unit_id for item in items[:k]],row['required_groups'],k) for k in ks},
                                context=context_metrics([store.units_by_id[uid] for uid in ids],annotations.get(row['id'])))
                            sync_device(args.device)
                        except Exception as exc:
                            result.update(status='ERROR',error=type(exc).__name__+': '+str(exc))
                        result.setdefault('elapsed_ms',round((time.perf_counter()-started)*1000,3))
                        records.append(result);f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush()
                        print(f"{len(records)} {row['id']} {method} {result['status']} {result['elapsed_ms']} ms",flush=True)
                        summarize(out,manifest,records)
    except Exception as exc:
        manifest['fatal_error']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        write(out/'manifest.json',manifest);summarize(out,manifest,records)
    return 0 if all(r['status']=='OK' for r in records) else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--artifact',required=True)
    parser.add_argument('--gold',required=True)
    parser.add_argument('--cache',default='.cache/retrieval_comparison')
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--date',default='2026-10-23')
    parser.add_argument('--out',default='artifacts/retrieval_comparison/run')
    parser.add_argument('--methods',nargs='+',choices=METHODS,default=list(METHODS))
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--k',type=int,default=10)
    parser.add_argument('--ks',nargs='+',type=int)
    parser.add_argument('--evidence-annotations')
    args=parser.parse_args()
    if args.repeats<1 or args.k<1 or len(args.methods)!=len(set(args.methods)):parser.error('Positive k/repeats and unique methods required')
    return prepare(args) if args.action=='prepare' else run(args)

if __name__=='__main__':sys.exit(main())
