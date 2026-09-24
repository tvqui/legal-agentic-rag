from __future__ import annotations
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
import yaml
from .metadata import DOCNO_RE
from .util import stable_id, write_jsonl, read_jsonl
from .evidence import locate_evidence, locate_document_evidence

ARTICLE_REF=re.compile(r'(?:điểm\s+(?P<point>[a-zđ])\s*[,;]?\s*)?(?:khoản\s+(?P<clause>\d+)\s*)?Điều\s+(?P<article>\d+[a-zđ]?)(?!\w)',re.I)
QUALIFIER=re.compile(r'^\s*(?:(?:của|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư|Nghị quyết)\b',re.I)
OPERATIVE_PREFIX=r'^\s*(?:(?:Điều\s+\d+[a-zđ]?|\d+)[.)]\s*)?'
REL_PATTERNS=[
    ('AMENDS',re.compile(OPERATIVE_PREFIX+r'Sửa đổi(?:,?\s*bổ sung)?[^\n]{0,220}',re.I)),
    ('REPEALS',re.compile(OPERATIVE_PREFIX+r'Bãi bỏ[^\n]{0,220}',re.I)),
    ('REPLACES',re.compile(OPERATIVE_PREFIX+r'(?:(?:Văn bản|Nghị định|Thông tư) này\s+)?thay thế[^\n]{0,220}',re.I)),
    ('IMPLEMENTS',re.compile(OPERATIVE_PREFIX+r'(?:(?:Văn bản|Nghị định|Thông tư) này\s+)?(?:quy định chi tiết|hướng dẫn thi hành)[^\n]{0,220}',re.I)),
]

def norm_docno(s):
    return s.upper().replace('ND-CP','NĐ-CP').replace('TT-BLDTBXH','TT-BLĐTBXH').replace('QD-BHXH','QĐ-BHXH')

def choose_document(candidates, evidence_date=''):
    candidates=[d for d in candidates if d.get('source_group')=='LEGAL_DOCUMENT' and d.get('version_role','ORIGINAL')!='CONSOLIDATED' and d.get('language','vi')=='vi']
    if evidence_date: candidates=[d for d in candidates if not d.get('effective_from') or str(d['effective_from'])<=evidence_date]
    if not candidates: return None
    rank=max(d.get('authority_rank',0) for d in candidates)
    candidates=[d for d in candidates if d.get('authority_rank',0)==rank]
    return candidates[0] if len(candidates)==1 else None

