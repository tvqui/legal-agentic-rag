"""Download ONLINE retrieval models before the backend accepts traffic."""
from __future__ import annotations
import argparse,os
from pathlib import Path
import yaml

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config',default='config/online_kaggle.yaml'); args=parser.parse_args()
    raw=yaml.safe_load(Path(args.config).read_text(encoding='utf-8')) or {}; cfg=raw.get('online',raw)
    models=[]
    if (cfg.get('retrieval') or {}).get('dense_enabled',True) and not cfg.get('embedding_model_path'):
        models.append(cfg.get('embedding_model','BAAI/bge-m3'))
    reranker=cfg.get('reranker') or {}
    if reranker.get('enabled') and not reranker.get('model_path'): models.append(reranker.get('model','BAAI/bge-reranker-v2-m3'))
    from huggingface_hub import snapshot_download
    for model in dict.fromkeys(models):
        print('Preparing ONLINE model:',model,flush=True)
        path=snapshot_download(model,token=os.getenv('HF_TOKEN') or None)
        if not (Path(path)/'config.json').is_file(): raise RuntimeError(f'Incomplete model snapshot: {model}')
        print('Model ready:',path,flush=True)
if __name__=='__main__': main()
