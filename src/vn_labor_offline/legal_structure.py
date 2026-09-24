from __future__ import annotations
import re
from collections import Counter
from pathlib import Path
from .util import stable_id, write_jsonl

ARTICLE_RE = re.compile(r"^\s*(?:Điều|ĐIỀU)\s+(\d+[a-zA-ZĐđ]?)\s*(?:[\.:]\s*(.*)|$)")
CLAUSE_RE = re.compile(r"^\s*(\d+)\s*[\.)]\s+(.+)$")
POINT_RE = re.compile(r"^\s*([a-zA-ZđĐ])\s*[\)\.]\s+(.+)$")
CHAPTER_RE = re.compile(r"^\s*(?:Chương|CHƯƠNG)\s+([IVXLCDM\d]+)\s*$")
SECTION_RE = re.compile(r"^\s*(?:Mục|MỤC)\s+(\d+)\s*$")


def _join(lines: list[str]) -> str:
    return "\n".join(x for x in lines if x is not None).strip()


def _locate_source_span(source_text: str, provision_text: str, search_at: int) -> tuple[int | None, int | None]:
    """Locate normalized provision lines inside one segment's original text."""
    lines=[line.strip() for line in provision_text.splitlines() if line.strip()]
    if not lines:
        return None,None
    start=source_text.find(lines[0],search_at)
    if start < 0:
        start=source_text.find(lines[0])
    if start < 0:
        return None,None
    cursor=start; end=start
    for line in lines:
        position=source_text.find(line,cursor)
        if position < 0:
            return None,None
        end=position+len(line)
        cursor=end
    return start,end


def _parse_main_body(doc: dict, text: str) -> list[dict]:
    from .segmentation import structural_line
    lines = text.splitlines()
    articles: list[dict] = []
    current_article = None
    current_clause = None
    current_point = None
    chapter = ""; section = ""
    order = 0
    quote_depth=0; ascii_quote=False

    def finish_point():
        nonlocal current_point
        if current_point:
            current_point["text"] = _join(current_point.pop("_lines"))
            current_clause["points"].append(current_point)
            current_point = None

    def finish_clause():
        nonlocal current_clause
        finish_point()
        if current_clause:
            current_clause["text"] = _join(current_clause.pop("_lines"))
            current_article["clauses"].append(current_clause)
            current_clause = None

    def finish_article():
        nonlocal current_article
        finish_clause()
        if current_article:
            current_article["text"] = _join(current_article.pop("_lines"))
            articles.append(current_article)
            current_article = None

    for line in lines:
        original=line.strip()
        s = structural_line(line)
        if not s: continue
        starts_quote=re.match(r'^[“"]\s*(?:Điều\s+\d|\d+[.)]|[a-zđ][.)])',s,re.I)
        if quote_depth or ascii_quote or starts_quote:
            target=current_point or current_clause or current_article
            if target: target['_lines'].append(original)
            quote_depth=max(0,quote_depth+s.count('“')-s.count('”'))
            if s.count('"') % 2: ascii_quote=not ascii_quote
            continue
        m = CHAPTER_RE.match(s)
        if m:
            finish_article(); chapter = m.group(1); section = ""
            continue
        m = SECTION_RE.match(s)
        if m:
            finish_article(); section = m.group(1)
            continue
        m = ARTICLE_RE.match(s)
        if m:
            finish_article(); order += 1
            no, heading = m.group(1), (m.group(2) or '').strip()
            current_article = {"number": no, "heading": heading, "_lines": [original], "clauses": [], "chapter": chapter, "section": section, "order": order}
            continue
        if current_article:
            m = CLAUSE_RE.match(s)
            if m:
                finish_clause()
                current_clause = {"number": m.group(1), "_lines": [original], "points": [], "order": len(current_article["clauses"]) + 1}
                continue
            if current_clause:
                m = POINT_RE.match(s)
                if m:
                    finish_point()
                    current_point = {"number": m.group(1).lower(), "_lines": [original], "order": len(current_clause["points"]) + 1}
                    continue
            if current_point: current_point["_lines"].append(original)
            elif current_clause: current_clause["_lines"].append(original)
            else: current_article["_lines"].append(original)
    finish_article()

    provisions: list[dict] = []
    for a in articles:
        aid = stable_id(doc["document_id"], "article", a["number"], prefix="prov")
        provisions.append({
            "provision_id": aid, "document_id": doc["document_id"], "level": "ARTICLE", "number": a["number"],
            "heading": a["heading"], "text": a["text"], "parent_id": doc["document_id"], "order": a["order"],
            "chapter": a["chapter"], "section": a["section"],
        })
        for c in a["clauses"]:
            cid = stable_id(doc["document_id"], "article", a["number"], "clause", c["number"], prefix="prov")
            provisions.append({
                "provision_id": cid, "document_id": doc["document_id"], "level": "CLAUSE", "number": c["number"],
                "heading": "", "text": c["text"], "parent_id": aid, "order": c["order"],
                "article_number": a["number"],
            })
            for p in c["points"]:
                pid = stable_id(doc["document_id"], "article", a["number"], "clause", c["number"], "point", p["number"], prefix="prov")
                provisions.append({
                    "provision_id": pid, "document_id": doc["document_id"], "level": "POINT", "number": p["number"],
                    "heading": "", "text": p["text"], "parent_id": cid, "order": p["order"],
                    "article_number": a["number"], "clause_number": c["number"],
                })
    return provisions


