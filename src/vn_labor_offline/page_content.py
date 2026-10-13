"""Geometry-backed footnote separation without changing source coordinates."""
from __future__ import annotations
import hashlib, json, re, statistics
from pathlib import Path

FOOTNOTE_START=re.compile(r'^\s*(\d{1,3})\s+(?:(?:Khoản|Điều|Điểm|Cụm từ|Nội dung|Tên)\s+.*(?:được|này)|(?:Được|Bổ sung|Sửa đổi|Bãi bỏ|Thay thế)\b)',re.I)
RULE_HEADING=re.compile(r'^\s*(?:Điều\s+\d|\d+[.)]\s|[a-zđ][.)]\s|CHƯƠNG|MỤC)',re.I)


def pdf_note_candidates(page):
    """Require a legal editorial note, smaller font and lower-page location."""
    lines=[]; sizes=[]
    for block in page.get_text('dict').get('blocks',[]):
        for line in block.get('lines',[]):
            spans=[s for s in line.get('spans',[]) if s.get('text','').strip()]
            if not spans: continue
            text=''.join(s['text'] for s in spans).strip()
            size=max(s.get('size',0) for s in spans)
            sizes.extend([s.get('size',0) for s in spans for _ in range(min(100,len(s.get('text',''))))])
            lines.append({'text':text,'bbox':list(line['bbox']),'font_size':size})
    if not sizes: return []
    body_size=statistics.median(sizes); height=float(page.rect.height); result=[]
    for i,line in enumerate(lines):
        match=FOOTNOTE_START.match(line['text'])
        if not match or line['bbox'][1]<height*.65 or line['font_size']>body_size*.94: continue
        collected=[line]
        for following in lines[i+1:]:
            if (following['bbox'][1]<line['bbox'][1] or following['font_size']>body_size*.94 or
                    FOOTNOTE_START.match(following['text']) or RULE_HEADING.match(following['text'])): break
            collected.append(following)
        result.append({'schema':'pdf-footnote-v1','kind':'EDITORIAL_FOOTNOTE','marker':match[1],
            'text':'\n'.join(r['text'] for r in collected),'bbox':[min(r['bbox'][0] for r in collected),
            min(r['bbox'][1] for r in collected),max(r['bbox'][2] for r in collected),max(r['bbox'][3] for r in collected)],
            'page_height':height,'font_size':line['font_size'],'body_font_size':body_size})
    return result


def align_notes(candidates,cleaned_page,page_number,source_sha256,document_offset):
    found=[]
    for note in candidates:
        pattern=r'\s+'.join(re.escape(word) for word in note['text'].split())
        matches=list(re.finditer(pattern,cleaned_page))
        if len(matches)!=1: continue
        m=matches[0]; exact=cleaned_page[m.start():m.end()]
        found.append({**note,'text':exact,'text_sha256':hashlib.sha256(exact.encode('utf-8')).hexdigest(),
            'page':page_number,'source_sha256':source_sha256,'document_char_start':document_offset+m.start(),
            'document_char_end':document_offset+m.end(),'detection_status':'GEOMETRY_AND_EXACT_TEXT_MATCH',
            'review_status':'REVIEW_REQUIRED'})
    return found


def validated_notes(document):
    text=document.get('text',''); source_sha=(document.get('text_source') or {}).get('sha256',document.get('sha256'))
    valid=[]
    for note in document.get('non_body_annotations',[]):
        start=note.get('document_char_start'); end=note.get('document_char_end')
        if (note.get('schema')!='pdf-footnote-v1' or note.get('source_sha256')!=source_sha or
                not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(text)): continue
        exact=text[start:end]
        if (note.get('text')!=exact or note.get('text_sha256')!=hashlib.sha256(exact.encode('utf-8')).hexdigest() or
                not FOOTNOTE_START.match(exact)): continue
        bbox=note.get('bbox') or []; height=note.get('page_height',0)
        if (len(bbox)!=4 or height<=0 or bbox[1]<height*.65 or
                note.get('font_size',0)>note.get('body_font_size',0)*.94): continue
        page=next((p for p in document.get('page_provenance',[]) if p.get('page')==note.get('page')),None)
        if not page or not page.get('text_start',0)<=start<end<=page.get('text_end',0): continue
        valid.append(note)
    return valid


def segment_note_spans(segment_text,notes):
    """Map only uniquely matched, source-validated annotations into a segment."""
    spans=[]
    for note in notes:
        matches=list(re.finditer(r'\s+'.join(re.escape(w) for w in note['text'].split()),segment_text))
        if len(matches)!=1: continue
        match=matches[0]
        spans.append({'kind':'EDITORIAL_FOOTNOTE','segment_char_start':match.start(),
            'segment_char_end':match.end(),'document_char_start':note['document_char_start'],
            'document_char_end':note['document_char_end'],'source_sha256':note['source_sha256'],
            'text_sha256':note['text_sha256'],'page':note['page']})
    return sorted(spans,key=lambda s:(s['segment_char_start'],s['segment_char_end']))


def mask_segment_notes(segment_text,notes):
    """Keep original segment for evidence; mask only the parser's input."""
    chars=list(segment_text)
    for span in segment_note_spans(segment_text,notes):
        for i in range(span['segment_char_start'],span['segment_char_end']):
            if chars[i]!='\n': chars[i]=' '
    return ''.join(chars)


def refresh_document_notes(document,path:Path):
    import pymupdf
    notes=[]
    with pymupdf.open(path) as pdf:
        for page in document.get('page_provenance',[]):
            i=page['page']-1
            if not 0<=i<len(pdf): raise ValueError('Page outside source PDF')
            start=page['text_start']; end=page['text_end']
            notes.extend(align_notes(pdf_note_candidates(pdf[i]),document['text'][start:end],page['page'],
                page.get('sha256',document['sha256']),start))
    document['non_body_annotations']=notes; document['page_content_schema']='page-content-v1'
    return notes


def write_notes(extracted,output_dir:Path):
    from .util import write_jsonl
    rows=[{**n,'file_id':d['file_id'],'relative_path':d['relative_path']} for d in extracted for n in validated_notes(d)]
    write_jsonl(output_dir/'01_extracted/footnotes.jsonl',rows)
    return rows


def native_form_layer(page,text,image_coverage):
    """Do not OCR a readable digital form merely because it has dotted blanks.

    Scanned bodies, signature-only layers, replacement/control characters and
    pages without a genuine form heading cannot use this exception.
    """
    letters=sum(c.isalpha() for c in text)
    dots=len(re.findall(r'[.·…_]{4,}',text))
    if (image_coverage>.25 or letters<250 or dots<3 or
            not re.search(r'Mẫu\s+số\s*\d',text,re.I) or '\ufffd' in text or '\x00' in text): return None
    import unicodedata
    if any(unicodedata.category(c)=='Cc' for c in text if c not in '\n\r\t'): return None
    lines=[line for block in page.get_text('dict').get('blocks',[]) for line in block.get('lines',[])]
    visible=[s for line in lines for s in line.get('spans',[]) if s.get('text','').strip()]
    if not visible or any(s.get('alpha',255)==0 for s in visible): return None
    directions=[list(line.get('dir',(1,0))) for line in lines if any(s.get('text','').strip() for s in line.get('spans',[]))]
    return {'schema':'native-form-layer-v1','letters':letters,'placeholder_runs':dots,
        'image_coverage':image_coverage,'native_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'line_directions':directions,'selection':'KEEP_NATIVE_WITH_REVIEW_WARNING'}
