from __future__ import annotations
import argparse,json
from pathlib import Path
from .artifact_store import ArtifactStore
from .config import load_config
from .models import QueryRequest
from .pipeline import OnlinePipeline
def main(argv=None):
    p=argparse.ArgumentParser(prog='vn-labor-online'); p.add_argument('--config',type=Path,default=Path('config/online.yaml'))
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('check'); ask=sub.add_parser('ask'); ask.add_argument('question'); ask.add_argument('--date')
    serve=sub.add_parser('serve'); serve.add_argument('--host',default='127.0.0.1'); serve.add_argument('--port',type=int,default=8000)
    a=p.parse_args(argv); cfg=load_config(a.config)
    if a.command=='check': print(json.dumps(ArtifactStore(cfg).report.model_dump(mode='json'),ensure_ascii=True,indent=2)); return 0
    if a.command=='ask': print(json.dumps(OnlinePipeline(cfg).ask(QueryRequest(question=a.question,query_date=a.date)).model_dump(mode='json'),ensure_ascii=True,indent=2)); return 0
    import os,uvicorn; os.environ['VN_LABOR_ONLINE_CONFIG']=str(a.config); uvicorn.run('vn_labor_online.api:create_app',factory=True,host=a.host,port=a.port); return 0
if __name__=='__main__': raise SystemExit(main())
