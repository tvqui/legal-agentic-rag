"""Pinned external-data adapters and an independent Zalo retrieval benchmark."""
from __future__ import annotations
import hashlib,json,math,re,time
from pathlib import Path
from common import save,read,jsonl,sha,mean

def field(row,*names):
    for name in names:
        if row.get(name) is not None:return row[name]
    raise ValueError('Missing columns '+str(names)+'; got '+str(sorted(row)))

def pin(repo,revision,cache):
    from huggingface_hub import HfApi
    # Persist the resolved SHA even if a later download fails. Resume must not
    # quietly move a dataset's 'main' to a different commit.
    pins=Path(cache)/'evaluation_pins';pins.mkdir(parents=True,exist_ok=True)
    path=pins/(hashlib.sha256((repo+revision).encode()).hexdigest()+'.json')
    if path.exists():return read(path)
    info=HfApi().dataset_info(repo,revision=revision)
    meta={'repo':repo,'revision':info.sha,'license':dict(info.card_data or {}).get('license'),
        'source':'https://huggingface.co/datasets/'+repo,'cache_dir':str(cache)}
    save(path,meta);return meta

def dataset(meta,config,split=None):
    from datasets import load_dataset,get_dataset_split_names
    if split is None:
        splits=get_dataset_split_names(meta['repo'],config,revision=meta['revision'])
        if len(splits)!=1:raise ValueError(f'Select split explicitly for {config}: {splits}')
        split=splits[0]
    return load_dataset(meta['repo'],config,split=split,revision=meta['revision'],cache_dir=meta['cache_dir'])

def prepare_zalo(run_dir,settings):
    out=Path(run_dir)/'zalo';out.mkdir(exist_ok=True)
    cfg=settings['zalo'];meta=pin(cfg['repo'],cfg['revision'],Path(settings['cache'])/'hf')
    corpus=dataset(meta,'corpus');queries=dataset(meta,'queries');relations=dataset(meta,'qrels',cfg['qrels_split'])
    docs=[]
    for row in corpus:
        uid=str(field(row,'corpus_id','_id','id'))
        text=str(field(row,'text','content'))
        if row.get('title'):text=str(row['title'])+'\n'+text
        docs.append({'id':uid,'text':text})
    if len({r['id'] for r in docs})!=len(docs):raise ValueError('Duplicate corpus IDs')
    ids={r['id'] for r in docs};qrels={}
    for row in relations:
        if float(field(row,'score'))<=0:continue
        qid=str(field(row,'query_id'));doc=str(field(row,'corpus_id'))
        if doc not in ids:raise ValueError('Qrel refers to missing corpus ID')
        qrels.setdefault(qid,set()).add(doc)
    qs=[]
    for row in queries:
        qid=str(field(row,'query_id','_id','id'))
        if qid in qrels:qs.append({'id':qid,'question':str(field(row,'text','query','question')),
          'relevant_ids':sorted(qrels[qid])})
    qs=sorted(qs,key=lambda r:r['id'])[:cfg['limit'] or None]
    if not qs:raise ValueError('No Zalo test questions')
    for name,rows in [('corpus',docs),('questions',qs)]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    save(out/'source.json',{**meta,'split':cfg['qrels_split'],'queries':len(qs),'corpus':len(docs),
      'selection':'all positive test qrels, query-ID sort, then configured limit; FULL corpus retained',
      'corpus_sha256':sha(out/'corpus.jsonl'),'questions_sha256':sha(out/'questions.jsonl')})

def labor_question(text):
    # A transparent screening heuristic, never human scope approval.
    return bool(re.search(r'lao động|hợp đồng lao động|thử việc|tiền lương|nghỉ hằng năm|nghỉ phép|sa thải|làm thêm giờ',text,re.I))

def prepare_vlsp(run_dir,settings):
    out=Path(run_dir)/'vlsp';out.mkdir(exist_ok=True);cfg=settings['vlsp']
    if cfg['subset']!='syllogism_questions':raise ValueError('This adapter evaluates free QA only (syllogism_questions)')
    if cfg['selection'] not in ('labor_keywords','all'):raise ValueError('Unknown VLSP selection')
    meta=pin(cfg['repo'],cfg['revision'],Path(settings['cache'])/'hf')
    ds=dataset(meta,cfg['subset'],cfg['split']);accepted=[];excluded=[]
    for index,row in enumerate(ds):
        question=str(field(row,'question'));reference=str(field(row,'answer'))
        uid='vlsp_'+str(index)
        if cfg['selection']=='labor_keywords' and not labor_question(question):
            excluded.append(uid);continue
        accepted.append({'id':uid,'question':question,'reference_answer':reference,
            'query_date':cfg['query_date'],'date_assumption':cfg['date_assumption'],
            'review_status':'EXTERNAL_REFERENCE_NOT_HUMAN_REVIEWED_FOR_THIS_CORPUS'})
    selected=accepted[:cfg['limit'] or None]
    (out/'questions.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected),encoding='utf-8')
    save(out/'source.json',{**meta,'subset':cfg['subset'],'split':cfg['split'],
      'total':len(ds),'eligible':len(accepted),'selected':len(selected),'excluded_ids':excluded,
      'selected_ids':[r['id'] for r in selected],'date_assumption':cfg['date_assumption'],
      'protocol':'Adapted RAG QA; NOT official LegalSLM protocol; source references may predate selected corpus',
      'questions_sha256':sha(out/'questions.jsonl')})
    if not selected:raise ValueError('No labor questions selected; do not silently test all domains')

def ir_metrics(ranked,relevant,k):
    truth=set(relevant);seen=set();hits=[]
    for rank,uid in enumerate(ranked[:k],1):
        if uid in truth and uid not in seen:hits.append(rank);seen.add(uid)
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(truth))))
    return {'recall_at_k':len(seen)/len(truth),'precision_at_k':len(seen)/k,
      'mrr_at_k':1/hits[0] if hits else 0,
      'ndcg_at_k':sum(1/math.log2(rank+1) for rank in hits)/ideal if ideal else 0}

