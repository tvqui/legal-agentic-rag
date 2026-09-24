"""Rebuild upstream semantics in an isolated directory using saved extraction.

This is a regression review, not a successful OCR rerun or a production migration.
"""
import argparse,json
from pathlib import Path
from vn_labor_offline.config import load_yaml,resolve_paths
from vn_labor_offline.pipeline import construct_from_extracted
from vn_labor_offline.util import read_jsonl,write_jsonl

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/pipeline.yaml')
    parser.add_argument('--refresh-native',action='store_true',help='Read PDF text again with new cleaning; explicitly disables OCR in this isolated review')
    args=parser.parse_args()
    cfg=resolve_paths(load_yaml(args.config),args.config)
    original=cfg['output_dir']; cfg['output_dir']=original/'review_v3'
    extracted=list(read_jsonl(original/'01_extracted/documents.jsonl'))
    if not extracted: raise SystemExit('No existing extraction to review')
    if args.refresh_native:
        import copy
        from vn_labor_offline.extract import extract_one,extract_docx
        from vn_labor_offline.cleaning import clean_text
        native_cfg=copy.deepcopy(cfg); native_cfg['extraction']['use_docling']='never'
        refreshed=[]
        for row in extracted:
            if row.get('extension') in {'.pdf','.html','.htm','.docx','.txt'}:
                row=extract_one(row,native_cfg,cfg['output_dir'])
            elif row.get('extension')=='.doc':
                converted=original/'01_extracted/converted_docx'/(Path(row['filename']).stem+'.docx')
                if converted.exists():
                    text=clean_text(extract_docx(converted))
                    row={**row,'text':text,'text_chars':len(text),'extraction_method':'cached_docx_v3_cleaning'}
            refreshed.append(row)
        extracted=refreshed
    write_jsonl(cfg['output_dir']/'01_extracted/documents.jsonl',extracted)
    write_jsonl(cfg['output_dir']/'00_manifest/files.jsonl',read_jsonl(original/'00_manifest/files.jsonl'))
    report=construct_from_extracted(cfg,extracted,build_indexes=False)
    print(json.dumps(report,ensure_ascii=False,indent=2))
