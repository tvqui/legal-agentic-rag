import json,sys
from pathlib import Path
from .indexes import build_dense_index
from .util import read_jsonl

if __name__=='__main__':
    cfg=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    for key in ('project_root','output_dir','data_dir'): cfg[key]=Path(cfg[key])
    build_dense_index(list(read_jsonl(cfg['output_dir']/'06_indexes/retrieval_units.jsonl')),cfg,cfg['output_dir'])
