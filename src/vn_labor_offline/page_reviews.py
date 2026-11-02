"""Explicit, SHA-bound page dispositions; never infer blank scans from OCR failure."""
from pathlib import Path
import hashlib
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
        if rule.get('action') not in {'NO_BODY_TEXT','ROTATE','TEXT_OVERRIDE'}:
            raise ValueError('Invalid page review action')
        if rule['action']=='ROTATE' and rule.get('degrees') not in {90,180,270}:
            raise ValueError('Invalid page rotation')
        if rule['action']=='TEXT_OVERRIDE':correction_text(rule,cfg)
    return pages


def correction_text(rule,cfg):
    allowed=(Path(cfg['project_root'])/'review/corrections').resolve()
    path=(Path(cfg['project_root'])/str(rule.get('path',''))).resolve()
    if not path.is_relative_to(allowed) or not path.is_file():raise ValueError('Page correction outside correction root')
    data=path.read_bytes()
    if not data or len(data)>100000:
        raise ValueError('Page correction SHA/size mismatch')
    # Git on Windows may check text out with CRLF. Bind the canonical UTF-8/LF
    # text used by extraction, while the source PDF SHA still binds the image.
    text=data.decode('utf-8').replace('\r\n','\n')
    if hashlib.sha256(text.encode('utf-8')).hexdigest()!=rule.get('text_sha256'):
        raise ValueError('Page correction SHA/size mismatch')
    if not text.strip() or '\x00' in text:raise ValueError('Invalid page correction text')
    if rule.get('review_kind') not in {'AI_VISUAL_TRANSCRIPTION','HUMAN_TRANSCRIPTION'}:
        raise ValueError('Page correction must declare its review kind')
    return text
