from __future__ import annotations
import hashlib, json, os, pickle, re, time
from pathlib import Path
import numpy as np
from .util import write_jsonl
from .provenance import _align_segment, _document_offset


def build_retrieval_units(provisions: list[dict], cases: list[dict], registry: list[dict], segments=None,
                          source_catalog=None, extracted=None) -> list[dict]:
    children=set(p["parent_id"] for p in provisions)
    docs={d["document_id"]:d for d in registry}
    catalog={r['file_id']:r for r in source_catalog or []}
    sources={r['file_id']:r for r in extracted or []}
    by_id={p['provision_id']:p for p in provisions}
    def metadata(d):
        result={k:d.get(k) for k in ('source_url','sha256','legal_status','binding','version_id','version_role','instrument_id','instrument_number',
            'issuer','authority_rank','language','provenance','temporal_verified','effective_from','effective_to','valid_from','valid_to',
            'consolidation_as_of','promulgated_date')}
        source=catalog.get(d.get('file_id'),{})
        result.update({"source_catalog_status":source.get('catalog_status','UNVERIFIED'),
                       "source_provider":source.get('source_provider'),"collected_at":source.get('collected_at'),
                       "official_source":source.get('official_source',False)})
        return result
    units=[]
    # Leaf provisions are the natural retrieval units; metadata keeps full hierarchy.
    for p in provisions:
        # Ancestors contain their own introductory rules, not duplicated descendant text.
        # Keep meaningful own text even when a provision also has children.
        d=docs.get(p["document_id"],{})
        ancestors=[]; current=p; seen=set()
        while current and current['provision_id'] not in seen:
            seen.add(current['provision_id']); ancestors.append(current)
            current=by_id.get(current.get('parent_id'))
        ancestors.reverse()
        labels={'ARTICLE':'Điều','CLAUSE':'Khoản','POINT':'Điểm'}
        chapter=next((a.get('chapter') for a in ancestors if a.get('chapter')),'')
        section=next((a.get('section') for a in ancestors if a.get('section')),'')
        breadcrumb=' > '.join([str(d.get('title','')),str(d.get('instrument_number') or d.get('document_number',''))]+([f'Chương {chapter}'] if chapter else [])+([f'Mục {section}'] if section else [])+
            [f"{labels.get(a['level'],a['level'])} {a['number']}"+(f" — {a['heading']}" if a.get('heading') else '') for a in ancestors])
        ancestor_text='\n'.join(a.get('text','')[:1500] for a in ancestors[:-1])
        units.append({
            **metadata(d),"unit_id":p["provision_id"], "kind":"PROVISION", "text":breadcrumb+'\n'+ancestor_text+'\n'+p.get("text",""),
            'ancestor_context':ancestor_text,
            'source_text':p.get('text',''),'breadcrumb':breadcrumb,'segment_type':p.get('segment_type','MAIN_BODY'),
            'provenance_span':{k:p.get(k) for k in ('segment_id','char_start','char_end','line_start','line_end',
                'span_scope','coordinate_space','segment_char_start','segment_char_end',
                'document_char_start','document_char_end','page_start','page_end','page_status','source_unit_type')},
            'chapter':chapter,'section':section,
            'article_number':p.get('article_number',''),'clause_number':p.get('clause_number',''),'point_number':p.get('point_number',''),
            "document_id":p["document_id"], "level":p["level"], "number":p["number"],
            "document_version_id":p.get("source_document_version_id") or p["document_id"],
            "provision_identity_id":p.get("provision_identity_id"),
            "provision_version_id":p.get("provision_version_id") or p["provision_id"],
            "temporal_status":p.get("temporal_status","UNKNOWN"),
            "provision_temporal_verified":p.get("provision_temporal_verified",False),
            "temporal_coverage_as_of":p.get("temporal_coverage_as_of"),
            "valid_from":p.get("valid_from") or None,"valid_to":p.get("valid_to") or None,
            "provenance_status":p.get("provenance_status","UNRESOLVED"),
            "document_number":d.get("document_number",""), "document_title":d.get("title",""),
            "effective_from":d.get("effective_from",""), "effective_to":d.get("effective_to",""),
        })
    for c in cases:
        d=docs.get(c['document_id'],{})
        source=sources.get(d.get('file_id'),{})
        document_text=source.get('text','')
        page_count=len(source.get('page_provenance',[]))
        units.append({
            **metadata(d),"unit_id":c["case_id"], "kind":"CASE", "text":c.get("search_text","")[:30000],
            'breadcrumb':c.get('case_number') or c['case_id'],'segment_type':'JUDICIAL',
            "document_id":c["document_id"], "case_number":c.get("case_number",""),
            "case_type":c.get("case_type",""), "decision_date":c.get("decision_date",""),
            "provenance_span":{"coordinate_space":"DOCUMENT_TEXT",
                "document_char_start":0 if document_text else None,
                "document_char_end":len(document_text) if document_text else None,
                "page_start":1 if page_count else None,"page_end":page_count or None,
                "page_status":"DOCUMENT_LEVEL" if page_count else "NOT_APPLICABLE"},
            "provenance_status":"DOCUMENT_LEVEL" if document_text else "UNRESOLVED",
        })
    for s in segments or []:
        if s['segment_type'] not in {'ANNEX','FORM','ATTACHED_REGULATION'}: continue
        d=docs.get(s['document_id'],{}); breadcrumb=f"{d.get('title','')} > {s['heading']}"
        source=sources.get(d.get('file_id'),{})
        alignment=_align_segment(s['text'],source.get('text',''))
        document_start=alignment[0] if alignment else None
        document_end=_document_offset(alignment,len(s['text'])) if alignment else None
        if document_start is not None and source.get('text','')[document_start:document_end]!=s['text']:
            document_start=document_end=None
        pages=[p['page'] for p in source.get('page_provenance',[]) if document_start is not None and
               p.get('text_start',0)<document_end and p.get('text_end',0)>document_start]
        span={"segment_id":s['segment_id'],"coordinate_space":"SEGMENT_TEXT",
              "segment_char_start":0,"segment_char_end":len(s['text']),
              "document_char_start":document_start,"document_char_end":document_end,
              "page_start":min(pages) if pages else None,"page_end":max(pages) if pages else None,
              "page_status":"RESOLVED" if pages else "UNRESOLVED" if source.get('page_provenance') else "NOT_APPLICABLE"}
        units.append({**metadata(d),'unit_id':s['segment_id'],'kind':s['segment_type'],'document_id':s['document_id'],
            'text':breadcrumb+'\n'+s['text'],'source_text':s['text'],'breadcrumb':breadcrumb,'segment_type':s['segment_type'],
            'provenance_span':span,'provenance_status':'RESOLVED' if document_start is not None and
                span['page_status']!='UNRESOLVED' else 'UNRESOLVED'})
    units=[u for u in units if len(u.get('source_text',u.get('text','')).strip())>=20]
    if len({u['unit_id'] for u in units})!=len(units): raise ValueError('Duplicate retrieval unit IDs')
    return units


