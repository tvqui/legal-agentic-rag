"""Build an evidence-backed review package without creating approvals."""
from __future__ import annotations
import argparse, csv, hashlib, json, shutil, zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _rows(data: bytes): return [json.loads(x) for x in data.decode("utf-8-sig").splitlines() if x.strip()]
def _write(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in rows),encoding="utf-8")
def _id(prefix: str, value: Any) -> str:
    return prefix+"_"+_sha(json.dumps(value,ensure_ascii=False,sort_keys=True).encode())[:16]
def _draft(row: dict) -> dict:
    return {**row,"review_status":"DRAFT","decision":None,"reviewer":None,
            "reviewed_at":None,"review_evidence":None,"review_note":None}

def source_cases(root: Path, export: Path) -> list[dict]:
    with (root/"review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv").open(
            encoding="utf-8-sig",newline="") as f: seeds=list(csv.DictReader(f))
    resolved=_rows((export/"source_catalog_auto.jsonl").read_bytes())
    by_sha={x.get("corpus_sha256"):x for x in resolved}
    out=[]
    for seed in seeds:
        r=by_sha.get(seed.get("corpus_sha256"),{})
        state=r.get("resolution_state")
        recommendation=("CONFIRM_AUTO_EXACT_SHA" if state=="AUTO_EXACT_SHA" else
                        "COMPARE_DIFFERENT_BINARY" if r.get("resolved_sha_match")=="NO" else "VERIFY_SOURCE")
        out.append(_draft({"case_id":_id("source",[seed.get("relative_path"),seed.get("corpus_sha256")]),
            "record_id":r.get("record_id"),"relative_path":seed.get("relative_path"),
            "source_group":seed.get("source_group"),"corpus_sha256":seed.get("corpus_sha256"),
            "document_number":seed.get("document_number") or seed.get("instrument_number"),"title":seed.get("title"),
            "candidate_source_url":seed.get("exact_source_url") or seed.get("direct_download_url") or seed.get("current_candidate_url"),
            "resolver_state":state,"resolved_sha_match":r.get("resolved_sha_match"),
            "resolved_downloaded_sha256":r.get("resolved_downloaded_sha256"),
            "final_identity_url":r.get("final_identity_url"),"final_binary_url":r.get("final_binary_url"),
            "identity_match":r.get("identity_match"),"reason_codes":r.get("reason_codes",[]),
            "recommendation":recommendation,"allowed_decisions":["APPROVED","REJECTED"]}))
    return out

def quarantine_cases(issues: list[dict], rows: list[dict], docs: dict) -> tuple[list[dict],list[dict]]:
    by_doc=defaultdict(list)
    for i,row in enumerate(rows): by_doc[row["document_id"]].append((i,row))
    assigned=set(); cases=[]; members=[]
    for issue in [x for x in issues if x.get("type")=="SHORT_PROVISION_QUARANTINED"]:
        ids={issue["provision_id"]}; changed=True
        while changed:
            changed=False
            for _,row in by_doc[issue["document_id"]]:
                if row.get("parent_id") in ids and row.get("provision_id") not in ids:
                    ids.add(row["provision_id"]); changed=True
        selected=[(i,r) for i,r in by_doc[issue["document_id"]] if r.get("provision_id") in ids and i not in assigned]
        assigned.update(i for i,_ in selected); cid=_id("quarantine",[issue["type"],issue["document_id"],issue["provision_id"]])
        doc=docs.get(issue["document_id"],{})
        cases.append(_draft({"case_id":cid,"issue_type":issue["type"],"document_id":issue["document_id"],
            "document_title":doc.get("title"),"relative_path":doc.get("relative_path"),
            "root_provision_ids":[issue["provision_id"]],"member_count":len(selected),
            "allowed_decisions":["APPROVED","EXCLUDED","REJECTED"]}))
        members.extend({"case_id":cid,"member_id":_id("member",[i,r]),**r} for i,r in selected)
    for issue in [x for x in issues if x.get("type")=="AMBIGUOUS_CANONICAL_PATH_QUARANTINED"]:
        selected=[(i,r) for i,r in by_doc[issue["document_id"]] if i not in assigned]
        assigned.update(i for i,_ in selected); cid=_id("quarantine",[issue["type"],issue["document_id"],issue.get("duplicate_ids")])
        doc=docs.get(issue["document_id"],{})
        cases.append(_draft({"case_id":cid,"issue_type":issue["type"],"document_id":issue["document_id"],
            "document_title":doc.get("title"),"relative_path":doc.get("relative_path"),
            "root_provision_ids":issue.get("duplicate_ids",[]),"member_count":len(selected),
            "reported_quarantined_rows":issue.get("quarantined_rows"),
            "allowed_decisions":["APPROVED","EXCLUDED","REJECTED"]}))
        members.extend({"case_id":cid,"member_id":_id("member",[i,r]),**r} for i,r in selected)
    if len(assigned)!=len(rows): raise ValueError(f"quarantine coverage {len(assigned)}/{len(rows)}")
    return sorted(cases,key=lambda x:x["case_id"]),sorted(members,key=lambda x:x["member_id"])

