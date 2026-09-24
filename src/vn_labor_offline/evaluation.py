"""Gate a separately reviewed gold evaluation against the exact current build.

Synthetic unit tests and FAISS self-search are never accepted as a gold evaluation.
The reviewed evaluation is an external input until a real corpus gold set exists.
"""
import hashlib,json


def reviewed_quality_gate(out,nodes,edges):
    path=out/'reports/reviewed_quality_evaluation.json'
    if not path.exists(): return {'passed':False,'status':'NOT_EVALUATED','reason':'Reviewed corpus citation/retrieval gold evaluation required'}
    report=json.loads(path.read_text(encoding='utf-8'))
    fingerprint=hashlib.sha256(json.dumps([nodes,edges],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    checks={
        'reviewed':report.get('reviewed') is True and bool(report.get('reviewer')),
        'current_build':report.get('build_id')==fingerprint,
        'gold_sources':bool(report.get('gold_source')),
        'citation_samples':report.get('citation_sample_count',0)>0,
        'citation_precision':.95<=report.get('citation_precision',0)<=1,
        'retrieval_evaluated':report.get('retrieval_sample_count',0)>0 and report.get('retrieval_passed') is True,
    }
    return {'passed':all(checks.values()),'status':'REVIEWED_EVALUATION','checks':checks}
