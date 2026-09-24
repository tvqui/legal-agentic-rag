"""Semantic checks independent of index construction; no inferred legal facts."""
import hashlib,json
from collections import Counter
from datetime import date
from .util import read_jsonl
from .temporal import instrument_key


def quality_issues(registry,extracted,provisions,nodes,edges,out,cfg=None):
    issues=[]; settings=cfg or {}; by_file={x['file_id']:x for x in extracted}
    docs={d['document_id']:d for d in registry}
    segments={s.get('segment_id'):s for s in read_jsonl(out/'03_structure/segments.jsonl')}
    def error(kind,**detail): issues.append({'severity':'ERROR','type':kind,**detail})
    for d in registry:
        legal=d.get('source_group') in {'LEGAL_DOCUMENT','CONSOLIDATED'}
        if not legal: continue
        for field in ('instrument_number','title','issuer','promulgated_date','source_url'):
            if not d.get(field): error('MISSING_'+field.upper(),document_id=d['document_id'])
        if not d.get('metadata_verified'): error('UNVERIFIED_METADATA',document_id=d['document_id'])
        if not d.get('temporal_verified'): error('UNVERIFIED_TEMPORAL_METADATA',document_id=d['document_id'])
        dates={}
        for field in ('promulgated_date','effective_from','effective_to','valid_from','valid_to','consolidation_as_of'):
            if d.get(field):
                try: dates[field]=date.fromisoformat(str(d[field]))
                except (TypeError,ValueError): error('INVALID_DATE',document_id=d['document_id'],field=field)
        if dates.get('effective_from') and dates.get('effective_to') and dates['effective_to']<=dates['effective_from']:
            error('TEMPORAL_CONTRADICTION',document_id=d['document_id'])
        if dates.get('valid_from') and dates.get('valid_to') and dates['valid_to']<=dates['valid_from']:
            error('TEMPORAL_VALIDITY_CONTRADICTION',document_id=d['document_id'])
        for effective,valid in (('effective_from','valid_from'),('effective_to','valid_to')):
            if str(d.get(effective) or '') != str(d.get(valid) or ''):
                error('TEMPORAL_ALIAS_MISMATCH',document_id=d['document_id'],effective_field=effective,valid_field=valid)
        if d.get('version_role')=='CONSOLIDATED' and not d.get('consolidation_as_of'):
            error('MISSING_CONSOLIDATION_AS_OF',document_id=d['document_id'])
        x=by_file.get(d['file_id'],{})
        if x.get('extension')=='.pdf' or x.get('text_source'):
            pages=x.get('page_provenance',[])
            if not pages or len(pages)!=x.get('page_count',len(pages)) or [p.get('page') for p in pages]!=list(range(1,len(pages)+1)):
                error('MISSING_PAGE_PROVENANCE',document_id=d['document_id'])
            if any(p.get('ocr_status') in {'FAILED','DISABLED'} or not p.get('blank') and p.get('chars',0)==0 for p in pages):
                error('INCOMPLETE_PAGE_EXTRACTION',document_id=d['document_id'])
        if 0<x.get('text_chars',0)<1200 and not d.get('short_document_verified'):
            error('SHORT_LEGAL_DOCUMENT_REVIEW',document_id=d['document_id'])
    for p in provisions:
        if p.get('segment_type')!='MAIN_BODY': error('NON_MAIN_BODY_PROVISION',provision_id=p['provision_id'])
        if not p.get('canonical_path'): error('MISSING_CANONICAL_PATH',provision_id=p['provision_id'])
        if p.get('source_unit_type') == 'PDF_PAGE' and p.get('page_status') != 'RESOLVED':
            error('MISSING_PAGE_SPAN',provision_id=p['provision_id'])
        if p.get('source_unit_type') != 'PDF_PAGE' and p.get('page_status') != 'NOT_APPLICABLE':
            error('INVALID_NONPAGINATED_PAGE_STATUS',provision_id=p['provision_id'])
        if p.get('char_start') is None or p.get('char_end') is None or p.get('line_start') is None or p.get('line_end') is None or not p.get('segment_id'):
            error('MISSING_PROVISION_PROVENANCE',provision_id=p['provision_id'])
            continue
        segment=segments.get(p['segment_id'])
        start=p['char_start']; end=p['char_end']; line_start=p['line_start']; line_end=p['line_end']
        valid_span=(segment is not None and p.get('span_scope')=='SEGMENT_TEXT' and
                    isinstance(start,int) and isinstance(end,int) and 0<=start<end<=len(segment.get('text','')) and
                    isinstance(line_start,int) and isinstance(line_end,int) and
                    segment.get('line_start',0)<=line_start<=line_end<=segment.get('line_end',0))
        if valid_span:
            source_lines=[x.strip() for x in segment['text'][start:end].splitlines() if x.strip()]
            provision_lines=[x.strip() for x in p.get('text','').splitlines() if x.strip()]
            valid_span=source_lines==provision_lines
        if not valid_span:
            error('INVALID_PROVISION_PROVENANCE',provision_id=p['provision_id'],segment_id=p.get('segment_id'))
            continue
        document_text=by_file.get(docs.get(p['document_id'],{}).get('file_id'),{}).get('text','')
        document_start,document_end=p.get('document_char_start'),p.get('document_char_end')
        if not (isinstance(document_start,int) and isinstance(document_end,int) and
                0<=document_start<document_end<=len(document_text) and
                document_text[document_start:document_end]==segment['text'][start:end]):
            error('INVALID_DOCUMENT_PROVENANCE',provision_id=p['provision_id'])
            continue
        source=by_file.get(docs.get(p['document_id'],{}).get('file_id'),{})
        pages=[row['page'] for row in source.get('page_provenance',[]) if
               row.get('text_start',0)<document_end and row.get('text_end',0)>document_start]
        if source.get('page_provenance') and (not pages or p.get('page_start')!=min(pages) or
            p.get('page_end')!=max(pages)):
            error('INVALID_PROVISION_PAGE_PROVENANCE',provision_id=p['provision_id'])
    for key,count in Counter(p.get('canonical_path') for p in provisions).items():
        if key and count>1: error('DUPLICATE_CANONICAL_PATH',canonical_path=key,count=count)
    ns={n['id']:n for n in nodes}
    for e in edges:
        if e['type']=='VERSION_OF':
            d=docs.get(e['source']); anchor=ns.get(e['target'],{})
            if not d or not d.get('instrument_number') or anchor.get('label')!='LegalInstrument' or anchor.get('properties',{}).get('canonical_key')!=instrument_key(d):
                error('INVALID_VERSION_OF',edge_id=e['id'])
    threshold=float(settings.get('knowledge',{}).get('relation_confidence_threshold',.55))
    relations=list(read_jsonl(out/'04_knowledge/relation_edges.jsonl'))
    for r in relations:
        if r['confidence']<threshold: error('RELATION_BELOW_THRESHOLD',edge_id=r['edge_id'])
        if r['source_id'] not in ns or r['target_id'] not in ns: error('DANGLING_RELATION',edge_id=r['edge_id'])
    issues.extend(read_jsonl(out/'reports/parsing_issues.jsonl'))
    issues.extend(read_jsonl(out/'reports/build_issues.jsonl'))
    units=list(read_jsonl(out/'06_indexes/retrieval_units.jsonl'))
    if not units: error('MISSING_RETRIEVAL_UNITS')
    for uid,count in Counter(u['unit_id'] for u in units).items():
        if count>1: error('DUPLICATE_UNIT_ID',unit_id=uid,count=count)
    for u in units:
        if not u.get('breadcrumb') or not u.get('provenance') or not u.get('segment_type'):
            error('INCOMPLETE_RETRIEVAL_METADATA',unit_id=u['unit_id'])
    dense=out/'06_indexes/dense/metadata.jsonl'
    if dense.exists() and list(read_jsonl(dense))!=units: error('STALE_DENSE_INDEX')
    bm25=out/'06_indexes/bm25/corpus.jsonl'
    if bm25.exists():
        actual=list(read_jsonl(bm25))
        expected=[{'id':u['unit_id'],'text':u['text'],'kind':u['kind']} for u in units]
        if actual!=expected: error('STALE_BM25_INDEX')
    load_report=out/'reports/neo4j_validation.json'
    fingerprint=hashlib.sha256(json.dumps([nodes,edges],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if not load_report.exists():
        issues.append({'severity':'INFO','type':'NEO4J_BUILD_NOT_VERIFIED'})
    else:
        report=json.loads(load_report.read_text(encoding='utf-8'))
        if not report.get('passed') or report.get('build_id')!=fingerprint: error('STALE_NEO4J_BUILD')
    return issues