def temporal_cases(versions: list[dict],docs: dict) -> tuple[list[dict],list[dict]]:
    grouped=defaultdict(list)
    for row in versions: grouped[row["source_document_version_id"]].append(row)
    cases=[]; members=[]
    for did,group in sorted(grouped.items()):
        doc=docs.get(did,{}); cid=_id("temporal",[did,doc.get("sha256")])
        intervals=sorted({(x.get("valid_from"),x.get("valid_to")) for x in group},key=lambda x:str(x))
        cases.append(_draft({"case_id":cid,"document_id":did,"document_title":doc.get("title"),
            "document_number":doc.get("document_number"),"relative_path":doc.get("relative_path"),
            "source_sha256":doc.get("sha256"),"provision_version_count":len(group),
            "candidate_intervals":[{"valid_from":a,"valid_to":b} for a,b in intervals],
            "member_ids_sha256":_sha("\n".join(sorted(x["provision_version_id"] for x in group)).encode()),
            "allowed_decisions":["APPROVED","EXCLUDED","REJECTED"]}))
        members.extend({"case_id":cid,**x} for x in group)
    return cases,members

def gold_candidates(units:list[dict],changes:list[dict],build_id:str)->list[dict]:
    by_kind=defaultdict(list)
    for x in units: by_kind[x.get("kind","")].append(x)
    p=by_kind["PROVISION"]; amended={x.get("source_document_id") for x in changes}
    pools={"DIRECT_PROVISION":p,"SCENARIO":[x for x in p if x.get("level") in {"CLAUSE","POINT"}],
      "CROSS_REFERENCE":[x for x in p if "Điều" in (x.get("source_text") or "")],
      "MULTI_HOP":[x for x in p if x.get("ancestor_context")],"TEMPORAL":[x for x in p if x.get("valid_from")],
      "AMENDMENT_REPEAL":[x for x in p if x.get("document_id") in amended],
      "CASE_LAW":by_kind["CASE"],"ANNEX_TABLE":by_kind["ANNEX"]}
    templates={"DIRECT_PROVISION":"Quy định trực tiếp tại {breadcrumb} là gì?",
      "SCENARIO":"Trong tình huống thuộc phạm vi {document_title}, quy định nào cần áp dụng?",
      "CROSS_REFERENCE":"Nội dung tại {breadcrumb} dẫn chiếu đến quy định nào?",
      "MULTI_HOP":"Hãy kết hợp bối cảnh cấp trên và nội dung tại {breadcrumb}.",
      "TEMPORAL":"Vào ngày {valid_from}, quy định tại {breadcrumb} có hiệu lực thế nào?",
      "AMENDMENT_REPEAL":"Quan hệ sửa đổi/bãi bỏ liên quan đến {document_title} là gì?",
      "CASE_LAW":"Vụ việc trong {document_title} được tòa án nhận định như thế nào?",
      "ANNEX_TABLE":"Dữ liệu phụ lục tại {breadcrumb} quy định gì?"}
    out=[]
    for typ,pool in pools.items():
        for u in sorted(pool,key=lambda x:x["unit_id"])[:2]:
            question=templates[typ]
            for key in ("breadcrumb","document_title","valid_from"): question=question.replace("{"+key+"}",str(u.get(key) or ""))
            out.append({"query_id":_id("gold",[typ,u["unit_id"]]),"question":question,"query_type":typ,
              "query_date":u.get("valid_from") if typ in {"TEMPORAL","AMENDMENT_REPEAL"} else None,
              "candidate_unit_ids":[u["unit_id"]],"gold_unit_ids":[],"candidate_evidence":{
              "breadcrumb":u.get("breadcrumb"),"source_text":(u.get("source_text") or "")[:800],
              "relative_path":(u.get("provenance") or {}).get("relative_path")},"build_id":build_id,
              "review_status":"DRAFT","reviewer":None,"reviewed_at":None,"gold_source":None,"review_note":None})
    out.append({"query_id":_id("gold","insufficient-facts"),"question":"Một tình huống lao động không nêu thời điểm, loại hợp đồng và sự kiện pháp lý thì có đủ dữ kiện kết luận không?",
      "query_type":"INSUFFICIENT_FACTS","candidate_unit_ids":[],"gold_unit_ids":[],"expected_no_answer":True,
      "build_id":build_id,"review_status":"DRAFT","reviewer":None,"reviewed_at":None,"gold_source":None,"review_note":None})
    return out

