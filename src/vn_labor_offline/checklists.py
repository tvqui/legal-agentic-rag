from __future__ import annotations
import json, re, os
from pathlib import Path
from .util import stable_id, write_jsonl, read_jsonl
from .evidence import locate_evidence
from .ai_enrichment import cache_dir, cached_structured, provider_from_config

SENTENCE_SPLIT = re.compile(r"(?<=[\.;:!?])\s+|\n+")
TRIGGERS = [
    ("EXCEPTION", ["trừ trường hợp", "ngoại trừ", "không áp dụng"]),
    ("PROHIBITION", ["không được", "nghiêm cấm"]),
    ("REQUIRED", ["phải ", "có trách nhiệm", "có nghĩa vụ"]),
    ("CONDITION", ["nếu ", "khi ", "trường hợp", "với điều kiện"]),
    ("PERMISSION", ["được ", "có quyền"]),
    ("DEADLINE", ["trong thời hạn", "chậm nhất", "trước ít nhất", "ngày làm việc"]),
]


def heuristic_checklist(provision: dict, segment_text: str = "", document_text: str = "",
                        pages: list[dict] | None = None) -> list[dict]:
    text = provision.get("text", "")
    items=[]
    for sent in SENTENCE_SPLIT.split(text):
        s=" ".join(sent.split()).strip()
        if len(s) < 18 or len(s) > 700: continue
        low=s.lower()
        if re.search(r'(?:nếu|khi).*vướng mắc|phản ánh.*về Bộ',low): continue
        typ=None
        for t, kws in TRIGGERS:
            if any(k in low for k in kws): typ=t; break
        if not typ: continue
        q = s
        if not q.endswith("?"):
            q = "Có thỏa mãn điều kiện/quy tắc sau không: " + q.rstrip(".;") + "?"
        evidence_text, evidence_span, provenance_status = locate_evidence(
            provision, s, segment_text, document_text, pages)
        items.append({
            "checklist_id": stable_id(provision["provision_id"], str(len(items)+1), s, prefix="diag"),
            "provision_id": provision["provision_id"], "source_provision_id": provision["provision_id"],
            "type": typ, "question": q, "source_text": s, "evidence_text": evidence_text,
            "evidence_span": evidence_span,
            "provenance_status": "VERIFIED" if provenance_status == "RESOLVED" else provenance_status,
            "generator": "heuristic", "confidence": .65,
        })
    return items[:20]


def ollama_checklist(provision: dict, model: str, segment_text: str = "", document_text: str = "",
                     pages: list[dict] | None = None) -> list[dict]:
    try:
        from ollama import chat
    except Exception as e:
        raise RuntimeError("Ollama Python package missing. Run uv sync --extra llm") from e
    schema = {
      "type":"object", "properties":{"items":{"type":"array","items":{"type":"object","properties":{
        "type":{"type":"string","enum":["REQUIRED","CONDITION","EXCEPTION","PROHIBITION","PERMISSION","DEADLINE"]},
        "question":{"type":"string"}, "source_text":{"type":"string"}, "fact_slots":{"type":"array","items":{"type":"string"}}
      },"required":["type","question","source_text","fact_slots"]}}}, "required":["items"]
    }
    prompt = f"""Bạn đang xây Diagnostic Checklist cho hệ thống hỏi đáp luật lao động Việt Nam.
Chỉ dùng nội dung pháp luật được cung cấp. Không thêm điều kiện không có trong văn bản.
Tách quy tắc thành câu hỏi kiểm tra nguyên tử. source_text phải là đoạn ngắn xuất hiện trong nguồn.

Nguồn:
{provision.get('text','')[:12000]}
"""
    resp = chat(model=model, messages=[{"role":"user","content":prompt}], format=schema, options={"temperature":0})
    data=json.loads(resp.message.content)
    out=[]
    for i,it in enumerate(data.get("items",[])[:20],1):
        evidence=it.get('source_text','')
        if not evidence or ' '.join(evidence.split()) not in ' '.join(provision.get('text','').split()): continue
        evidence_text, evidence_span, status = locate_evidence(
            provision, evidence, segment_text, document_text, pages)
        if status != "RESOLVED":
            continue
        out.append({
            "checklist_id": stable_id(provision["provision_id"], str(i), it.get("source_text",""), prefix="diag"),
            "provision_id": provision["provision_id"], "source_provision_id": provision["provision_id"],
            "provenance_status": "VERIFIED", "evidence_span": evidence_span,
            "type": it.get("type","CONDITION"),
            "question": it.get("question",""), "source_text": it.get("source_text",""),
            "evidence_text": evidence_text,
            "fact_slots": it.get("fact_slots",[]), "generator": f"ollama:{model}", "confidence": .85,
        })
    return out


