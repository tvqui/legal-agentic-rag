from __future__ import annotations
import re
from .ai_enrichment import cache_dir,cached_structured,provider_from_config,report_ai_progress
from .evidence import locate_document_evidence
from pathlib import Path
from .util import stable_id, write_jsonl
import json
from .integrity import _atomic

CASE_NO_RE = re.compile(r"(?:Bản án|Quyết định giám đốc thẩm|Quyết định)\s+(?:số\s*:\s*)?([0-9]{1,4}/[0-9]{4}/[A-ZĐa-zđ-]+)", re.I)
DATE_PATTERNS = [
    re.compile(r"Ngày\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})", re.I),
    re.compile(r"Ngày\s*:?\s*(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I),
]
MONEY_RE = re.compile(r"\b([0-9][0-9\.\s]{2,})\s*(?:đồng|VNĐ)\b", re.I)
PERCENT_RE = re.compile(r"\b(\d{1,3}(?:[,.]\d+)?)\s*%")
CITATION_RE = re.compile(r"(?:Điều\s+(\d+[a-zA-Z]?)|Khoản\s+(\d+)\s+Điều\s+(\d+[a-zA-Z]?))", re.I)

SECTIONS = {
    "facts": ["NỘI DUNG VỤ ÁN", "NỘI DUNG VỤ VIỆC"],
    "reasoning": ["NHẬN ĐỊNH CỦA TÒA ÁN", "NHẬN ĐỊNH CỦA TOÀ ÁN"],
    "decision": ["QUYẾT ĐỊNH"],
}


def _iso(m):
    if not m: return ""
    d,mo,y = m.group(1),m.group(2),m.group(3)
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def split_sections(text: str) -> dict:
    upper = text.upper()
    positions = []
    for key, names in SECTIONS.items():
        for name in names:
            pos = upper.find(name)
            if pos >= 0: positions.append((pos, key, name)); break
    positions.sort()
    out = {"facts": "", "reasoning": "", "decision": ""}
    for i,(pos,key,name) in enumerate(positions):
        start = pos + len(name)
        end = positions[i+1][0] if i+1 < len(positions) else len(text)
        out[key] = text[start:end].strip()
    if not positions:
        out["facts"] = text
    return out


def parse_case(doc: dict, text: str) -> dict:
    head = text[:7000]
    m = CASE_NO_RE.search(head)
    case_no = doc.get('case_number') or (m.group(1).upper() if m else "")
    date = ""
    for pat in DATE_PATTERNS:
        dm = pat.search(head)
        if dm: date = _iso(dm); break
    dispute = ""
    dv = re.search(r"V/v\s*[:\"]?\s*([^\n]{10,300})", head, re.I)
    if dv: dispute = dv.group(1).strip(" .\"")
    court = ""
    for line in [x.strip() for x in head.splitlines()[:20] if x.strip()]:
        if "TÒA ÁN" in line.upper() or "TOÀ ÁN" in line.upper():
            court = line; break
    sections = split_sections(text)
    features = []
    for value in MONEY_RE.findall(text[:25000])[:10]:
        features.append({"type":"MONEY", "value": value})
    for value in PERCENT_RE.findall(text[:25000])[:10]:
        features.append({"type":"PERCENT", "value": value})
    return {
        "case_id": stable_id(doc["document_id"], case_no or doc["sha256"], prefix="case"),
        "document_id": doc["document_id"],
        "case_number": case_no,
        "case_type": doc["document_type"],
        "court": court,
        "decision_date": date,
        "dispute": dispute,
        "facts": sections["facts"],
        "reasoning": sections["reasoning"],
        "decision": sections["decision"],
        "features": features,
        "search_text": "\n".join(x for x in [dispute, sections["facts"], sections["reasoning"], sections["decision"]] if x),
    }


def build_cases(registry: list[dict], extracted: list[dict], output_dir: Path) -> list[dict]:
    by_file = {x["file_id"]: x for x in extracted}
    rows=[]
    for doc in registry:
        if doc["document_type"] not in {"JUDGMENT", "CASSATION", "PRECEDENT"}: continue
        text = by_file.get(doc["file_id"],{}).get("text","")
        rows.append(parse_case(doc,text))
    write_jsonl(output_dir / "03_structure" / "cases.jsonl", rows)
    return rows

CASE_FEATURE_SCHEMA={"type":"object","additionalProperties":False,"properties":{"features":{"type":"array","maxItems":12,"items":{"type":"object","additionalProperties":False,"properties":{
  "type":{"type":"string","enum":["PARTY_PROFILE","EMPLOYMENT_RELATIONSHIP","EMPLOYMENT_EVENT","PROTECTED_STATUS","PROCEDURE","CLAIM_OR_REMEDY","OUTCOME"]},
  "value":{"type":"string"},"source_quote":{"type":"string"}
},"required":["type","value","source_quote"]}}},"required":["features"]}

def source_chunks(source,byte_budget=3500):
    if byte_budget<256: raise ValueError('Case chunk budget too small')
    start=0
    while start<len(source):
        end=start; consumed=0
        while end<len(source) and consumed+len(source[end].encode('utf-8'))<=byte_budget:
            consumed+=len(source[end].encode('utf-8')); end+=1
        yield start,source[start:end]
        if end==len(source): break
        # Overlap keeps sentences crossing a chunk boundary available in full.
        start=max(start+1,end-min(200,(end-start)//4))

def enrich_case_ontology(cases,cfg,output_dir):
    from .ai_requests import AIRequests
    provider=provider_from_config(cfg); requests=AIRequests(provider,cfg,output_dir,'case_ontology')
    enriched=[]; quality=[]; succeeded=fallback=0
    system="""Extract normalized Vietnamese labour-case ontology features from this fragment only.
Each feature needs a short exact source_quote. Distinguish allegations, court findings and outcomes.
Do not infer unstated facts. Use concise Vietnamese values. Return at most 12 features, only schema JSON."""
    try:
        for index,case in enumerate(cases,1):
            source='\n'.join(str(case.get(field) or '') for field in ('dispute','facts','reasoning','decision'))
            responses,errors,planned=requests.generate(system,{'case_id':case['case_id'],'source':source},
                CASE_FEATURE_SCHEMA,case['case_id'])
            from .anchored_ai import repair_grounding
            def grounded_item(item,response):
                if not item.get('value','').strip(): return False
                return locate_document_evidence(item.get('source_quote',''),response['source'])[2]=='RESOLVED'
            responses,errors=repair_grounding(requests,system,{'case_id':case['case_id'],'source':source},
                CASE_FEATURE_SCHEMA,case['case_id'],responses,errors,grounded_item)
            source_sha=__import__('hashlib').sha256(source.encode('utf-8')).hexdigest()
            features=[]
            for old in case.get('features',[]):
                if str(old.get('generator','')).startswith('structured-ai:'):
                    span=old.get('evidence_span') or {}; start=span.get('char_start'); end=span.get('char_end')
                    if not (span.get('coordinate_space')=='CASE_SOURCE_TEXT' and span.get('source_sha256')==source_sha
                            and type(start) is int and type(end) is int and 0<=start<end<=len(source)
                            and source[start:end]==old.get('source_quote')): continue
                features.append(old)
            retained=sum(str(item.get('generator','')).startswith('structured-ai:') for item in features)
            accepted=0
            for response in responses:
                chunk=response['source']; offset=response['source_offset']; grounded=[]
                for item in response['data'].get('features',[]):
                    value=' '.join(item['value'].split()); quote=' '.join(item['source_quote'].split())
                    if not value or not quote: continue
                    evidence_text,local_span,status=locate_document_evidence(quote,chunk)
                    if status!='RESOLVED': continue
                    start=offset+local_span['document_char_start']; end=offset+local_span['document_char_end']
                    if source[start:end]!=evidence_text: continue
                    evidence_span={'coordinate_space':'CASE_SOURCE_TEXT','char_start':start,'char_end':end,
                        'source_sha256':__import__('hashlib').sha256(source.encode('utf-8')).hexdigest()}
                    grounded.append({'type':item['type'],'value':value,'source_quote':evidence_text,
                        'evidence_span':evidence_span,'source_chunk_offset':offset,'provenance_status':'VERIFIED',
                        'generator':'structured-ai:'+str(getattr(provider,'model','unknown'))})
                if len(grounded)!=len(response['data']['features']):
                    errors.append({'reason':'UNGROUNDED_AI_FEATURES','source_start':offset,'source_end':offset+len(chunk)})
                features.extend(grounded); accepted+=len(grounded)
            unique={(x.get('type'),x.get('value'),x.get('source_quote')):x for x in features}
            enriched.append({**case,'features':list(unique.values())})
            if accepted: succeeded+=1
            else: fallback+=1
            quality.append({'case_id':case['case_id'],'source_chars':len(source),'chunks_planned':planned,
                'chunks_completed':len(responses),'accepted_features':accepted,'retained_ai_features':retained,
                'errors':[e['reason'] for e in errors],'error_details':errors,
                'coverage_complete':len(responses)==planned and not errors,
                'complete':len(responses)==planned and not errors and accepted>0})
            # Preserve the full set of case records if interrupted partway through.
            write_jsonl(output_dir/'03_structure/cases.jsonl',enriched+cases[index:])
            _atomic(output_dir/'reports/case_ai_quality.json',{'cases':quality,'total_cases':len(cases),
                'ai_attempted':requests.network_calls,'ai_cache_hits':requests.cache_hits,
                'ai_succeeded':succeeded,'complete_cases':sum(r['complete'] for r in quality),
                'partial_cases':sum(bool(r['accepted_features']) and not r['complete'] for r in quality),
                'unprocessed_cases':len(cases)-len(quality),'run_id':requests.run_id,
                'ai_fallback':fallback,'circuit_open':requests.stop_reason=='AI_CIRCUIT_OPEN',
                'stop_reason':requests.stop_reason,'complete':len(quality)==len(cases) and all(r['complete'] for r in quality)})
            report_ai_progress(output_dir,'case_ontology',index,len(cases),ai_attempted=requests.network_calls,
                ai_cache_hits=requests.cache_hits,ai_succeeded=succeeded,ai_fallback=fallback)
    finally:
        close=getattr(provider,'close',None)
        if callable(close): close()
    return enriched
