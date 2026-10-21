from __future__ import annotations
from pathlib import Path
import yaml
from .util import stable_id, write_jsonl, read_jsonl
from .evidence import locate_evidence, locate_document_evidence


def load_issue_config(project_root: Path) -> dict:
    p = project_root / "config" / "issues.yaml"
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    issues = raw.get("issues", {})
    vocabulary = raw.get('ontology_vocabulary') or {}
    if vocabulary.get('enabled', False):
        from .ontology_vocabulary import lexical_aliases
        path = (project_root / vocabulary['path']).resolve()
        if not path.is_relative_to(project_root.resolve()):
            raise ValueError('Ontology vocabulary must remain inside the project')
        aliases, _ = lexical_aliases(path, vocabulary['sha256'])
        for issue_key, keywords in aliases.items():
            if issue_key not in issues:
                raise ValueError(f'Unknown OFFLINE ontology crosswalk target: {issue_key}')
            existing = issues[issue_key].get('keywords', [])
            combined = dict.fromkeys(str(word).casefold() for word in [*existing, *keywords])
            issues[issue_key]['keywords'] = list(combined)
    return issues


def score_issues(text: str, issues: dict, min_score: int = 1) -> list[dict]:
    t = (text or "").lower()
    out = []
    for key, cfg in issues.items():
        hits = [kw for kw in cfg.get("keywords", []) if kw.lower() in t]
        if len(hits) >= min_score:
            out.append({"issue_key": key, "label_vi": cfg.get("label_vi", key), "score": len(hits), "hits": hits[:12]})
    return sorted(out, key=lambda x: (-x["score"], x["issue_key"]))


def build_issue_assignments(provisions: list[dict], cases: list[dict], cfg: dict, output_dir: Path) -> tuple[list[dict], list[dict]]:
    issues = load_issue_config(cfg["project_root"])
    raw_config = yaml.safe_load((cfg['project_root'] / 'config/issues.yaml').read_text(encoding='utf-8')) or {}
    vocabulary = raw_config.get('ontology_vocabulary') or {}
    if vocabulary.get('enabled', False):
        from .ontology_vocabulary import lexical_aliases
        import json
        _, audit = lexical_aliases(cfg['project_root'] / vocabulary['path'], vocabulary['sha256'])
        report = output_dir / 'reports/ontology_vocabulary.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    min_score = int(cfg["knowledge"].get("issue_min_score", 1))
    nodes = [{"issue_id": stable_id(k, prefix="issue"), "issue_key": k, "label_vi": v.get("label_vi", k)} for k,v in issues.items()]
    segments = {s["segment_id"]:s["text"] for s in read_jsonl(output_dir/'03_structure/segments.jsonl')}
    documents = {d["document_id"]:d for d in read_jsonl(output_dir/'02_registry/documents.jsonl')}
    extracted = {x["file_id"]:x for x in read_jsonl(output_dir/'01_extracted/documents.jsonl')}
    edges = []
    for p in provisions:
        source=extracted.get(documents.get(p['document_id'],{}).get('file_id'),{})
        for it in score_issues(p.get("text", ""), issues, min_score):
            evidence_text,evidence_span,status=locate_evidence(p,it['hits'][0],
                segments.get(p.get('segment_id'),''),source.get('text',''),source.get('page_provenance',[]))
            edges.append({"source_id": p["provision_id"], "target_id": stable_id(it["issue_key"], prefix="issue"), "type": "RELATES_TO_ISSUE", "score": it["score"], "evidence": ", ".join(it["hits"]),
                          "evidence_text": evidence_text, "evidence_span": evidence_span,
                          "matched_keywords": it['hits'],
                          "provenance_status": "VERIFIED" if status == "RESOLVED" else status})
    for c in cases:
        source=extracted.get(documents.get(c['document_id'],{}).get('file_id'),{})
        for it in score_issues(c.get("search_text", ""), issues, min_score):
            evidence_text,evidence_span,status=locate_document_evidence(it['hits'][0],
                source.get('text',''),source.get('page_provenance',[]))
            edges.append({"source_id": c["case_id"], "target_id": stable_id(it["issue_key"], prefix="issue"), "type": "HAS_ISSUE", "score": it["score"], "evidence": ", ".join(it["hits"]),
                          "evidence_text": evidence_text, "evidence_span": evidence_span,
                          "matched_keywords":it['hits'],
                          "provenance_status": "VERIFIED" if status == "RESOLVED" else status})
    accepted=[r for r in edges if r.get('provenance_status')=='VERIFIED']
    write_jsonl(output_dir / "04_knowledge" / "issue_review_queue.jsonl",
                [r for r in edges if r.get('provenance_status')!='VERIFIED'])
    write_jsonl(output_dir / "04_knowledge" / "issues.jsonl", nodes)
    write_jsonl(output_dir / "04_knowledge" / "issue_edges.jsonl", accepted)
    return nodes, accepted
