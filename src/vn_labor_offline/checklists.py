from __future__ import annotations
import json, re, os
from pathlib import Path
from .util import stable_id, write_jsonl, read_jsonl
from .evidence import locate_evidence
from .ai_enrichment import cache_dir, cached_structured, provider_from_config, report_ai_progress

SENTENCE_SPLIT = re.compile(r"(?<=[\.;:!?])\s+|\n+")
TRIGGERS = [
    ("EXCEPTION", ["trừ trường hợp", "ngoại trừ", "không áp dụng"]),
    ("PROHIBITION", ["không được", "nghiêm cấm"]),
    ("REQUIRED", ["phải ", "có trách nhiệm", "có nghĩa vụ"]),
    ("CONDITION", ["nếu ", "khi ", "trường hợp", "với điều kiện"]),
    ("PERMISSION", ["được ", "có quyền"]),
    ("DEADLINE", ["trong thời hạn", "chậm nhất", "trước ít nhất", "ngày làm việc"]),
]

LEVEL_PRIORITY = {"POINT": 0, "CLAUSE": 1, "ARTICLE": 2}

# Increment this when the semantic identity of a DiagnosticItem changes. The
# Kaggle notebook probes it before starting a multi-hour model run so an old
# code Dataset fails in minutes rather than at graph export.
CHECKLIST_ID_SCHEMA_VERSION = 2


def checklist_identity(provision_id: str, rule_type: str, source_text: str) -> str:
    """Return one stable ID for one grounded atomic rule.

    Generator position is deliberately excluded: heuristic and AI generation
    can enumerate the same quote at different positions. Rule type is part of
    the identity because one quote can express more than one atomic rule.
    """
    normalized_type = str(rule_type or "CONDITION").strip().upper()
    normalized_quote = " ".join(str(source_text or "").split())
    return stable_id(provision_id, normalized_type, normalized_quote, prefix="diag")


def finalize_checklists(rows: list[dict]) -> list[dict]:
    """Prefer grounded AI rows, assign canonical IDs and reject real collisions."""
    unique = {}
    for original in rows:
        row = dict(original)
        row["type"] = str(row.get("type") or "CONDITION").strip().upper()
        row["source_text"] = " ".join(str(row.get("source_text") or "").split())
        key = (row.get("provision_id"), row["type"], row["source_text"])
        current = unique.get(key)
        if current is None or (str(row.get("generator", "")).startswith("structured-ai:") and
                               not str(current.get("generator", "")).startswith("structured-ai:")):
            row["checklist_id"] = checklist_identity(*key)
            unique[key] = row
    result = list(unique.values())
    ids = [row["checklist_id"] for row in result]
    if len(ids) != len(set(ids)):
        raise ValueError("Diagnostic checklist ID collision after semantic normalization")
    return result


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
            "checklist_id": checklist_identity(provision["provision_id"], typ, s),
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
            "checklist_id": checklist_identity(provision["provision_id"], it.get("type"), evidence),
            "provision_id": provision["provision_id"], "source_provision_id": provision["provision_id"],
            "provenance_status": "VERIFIED", "evidence_span": evidence_span,
            "type": it.get("type","CONDITION"),
            "question": it.get("question",""), "source_text": it.get("source_text",""),
            "evidence_text": evidence_text,
            "fact_slots": it.get("fact_slots",[]), "generator": f"ollama:{model}", "confidence": .85,
        })
    return out


AI_CHECKLIST_SCHEMA={"type":"object","additionalProperties":False,"properties":{"items":{"type":"array","maxItems":12,"items":{"type":"object","additionalProperties":False,"properties":{
  "type":{"type":"string","enum":["REQUIRED","CONDITION","EXCEPTION","PROHIBITION","PERMISSION","DEADLINE"]},
  "question":{"type":"string"},"source_text":{"type":"string"},"fact_slots":{"type":"array","items":{"type":"string"}}
},"required":["type","question","source_text","fact_slots"]}}},"required":["items"]}

class AIItems(list):
    def __init__(self,values,errors,planned,completed):
        super().__init__(values); self.errors=errors; self.planned=planned; self.completed=completed
        self.complete=completed==planned and not errors and bool(values)


