"""Create source-bound review evidence; never approve or alter a corpus build."""
from __future__ import annotations
import argparse,csv,hashlib,html,json,re,unicodedata,zipfile
from datetime import date
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


def read_rows(z,name):
    return [json.loads(s) for s in z.read(name).decode('utf-8-sig').splitlines() if s.strip()]


def write_rows(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')


def official(url):
    host=(urlparse(url).hostname or '').lower()
    return urlparse(url).scheme=='https' and (host=='vbpl.vn' or host.endswith('.vbpl.vn') or host.endswith('.gov.vn')
        or host=='chinhphu.vn' or host.endswith('.chinhphu.vn'))


def question_date_conflict(question,query_date):
    """Flag inconsistent benchmark inputs; never silently rewrite a date."""
    if not query_date:return False
    for value in re.findall(r'\b(\d{1,2}/\d{1,2}/\d{4})\b',question):
        try:
            day,month,year=map(int,value.split('/'))
            if date(year,month,day).isoformat()!=query_date:return True
        except ValueError:pass
    years=re.findall(r'\bnăm\s+(20\d{2})\b',question,re.I)
    return any(year!=query_date[:4] for year in years)


def audit(artifact,output,gold_archive=None,annotation_path=None,snapshot_as_of=None,catalog_path=None,seed_path=None):
    # A build date is not a legal snapshot date. Require an explicit cutoff.
    snapshot_as_of=date.fromisoformat(snapshot_as_of).isoformat()
    artifact=Path(artifact);output=Path(output)
    # A separate new directory prevents stale reports being mistaken for this run.
    output.mkdir(parents=True,exist_ok=False)
    with artifact.open('rb') as stream:artifact_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    with zipfile.ZipFile(artifact) as z:
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate ZIP member')
        registry=read_rows(z,'artifacts/02_registry/documents.jsonl')
        provisions=read_rows(z,'artifacts/03_structure/provisions.jsonl')
        units=read_rows(z,'artifacts/06_indexes/retrieval_units.jsonl')
        changes=read_rows(z,'artifacts/04_knowledge/legal_changes.jsonl')
        quarantine=read_rows(z,'artifacts/03_structure/quarantined_provisions.jsonl')
        pages=read_rows(z,'artifacts/reviews/page_quality/page_review_evidence.jsonl')
        summary=json.loads(z.read('artifacts/reports/summary.json'))
        stages=json.loads(z.read('artifacts/reports/final_outputs_validation.json'))['stages']
    docs={d['document_id']:d for d in registry};by_provision={p['provision_id']:p for p in provisions}
    source_rows=[{'document_id':d['document_id'],'relative_path':d['relative_path'],'sha256':d['sha256'],
        'document_number':d.get('document_number'),'title':d.get('title'),'source_url':d.get('source_url'),
        'official_url_candidate':official(d.get('source_url') or ''),'effective_from_candidate':d.get('effective_from'),
        'effective_to_candidate':d.get('effective_to'),'review_status':'DRAFT','reviewer':None} for d in registry]
    catalog={};seeds={}
    if catalog_path:
        import yaml
        catalog=(yaml.safe_load(Path(catalog_path).read_text(encoding='utf-8')) or {}).get('sources',{})
    if seed_path:
        with Path(seed_path).open(encoding='utf-8-sig',newline='') as stream:
            seeds={s.get('corpus_sha256'):s for s in csv.DictReader(stream)}
    for row in source_rows:
        candidates=[];cat=catalog.get(row['relative_path'],{})
        if cat.get('sha256')==row['sha256'] and cat.get('source_url'):
            candidates.append({'url':cat['source_url'],'origin':'SHA_MATCHED_CATALOG'})
        seed=seeds.get(row['sha256'],{})
        for key in ('exact_source_url','direct_download_url','current_candidate_url'):
            if seed.get(key):candidates.append({'url':seed[key],'origin':'SHA_MATCHED_SEED:'+key})
        row['build_source_url']=row.get('source_url')
        row['candidate_urls']=list({c['url']:c for c in candidates}.values())
        if not row.get('source_url') and candidates:row['source_url']=candidates[0]['url']
        row['official_url_candidate']=official(row.get('source_url') or '')
    write_rows(output/'source_review.jsonl',source_rows)
    temporal=[]
    for change in changes:
        p=by_provision.get(change.get('source_provision_id'),{});doc=docs.get(change.get('source_document_id'),{})
        text=p.get('text') or change.get('evidence_text','')
        temporal.append({**change,'review_status':'DRAFT','reviewer':None,'source_document_number':doc.get('document_number'),
            'source_url':doc.get('source_url'),'full_operative_text':text,
            'target_number_candidates':re.findall(r'\b\d{1,3}/\d{4}/[A-ZĐ][A-Za-zĐđ0-9-]+',text),
            'note':'Candidate identifiers only; no target/interval is applied or approved by this audit.'})
    write_rows(output/'temporal_changes_review.jsonl',temporal)
    grouped={}
    for row in quarantine:
        key=(row.get('document_id'),row.get('segment_id'),row.get('article_number'),row.get('clause_number'),row.get('point_number'))
        grouped.setdefault(key,[]).append(row)
    write_rows(output/'quarantine_review.jsonl',[{'document_id':key[0],'relative_path':docs.get(key[0],{}).get('relative_path'),
        'canonical_location':list(key[1:]),'review_status':'DRAFT','reviewer':None,'members':members}
        for key,members in grouped.items()])
    write_rows(output/'page_review.jsonl',[{**p,'review_status':'REVIEW_REQUIRED','reviewer':None,
        'current_artifact_sha256':artifact_sha,
        'note':'Retains original SHA-bound evidence; numeric differences are not automatically OCR errors.'} for p in pages])
    gold=[];gold_html=[]
    if gold_archive:
        with zipfile.ZipFile(gold_archive) as z:questions=read_rows(z,'labor_gold.jsonl')
        by_id={u['unit_id']:u for u in units}
        annotations=json.loads(Path(annotation_path).read_text(encoding='utf-8')).get('question_notes',{}) if annotation_path else {}
        for row in questions:
            groups=row.get('required_groups',[]);found=[];missing=[]
            for group in groups:
                matches=[by_id[uid] for uid in group if uid in by_id]
                if not matches:missing.append(group)
                found.append([{'unit_id':u['unit_id'],'document_number':u.get('document_number'),
                    'article':u.get('article_number'),'clause':u.get('clause_number'),'point':u.get('point_number'),
                    'source_url':u.get('source_url'),'text':u.get('source_text') or u.get('text'),
                    'provenance_span':u.get('provenance_span')} for u in matches])
            flags=[]
            if missing:flags.append('REQUIRED_GROUP_NOT_IN_CURRENT_BUILD')
            if row.get('query_date','')>snapshot_as_of:flags.append('QUERY_AFTER_CORPUS_SNAPSHOT')
            if question_date_conflict(row['question'],row.get('query_date')):flags.append('QUESTION_DATE_DIFFERS_QUERY_DATE')
            if row['id'] in annotations:flags.append('HAS_PRIOR_ANNOTATION_CONCERN')
            if not groups and row.get('retrieval_eligible'):flags.append('ANSWERABLE_WITHOUT_QRELS')
            packet={'id':row['id'],'question':row['question'],'query_date':row.get('query_date'),
                'reference_answer':row.get('reference_answer'),'expected_status':row.get('expected_status'),
                'required_evidence_groups':found,'unresolved_groups':missing,'engineering_flags':flags,
                'annotation':annotations.get(row['id'],{}),'review_status':'DRAFT','reviewer':None,
                'artifact_sha256':artifact_sha,'legal_approved':False}
            gold.append(packet)
            gold_html.append('<details><summary>'+html.escape(row['id']+' — '+row['question'])+'</summary><pre>'+
                html.escape(json.dumps(packet,ensure_ascii=False,indent=2))+'</pre></details>')
        write_rows(output/'gold100_review.jsonl',gold)
    counts={'artifact_sha256':artifact_sha,'technical_stages':stages,'documents':len(registry),
        'provisions':len(provisions),'page_review_required':len(pages),'quarantined_rows':len(quarantine),
        'quarantine_location_groups':len(grouped),'pending_changes':len(changes),
        'official_url_candidates':sum(r['official_url_candidate'] for r in source_rows),
        'gold_questions':len(gold),'gold_with_unresolved_groups':sum(bool(r['unresolved_groups']) for r in gold),
        'gold_flags':dict(Counter(flag for r in gold for flag in r['engineering_flags'])),
        'human_approvals_created':0,'source_readiness':summary.get('source_catalog_quality'),
        'semantic_readiness':summary.get('semantic_quality'),
        'corpus_snapshot_as_of':snapshot_as_of,'legal_current_through_today':False,
        'note':'Evidence preparation and engineering checks only; input archives and approvals are unchanged.'}
    (output/'summary.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'gold100_review.html').write_text('<!doctype html><meta charset="utf-8"><title>Gold 100 — căn cứ chờ duyệt</title>'
        '<style>body{font:16px Arial;margin:28px}summary{padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>100 câu Gold: đối chiếu đáp án và căn cứ</h1><p>Mọi bản ghi vẫn DRAFT; chưa tạo approval pháp lý.</p>'+''.join(gold_html),encoding='utf-8')
    return counts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gold-archive',type=Path);p.add_argument('--annotations',type=Path)
    p.add_argument('--snapshot-as-of',required=True,help='Legal coverage cutoff, not archive creation date (YYYY-MM-DD)')
    p.add_argument('--catalog',type=Path);p.add_argument('--source-seed',type=Path)
    a=p.parse_args();print(json.dumps(audit(a.artifact,a.output,a.gold_archive,a.annotations,a.snapshot_as_of,a.catalog,a.source_seed),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
