"""Validate integrity and coverage of an offline review package."""
from __future__ import annotations
import argparse,hashlib,json,zipfile
from pathlib import Path
EXPECTED={"source_review_cases.jsonl":95,"legal_change_review_cases.jsonl":25,"quarantine_review_cases.jsonl":36,
 "quarantine_review_members.jsonl":837,"temporal_review_cases.jsonl":61,"temporal_review_members.jsonl":18449,
 "gold_query_candidates.jsonl":17}
def _sha(data): return hashlib.sha256(data).hexdigest()
def _rows(data): return [json.loads(x) for x in data.decode("utf-8-sig").splitlines() if x.strip()]
def validate(path:Path,build_id:str)->dict:
    errors=[]; observed={}
    with zipfile.ZipFile(path) as z:
        if z.testzip(): errors.append("CRC_FAILURE")
        names=set(z.namelist()); forbidden=[n for n in names if any(x in n.lower() for x in ("secret",".cache","pytorch_model","token"))]
        if forbidden: errors.append("forbidden:"+",".join(sorted(forbidden)))
        try: manifest=json.loads(z.read("MANIFEST.json"))
        except Exception as exc: manifest={}; errors.append("manifest:"+str(exc))
        if manifest.get("build_id")!=build_id: errors.append("build_id_mismatch")
        for item in manifest.get("files",[]):
            if item.get("path") not in names: errors.append("missing:"+str(item.get("path"))); continue
            data=z.read(item["path"])
            if len(data)!=item.get("size") or _sha(data)!=item.get("sha256"): errors.append("hash:"+item["path"])
        loaded={}
        for name,count in EXPECTED.items():
            try: loaded[name]=_rows(z.read(name)); observed[name]=len(loaded[name])
            except Exception as exc: errors.append(f"read:{name}:{exc}"); continue
            if len(loaded[name])!=count: errors.append(f"count:{name}:{len(loaded[name])}!={count}")
            if name.endswith("cases.jsonl") or name=="gold_query_candidates.jsonl":
                ids=[r.get("case_id") or r.get("query_id") for r in loaded[name]]
                if None in ids or len(ids)!=len(set(ids)): errors.append("ids:"+name)
                if any(r.get("review_status")!="DRAFT" or r.get("reviewer") or r.get("reviewed_at") for r in loaded[name]): errors.append("fabricated_review:"+name)
        for prefix,count_field in (("quarantine","member_count"),("temporal","provision_version_count")):
            cases=loaded.get(prefix+"_review_cases.jsonl",[]); members=loaded.get(prefix+"_review_members.jsonl",[])
            counts={x["case_id"]:0 for x in cases}
            for m in members:
                if m.get("case_id") not in counts: errors.append("orphan_"+prefix)
                else: counts[m["case_id"]]+=1
            for case in cases:
                if counts[case["case_id"]]!=case.get(count_field): errors.append("member_count:"+case["case_id"])
    return {"schema_version":1,"passed":not errors,"build_id":build_id,"package":str(path),"package_sha256":_sha(path.read_bytes()),"observed":observed,"errors":sorted(set(errors))}
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--package",type=Path,required=True); p.add_argument("--build-id",required=True)
    p.add_argument("--out",type=Path,default=Path("artifacts/reports/offline_human_review_package_validation.json")); a=p.parse_args()
    result=validate(a.package,a.build_id); a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=True,indent=2)); raise SystemExit(0 if result["passed"] else 1)