AI_CHECKLIST_SCHEMA={"type":"object","additionalProperties":False,"properties":{"items":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{
  "type":{"type":"string","enum":["REQUIRED","CONDITION","EXCEPTION","PROHIBITION","PERMISSION","DEADLINE"]},
  "question":{"type":"string"},"source_text":{"type":"string"},"fact_slots":{"type":"array","items":{"type":"string"}}
},"required":["type","question","source_text","fact_slots"]}}},"required":["items"]}

def ai_checklist(provision,provider,cache,segment_text='',document_text='',pages=None):
    payload={'provision_id':provision['provision_id'],'level':provision.get('level'),'source':provision.get('text','')[:12000]}
    system="""Create atomic Diagnostic Checklist questions for Vietnamese labour law.
Use only the quoted source. Every source_text must be a short exact quote from the source. Do not add a legal condition or exception.
Return at most 20 items and only JSON matching the schema."""
    data=cached_structured(provider,system,payload,AI_CHECKLIST_SCHEMA,cache,provision['provision_id'])
    normalized_source=' '.join(provision.get('text','').split()); out=[]
    for index,item in enumerate(data.get('items',[])[:20],1):
        quote=' '.join(str(item.get('source_text','')).split())
        if not quote or quote not in normalized_source: continue
        evidence_text,evidence_span,status=locate_evidence(provision,quote,segment_text,document_text,pages)
        if status!='RESOLVED': continue
        out.append({'checklist_id':stable_id(provision['provision_id'],str(index),quote,prefix='diag'),
          'provision_id':provision['provision_id'],'source_provision_id':provision['provision_id'],
          'provenance_status':'VERIFIED','evidence_span':evidence_span,'type':item.get('type','CONDITION'),
          'question':item.get('question',''),'source_text':quote,'evidence_text':evidence_text,
          'fact_slots':item.get('fact_slots',[]),'generator':'structured-ai:'+str(getattr(provider,'model','unknown')),'confidence':.85})
    return out

def build_checklists(provisions: list[dict], cfg: dict, output_dir: Path, mode: str | None=None) -> list[dict]:
    mode = mode or cfg["knowledge"].get("checklist_mode", "heuristic")
    model = cfg["knowledge"].get("ollama_model", "qwen3:4b")
    segments = {row["segment_id"]: row["text"] for row in
                read_jsonl(output_dir / "03_structure" / "segments.jsonl")}
    source_by_file = {row["file_id"]: row for row in
                      read_jsonl(output_dir / "01_extracted" / "documents.jsonl")}
    registry = {row["document_id"]: row for row in
                read_jsonl(output_dir / "02_registry" / "documents.jsonl")}
    rows=[]; provider=None
    if mode in {'ai','hybrid_ai'}: provider=provider_from_config(cfg)
    for p in provisions:
        # Parser stores each level's own text; ancestor introductions can contain rules too.
        if len(p.get("text", "")) < 40: continue
        source = source_by_file.get(registry.get(p["document_id"], {}).get("file_id"), {})
        evidence_args = (segments.get(p.get("segment_id"), ""), source.get("text", ""),
                         source.get("page_provenance", []))
        heuristic=heuristic_checklist(p,*evidence_args)
        if mode == "ollama":
            try: rows.extend(ollama_checklist(p, model, *evidence_args))
            except Exception: rows.extend(heuristic)
        elif mode=='ai' or mode=='hybrid_ai' and not heuristic:
            try: rows.extend(ai_checklist(p,provider,cache_dir(cfg),*evidence_args))
            except Exception: rows.extend(heuristic)
        else: rows.extend(heuristic)
    accepted=[r for r in rows if r.get('provenance_status')=='VERIFIED']
    write_jsonl(output_dir / "04_knowledge" / "diagnostic_review_queue.jsonl",
                [r for r in rows if r.get('provenance_status')!='VERIFIED'])
    write_jsonl(output_dir / "04_knowledge" / "diagnostic_checklists.jsonl", accepted)
    return accepted