def parse_legal_document(doc: dict, text: str) -> list[dict]:
    from .segmentation import segment_document
    result=[]; preamble=''
    for segment in segment_document(doc,text):
        if segment['segment_type']=='PREAMBLE': preamble=segment['text']
        if segment['segment_type']!='MAIN_BODY': continue
        chapter_lines=[line for line in preamble.splitlines() if CHAPTER_RE.match(line) or SECTION_RE.match(line)]
        parsed=_parse_main_body(doc,'\n'.join(chapter_lines[-2:])+'\n'+segment['text'])
        search_at=0
        for p in parsed:
            p['segment_id']=segment['segment_id']; p['segment_type']='MAIN_BODY'
            p['article_number']=p['number'] if p['level']=='ARTICLE' else p.get('article_number','')
            p['clause_number']=p['number'] if p['level']=='CLAUSE' else p.get('clause_number','')
            p['point_number']=p['number'] if p['level']=='POINT' else ''
            p['canonical_path']='/'.join(str(x) for x in [p['document_id'],'MAIN_BODY',p['article_number'],p['clause_number'],p['point_number']] if x)
            # Preserve a deterministic source span for downstream evidence and
            # retrieval. Nested provisions are searched from the previous match
            # so repeated legal wording cannot silently point to the first hit.
            source_text=segment['text']
            span_start,span_end=_locate_source_span(source_text,p.get('text',''),search_at)
            if span_start is not None:
                p['char_start']=span_start
                p['char_end']=span_end
                p['line_start']=segment['line_start']+source_text[:span_start].count('\n')
                p['line_end']=segment['line_start']+source_text[:span_end].count('\n')
                p['span_scope']='SEGMENT_TEXT'
                search_at=span_start+1
            else:
                p['char_start']=None; p['char_end']=None
                p['line_start']=segment['line_start']; p['line_end']=segment['line_end']
                p['span_scope']='SEGMENT_TEXT'
            p['valid_from']=doc.get('valid_from') or doc.get('effective_from') or ''
            p['valid_to']=doc.get('valid_to') or doc.get('effective_to') or ''
        result.extend(parsed)
    return result


def parse_all(registry: list[dict], extracted: list[dict], output_dir: Path, cfg: dict | None=None) -> list[dict]:
    from .segmentation import segment_document
    settings=(cfg or {}).get('parsing',{})
    by_file = {x["file_id"]: x for x in extracted}
    rows = []; segments=[]; problems=[]; quarantined=[]
    for doc in registry:
        if doc["document_type"] not in {"LAW", "DECREE", "CIRCULAR", "RESOLUTION", "CONSOLIDATED", "HISTORICAL"}:
            continue
        text = by_file.get(doc["file_id"], {}).get("text", "")
        parts=segment_document(doc,text,settings.get('keep_unparsed_preamble',True))
        segments.extend(parts)
        parsed=parse_legal_document(doc,text)
        counts=Counter(p['provision_id'] for p in parsed)
        repeated=[key for key,count in counts.items() if count>1]
        if repeated:
            # Keep every unambiguous subtree. Duplicate paths and all of their
            # descendants are excluded from retrieval/graph, so accepted rows
            # retain valid unique parents while the source remains reviewable.
            ambiguous=set(repeated)
            changed=True
            while changed:
                descendants={p['provision_id'] for p in parsed if p.get('parent_id') in ambiguous}
                changed=not descendants.issubset(ambiguous); ambiguous.update(descendants)
            rejected=[p for p in parsed if p['provision_id'] in ambiguous]
            parsed=[p for p in parsed if p['provision_id'] not in ambiguous]
            problems.append({'severity':'WARN','type':'AMBIGUOUS_CANONICAL_PATH_QUARANTINED',
                'document_id':doc['document_id'],'duplicate_ids':repeated,'quarantined_rows':len(rejected)})
            quarantined.extend(rejected)
        minimum=int(settings.get('minimum_provision_chars',10))
        short=[p for p in parsed if p['level']!='POINT' and len(p['text'])<minimum]
        if short:
            short_ids={p['provision_id'] for p in short}
            # A short parent cannot safely support descendants.
            changed=True
            while changed:
                descendants={p['provision_id'] for p in parsed if p.get('parent_id') in short_ids}
                changed=not descendants.issubset(short_ids); short_ids.update(descendants)
            rejected=[p for p in parsed if p['provision_id'] in short_ids]
            parsed=[p for p in parsed if p['provision_id'] not in short_ids]
            quarantined.extend(rejected)
            for p in short:
                problems.append({'severity':'WARN','type':'SHORT_PROVISION_QUARANTINED',
                                 'provision_id':p['provision_id'],'document_id':doc['document_id']})
        for part in parts:
            if part['segment_type']=='ATTACHED_REGULATION':
                problems.append({'severity':'ERROR','type':'ATTACHED_REGULATION_REQUIRES_REVIEW','segment_id':part['segment_id']})
        rows.extend(parsed)
    write_jsonl(output_dir/'03_structure'/'segments.jsonl',segments)
    write_jsonl(output_dir/'03_structure'/'quarantined_provisions.jsonl',quarantined)
    write_jsonl(output_dir/'reports'/'parsing_issues.jsonl',problems)
    write_jsonl(output_dir / "03_structure" / "provisions.jsonl", rows)
    return rows
