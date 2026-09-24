"""Review a results ZIP in isolation without OCR, models, or a database connection."""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from vn_labor_offline.config import load_yaml, resolve_paths
from vn_labor_offline.extract import extract_one, extract_docx
from vn_labor_offline.cleaning import clean_text
from vn_labor_offline.pipeline import construct_from_extracted
from vn_labor_offline.page_reviews import reviewed_pages
from vn_labor_offline.util import read_jsonl, write_jsonl


def review(archive, config, replacement_files=()):
    cfg=resolve_paths(load_yaml(config),config)
    # Fixed destination prevents accidental replacement of production artifacts.
    out=cfg['output_dir']/'review_kaggle_v4'; cfg['output_dir']=out
    with zipfile.ZipFile(archive) as z:
        extracted=[json.loads(line) for line in z.read('artifacts/01_extracted/documents.jsonl').splitlines()]
        manifest=[json.loads(line) for line in z.read('artifacts/00_manifest/files.jsonl').splitlines()]
        previous=json.loads(z.read('artifacts/reports/summary.json'))
        converted_docs={Path(n).name:z.read(n) for n in z.namelist()
                        if n.startswith('artifacts/01_extracted/converted_docx/') and n.endswith('.docx')}
    out.mkdir(parents=True,exist_ok=True)
    native_cfg=copy.deepcopy(cfg); native_cfg['extraction']['use_docling']='never'
    replacements={}
    for path in replacement_files:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        if value.get('extraction_error') or not value.get('text') or not value.get('page_provenance'):
            raise ValueError(f'Invalid replacement extraction: {path}')
        replacements[value['relative_path']]=value
    refreshed=[]
    for row in extracted:
        row['path']=str(cfg['data_dir']/row['relative_path'])
        replacement=replacements.get(row['relative_path'])
        if replacement:
            if replacement.get('sha256')!=row.get('sha256'):
                raise ValueError(f'Replacement source SHA mismatch: {row["relative_path"]}')
            original_path=row['path']
            row.clear(); row.update(replacement); row['path']=original_path
            continue
        if row['extension']=='.doc':
            payload=converted_docs.get(Path(row['filename']).stem+'.docx')
            if payload is not None:
                with tempfile.TemporaryDirectory(dir=out,prefix='review-docx-') as temporary:
                    converted=Path(temporary)/'document.docx'; converted.write_bytes(payload)
                    row['text']=clean_text(extract_docx(converted))
                row['text_chars']=len(row['text']); row['extraction_method']='review_zip_converted_docx_ordered'
        review_row={**row,'sha256':(row.get('text_source') or {}).get('sha256',row['sha256'])}
        reviews=reviewed_pages(review_row,cfg)
        if reviews and row.get('page_provenance'):
            texts=[]; offset=0
            for page in row['page_provenance']:
                content=row['text'][page['text_start']:page['text_end']]
                rule=reviews.get(page['page'],{})
                if rule.get('action')=='NO_BODY_TEXT':
                    content=''
                    page.update(blank=True,error=None,ocr_status='REVIEWED_NO_BODY_TEXT',
                                method='reviewed_no_body_text',chars=0,ocr=False,page_review=rule)
                page.update(text_start=offset,text_end=offset+len(content),cleaned_chars=len(content))
                texts.append(content); offset+=len(content)+2
            row['text']='\n\n'.join(texts); row['text_chars']=len(row['text'])
            row['needs_ocr']=any(p['ocr_status'] in {'FAILED','DISABLED'} for p in row['page_provenance'])
            if not row['needs_ocr']: row['extraction_error']=None
        if row['extension'] in {'.html','.htm'}:
            current=extract_one(row,native_cfg,out)
            if current.get('text_source') and not current.get('extraction_error'):
                row.clear(); row.update(current)
            if current.get('text_source'):
                refreshed.append({'relative_path':current['relative_path'],'text_chars':current['text_chars'],
                                  'used':not bool(current.get('extraction_error')),
                                  'extraction_error':current['extraction_error']})
    write_jsonl(out/'01_extracted/documents.jsonl',extracted)
    write_jsonl(out/'00_manifest/files.jsonl',manifest)
    report=construct_from_extracted(cfg,extracted,checklist_mode='heuristic',build_indexes=False)
    issues=list(read_jsonl(out/'reports/validation_issues.jsonl'))
    registry=list(read_jsonl(out/'02_registry/documents.jsonl'))
    by_doc={}
    for issue in issues:
        if issue.get('document_id'): by_doc.setdefault(issue['document_id'],set()).add(issue['type'])
    fields=['relative_path','document_id','sha256','document_number','instrument_number','issuer',
            'promulgated_date','effective_from','effective_to','legal_status','source_url',
            'consolidation_as_of','metadata_verified','temporal_verified','issues']
    with (out/'reports/metadata_review_queue.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore'); writer.writeheader()
        for d in registry:
            if d.get('source_group') in {'LEGAL_DOCUMENT','CONSOLIDATED'} and by_doc.get(d['document_id']):
                writer.writerow({**d,'issues':'; '.join(sorted(by_doc[d['document_id']]))})
    with Path(archive).open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    comparison={'mode':'ISOLATED_REVIEW_NO_OCR_NO_INDEX_BUILD_NO_AURA',
                'input_zip_sha256':digest,'html_full_text_refresh':refreshed,
                'verified_replacement_extractions':sorted(replacements),
                'previous_issues':previous['issues_by_type'],'review_issues':report['issues_by_type'],
                'review_counts':{k:report[k] for k in ('documents','provisions','cases','diagnostic_items','graph_nodes','graph_edges')},
                'ready_for_offline_v1':False}
    (out/'reports/comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(comparison,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--config',type=Path,default=Path('config/pipeline.yaml'))
    parser.add_argument('--replacement-json',type=Path,action='append',default=[])
    args=parser.parse_args(); review(args.archive,args.config,args.replacement_json)
