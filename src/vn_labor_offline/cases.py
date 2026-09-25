from __future__ import annotations
import re
from .ai_enrichment import cache_dir,cached_structured,provider_from_config
from .evidence import locate_document_evidence
from pathlib import Path
from .util import stable_id, write_jsonl

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
        "search_text": "\n".join(x for x in [dispute, sections["facts"][:12000], sections["reasoning"][:12000]] if x),
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

CASE_FEATURE_SCHEMA={"type":"object","additionalProperties":False,"properties":{"features":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{
  "type":{"type":"string","enum":["PARTY_PROFILE","EMPLOYMENT_RELATIONSHIP","EMPLOYMENT_EVENT","PROTECTED_STATUS","PROCEDURE","CLAIM_OR_REMEDY","OUTCOME"]},
  "value":{"type":"string"},"source_quote":{"type":"string"}
},"required":["type","value","source_quote"]}}},"required":["features"]}

def enrich_case_ontology(cases,cfg,output_dir):
    provider=provider_from_config(cfg); cache=cache_dir(cfg); enriched=[]
    system="""Extract normalized Vietnamese labour-case ontology features from the quoted case only.
Every feature must have a short exact source_quote. Do not infer unstated facts, guilt, intent, or criminal-law attributes.
Return only JSON matching the schema."""
    for case in cases:
        source='\n'.join(str(case.get(field) or '') for field in ('dispute','facts','reasoning','decision'))
        payload={'case_id':case['case_id'],'source':source[:30000]}
        try: data=cached_structured(provider,system,payload,CASE_FEATURE_SCHEMA,cache,case['case_id'])
        except Exception: enriched.append(case); continue
        features=list(case.get('features',[]))
        allowed={'PARTY_PROFILE','EMPLOYMENT_RELATIONSHIP','EMPLOYMENT_EVENT','PROTECTED_STATUS','PROCEDURE','CLAIM_OR_REMEDY','OUTCOME'}
        for item in data.get('features',[])[:40] if isinstance(data,dict) else []:
            typ=item.get('type'); value=' '.join(str(item.get('value','')).split())
            quote=' '.join(str(item.get('source_quote','')).split())
            if typ not in allowed or not value or not quote: continue
            evidence_text,evidence_span,status=locate_document_evidence(quote,source)
            if status!='RESOLVED': continue
            features.append({'type':typ,'value':value,'source_quote':evidence_text,'evidence_span':evidence_span,
              'provenance_status':'VERIFIED','generator':'structured-ai:'+str(getattr(provider,'model','unknown'))})
        unique={(x.get('type'),x.get('value'),x.get('source_quote')):x for x in features}
        enriched.append({**case,'features':list(unique.values())})
    write_jsonl(output_dir/'03_structure'/'cases.jsonl',enriched)
    return enriched