INSTRUCTIONS="""# Hướng dẫn duyệt OFFLINE

Gói này chỉ chuẩn bị bằng chứng; mọi quyết định đều là `DRAFT`.

1. Kiểm file gốc theo `relative_path` và SHA-256, không chỉ dựa vào tên file hoặc URL.
2. Duyệt 95 source, 25 legal-change, 36 quarantine và 61 temporal cases. File members chứa toàn bộ dòng bị tác động.
3. `AUTO_EXACT_SHA` là bằng chứng mạnh nhưng vẫn cần người duyệt. `candidate_unit_ids` chỉ là gợi ý Gold.
4. Quyết định cuối cùng phải có reviewer, reviewed_at, review_evidence và decision hợp lệ. Không phê duyệt hàng loạt khi chưa đọc bằng chứng.
5. Sau review: validate return, merge dry-run, chạy lại pipeline/Kaggle + Aura, rồi audit cùng build.
"""

def build(root:Path,archive_path:Path,resolver_export:Path,output_dir:Path,build_id:str)->dict:
    review_root=root/"review/inputs/v8_1"; workspace=review_root/f"offline_review_{build_id}"
    if workspace.exists(): shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as z:
        if z.testzip(): raise ValueError("technical ZIP CRC failure")
        read=lambda n:_rows(z.read(n)); docs_list=read("artifacts/02_registry/documents.jsonl"); docs={x["document_id"]:x for x in docs_list}
        changes=read("artifacts/04_knowledge/legal_changes.jsonl"); quarantine=read("artifacts/03_structure/quarantined_provisions.jsonl")
        issues=read("artifacts/reports/validation_issues.jsonl"); versions=read("artifacts/03_structure/provision_versions.jsonl")
        units=read("artifacts/06_indexes/retrieval_units.jsonl"); final=json.loads(z.read("artifacts/reports/final_outputs_validation.json"))
        references={
          "documents_reference.jsonl":z.read("artifacts/02_registry/documents.jsonl"),
          "provisions_reference.jsonl":z.read("artifacts/03_structure/provisions.jsonl"),
          "retrieval_units_reference.jsonl":z.read("artifacts/06_indexes/retrieval_units.jsonl"),
          "graph_nodes_reference.jsonl":z.read("artifacts/05_graph/nodes.jsonl"),
          "graph_edges_reference.jsonl":z.read("artifacts/05_graph/edges.jsonl")}
    src=source_cases(root,resolver_export)
    legal=[_draft({**x,"case_id":_id("change",x["change_id"]),"source_sha256":docs.get(x["source_document_id"],{}).get("sha256"),
        "source_relative_path":docs.get(x["source_document_id"],{}).get("relative_path"),"source_title":docs.get(x["source_document_id"],{}).get("title"),
        "allowed_decisions":["APPROVED","EXCLUDED","REJECTED"]}) for x in changes]
    qc,qm=quarantine_cases(issues,quarantine,docs); tc,tm=temporal_cases(versions,docs); gold=gold_candidates(units,changes,final["gold_build_id"])
    outputs={"source_review_cases.jsonl":src,"legal_change_review_cases.jsonl":legal,"quarantine_review_cases.jsonl":qc,
      "quarantine_review_members.jsonl":qm,"temporal_review_cases.jsonl":tc,"temporal_review_members.jsonl":tm,"gold_query_candidates.jsonl":gold}
    for name,data in outputs.items(): _write(workspace/name,data)
    for name,data in references.items(): (workspace/name).write_bytes(data)
    # Keep the complete immutable resolver trail beside the compact review cases.
    for name in ("source_catalog_auto.jsonl", "source_resolution_evidence.jsonl",
                 "source_resolution_review_queue.csv"):
        source = resolver_export / name
        if not source.exists(): raise FileNotFoundError(source)
        shutil.copy2(source, workspace / name)
    shutil.copy2(root/"review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv",
                 workspace/"source_review_tracking_seed.csv")
    _write(review_root/"legal_change_review_queue.jsonl",legal); _write(review_root/"quarantine_review_cases.jsonl",qc)
    thresholds={"build_id":final["gold_build_id"],"review_status":"DRAFT","reviewer":None,"reviewed_at":None,"k":10,
      "minimum_union_recall_at_k":0.8,"minimum_approved_queries":len(gold),"minimum_retrieval_queries":len(gold)-1,
      "required_query_types":sorted({x["query_type"] for x in gold})}
    (workspace/"quality_thresholds_draft.json").write_text(json.dumps(thresholds,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (workspace/"REVIEW_INSTRUCTIONS.md").write_text(INSTRUCTIONS,encoding="utf-8")
    provenance={"schema_version":1,"graph_build_id":build_id,"evaluation_build_id":final["gold_build_id"],
      "technical_archive":archive_path.name,"technical_archive_sha256":_sha(archive_path.read_bytes()),
      "counts":{k:len(v) for k,v in outputs.items()},"approved_records_created":0}
    (workspace/"package_provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    entries=[]
    for path in sorted(workspace.iterdir(),key=lambda x:x.name):
        entries.append({"path":path.name,"size":path.stat().st_size,"sha256":_sha(path.read_bytes())})
    (workspace/"MANIFEST.json").write_text(json.dumps({"schema_version":1,"build_id":build_id,"files":entries},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    output_dir.mkdir(parents=True,exist_ok=True); target=output_dir/f"offline_human_review_{build_id}.zip"
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for path in sorted(workspace.iterdir(),key=lambda x:x.name): z.write(path,path.name)
    digest=_sha(target.read_bytes()); target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n",encoding="utf-8")
    return {"schema_version":2,"build_id":build_id,"workspace":str(workspace),"zip":str(target),"sha256":digest,"counts":provenance["counts"]}

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,default=Path(".")); p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--resolver-export",type=Path,required=True); p.add_argument("--build-id",required=True); p.add_argument("--output-dir",type=Path,default=Path("build/review"))
    a=p.parse_args(); print(json.dumps(build(a.root.resolve(),a.archive,a.resolver_export,a.output_dir,a.build_id),ensure_ascii=True,indent=2))