def build_dense_index(units: list[dict], cfg: dict, output_dir: Path) -> dict[str,np.ndarray]:
    idir=output_dir/"06_indexes"/"dense"; idir.mkdir(parents=True,exist_ok=True)
    if not units:
        raise ValueError('No retrieval units available for Dense indexing.')
    try:
        import faiss
        import torch
        from FlagEmbedding import BGEM3FlagModel
    except Exception as e:
        raise RuntimeError('Dense dependencies unavailable; run RUN_0_SETUP_FULL.bat') from e
    started=time.monotonic()
    settings=cfg['retrieval']
    model_name=settings.get('embedding_model','BAAI/bge-m3')
    model_path=settings.get('embedding_model_path')
    if model_path:
        local=Path(model_path)
        if not local.is_absolute(): local=cfg['project_root']/local
        if not (local/'config.json').is_file() or not any((local/name).is_file() for name in ('pytorch_model.bin','model.safetensors')):
            raise RuntimeError('Local Dense model incomplete. Run scripts/prepare_dense_model.py first.')
        model_path=str(local.resolve())
    device=settings.get('embedding_device','auto')
    if device == 'auto': device='cuda:0' if torch.cuda.is_available() else 'cpu'
    fp16=bool(settings.get('embedding_use_fp16',False)) and device != 'cpu'
    batch_size=int(settings.get('embedding_batch_size',4))
    max_length=int(settings.get('embedding_max_length',1024))
    chunk_size=int(settings.get('embedding_chunk_size',128))
    if min(batch_size,max_length,chunk_size) < 1:
        raise ValueError('Dense batch size, chunk size and max length must be positive.')
    source={}
    if model_path and (Path(model_path)/'source.json').is_file():
        source=json.loads((Path(model_path)/'source.json').read_text(encoding='utf-8'))
    fingerprint=hashlib.sha256(json.dumps({
        'units':units,'model':model_name,'path':model_path,'revision':source.get('sha'),
        'max_length':max_length,'fp16':fp16,'pooling':'cls',
    },ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
    print(f'Dense: {len(units)} units; device={device}; fp16={fp16}; batch={batch_size}; max_length={max_length}',flush=True)
    model=BGEM3FlagModel(model_path or model_name,use_fp16=fp16,devices=device)
    state_path=idir/'checkpoint.json'
    partial_path=idir/'vectors.partial.npy'
    completed=0; vec=None
    if state_path.exists() and partial_path.exists():
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('fingerprint') == fingerprint:
            candidate=np.load(partial_path,mmap_mode='r+',allow_pickle=False)
            if candidate.ndim == 2 and candidate.shape[0] == len(units) and 0 <= state.get('completed',-1) <= len(units):
                completed=state['completed']; vec=candidate
                print(f'Resuming Dense from {completed}/{len(units)} units',flush=True)
    for start in range(completed,len(units),chunk_size):
        end=min(start+chunk_size,len(units))
        result=model.encode([u['text'] for u in units[start:end]],batch_size=batch_size,
                            max_length=max_length,return_dense=True,return_sparse=False,return_colbert_vecs=False)
        block=np.asarray(result['dense_vecs'],dtype='float32')
        if block.ndim != 2 or len(block) != end-start or not np.isfinite(block).all():
            raise RuntimeError('Invalid Dense embedding batch')
        if vec is None:
            vec=np.lib.format.open_memmap(partial_path,mode='w+',dtype='float32',shape=(len(units),block.shape[1]))
        vec[start:end]=block; vec.flush()
        temporary=state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'fingerprint':fingerprint,'completed':end}),encoding='utf-8')
        os.replace(temporary,state_path)
        print(f'Dense checkpoint: {end}/{len(units)} units ({time.monotonic()-started:.1f}s)',flush=True)
    # BGE-M3 dense vectors are normalized; normalize again defensively for cosine/IP.
    if vec is None or not np.isfinite(vec).all() or np.any(np.linalg.norm(vec,axis=1) == 0):
        raise RuntimeError('Dense embeddings contain invalid or empty vectors')
    faiss.normalize_L2(vec)
    index=faiss.IndexFlatIP(vec.shape[1]); index.add(vec)
    # Python handles Unicode paths; FAISS's native filename API does not on Windows.
    index_bytes=faiss.serialize_index(index).tobytes()
    restored=faiss.deserialize_index(np.frombuffer(index_bytes,dtype='uint8').copy())
    sample=vec[np.linspace(0,len(units)-1,min(16,len(units)),dtype=int)].copy()
    scores,positions=restored.search(sample,1)
    if restored.ntotal != len(units) or not np.allclose(np.linalg.norm(vec,axis=1),1,atol=1e-3) or not np.isfinite(scores).all() or not (scores[:,0] > .99).all() or not (positions >= 0).all():
        raise RuntimeError('Dense index round-trip/query validation failed')
    queries=['thời hạn báo trước khi người lao động đơn phương chấm dứt hợp đồng lao động',
             'tiền lương làm thêm giờ vào ngày nghỉ lễ',
             'điều kiện hưởng trợ cấp thất nghiệp']
    query_vec=np.asarray(model.encode(queries,batch_size=batch_size,max_length=max_length,
                         return_dense=True,return_sparse=False,return_colbert_vecs=False)['dense_vecs'],dtype='float32')
    faiss.normalize_L2(query_vec)
    query_scores,query_ids=restored.search(query_vec,min(3,len(units)))
    if not np.isfinite(query_scores).all() or (query_ids < 0).any():
        raise RuntimeError('Dense text query validation failed')
    (idir/'faiss.index.tmp').write_bytes(index_bytes)
    write_jsonl(idir/'metadata.jsonl.tmp',units)
    with (idir/'vectors.npy.tmp').open('wb') as stream:
        np.save(stream,vec,allow_pickle=False)
    for name in ('faiss.index','metadata.jsonl','vectors.npy'):
        os.replace(idir/(name+'.tmp'),idir/name)
    (idir/'SKIPPED.txt').unlink(missing_ok=True)
    report={'dense_passed':True,'units':len(units),'dimensions':index.d,'model':model_name,
            'model_path':model_path,'model_revision':source.get('sha'),'fingerprint':fingerprint,
            'device':device,'fp16':fp16,'max_length':max_length,'batch_size':batch_size,
            'elapsed_seconds':round(time.monotonic()-started,2),'resumed_units':completed,
            'duplicate_unit_id_rows':len(units)-len({u['unit_id'] for u in units}),
            'checks':{'row_count':True,'finite_normalized_vectors':True,'faiss_round_trip':True,'self_search':True,'text_queries':True},
            'queries':[{'query':q,'results':[{'unit_id':units[int(pos)]['unit_id'],'document_number':units[int(pos)].get('document_number',''),
                         'score':float(score)} for pos,score in zip(query_ids[i],query_scores[i])]} for i,q in enumerate(queries)],
            'note':'Dense technical validation only; existing corpus/metadata/duplicate-ID issues remain.'}
    rdir=output_dir/'reports'; rdir.mkdir(parents=True,exist_ok=True)
    (rdir/'dense_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Dense index validated: {index.ntotal} vectors x {index.d} dimensions',flush=True)
    return {u["unit_id"]:vec[i] for i,u in enumerate(units)}


def build_bm25_index(units: list[dict], cfg: dict, output_dir: Path) -> None:
    idir=output_dir/"06_indexes"/"bm25"; idir.mkdir(parents=True,exist_ok=True)
    try:
        import bm25s
    except Exception as e:
        (idir/"SKIPPED.txt").write_text("BM25 index not built. Run RUN_0_SETUP_FULL.bat\n"+str(e),encoding="utf-8")
        return
    corpus=[{"id":u["unit_id"],"text":u["text"],"kind":u["kind"]} for u in units]
    # Vietnamese whitespace tokenization remains robust for exact legal phrases/article numbers.
    tokens=bm25s.tokenize([u["text"].lower() for u in units],stopwords=None,stemmer=None)
    retriever=bm25s.BM25(method=str(cfg["retrieval"].get("bm25_method","lucene")))
    retriever.index(tokens)
    retriever.save(str(idir),corpus=corpus)
