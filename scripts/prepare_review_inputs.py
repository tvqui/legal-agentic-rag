"""Create review queues from a Kaggle result ZIP without approving legal facts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import yaml


def rows(archive: zipfile.ZipFile, name: str) -> list[dict]:
    return [json.loads(line) for line in archive.read('artifacts/'+name).splitlines() if line.strip()]


def build(archive_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True,exist_ok=True)
    with archive_path.open('rb') as stream:
        archive_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    with zipfile.ZipFile(archive_path) as archive:
        bad=archive.testzip()
        if bad: raise ValueError(f'Bad ZIP member: {bad}')
        manifest=rows(archive,'00_manifest/files.jsonl')
        registry=rows(archive,'02_registry/documents.jsonl')
        changes=rows(archive,'04_knowledge/legal_changes.jsonl')
        quarantine=rows(archive,'03_structure/quarantined_provisions.jsonl')
        by_file={r['file_id']:r for r in registry}
        by_document={r['document_id']:r for r in registry}
        sources={}
        for file in manifest:
            doc=by_file.get(file['file_id'],{})
            sources[file['relative_path']]={
                'sha256':file['sha256'],'source_group':file.get('source_group'),
                'candidate_source_url':doc.get('source_url') or None,
                'source_provider':None,'source_url':None,'collected_at':None,
                'official_source':False,'metadata_verified':False,
                'reviewer':None,'reviewed_at':None,'review_evidence':None,
                'review_note':'Confirm the exact source file/URL, collection record and authority before copying to config/source_catalog.yaml',
            }
        (output_dir/'source_catalog_review_draft.yaml').write_text(
            yaml.safe_dump({'sources':sources},allow_unicode=True,sort_keys=False),encoding='utf-8')
        with (output_dir/'legal_change_review_queue.jsonl').open('w',encoding='utf-8') as stream:
            for change in changes:
                doc=by_document.get(change['source_document_id'],{})
                row={**change,'source_sha256':doc.get('sha256'),
                     'candidate_source_url':doc.get('source_url'),
                     'review_status':'DRAFT','reviewer':None,'reviewed_at':None,
                     'review_evidence':None,'exclusion_reason':None}
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        with (output_dir/'quarantine_review_queue.jsonl').open('w',encoding='utf-8') as stream:
            for provision in quarantine:
                stream.write(json.dumps({**provision,'review_status':'DRAFT',
                                         'reviewer':None,'review_note':None},ensure_ascii=False)+'\n')
    report={'archive':str(archive_path),'archive_sha256':archive_sha,
            'source_records':len(manifest),'legal_change_candidates':len(changes),
            'quarantined_rows':len(quarantine),'approved_records_created':0}
    (output_dir/'review_input_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output directory. Required to prevent overwriting an existing review set.',
    )
    args=parser.parse_args()
    print(json.dumps(build(args.archive,args.output),ensure_ascii=False,indent=2))
