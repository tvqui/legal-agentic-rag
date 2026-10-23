"""Read candidate Gold ZIPs without extracting or promoting legal approval."""
from __future__ import annotations
import copy, hashlib, json, re, unicodedata, zipfile
from collections import Counter
from datetime import date
from pathlib import Path

STATUSES={'ANSWERABLE','NEED_MORE_FACTS','INSUFFICIENT_EVIDENCE'}

def norm(text):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text)).strip()

def locator(text):
    values={}
    for pattern,key in [(r'Điều\s+(\d+[a-z]?)','article_number'),
                        (r'khoản\s+(\d+[a-z]?)','clause_number'),
                        (r'điểm\s+([a-zđ])','point_number')]:
        match=re.search(pattern,text,re.I)
        values[key]=match.group(1).lower() if match else ''
    if not values['article_number']:raise ValueError('Gold locator lacks article')
    values['level']='POINT' if values['point_number'] else 'CLAUSE' if values['clause_number'] else 'ARTICLE'
    return values

def read_candidate(path):
    """Bounded, explicit member reads; no extractall, pickle, XLSX execution."""
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP members')
        def member(name):
            matches=[n for n in names if Path(n.replace('\\','/')).name==name]
            if len(matches)!=1:raise ValueError('Need exactly one Gold ZIP member: '+name)
            info=archive.getinfo(matches[0])
            if info.file_size>20*1024*1024 or info.flag_bits & 1:raise ValueError('Oversized/encrypted Gold member')
            return archive.read(info).decode('utf-8-sig')
        rows=[json.loads(s) for s in member('labor_gold_100.jsonl').splitlines() if s.strip()]
        catalog=[json.loads(s) for s in member('evidence_catalog.jsonl').splitlines() if s.strip()]
        manifest=json.loads(member('manifest.json'))
    return rows,catalog,manifest

