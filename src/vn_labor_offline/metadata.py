from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
import yaml
from .util import stable_id, write_jsonl

DOCNO_RE = re.compile(
    r"(?<!\d)(\d{1,4}/(?:\d{4}/)?(?:QH\d+|QH\d{1,2}|NĐ-CP|ND-CP|TT-[A-ZĐ]+(?:TBXH|NV)?|TT-BLĐTBXH|TT-BNV|NQ-HĐTP|NQ-UBTVQH\d+|UBTVQH\d+|VBHN-VPQH|QĐ-BHXH|QD-BHXH))(?!\w)",
    re.I,
)
DATE_DMY = re.compile(r"(?:ngày\s*)?(\d{1,2})[/-](\d{1,2})[/-](\d{4})", re.I)
DATE_WORDS = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I)
EFFECTIVE_PATTERNS = [
    re.compile(r"có hiệu lực(?: thi hành)?(?: kể từ)?\s*(?:từ)?\s*ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I),
    re.compile(r"có hiệu lực(?: thi hành)?(?: kể từ)?\s*(?:từ)?\s*ngày\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})", re.I),
]

ISSUER_HINTS = [
    ("QUỐC HỘI", "Quốc hội"), ("ỦY BAN THƯỜNG VỤ QUỐC HỘI", "Ủy ban Thường vụ Quốc hội"),
    ("CHÍNH PHỦ", "Chính phủ"), ("BỘ LAO ĐỘNG", "Bộ Lao động - Thương binh và Xã hội"),
    ("BỘ NỘI VỤ", "Bộ Nội vụ"), ("HỘI ĐỒNG THẨM PHÁN", "Hội đồng Thẩm phán TANDTC"),
    ("BẢO HIỂM XÃ HỘI VIỆT NAM", "Bảo hiểm xã hội Việt Nam"),
]

METADATA_FIELDS={'document_number','source_document_number','instrument_number','instrument_type','document_type',
    'title','issuer','promulgated_date','effective_from','effective_to','valid_from','valid_to','status','legal_status','source_url',
    'version_role','consolidation_as_of','status_checked_at','metadata_verified','temporal_verified','short_document_verified',
    'binding','canonical_for_text','language','authority_rank','citation_aliases','policy_series','case_number'}


def checked_metadata(values):
    unknown=set(values)-METADATA_FIELDS-{'sha256'}
    if unknown: raise ValueError(f'Unknown/protected metadata fields: {sorted(unknown)}')
    return {key:value for key,value in values.items() if key in METADATA_FIELDS and value is not None}


def iso_date(d: str, m: str, y: str) -> str:
    try: return datetime(int(y), int(m), int(d)).date().isoformat()
    except Exception: return ""


def find_doc_number(text: str, filename: str) -> str:
    sample = filename
    m = DOCNO_RE.search(sample)
    if m:
        return m.group(1).upper().replace("ND-CP", "NĐ-CP").replace("QD-BHXH", "QĐ-BHXH")

    # Official download filenames normally replace legal slashes with '-' or '_'.
    # Normalize Vietnamese Đ only for matching, and allow a suffix after the legal number.
    stem = Path(filename).stem.upper().replace("Đ", "D")
    pats = [
        (r"(?<!\d)(\d{1,4})[-_](\d{4})[-_](QH\d+)(?=$|[-_ (])", lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}"),
        (r"(?<!\d)(\d{1,4})[-_](\d{4})[-_]ND[-_]CP(?=$|[-_ (])", lambda m: f"{m.group(1)}/{m.group(2)}/NĐ-CP"),
        (r"(?<!\d)(\d{1,4})[-_](\d{4})[-_]TT[-_](BLDTBXH|BNV)(?=$|[-_ (])", lambda m: f"{m.group(1)}/{m.group(2)}/TT-{m.group(3)}"),
        (r"(?<!\d)(\d{1,4})[-_](\d{4})[-_]NQ[-_]HDTP(?=$|[-_ (])", lambda m: f"{m.group(1)}/{m.group(2)}/NQ-HĐTP"),
        (r"(?<!\d)(\d{1,4})[-_](\d{4})[-_]NQ[-_]UBTVQH(\d+)(?=$|[-_ (])", lambda m: f"{m.group(1)}/{m.group(2)}/NQ-UBTVQH{m.group(3)}"),
        (r"(?<!\d)(\d{1,4})[-_](\d{4})[-_]UBTVQH(\d+)(?=$|[-_ (])", lambda m: f"{m.group(1)}/{m.group(2)}/UBTVQH{m.group(3)}"),
        (r"(?<!\d)(\d{1,4})[-_]QD[-_]BHXH(?=$|[-_ (])", lambda m: f"{m.group(1)}/QĐ-BHXH"),
        (r"(?<!\d)(\d{1,4})[-_]VBHN[-_]VPQH(?=$|[-_ (])", lambda m: f"{m.group(1)}/VBHN-VPQH"),
    ]
    for pat, fmt in pats:
        fm = re.search(pat, stem)
        if fm:
            return fmt(fm).replace('TT-BLDTBXH','TT-BLĐTBXH')

    # A few official files omit the year in the filename but expose it in extracted text.
    for line in text[:3000].splitlines():
        if re.match(r'^\s*(?:(?:Luật|Bộ luật|Nghị định|Thông tư|Nghị quyết)\s+)?Số\s*:',line,re.I):
            m=DOCNO_RE.search(line)
            if m: return m.group(1).upper().replace('ND-CP','NĐ-CP')
    return ""


def find_effective_from(text: str) -> str:
    # Only an instrument's own commencement sentence. Never infer from VBHN footnotes.
    normalized=text.replace('Iực','lực')
    normalized=re.sub(r'(?i)biệu\s*[- ]?lực','hiệu lực',normalized)
    normalized=re.sub(r'(?i)(?<=\d)[Il](?=\s*(?:tháng|năm|[/-]))','1',normalized)
    normalized=re.sub(r'(?i)\bO(?=\d)','0',normalized)
    normalized=re.sub(r'(?i)\btù\s+ngày\b','từ ngày',normalized)
    normalized=re.sub(r'(?i)(\d)(năm\b)',r'\1 \2',normalized)
    dates=set()
    # Require the instrument itself at the start of a physical line. Legal OCR
    # often drops the dot after a clause number and does not terminate headings.
    subjects=list(re.finditer(
        r'(?:^|(?<=[.!?])\s+)\s*(?:\d+\s*(?:[.)]\s*)?)?(?:Bộ luật|Luật|Nghị định|Thông tư|Nghị quyết) này\b',
        normalized,re.I|re.M))
    for index,subject in enumerate(subjects):
        end=subjects[index+1].start() if index+1<len(subjects) else len(normalized)
        end=min(end,subject.start()+500)
        next_clause=re.search(r'\n\s*\d+\s*(?:[.)]\s*)?\S',normalized[subject.end():end])
        if next_clause: end=subject.end()+next_clause.start()
        sentence=normalized[subject.start():end]
        for pat in EFFECTIVE_PATTERNS:
            for m in pat.finditer(sentence):
                value=iso_date(*m.groups())
                if value: dates.add(value)
    return next(iter(dates)) if len(dates)==1 else ''


def infer_issuer(text: str) -> str:
    head = re.split(r'Căn cứ|Điều\s+1\b',text[:3000],maxsplit=1,flags=re.I)[0]
    hints=sorted(ISSUER_HINTS,key=lambda item:-len(item[0]))
    for line in head.splitlines()[:25]:
        for token,issuer in hints:
            if line.strip().upper().startswith(token): return issuer
        if line.strip().upper().startswith(('TÒA ÁN NHÂN DÂN','TOÀ ÁN NHÂN DÂN')): return line.strip()
    return ""


def issuer_from_number(number: str) -> str:
    upper=(number or '').upper()
    if re.search(r'/QH\d+$',upper): return 'Quốc hội'
    if upper.endswith('/NĐ-CP'): return 'Chính phủ'
    if '/TT-BNV' in upper: return 'Bộ Nội vụ'
    if '/TT-BLĐTBXH' in upper: return 'Bộ Lao động - Thương binh và Xã hội'
    if '/NQ-HĐTP' in upper: return 'Hội đồng Thẩm phán TANDTC'
    if 'UBTVQH' in upper: return 'Ủy ban Thường vụ Quốc hội'
    return ''


def infer_title(text: str, row: dict) -> str:
    lines = [x.strip() for x in text[:6000].splitlines() if x.strip()]
    for i,line in enumerate(lines):
        if re.match(r'^(Căn cứ|Điều\s+\d)',line,re.I): break
        if re.match(r'^(BỘ LUẬT|LUẬT|NGHỊ ĐỊNH|THÔNG TƯ|NGHỊ QUYẾT|VĂN BẢN HỢP NHẤT)(?:\s|$)',line) and not re.search(r'ban hành kèm theo',line,re.I):
            title=[line]
            for following in lines[i+1:i+4]:
                if re.match(r'^(Căn cứ|Điều|Số:|\(?Ban hành kèm)',following,re.I): break
                title.append(following)
            return ' '.join(title)[:350]
    return Path(row["filename"]).stem.replace("_", " ")


def load_overrides(project_root: Path) -> dict:
    p = project_root / "config" / "metadata_overrides.yaml"
    if not p.exists(): return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("overrides", {})


def build_registry(extracted: list[dict], cfg: dict, output_dir: Path) -> list[dict]:
    overrides = load_overrides(cfg["project_root"])
    catalog_path=cfg['project_root']/'config/source_catalog.yaml'
    catalog=(yaml.safe_load(catalog_path.read_text(encoding='utf-8')) or {}).get('sources',{}) if catalog_path.exists() else {}
    rows = []
    for r in extracted:
        text = r.get("text", "")
        source_kind = r["document_type_hint"]
        legal=r['source_group'] in {'LEGAL_DOCUMENT','CONSOLIDATED'}
        doc_number = find_doc_number(text, r['filename']) if legal else ''
        role=source_kind if source_kind in {'HISTORICAL','CONSOLIDATED'} else 'ORIGINAL'
        own_number=doc_number
        instrument_number=doc_number if legal and role!='CONSOLIDATED' else ''
        case_number=''
        if r['source_group']=='JUDICIAL':
            match=re.search(r'(\d{1,4})[-/](\d{4})[-/]((?:LĐ|LD)[A-ZĐ-]*|AL)(?=$|[_. ])',Path(r['filename']).stem,re.I)
            if match: case_number='/'.join(match.groups()).upper()
            else:
                match=re.search(r'^\s*(?:Bản án|Quyết định|Án lệ)(?:\s+số)?\s*:?\s*(\d+/\d{4}/[A-ZĐ-]+)',text[:1200],re.M|re.I)
                if match: case_number=match.group(1).upper()
        from .segmentation import segment_document
        main='\n'.join(s['text'] for s in segment_document({'document_id':r['file_id']},text) if s['segment_type']=='MAIN_BODY')
        effective=find_effective_from(main) if legal and role!='CONSOLIDATED' else ''
        title = infer_title(text, r)
        record = {
            "document_id": stable_id(r['sha256'], r["relative_path"], prefix="doc"),
            "file_id": r["file_id"],
            "document_number": doc_number,
            "title": title,
            "document_type": source_kind,
            "source_group": r["source_group"],
            "issuer": infer_issuer(text),
            "promulgated_date": "",
            "effective_from": effective,
            "effective_to": "",
            "status": "UNKNOWN" if legal else 'NOT_APPLICABLE',
            "binding": bool(r["binding_default"]),
            "canonical_for_text": source_kind not in {"ILO", "OFFICIAL_GUIDANCE"},
            "source_url": "",
            "relative_path": r["relative_path"],
            "sha256": r["sha256"],
            "text_chars": r.get("text_chars", 0),
            "needs_ocr": r.get("needs_ocr", False),
            'instrument_number':instrument_number,'source_document_number':own_number,
            'case_number':case_number,'cited_document_numbers':sorted(set(m.group(0).upper() for m in DOCNO_RE.finditer(text))),
            'version_role':role,'language':'en' if source_kind=='ILO' else 'vi',
            'authority_rank':100 if legal else 50 if r['source_group']=='JUDICIAL' else 10,
            'metadata_verified':False,'temporal_verified':False,
            'provenance':{'file_id':r['file_id'],'sha256':r['sha256'],'relative_path':r['relative_path']},
            'metadata_evidence':{'effective_from':'own_commencement_clause' if effective else 'unresolved'},
        }
        head=re.split(r'Căn cứ|Điều\s+1\b',text[:1500],maxsplit=1,flags=re.I)[0]
        dates={iso_date(*m.groups()) for m in DATE_WORDS.finditer(head)}-{''}
        if len(dates)==1 and legal: record['promulgated_date']=next(iter(dates))
        ov = overrides.get(r['relative_path']) or overrides.get(r["filename"]) or (overrides.get(doc_number) if role!='CONSOLIDATED' else {}) or {}
        record.update(checked_metadata(ov))
        source=catalog.get(r['relative_path']) or catalog.get(r['filename']) or {}
        if source.get('sha256') and source['sha256']!=r['sha256']:
            raise ValueError(f"Source catalog SHA mismatch: {r['relative_path']}")
        record.update(checked_metadata(source))
        if not legal:
            record['document_number']=''; record['instrument_number']=''
        elif role!='CONSOLIDATED':
            record['instrument_number']=record.get('instrument_number') or record['document_number']
            record['document_number']=record['instrument_number']
        number=record.get('instrument_number','')
        if legal and not record.get('issuer'):
            record['issuer']=issuer_from_number(number)
            if record['issuer']: record['metadata_evidence']['issuer']='instrument_number_authority'
        record['instrument_type']=next((typ for token,typ in [('QH','LAW'),('NĐ-CP','DECREE'),('TT-','CIRCULAR'),('UBTVQH','RESOLUTION'),('NQ-','RESOLUTION')] if token in number),'UNKNOWN') if legal else 'NOT_APPLICABLE'
        if 'UBTVQH' in number: record['instrument_type']='RESOLUTION'
        if source.get('instrument_type'): record['instrument_type']=source['instrument_type']
        record['legal_status']=record.get('legal_status',record['status'])
        record['status']=record['legal_status']
        for field in ('effective_from','effective_to','promulgated_date','consolidation_as_of','status_checked_at'):
            record[field]=str(record.get(field) or '')
        # Keep architecture terminology alongside the legacy effective_* names.
        # Both are sourced from the same curated metadata and remain explicit
        # when validity is unknown.
        record['valid_from']=record['effective_from']
        record['valid_to']=record['effective_to']
        record['version_id']=record['document_id']
        from .temporal import instrument_id
        record['instrument_id']=instrument_id(record) if legal else ''
        record['provenance']['source_url']=record.get('source_url','')
        if r.get('text_source'):
            record['provenance']['full_text_source']=r['text_source']
        rows.append(record)
    write_jsonl(output_dir / "02_registry" / "documents.jsonl", rows)
    try:
        import pandas as pd
        pd.DataFrame(rows).to_csv(output_dir / "02_registry" / "documents.csv", index=False, encoding="utf-8-sig")
    except Exception:
        pass
    return rows
