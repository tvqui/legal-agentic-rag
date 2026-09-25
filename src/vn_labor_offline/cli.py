from __future__ import annotations
import argparse, json
from pathlib import Path
from .config import load_yaml, resolve_paths
from .pipeline import run_all, rerun_enrichment
from .neo4j_loader import load_neo4j


def main():
    p=argparse.ArgumentParser(description='Vietnamese Labor Law offline data & knowledge construction')
    sub=p.add_subparsers(dest='cmd',required=True)
    pa=sub.add_parser('all'); pa.add_argument('--config',default='config/pipeline.yaml'); pa.add_argument('--mode',choices=['heuristic','ollama','ai','hybrid_ai'],default=None)
    pe=sub.add_parser('enrich'); pe.add_argument('--config',default='config/pipeline.yaml'); pe.add_argument('--mode',choices=['heuristic','ollama','ai','hybrid_ai'],default='ollama')
    pn=sub.add_parser('load-neo4j'); pn.add_argument('--config',default='config/pipeline.yaml')
    pn.add_argument('--replace-legacy',action='store_true',help='Explicit migration: remove unowned Entity nodes in this dedicated database')
    pd=sub.add_parser('dense'); pd.add_argument('--config',default='config/pipeline.yaml')
    ps=sub.add_parser('source-resolver')
    ps.add_argument('resolver_args', nargs=argparse.REMAINDER)
    args=p.parse_args()
    if args.cmd == 'source-resolver':
        from .source_resolver.cli import main as resolver_main
        raise SystemExit(resolver_main(args.resolver_args))
    cfg=resolve_paths(load_yaml(args.config),args.config)
    if args.cmd=='all':
        summary=run_all(cfg,args.mode); print(json.dumps(summary,ensure_ascii=False,indent=2))
    elif args.cmd=='enrich':
        summary=rerun_enrichment(cfg,args.mode); print(json.dumps(summary,ensure_ascii=False,indent=2))
    elif args.cmd=='load-neo4j':
        load_neo4j(cfg['output_dir'],int(cfg['neo4j'].get('load_batch_size',500)),replace_legacy=args.replace_legacy)
        print('Neo4j load complete.')
    elif args.cmd=='dense':
        from .indexes import build_dense_index
        from .util import read_jsonl
        units=list(read_jsonl(cfg['output_dir']/'06_indexes'/'retrieval_units.jsonl'))
        build_dense_index(units,cfg,cfg['output_dir'])
        print('Dense rebuild complete. See artifacts/reports/dense_validation.json.')

if __name__=='__main__': main()