def rrf(lists,k=60):
    scores={}
    for values in lists:
        for rank,uid in enumerate(values,1):scores[uid]=scores.get(uid,0)+1/(k+rank)
    return sorted(scores,key=lambda uid:(-scores[uid],uid))

def run_zalo(run_dir,settings):
    import numpy as np,bm25s,faiss
    from FlagEmbedding import BGEM3FlagModel
    from huggingface_hub import HfApi,snapshot_download
    out=Path(run_dir)/'zalo';docs=jsonl(out/'corpus.jsonl');queries=jsonl(out/'questions.jsonl')
    cfg=settings['zalo'];source=read(out/'source.json')
    # Keep the external corpus separate from labour-law artifacts and models.
    repo='BAAI/bge-m3';revision=HfApi().model_info(repo).sha
    model_path=snapshot_download(repo,revision=revision,cache_dir=str(Path(settings['cache'])/'hf_models'))
    model=BGEM3FlagModel(model_path,use_fp16=settings['device']!='cpu',devices=settings['device'])
    texts=[r['text'] for r in docs];ids=[r['id'] for r in docs]
    tokenized=bm25s.tokenize([text.lower() for text in texts],stopwords=None,stemmer=None)
    lexical=bm25s.BM25();lexical.index(tokenized)
    cache_key=hashlib.sha256((source['corpus_sha256']+revision+str(cfg['max_length'])).encode()).hexdigest()
    cache=Path(settings['cache'])/'zalo'/cache_key;cache.mkdir(parents=True,exist_ok=True)
    marker=cache/'progress.json';done=read(marker).get('completed',0) if marker.exists() else 0
    vectors=None
    if done:
        vectors=np.load(cache/'vectors.npy',mmap_mode='r+')
        if len(vectors)!=len(texts) or done>len(texts):raise ValueError('Invalid cached embeddings')
    for start in range(done,len(texts),cfg['batch_size']):
        stop=min(start+cfg['batch_size'],len(texts))
        encoded=np.asarray(model.encode(texts[start:stop],batch_size=cfg['batch_size'],max_length=cfg['max_length'],
            return_dense=True,return_sparse=False,return_colbert_vecs=False)['dense_vecs'],dtype='float32')
        faiss.normalize_L2(encoded)
        if vectors is None:vectors=np.lib.format.open_memmap(cache/'vectors.npy',mode='w+',dtype='float32',shape=(len(texts),encoded.shape[1]))
        vectors[start:stop]=encoded;vectors.flush();save(marker,{'completed':stop,'total':len(texts)})
        if start%max(cfg['batch_size'],256)<cfg['batch_size']:print(f'ZALO_EMBED {stop}/{len(texts)}',flush=True)
    if vectors is None:raise ValueError('Empty corpus')
    index=faiss.IndexFlatIP(vectors.shape[1])
    for start in range(0,len(vectors),1024):index.add(np.asarray(vectors[start:start+1024]))
    records=[];summary={'scope':'independent_external_ir_full_corpus','source':source,
      'embedding_model':repo,'embedding_revision':revision,'methods':{},'expected_attempts':len(queries)*settings['repeats']*3}
    def search(method,question):
        channels=[]
        if method in ('bm25','hybrid'):
            tokens=bm25s.tokenize([question.lower()],stopwords=None,stemmer=None)
            positions,_=lexical.retrieve(tokens,k=min(30,len(docs)))
            channels.append([ids[int(i)] for i in positions[0]])
        if method in ('dense','hybrid'):
            v=np.asarray(model.encode([question],batch_size=1,max_length=cfg['max_length'],return_dense=True,
                return_sparse=False,return_colbert_vecs=False)['dense_vecs'],dtype='float32')
            faiss.normalize_L2(v);_,positions=index.search(v,min(30,len(docs)))
            channels.append([ids[int(i)] for i in positions[0] if i>=0])
        return channels[0] if len(channels)==1 else rrf(channels)
    for method in ('bm25','dense','hybrid'):search(method,queries[0]['question'])
    with (out/'responses.jsonl').open('w',encoding='utf-8') as f:
        for repeat in range(settings['repeats']):
            for q in queries:
                for method in ('bm25','dense','hybrid'):
                    started=time.perf_counter();ranked=search(method,q['question'])
                    row={'id':q['id'],'question':q['question'],'method':method,'repeat':repeat+1,'status':'OK',
                      'elapsed_ms':(time.perf_counter()-started)*1000,'top_ids':ranked[:settings['k']],
                      **ir_metrics(ranked,q['relevant_ids'],settings['k'])}
                    records.append(row);f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                for method in ('bm25','dense','hybrid'):
                    values=[r for r in records if r['method']==method]
                    summary['methods'][method]={key:mean([r[key] for r in values]) for key in ['recall_at_k','precision_at_k','mrr_at_k','ndcg_at_k','elapsed_ms']}
                    summary['methods'][method]['attempts']=len(values)
                summary['complete']=len(records)==summary['expected_attempts'];save(out/'summary.json',summary)
                print(f'ZALO_QUERY {repeat+1} {q["id"]}',flush=True)
    return summary
