from __future__ import annotations
import json, re, os
from pathlib import Path
from .util import stable_id, write_jsonl, read_jsonl
from .evidence import locate_evidence

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


def build_checklists(provisions: list[dict], cfg: dict, output_dir: Path, mode: str | None=None) -> list[dict]:
    mode = mode or cfg["knowledge"].get("checklist_mode", "heuristic")
    model = cfg["knowledge"].get("ollama_model", "qwen3:4b")
    segments = {row["segment_id"]: row["text"] for row in
                read_jsonl(output_dir / "03_structure" / "segments.jsonl")}
    source_by_file = {row["file_id"]: row for row in
                      read_jsonl(output_dir / "01_extracted" / "documents.jsonl")}
    registry = {row["document_id"]: row for row in
                read_jsonl(output_dir / "02_registry" / "documents.jsonl")}
    rows=[]
    for p in provisions:
        # Parser stores each level's own text; ancestor introductions can contain rules too.
        if len(p.get("text", "")) < 40: continue
        source = source_by_file.get(registry.get(p["document_id"], {}).get("file_id"), {})
        evidence_args = (segments.get(p.get("segment_id"), ""), source.get("text", ""),
                         source.get("page_provenance", []))
        if mode == "ollama":
            try: rows.extend(ollama_checklist(p, model, *evidence_args))
            except Exception: rows.extend(heuristic_checklist(p, *evidence_args))
        else: rows.extend(heuristic_checklist(p, *evidence_args))
    accepted=[r for r in rows if r.get('provenance_status')=='VERIFIED']
    write_jsonl(output_dir / "04_knowledge" / "diagnostic_review_queue.jsonl",
                [r for r in rows if r.get('provenance_status')!='VERIFIED'])
    write_jsonl(output_dir / "04_knowledge" / "diagnostic_checklists.jsonl", accepted)
    return accepted
