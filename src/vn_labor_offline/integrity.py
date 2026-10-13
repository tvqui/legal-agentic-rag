"""Fail early on incomplete extraction and publish observable build coverage."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

def _atomic(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)

def report_progress(output_dir,stage,completed,total,**details):
    value={'schema_version':1,'stage':stage,'completed':completed,'total':total,
        'updated_at':datetime.now(timezone.utc).isoformat(),**details}
    _atomic(Path(output_dir)/'reports/offline_build_progress.json',value)
    print('BUILD_PROGRESS '+json.dumps(value,ensure_ascii=False),flush=True)

def require_complete_extraction(rows,output_dir):
    errors=[]; seen=set()
    if not rows: errors.append({'reason':'NO_EXTRACTED_DOCUMENTS'})
    for row in rows:
        identity=row.get('file_id')
        if not identity or identity in seen:
            errors.append({'file_id':identity,'reason':'MISSING_OR_DUPLICATE_FILE_ID'})
        seen.add(identity)
        if row.get('extraction_error') or not str(row.get('text') or '').strip():
            errors.append({'file_id':identity,'path':row.get('relative_path'),'reason':'FAILED_OR_EMPTY_DOCUMENT',
                           'detail':row.get('extraction_error')})
        pages=row.get('page_provenance',[])
        if row.get('page_count',len(pages))!=len(pages):
            errors.append({'file_id':identity,'reason':'PAGE_COUNT_MISMATCH'})
        for page in pages:
            if page.get('ocr_status') in {'FAILED','DISABLED'}:
                errors.append({'file_id':identity,'path':row.get('relative_path'),'page':page.get('page'),
                               'reason':'UNREADABLE_PAGE','detail':page.get('error')})
            if page.get('page_quality_status')=='ERROR':
                errors.append({'file_id':identity,'path':row.get('relative_path'),'page':page.get('page'),
                               'reason':'PAGE_QUALITY_ERROR','reason_codes':page.get('quality_reason_codes',[])})
    # The page-quality writer supplies richer reasons than extraction workers.
    quality_path=Path(output_dir)/'reports/page_extraction_quality.json'
    if quality_path.exists():
        quality=json.loads(quality_path.read_text(encoding='utf-8'))
        if quality.get('errors',0) or quality.get('error_pages',0):
            errors.append({'reason':'PAGE_QUALITY_ERRORS','detail':quality})
    report={'schema_version':1,'passed':not errors,'documents':len(rows),'errors':errors}
    _atomic(Path(output_dir)/'reports/extraction_integrity.json',report)
    if errors:
        for error in errors[:5]:
            print('EXTRACTION_ERROR '+json.dumps({key:value for key,value in error.items() if key!='detail'},
                                                ensure_ascii=False),flush=True)
        raise RuntimeError('Extraction incomplete; see reports/extraction_integrity.json')
    return report

def write_structure_coverage(registry,provisions,output_dir):
    groups={}
    for p in provisions:
        key=p.get('document_id'); counts=groups.setdefault(key,{})
        level=p.get('level','UNKNOWN'); counts[level]=counts.get(level,0)+1
    rows=[{'document_id':d['document_id'],'document_number':d.get('document_number'),
        'document_type':d.get('document_type'),'levels':groups.get(d['document_id'],{})} for d in registry]
    _atomic(Path(output_dir)/'reports/structure_coverage.json',{
        'schema_version':1,'documents':rows,'provisions':len(provisions),
        'scope':'Parser coverage, not certification of legal completeness or OCR accuracy'})


def require_complete_provenance(registry,extracted,provisions,output_dir):
    from .quality import provision_provenance_issues
    errors=provision_provenance_issues(registry,extracted,provisions,Path(output_dir))
    report={'schema_version':1,'passed':not errors,'provisions':len(provisions),'errors':errors,
        'scope':'Exact source, annotation, document and page spans; checked before AI/index work.'}
    _atomic(Path(output_dir)/'reports/provision_provenance_integrity.json',report)
    if errors:
        for error in errors[:5]: print('PROVENANCE_ERROR '+json.dumps(error,ensure_ascii=False),flush=True)
        raise RuntimeError('Provision provenance invalid; see reports/provision_provenance_integrity.json')
    print('PROVENANCE_INTEGRITY '+json.dumps({'passed':True,'provisions':len(provisions)}),flush=True)
    return report