def ai_checklist(provision,provider,cache,segment_text='',document_text='',pages=None,requests=None):
    from .ai_requests import AIRequests
    if requests is None:
        requests=AIRequests(provider,{'project_root':cache.parent,'knowledge':{'ai_cache_dir':str(cache.resolve())}},
            cache.parent,'checklists')
    payload={'provision_id':provision['provision_id'],'level':provision.get('level'),'source':provision.get('text',''),
        'ancestor_context':provision.get('ancestor_context','')}
    system="""Create atomic Vietnamese labour-law checklist questions from this fragment.
Preserve scope, actor, prohibitions and exceptions inherited from ancestor_context.
Do not turn prohibition into permission. Use only the source; each source_text is a short exact quote.
Do not invent missing conditions. Use concise questions. Return at most 12 items, only schema JSON."""
    responses,errors,planned=requests.generate(system,payload,AI_CHECKLIST_SCHEMA,provision['provision_id'])
    out=[]
    for response in responses:
        normalized_source=' '.join(response['source'].split()); grounded=[]
        for item in response['data'].get('items',[]):
            quote=' '.join(str(item.get('source_text','')).split())
            if not quote or quote not in normalized_source: continue
            evidence_text,evidence_span,status=locate_evidence(provision,quote,segment_text,document_text,pages)
            if status!='RESOLVED': continue
            grounded.append({'checklist_id':checklist_identity(provision['provision_id'],item.get('type'),quote),
                'provision_id':provision['provision_id'],'source_provision_id':provision['provision_id'],
                'provenance_status':'VERIFIED','evidence_span':evidence_span,'type':item['type'],
                'question':item['question'],'source_text':quote,'evidence_text':evidence_text,
                'fact_slots':item['fact_slots'],'generator':'structured-ai:'+str(getattr(provider,'model','unknown')),'confidence':.85})
        if len(grounded)!=len(response['data']['items']):
            errors.append({'reason':'NO_GROUNDED_AI_ITEMS','source_start':response['source_offset'],
                'source_end':response['source_offset']+len(response['source'])})
        out.extend(grounded)
    return AIItems(finalize_checklists(out),errors,planned,len(responses))


