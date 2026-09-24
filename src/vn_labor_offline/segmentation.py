"""Conservative, line-based segmentation; never treat a citation as an annex heading."""
import re
import unicodedata
from .util import stable_id

ARTICLE = re.compile(r'^Điều\s+\d+[a-zđ]?[.:\s]', re.I)
ATTACHMENT = re.compile(r'^(PHỤ LỤC(?:\s+[IVXLCDM\dA-Z]+)?|MẪU(?:\s+SỐ)?\s+\d+[A-Z]?)(?:\s|[.:]|$)', re.I)


def structural_line(line):
    # Match known OCR spelling errors in structural keywords only; keep original
    # source text in provisions. Never change article/clause numbers.
    s=line.strip().lstrip('#').strip()
    s=re.sub(r'^[-*]\s+(?=(?:[a-zđ][.)]|Điều|Đỉều|Phụ lục|Mẫu số))','',s,flags=re.I)
    # EasyOCR commonly varies accents in "Điều" and confuses 1/I/l or 0/O
    # inside article numbers. Normalize only a complete heading prefix; the
    # source line stored in provisions remains untouched.
    candidate=re.match(r'^([^\W\d_]{3,7})\s+([0-9IlOo]{1,4})([a-zđ]?)\s*([.:])',s,re.I)
    if candidate:
        token=''.join(c for c in unicodedata.normalize('NFD',candidate.group(1).casefold())
                      if unicodedata.category(c)!='Mn').replace('đ','d')
        # One recognition error is tolerated around the four-letter keyword.
        distance=sum(a!=b for a,b in zip(token,'dieu'))+abs(len(token)-4)
        if distance<=1:
            number=candidate.group(2).translate(str.maketrans({'I':'1','l':'1','O':'0','o':'0'}))
            s='Điều '+number+candidate.group(3)+candidate.group(4)+s[candidate.end():]
    return s


def attachment_kind(line):
    # Allow a numbered heading plus a title. Require a complete heading shape,
    # not a body sentence mentioning an annex/form.
    s=structural_line(line)
    if re.fullmatch(r'Phụ\s+[lLjJ]ục(?:\s+[IVXLCDM\d]+)?[.:]?',s,re.I): return 'ANNEX'
    if re.match(r'^Phụ\s+[lLjJ]ục\s+[IVXLCDM\d]+\s*[.:]\s+\S',s,re.I): return 'ANNEX'
    if re.match(r'^Mẫu\s+số\s*\d+[A-Z]?(?:[/.-]\d+)?(?:\s*[:.]\s*.*|\s+[-–]\s+.*)?$',s,re.I): return 'FORM'
    if s.isupper() and ATTACHMENT.match(s):
        return 'FORM' if s.startswith('MẪU') else 'ANNEX'
    return None


def segment_document(doc, text, keep_preamble=True):
    # Repair old extraction's glued uppercase chapter titles, not ordinary citations.
    def heading(match):
        return match[1]+'\n'+match[2] if match[1].isupper() else match[0]
    text=re.sub(r'^([^\n]+?)\s+(Điều\s+\d+[a-zđ]?\.\s+[^\n]+)$',heading,text,flags=re.M)
    lines=text.splitlines(); segments=[]; start=0; kind='PREAMBLE'; seen_article=False
    def emit(end):
        content='\n'.join(lines[start:end]).strip()
        if content and (kind!='PREAMBLE' or keep_preamble):
            segments.append({'segment_id':stable_id(doc['document_id'],kind,str(start+1),prefix='seg'),
                'document_id':doc['document_id'],'segment_type':kind,'text':content,
                'line_start':start+1,'line_end':end,'heading':lines[start].strip() if start<len(lines) else ''})
    for i,line in enumerate(lines):
        s=structural_line(line); new=None
        if not seen_article and ARTICLE.match(s):
            new='MAIN_BODY'; seen_article=True
        elif seen_article and len(s)<180 and attachment_kind(s):
            new=attachment_kind(s)
        elif seen_article and s.upper() in {'ĐỀ CƯƠNG BÁO CÁO','DANH MỤC'}:
            new='ANNEX'
        elif seen_article and re.match(r'^(?:Nơi nhận\s*:|KT\.\s|TM\.\s)',s):
            new='SIGNATURE'
        # Attached regulations can have their own genuine Article hierarchy.
        elif seen_article and s.upper() in {'QUY ĐỊNH','QUY CHẾ'} and kind in {'SIGNATURE','ANNEX'}:
            new='ATTACHED_REGULATION'
        if new and (new!=kind or new in {'FORM','ANNEX','ATTACHED_REGULATION'}):
            emit(i); start=i; kind=new
    emit(len(lines))
    return segments
