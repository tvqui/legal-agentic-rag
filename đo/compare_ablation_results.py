"""Combine independently measured ablation ZIPs. No API/model calls or rescore."""
import argparse,json,stat,zipfile
from pathlib import Path,PurePosixPath
import eval_core as e

METHODS={'full','without_graph','without_reranker','without_auditor','without_review'}

def extract_checked(archive,destination):
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();seen=set()
        if sum(i.file_size for i in infos)>8*1024**3:raise ValueError('Archive too large')
        for info in infos:
            name=PurePosixPath(info.filename)
            if name.is_absolute() or '..' in name.parts or chr(92) in info.filename or ':' in info.filename or stat.S_ISLNK(info.external_attr>>16):
                raise ValueError('Unsafe archive path')
            normalized=str(name).casefold()
            if normalized in seen:raise ValueError('Duplicate archive member')
            seen.add(normalized)
        destination.mkdir(parents=True)
        z.extractall(destination)

def compare(inputs,out):
    out=Path(out)
    if out.exists():raise FileExistsError('Use a NEW output folder; original results will not be overwritten')
    paths=[Path(p).resolve() for p in inputs]
    if len(set(paths))!=len(paths):raise ValueError('Duplicate input paths')
    if any(not p.exists() for p in paths):raise FileNotFoundError('Input missing')
    out.mkdir(parents=True)
    manifests=[];provenance=[]
    for index,path in enumerate(paths):
        if path.is_file():
            digest=e.sha(path);root=out/'inputs'/str(index)
            extract_checked(path,root)
            provenance.append({'input':str(path),'zip_sha256':digest})
        else:
            root=path;provenance.append({'input':str(path),'kind':'DIRECTORY'})
        manifests.extend(sorted(root.rglob('run_manifest.json')))
    if not manifests:raise ValueError('No ablation run manifests found')
    runs=[];seen=set()
    for path in manifests:
        m=e.read(path);methods=m.get('methods',[])
        if m.get('task')!='qa' or len(methods)!=1 or methods[0] not in METHODS:
            raise ValueError('Expected one ablation configuration per run')
        if m.get('comparison_key')!=e.fingerprint(m.get('comparison_controls')):
            raise ValueError('Comparison controls fingerprint mismatch')
        identity=(m['comparison_key'],methods[0])
        if identity in seen:raise ValueError('Duplicate configuration in same comparison group; provide only one final/checkpoint ZIP per configuration')
        seen.add(identity)
        record_keys=set()
        for r in e.rows(path.parent/'responses.jsonl'):
            record_key=(r.get('id'),r.get('method'),r.get('repeat'))
            if r.get('method')!=methods[0] or r.get('id') not in m['selected_ids'] or not 1<=r.get('repeat',0)<=m['repeats']:
                raise ValueError('Foreign method/question/repeat in responses')
            if record_key in record_keys:raise ValueError('Duplicate response attempt')
            record_keys.add(record_key)
        runs.append(path.parent)
    table=e.report_runs(runs,out/'comparison')
    e.dump(out/'input_provenance.json',{'inputs':provenance,'run_count':len(runs),
        'comparison_groups':len({key for key,_ in seen}),
        'note':'No inference or AI scoring performed. Different comparison keys stay separate; incomplete results and errors are retained.'})
    return table

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',nargs='+',required=True,help='Per-configuration ZIPs or directories')
    p.add_argument('--out',required=True)
    args=p.parse_args();compare(args.inputs,args.out)
    print('Comparison:',Path(args.out)/'comparison/comparison.md')

if __name__=='__main__':main()