def build_relation_edges(registry, provisions, cases, output_dir: Path, extracted=None, cfg=None):
    threshold=float((cfg or {}).get('knowledge',{}).get('relation_confidence_threshold',.55))
    by_number=defaultdict(list); by_path=defaultdict(list); edges=[]; citations=[]; legal_changes=[]
    source_provisions={p['provision_id']:p for p in provisions}
    source_cases={c['case_id']:c for c in cases}
    documents={d['document_id']:d for d in registry}
    review_path=Path((cfg or {}).get('project_root') or output_dir.parent)/'config/legal_change_reviews.yaml'
    reviewed_changes=(yaml.safe_load(review_path.read_text(encoding='utf-8')) or {}).get('changes',{}) if review_path.exists() else {}
    identities={p.get('provision_identity_id') for p in provisions if p.get('provision_identity_id')}
    segments={s['segment_id']:s['text'] for s in read_jsonl(output_dir/'03_structure/segments.jsonl')}
    by_file={row['file_id']:row for row in extracted or []}
    source_documents={d['document_id']:by_file.get(d['file_id'],{}) for d in registry}
    def evidence_location(owner, phrase):
        p=source_provisions.get(owner)
        if not p:
            case=source_cases.get(owner)
            if not case: return phrase, {}, 'UNRESOLVED'
            source=source_documents.get(case.get('document_id'),{})
            return locate_document_evidence(phrase,source.get('text',''),
                                            source.get('page_provenance',[]))
        source=source_documents.get(p['document_id'],{})
        return locate_evidence(p,phrase,segments.get(p.get('segment_id'),''),
                               source.get('text',''),source.get('page_provenance',[]))
    for d in registry:
        number=d.get('instrument_number') or (d.get('document_number') if d.get('source_group')=='LEGAL_DOCUMENT' else '')
        if number: by_number[norm_docno(number)].append(d)
    for p in provisions:
        key=(p['document_id'],str(p.get('article_number') or p['number']).lower(),str(p.get('clause_number') or (p['number'] if p['level']=='CLAUSE' else '')).lower(),str(p.get('point_number') or (p['number'] if p['level']=='POINT' else '')).lower())
        by_path[key].append(p)
    def emit(source,target,typ,evidence,confidence,method,evidence_owner=None,scope='PROVISION'):
        if confidence<threshold or source==target: return False
        evidence_text,evidence_span,evidence_status=evidence_location(evidence_owner or source,evidence)
        edges.append({'edge_id':stable_id(source,target,typ,evidence,prefix='edge'),'source_id':source,'target_id':target,'type':typ,'confidence':confidence,'evidence':evidence,
                      'evidence_text':evidence_text,'evidence_span':evidence_span,
                      'evidence_status':evidence_status,'resolution_scope':scope,
                      'method':method})
        return True
    def resolve(source,text,owner=None,date=''):
        for m in ARTICLE_REF.finditer(text):
            article=m['article'].lower(); clause=m['clause'] or ''; point=(m['point'] or '').lower()
            suffix=re.split(r'[\n.;]',text[m.end():m.end()+200],maxsplit=1)[0]
            explicit=DOCNO_RE.search(suffix); external=bool(QUALIFIER.match(suffix))
            target_doc=None; method='unresolved'; confidence=0.0
            if explicit and (external or explicit.start()<15):
                target_doc=choose_document(by_number.get(norm_docno(explicit.group()),[]),date)
                method='explicit_instrument_number'; confidence=.98
            elif external and not re.match(r'^\s*(?:(?:của|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư|Nghị quyết)\s+này\b',suffix,re.I):
                candidates=[d for d in registry if any(suffix.strip().lower().startswith(alias.lower()) for alias in d.get('citation_aliases',[]))]
                target_doc=choose_document(candidates,date); method='curated_alias'; confidence=.95
            elif owner is not None:
                target_doc=documents.get(owner); method='same_instrument'; confidence=.93
            matches=by_path.get((target_doc['document_id'],article,clause,point),[]) if target_doc else []
            target=matches[0] if len(matches)==1 else None
            if target and target['provision_id']==source: continue
            evidence=text[m.start():m.end()+len(suffix)]; status='UNRESOLVED'
            evidence_text,evidence_span,evidence_status=evidence_location(source,evidence)
            if target:
                status='BELOW_THRESHOLD' if confidence<threshold else 'RESOLVED'
                if status=='RESOLVED': emit(source,target['provision_id'],'REFERENCES' if owner else 'CITES',evidence,confidence,method)
            citations.append({'citation_id':stable_id(source,str(m.start()),evidence,prefix='cite'),'source_id':source,'raw_text':evidence,
                              'evidence_text':evidence_text,'evidence_span':evidence_span,'evidence_status':evidence_status,
                              'status':status,'confidence':confidence if target else 0,'target_id':target['provision_id'] if target else None,
                              'target_article':article,'target_clause':clause,'target_point':point,'method':method,'candidate_count':len(matches)})
    for p in provisions:
        resolve(p['provision_id'],p.get('text',''),p['document_id'])
        for line in p.get('text','').splitlines():
            for typ,pattern in REL_PATTERNS:
                match=pattern.search(line)
                if not match: continue
                for number in DOCNO_RE.finditer(match.group()):
                    target=choose_document(by_number.get(norm_docno(number.group()),[]))
                    operation={'AMENDS':'AMEND','REPEALS':'REPEAL','REPLACES':'REPLACE','IMPLEMENTS':'IMPLEMENT'}[typ]
                    change={'change_id':stable_id(p['provision_id'],operation,match.group(),number.group(),prefix='change'),
                            'operation':operation,'source_document_id':p['document_id'],
                            'source_provision_id':p['provision_id'],'target_instrument_id':None,
                            'target_provision_identity_id':None,'target_article':None,
                            'target_clause':None,'target_point':None,'resolution_scope':'UNRESOLVED',
                            'effective_from':None,'temporal_status':'UNKNOWN',
                            'evidence_text':match.group(),
                            'evidence_span':{},'evidence_status':'UNRESOLVED',
                            'method':'operative_main_body','confidence':0.0,
                            'resolution_status':'UNRESOLVED','candidate_count':0}
                    change['evidence_text'],change['evidence_span'],change['evidence_status']=evidence_location(p['provision_id'],match.group())
                    review=reviewed_changes.get(change['change_id']) or {}
                    excluded=review.get('review_status')=='EXCLUDED'
                    if target:
                        change['target_instrument_id']=target.get('instrument_id') or target['document_id']
                        change['resolution_scope']='DOCUMENT'
                        change['confidence']=.85
                        change['resolution_status']='RESOLVED'
                        change['candidate_count']=1
                        if not excluded:
                            emit(p['document_id'],target['document_id'],typ,match.group(),.85,'operative_main_body',
                                 evidence_owner=p['provision_id'],scope='DOCUMENT')
                        # When the operative sentence names a concrete
                        # Article/Clause/Point, retain that more useful
                        # document-to-provision edge as well.
                        for ref in ARTICLE_REF.finditer(match.group()):
                            article=ref['article'].lower(); clause=ref['clause'] or ''
                            point=(ref['point'] or '').lower()
                            candidates=by_path.get((target['document_id'],article,clause,point),[])
                            if len(candidates)==1:
                                change['target_provision_identity_id']=candidates[0].get('provision_identity_id')
                                change['target_article']=article
                                change['target_clause']=clause or None
                                change['target_point']=point or None
                                change['resolution_scope']='POINT' if point else 'CLAUSE' if clause else 'ARTICLE'
                                if not excluded:
                                    emit(p['provision_id'],candidates[0]['provision_id'],typ,match.group(),.82,'operative_provision',
                                         scope=change['resolution_scope'])
                    if review:
                        required=(('reviewer','reviewed_at','source_sha256','evidence','exclusion_reason') if excluded else
                                  ('reviewer','reviewed_at','source_sha256','evidence','effective_from','target_provision_identity_id'))
                        if review.get('review_status') not in {'APPROVED','EXCLUDED'} or not all(review.get(k) for k in required):
                            raise ValueError(f"Incomplete LegalChange review: {change['change_id']}")
                        if review['source_sha256']!=documents[p['document_id']].get('sha256'):
                            raise ValueError(f"LegalChange source SHA mismatch: {change['change_id']}")
                        try:
                            date.fromisoformat(str(review['reviewed_at']))
                            if not excluded: date.fromisoformat(str(review['effective_from']))
                        except (TypeError,ValueError) as exc:
                            raise ValueError(f"Invalid LegalChange review date: {change['change_id']}") from exc
                        if excluded:
                            change.update({'review_status':'EXCLUDED','resolution_scope':'OUT_OF_SCOPE',
                                'temporal_status':'REVIEWED_EXCLUSION',
                                'exclusion_reason':review['exclusion_reason'],'reviewer':review['reviewer'],
                                'reviewed_at':review['reviewed_at'],'review_evidence':review['evidence']})
                        else:
                            identity=review['target_provision_identity_id']
                            if identity not in identities or (change['target_provision_identity_id'] and
                                change['target_provision_identity_id']!=identity):
                                raise ValueError(f"LegalChange target identity mismatch: {change['change_id']}")
                            change.update({'target_provision_identity_id':identity,
                                'effective_from':review['effective_from'],'temporal_status':'REVIEWED_CHANGE',
                                'resolution_scope':'PROVISION_IDENTITY','resolution_status':'RESOLVED',
                                'review_status':'APPROVED','reviewer':review['reviewer'],
                                'reviewed_at':review['reviewed_at'],'review_evidence':review['evidence']})
                            emit(p['provision_id'],identity,typ,match.group(),.99,'reviewed_change',
                                 scope='PROVISION_IDENTITY')
                    legal_changes.append(change)
    for case in cases:
        resolve(case['case_id'],'\n'.join(case.get(k,'') for k in ('facts','reasoning','decision')),date=case.get('decision_date',''))
    result=list({e['edge_id']:e for e in edges}.values())
    write_jsonl(output_dir/'04_knowledge'/'relation_edges.jsonl',result)
    write_jsonl(output_dir/'04_knowledge'/'citations.jsonl',citations)
    write_jsonl(output_dir/'04_knowledge'/'legal_changes.jsonl',legal_changes)
    return result
