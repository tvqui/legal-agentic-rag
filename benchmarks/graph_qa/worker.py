"""Gold-blind persistent inference process; stdout is a JSONL transport only."""
from __future__ import annotations
import contextlib,json,os,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from protocol import config,sha,write,safe_error,environment

def pin_models(pipe,s):
    import re
    from huggingface_hub import snapshot_download
    report=pipe.store.dense_report
    model=report.get('model');revision=report.get('model_revision')
    if not model or not re.fullmatch(r'[a-f0-9]{40}',str(revision)):raise ValueError('Artifact embedding commit unavailable')
    base=Path(s['cache'])/'huggingface'
    embedding=snapshot_download(model,revision=revision,cache_dir=str(base))
    reranker=snapshot_download('BAAI/bge-reranker-v2-m3',revision=s['reranker_revision'],cache_dir=str(base))
    pipe.cfg.embedding_model=model;pipe.cfg.embedding_model_path=embedding;pipe.cfg.reranker.model_path=reranker
    return {'embedding_model':model,'embedding_revision':revision,'reranker_revision':s['reranker_revision']}

def ollama_digest(s):
    from urllib.parse import urlsplit
    url=urlsplit(s['ollama_url']);endpoint=f'{url.scheme}://{url.netloc}/api/tags'
    with urllib.request.urlopen(endpoint,timeout=15) as r:tags=json.load(r)
    found=[m for m in tags.get('models',[]) if m.get('name')==s['llm_model'] or m.get('model')==s['llm_model']]
    if len(found)!=1 or not found[0].get('digest'):raise ValueError('Requested Ollama model not uniquely installed')
    return found[0]['digest']

def init(state):
    from vn_labor_online.pipeline import OnlinePipeline
    from vn_labor_online.providers import OllamaProvider,GeminiProvider
    cfg=config(state['settings'],state['artifact_root'],False)
    pipe=OnlinePipeline(cfg);s=state['settings']
    for key,relative in [('units','06_indexes/retrieval_units.jsonl'),('nodes','05_graph/nodes.jsonl'),('edges','05_graph/edges.jsonl')]:
        if sha(pipe.store.path(relative))!=state['artifact_hashes'][key]:raise ValueError('Artifact changed before inference')
    for name,expected in state['all_artifact_files_sha256'].items():
        if sha(pipe.store.path(name))!=expected:raise ValueError('Artifact indexes/reports changed')
    pins=pin_models(pipe,s);pins['ollama_digest']=ollama_digest(s)
    # Fixed neutral warmup; no study questions or Gold labels are loaded here.
    start=time.perf_counter();items=pipe.retriever.bm25('quan hệ lao động',5)
    pipe.retriever.dense('quan hệ lao động',5);pipe.retriever.neural_rerank(items,'quan hệ lao động')
    schema={'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False}
    provider=OllamaProvider(s['ollama_url'],s['llm_model'],timeout=s['provider_timeout_seconds'],max_output_tokens=128)
    try:
        if provider.structured('Return JSON only.','Return ready=true.',schema).get('ready') is not True:raise ValueError('Ollama probe failed')
    finally:provider.close()
    if s['semantic_review'] and state.get('probe_review',False):
        provider=GeminiProvider(s['review_model'],api_key=os.getenv('GEMINI_API_KEY'),timeout=s['provider_timeout_seconds'],max_output_tokens=128)
        try:
            if provider.structured('Return JSON only.','Return ready=true.',schema).get('ready') is not True:raise ValueError('Gemini probe failed')
        finally:provider.close()
    return pipe,{'pins':pins,'warmup_ms':(time.perf_counter()-start)*1000,'environment':environment(),
        'compatibility':pipe.store.report.model_dump(mode='json')}

def main(state_path):
    state=json.loads(Path(state_path).read_text(encoding='utf-8'));out=sys.stdout;pipe=None
    def emit(value):out.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');out.flush()
    try:
        with contextlib.redirect_stdout(sys.stderr):pipe,meta=init(state)
        emit({'kind':'ready',**meta})
        for line in sys.stdin:
            command=json.loads(line)
            if command.get('command')=='stop':break
            try:
                from vn_labor_online.models import QueryRequest
                # No Gold/locators/task lists/reference answer can be accepted by this transport.
                if set(command)!={'id','arm','question','query_date'}:raise ValueError('Unknown inference fields')
                if command['arm'] not in ('graph_off','graph_on'):raise ValueError('Unknown arm')
                pipe.cfg.graph.enabled=command['arm']=='graph_on'
                start=time.perf_counter()
                with contextlib.redirect_stdout(sys.stderr):response=pipe.ask(QueryRequest(question=command['question'],query_date=command['query_date']))
                result=response.model_dump(mode='json')
                # Capture selected source text and graph path from the immutable corpus, not only citation IDs.
                ids=set()
                for event in (result.get('trace') or {}).get('events',[]):
                    if event.get('event')=='selection':ids.update(event.get('evidence_ids',[]))
                steps=(result.get('trace') or {}).get('execution_steps',[])
                emit({'kind':'answer','status':'OK','response':result,'elapsed_ms':(time.perf_counter()-start)*1000,
                    'selected_evidence':[pipe.store.units_by_id[x] for x in sorted(ids) if x in pipe.store.units_by_id],
                    'llm_calls_recorded':sum(x.get('step')=='model_call' or x.get('name')=='model_call' for x in steps),
                    'llm_call_count_status':'LOWER_BOUND' if (result.get('trace') or {}).get('execution_steps_dropped') else 'RECORDED_STEPS'})
            except Exception as exc:emit({'kind':'answer','status':'ERROR','error':safe_error(exc)})
    except Exception as exc:emit({'kind':'fatal','error':safe_error(exc)});return 1
    finally:
        if pipe is not None:
            with contextlib.redirect_stdout(sys.stderr):pipe.close()
    return 0
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
