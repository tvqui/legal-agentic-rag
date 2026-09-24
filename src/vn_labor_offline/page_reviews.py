"""Explicit, SHA-bound page dispositions; never infer blank scans from OCR failure."""
from pathlib import Path
import yaml


def reviewed_pages(row, cfg):
    path=Path(cfg['project_root'])/'config/page_reviews.yaml'
    catalog=(yaml.safe_load(path.read_text(encoding='utf-8')) or {}).get('documents',{}) if path.exists() else {}
    record=catalog.get(row.get('relative_path'))
    if not record: return {}
    if record.get('sha256')!=row['sha256']:
        raise ValueError('Page review SHA mismatch: '+row['relative_path'])
    pages=record.get('pages',{})
    for number,rule in pages.items():
        if not isinstance(number,int) or number<1 or not rule.get('reason'):
            raise ValueError('Invalid page review entry')
        if rule.get('action') not in {'NO_BODY_TEXT','ROTATE'}:
            raise ValueError('Invalid page review action')
        if rule['action']=='ROTATE' and rule.get('degrees') not in {90,180,270}:
            raise ValueError('Invalid page rotation')
    return pages
