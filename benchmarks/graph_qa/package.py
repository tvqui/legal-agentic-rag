"""Build a self-contained source-only Kaggle input ZIP; never package keys/data/runs."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def members(root=ROOT):
    base=root/'benchmarks/graph_qa'
    selected=list((root/'src').rglob('*.py'))
    selected += [p for p in base.iterdir() if p.suffix in ('.py','.md','.ipynb') or p.name=='questions.jsonl']
    selected += [root/'pyproject.toml']
    return {p.relative_to(root).as_posix():p.read_bytes() for p in sorted(selected) if p.is_file()}
def build(output,root=ROOT):
    files=members(root)
    if len(files)>4999 or sum(map(len,files.values()))>99*1024**2:raise ValueError('Package exceeds safety limits')
    manifest={'schema_version':1,'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['package_manifest.json']=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode('utf-8')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    return {'output':str(output),'files':len(files),'sha256':digest,'bytes':output.stat().st_size}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default=str(ROOT/'benchmarks/graph_qa/PhapDienAI_GraphQA_Code.zip'))
    print(json.dumps(build(parser.parse_args().output),indent=2))