def import_candidate(path,store,fingerprint):
    path=Path(path);rows,catalog,manifest=read_candidate(path)
    source_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    note_file=Path(__file__).with_name('gold100_annotation_notes.json')
    notes=json.loads(note_file.read_text(encoding='utf-8')) if note_file.exists() else {}
    notes=notes.get('question_notes',{}) if notes.get('source_zip_sha256')==source_sha else {}
    if not rows:raise ValueError('Empty candidate Gold')
    ids=[r['question_id'] for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate question IDs')
    evidence={c['evidence_id']:c for c in catalog}
    if len(evidence)!=len(catalog):raise ValueError('Duplicate catalog evidence IDs')
    if manifest.get('size')!=len(rows) or manifest.get('distinct_evidence_ids')!=len(evidence):raise ValueError('Manifest count mismatch')
    if manifest.get('counts_by_expected_status')!=dict(Counter(r['expected_status'] for r in rows)):raise ValueError('Manifest status counts mismatch')
    date.fromisoformat(manifest['data_cutoff'])
    snapshot=store.report.corpus_snapshot_as_of
    mapped={};checks=[];migrations=[]
    from vn_labor_online.retrieval import as_evidence,temporal_filter
    for uid,entry in evidence.items():
        loc=locator(entry['locator']);unit=store.units_by_id.get(uid)
        # Same ID must still identify exactly the annotated content and source.
        if unit is not None:
            if unit.get('document_id')!=entry['source_document_id']:raise ValueError('Gold document mismatch: '+uid)
            candidates=[unit]
        else:
            # Resolve a changed build only against the same law AND text. This is
            # migration, never a guarantee that a newer legal version is equal.
            candidates=[u for u in store.units if
                (u.get('instrument_number') or u.get('document_number'))=='45/2019/QH14'
                and all(str(u.get(k) or '')==v for k,v in loc.items())
                and norm(entry['evidence_text'])==norm(u.get('source_text') or u['text'])]
            if not candidates:raise ValueError('Unresolved Gold evidence; review new build: '+uid)
            migrations.append(uid)
        for unit in candidates:
            if not all(str(unit.get(k) or '')==v for k,v in loc.items()):raise ValueError('Gold locator mismatch: '+uid)
            if norm(entry['evidence_text'])!=norm(unit.get('source_text') or unit['text']):
                raise ValueError('Gold quotation differs from corpus: '+uid)
            if unit.get('source_url')!=entry.get('source_url'):raise ValueError('Gold source URL mismatch: '+uid)
        mapped[uid]=candidates
        checks.append({'evidence_id':uid,'resolved_ids':[u['unit_id'] for u in candidates],
            'locator':entry['locator'],'text_match':'WHITESPACE_NFC_ONLY','document_match':True,
            'source_url_match':True,'provision_temporal_verified':all(bool(u.get('provision_temporal_verified')) for u in candidates)})
    result=[];questions=[]
    for original in rows:
        qid=original['question_id'];status=original['expected_status']
        if status not in STATUSES:raise ValueError('Unknown expected status: '+qid)
        date.fromisoformat(original['applicable_date'])
        if not original.get('question','').strip() or not original.get('gold_answer','').strip():raise ValueError('Empty question/reference: '+qid)
        refs=original['gold_evidence_ids'];locs=original['gold_evidence_locators']
        if not refs or len(refs)!=len(set(refs)) or len(refs)!=len(locs):raise ValueError('Invalid qrels: '+qid)
        if not isinstance(original.get('missing_facts'),list):raise ValueError('Missing facts must be a list: '+qid)
        if status=='NEED_MORE_FACTS' and not original['missing_facts']:raise ValueError('No missing facts: '+qid)
        for detail in original.get('evidence_details',[]):
            entry=evidence.get(detail.get('evidence_id'))
            if not entry or detail['evidence_id'] not in refs or locator(detail['locator'])!=locator(entry['locator']):
                raise ValueError('Invalid evidence_details: '+qid)
            if norm(detail['evidence_excerpt']) not in norm(entry['evidence_text']):raise ValueError('Altered evidence excerpt: '+qid)
        groups=[];portable=[]
        for uid,loc in zip(refs,locs):
            if uid not in mapped:raise ValueError('Unknown catalog ID: '+qid)
            if locator(loc)!=locator(evidence[uid]['locator']):raise ValueError('Row/catalog locator mismatch: '+qid)
            if original['source_document_id']!=evidence[uid]['source_document_id'] or original['source_url']!=evidence[uid]['source_url']:
                raise ValueError('Row/catalog document or source mismatch: '+qid)
            active,_=temporal_filter([as_evidence(u,1,'gold_mapping',1) for u in mapped[uid]],original['applicable_date'],strict=False)
            group=sorted({e.unit_id for e in active})
            if not group:raise ValueError('No dated Gold evidence: '+qid)
            groups.append(group)
            portable.append([{**locator(loc),'instrument_number':'45/2019/QH14'}])
        beyond=bool(snapshot and original['applicable_date']>snapshot)
        row={'id':qid,'question':original['question'],'category':original['category'],
            'query_date':original['applicable_date'],'reference_answer':original['gold_answer'],
            'expected_status':status,'missing_facts':original['missing_facts'],
            'required_groups':groups,'required_group_locators':portable,
            'corpus_fingerprint':fingerprint,'review_status':'DRAFT','reviewer':None,'reviewed_at':None,
            'source_annotation':copy.deepcopy(original),'gold_candidate':True,
            'reference_cutoff':manifest.get('data_cutoff'),'corpus_snapshot_as_of':snapshot,
            'query_after_corpus_snapshot':beyond,
            'retrieval_eligible':status=='ANSWERABLE',
            'retrieval_exclusion_reason':None if status=='ANSWERABLE' else 'NOT_POSITIVE_ANSWERABLE_RETRIEVAL_QREL',
            # This is explicitly a draft, dataset-relative disposition metric.
            'status_scoring_scope':'DRAFT_CORPUS_RELATIVE_NOT_LEGAL_ACCURACY'}
        row['annotation_review']=notes.get(qid,{})
        row['status_score_eligible']=row['annotation_review'].get('status_score_eligible',True)
        row['qa_judge_eligible']=row['annotation_review'].get('qa_judge_eligible',True)
        questions.append({'id':qid,'expected_status':status,'retrieval_eligible':row['retrieval_eligible'],
            'query_after_corpus_snapshot':beyond})
        result.append(row)
    report={'schema_version':1,'source_zip_sha256':source_sha,
        'source_manifest':manifest,'corpus_build_id':store.report.build_id,'corpus_fingerprint':fingerprint,
        'corpus_snapshot_as_of':snapshot,'questions':len(rows),'evidence_records':len(evidence),
        'counts_by_status':dict(Counter(r['expected_status'] for r in rows)),
        'counts_by_category':dict(Counter(r['category'] for r in rows)),
        'retrieval_questions':sum(r['retrieval_eligible'] for r in result),
        'retrieval_excluded_ids':[r['id'] for r in result if not r['retrieval_eligible']],
        'status_scoring_excluded_review_ids':[r['id'] for r in result if not r['status_score_eligible']],
        'annotation_review_notes':notes,
        'duplicate_question_texts':[q for q,n in Counter(norm(r['question']) for r in rows).items() if n>1],
        'query_after_snapshot_ids':[r['id'] for r in result if r['query_after_corpus_snapshot']],
        'migrated_evidence_ids':migrations,'mapping_status':'PASS','legal_approval':'NOT_APPROVED',
        'warnings':['Candidate labels and non-exhaustive evidence, not legal expert Gold.',
            'Reference cutoff is a dataset assertion, not proof of corpus completeness.',
            'Future-law abstention is corpus-relative, not a universal legal answer.',
            'Single consolidated law; no independent coverage of all labour law, historical law or dialogue.'],
        'evidence_checks':checks,'question_checks':questions}
    return result,report

def select_rows(rows,limit):
    """Deterministic, stratified smoke sample; never call it all 100."""
    if limit is None:return list(rows)
    if type(limit) is not int or limit<1:raise ValueError('labor_limit must be positive or null')
    buckets={}
    for row in rows:buckets.setdefault((row.get('category',''),row.get('expected_status','')),[]).append(row)
    selected=[]
    while buckets and len(selected)<limit:
        for key in list(buckets):
            selected.append(buckets[key].pop(0))
            if not buckets[key]:del buckets[key]
            if len(selected)==limit:break
    return selected

def status_comparison(expected,actual):
    # A partial answer is informative but not a complete ANSWERABLE result.
    # Actual dispositions alone NEVER establish substantive legal correctness.
    if not expected:return None
    acceptable={'ANSWERABLE':{'SUFFICIENT'},'NEED_MORE_FACTS':{'NEED_MORE_FACTS'},
                'INSUFFICIENT_EVIDENCE':{'INSUFFICIENT_EVIDENCE','ABSTAIN'}}
    return actual in acceptable[expected]