def select_hybrid_ai_ids(prepared,max_records,byte_budget=None):
    """Select a deterministic, bounded set of provisions that already show legal-rule signals.

    AI refines provisions for which the deterministic parser found at least one grounded
    rule. Sending every no-signal fragment to an 8B model created more than 15,000
    sequential requests and did not improve coverage reliably.
    """
    limit=max(0,int(max_records))
    candidates=[(provision,heuristic) for provision,heuristic,_ in prepared if heuristic and
        (byte_budget is None or len(json.dumps({'source':provision.get('text',''),
        'ancestor_context':provision.get('ancestor_context','')},ensure_ascii=False).encode('utf-8'))<=byte_budget)]
    candidates.sort(key=lambda row:(
      -len(row[1]),LEVEL_PRIORITY.get(str(row[0].get('level','')).upper(),9),
      -min(len(row[0].get('text','')),12000),row[0]['provision_id']))
    return {provision['provision_id'] for provision,_ in candidates[:limit]}

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
    prepared=[]
    by_id={p['provision_id']:p for p in provisions}
    for original in provisions:
        p=dict(original); ancestors=[]; parent=by_id.get(p.get('parent_id')); seen=set()
        while parent and parent['provision_id'] not in seen:
            seen.add(parent['provision_id']); ancestors.append(parent.get('text','')); parent=by_id.get(parent.get('parent_id'))
        p['ancestor_context']='\n'.join(reversed(ancestors))
        # Parser stores each level's own text; ancestor introductions can contain rules too.
        if len(p.get("text", "")) < 40: continue
        source = source_by_file.get(registry.get(p["document_id"], {}).get("file_id"), {})
        evidence_args = (segments.get(p.get("segment_id"), ""), source.get("text", ""),
                         source.get("page_provenance", []))
        heuristic=heuristic_checklist(p,*evidence_args)
        prepared.append((p,heuristic,evidence_args))
    ai_limit=int(cfg['knowledge'].get('ai_max_provisions',2000))
    hybrid_ids=select_hybrid_ai_ids(prepared,ai_limit) if mode=='hybrid_ai' else set()
    from .ai_requests import AIRequests
    requests=AIRequests(provider,cfg,output_dir,'checklists') if provider else None
    planned=len(prepared) if mode=='ai' else len(hybrid_ids) if mode=='hybrid_ai' else 0
    report_ai_progress(output_dir,'checklists',0,len(prepared),mode=mode,ai_planned=planned,
                       ai_attempted=0,ai_succeeded=0,ai_fallback=0)
    ai_attempted=ai_succeeded=ai_fallback=ai_partial=0; failure_rows=[]; record_status=[]
    try:
        for index,(p,heuristic,evidence_args) in enumerate(prepared,1):
            selected=mode=='ai' or p['provision_id'] in hybrid_ids
            if mode=='ollama':
                try: rows.extend(ollama_checklist(p,model,*evidence_args))
                except Exception: rows.extend(heuristic)
            elif selected:
                before_calls=requests.network_calls+requests.cache_hits
                generated=ai_checklist(p,provider,cache_dir(cfg),*evidence_args,requests=requests)
                rows.extend(heuristic); rows.extend(generated)
                ai_attempted+=int(requests.network_calls+requests.cache_hits>before_calls)
                if generated.complete: ai_succeeded+=1
                else:
                    ai_fallback+=1
                    if generated: ai_partial+=1
                    errors=generated.errors or [{'reason':'NO_GROUNDED_AI_ITEMS'}]
                    failure_rows.extend({'provision_id':p['provision_id'],**error} for error in errors)
                record_status.append({'provision_id':p['provision_id'],'complete':generated.complete,
                    'chunks_planned':generated.planned,'chunks_completed':generated.completed,
                    'accepted_items':len(generated),'errors':generated.errors})
            else: rows.extend(heuristic)
            if mode in {'ai','hybrid_ai'} and (selected or index==len(prepared) or index%250==0):
                # Actual network count differs from records attempted and cache hits.
                report_ai_progress(output_dir,'checklists',index,len(prepared),mode=mode,ai_planned=planned,
                    ai_attempted=requests.network_calls,ai_succeeded=ai_succeeded,ai_cache_hits=requests.cache_hits)
                from .integrity import _atomic
                _atomic(output_dir/'reports/checklist_ai_quality.json',{'mode':mode,'planned':planned,
                    'attempted':ai_attempted,'network_calls':requests.network_calls,'cache_hits':requests.cache_hits,
                    'succeeded':ai_succeeded,'partial':ai_partial,'fallback':ai_fallback,
                    'skipped':max(0,planned-ai_attempted),'records':record_status,
                    'complete':planned==ai_succeeded,'circuit_open':requests.stop_reason=='AI_CIRCUIT_OPEN',
                    'stop_reason':requests.stop_reason})
                # An interrupted run must retain the complete heuristic baseline,
                # including provisions whose AI refinement has not started.
                checkpoint_rows=rows+[row for _,baseline,_ in prepared[index:] for row in baseline]
                write_jsonl(output_dir/'04_knowledge/diagnostic_checklists.jsonl',
                    finalize_checklists([r for r in checkpoint_rows if r.get('provenance_status')=='VERIFIED']))
    finally:
        close=getattr(provider,'close',None)
        if callable(close): close()
    write_jsonl(output_dir/'reports/checklist_ai_failures.jsonl',failure_rows)
    from .integrity import _atomic
    _atomic(output_dir/'reports/checklist_ai_quality.json',{'mode':mode,'planned':planned,
        'attempted':ai_attempted,'network_calls':requests.network_calls if requests else 0,
        'cache_hits':requests.cache_hits if requests else 0,'succeeded':ai_succeeded,'partial':ai_partial,
        'fallback':ai_fallback,'skipped':max(0,planned-ai_attempted),'records':record_status,
        'complete':planned==ai_succeeded,'circuit_open':bool(requests and requests.stop_reason=='AI_CIRCUIT_OPEN'),
        'stop_reason':requests.stop_reason if requests else None})
    # Prefer the structured-AI form when both generators ground the same atomic rule.
    rows=finalize_checklists(rows)
    accepted=[r for r in rows if r.get('provenance_status')=='VERIFIED']
    write_jsonl(output_dir / "04_knowledge" / "diagnostic_review_queue.jsonl",
                [r for r in rows if r.get('provenance_status')!='VERIFIED'])
    write_jsonl(output_dir / "04_knowledge" / "diagnostic_checklists.jsonl", accepted)
    return accepted
