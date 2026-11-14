"""Freeze artifact-grounded DEVELOPMENT gold before model inference (no legal approval)."""
from __future__ import annotations
import argparse, hashlib, json, re, zipfile
from datetime import date
from pathlib import Path

FILES = {"units": "06_indexes/retrieval_units.jsonl", "nodes": "05_graph/nodes.jsonl", "edges": "05_graph/edges.jsonl"}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def read_artifact(artifact):
    """Return (records by units/nodes/edges, SHA256 by file); never execute/extract ZIP."""
    artifact = Path(artifact)
    data, hashes = {}, {}
    with zipfile.ZipFile(artifact) if artifact.is_file() else _Directory(artifact) as source:
        names = source.namelist()
        for key, suffix in FILES.items():
            found = [n for n in names if n.replace("\\", "/").endswith(suffix)]
            if len(found) != 1:
                raise ValueError(f"Expected one {suffix}, found {len(found)}")
            raw = source.read(found[0]); hashes[key] = digest(raw)
            data[key] = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    return data, hashes

class _Directory:
    def __init__(self, root): self.root = root
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def namelist(self): return [p.relative_to(self.root).as_posix() for p in self.root.rglob("*.jsonl")]
    def read(self, name): return (self.root / name).read_bytes()

def normalized(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def resolve(units, locator, as_of):
    target = date.fromisoformat(as_of)
    candidates = []
    for unit in units:
        if unit.get("kind") != "PROVISION": continue
        if any(normalized(unit.get(field)) != normalized(locator.get(field)) for field in
               ("instrument_number", "version_role", "article_number", "clause_number", "point_number")):
            continue
        start, end = unit.get("valid_from"), unit.get("valid_to")
        if not start: raise ValueError(f"Missing validity start: {locator}")
        if date.fromisoformat(start[:10]) <= target and (not end or target < date.fromisoformat(end[:10])):
            candidates.append(unit)
    if len(candidates) != 1:
        raise ValueError(f"Missing/ambiguous/date-incompatible locator ({len(candidates)}): {locator}")
    unit = candidates[0]
    if not normalized(unit.get("source_text")) or not str(unit.get("source_url") or "").startswith("https://"):
        raise ValueError(f"Missing exact source text/HTTPS source: {locator}")
    if unit.get("provenance_status") not in ("VALID", "VERIFIED", "RESOLVED"):
        raise ValueError(f"Unusable provenance: {unit.get('provenance_status')}: {locator}")
    return unit

def bind(spec, units, edges):
    selected = [resolve(units, loc, spec["query_date"]) for loc in spec["locators"]]
    context_support = []
    for locator in spec.get("context_locators", []):
        context = resolve(units, locator, spec["query_date"])
        quote = normalized(context["source_text"])
        if not any(quote in normalized(u.get("ancestor_context")) for u in selected):
            raise ValueError(f"Context-only parent not included verbatim in selected child: {locator}")
        context_support.append({"unit_id": context["unit_id"], "locator": locator,
            "quote": context["source_text"], "source_url": context["source_url"],
            "role": "CONTEXT_ONLY_NOT_ADDITIONAL_RETRIEVAL_TARGET"})
    ids = [u["unit_id"] for u in selected]
    support = []
    for index, (unit, locator) in enumerate(zip(selected, spec["locators"])):
        support.append({"group_index": index, "unit_ids": [unit["unit_id"]], "locator": locator,
            "quote": unit["source_text"], "ancestor_context": unit.get("ancestor_context", []),
            "source_url": unit["source_url"], "valid_from": unit.get("valid_from"), "valid_to": unit.get("valid_to"),
            "version_id": unit.get("version_id"), "document_number": unit.get("document_number"),
            "temporal_verified": unit.get("provision_temporal_verified", False),
            "source_catalog_status": unit.get("source_catalog_status"), "provenance_status": unit.get("provenance_status")})
    direct = [{"source": e["source"], "target": e["target"], "type": e["type"]} for e in edges
              if e.get("type") == "REFERENCES" and e.get("source") in ids and e.get("target") in ids]
    result = dict(spec)
    result.update(required_groups=[[x] for x in ids], support=support, context_support=context_support,
        graph_support={"direct_references": direct, "direct_reference_count": len(direct),
            "hypothesis": spec["group"], "graph_required": False,
            "note": "Missing graph edges are a diagnostic negative, not evidence that the question is unanswerable."},
        label_status="ARTIFACT_VERIFIED_DRAFT", review_status="DRAFT", reviewer=None, reviewed_at=None,
        evaluation_partition="DEVELOPMENT", legal_status="PROVISIONAL")
    return result

def build(artifact, output, specs_path=None):
    output = Path(output)
    specs_path = Path(specs_path) if specs_path else Path(__file__).with_name("questions.jsonl")
    raw_specs = specs_path.read_bytes()
    specs = [json.loads(x) for x in raw_specs.decode("utf-8-sig").splitlines() if x.strip()]
    if len(specs) != 24 or len({s["id"] for s in specs}) != 24:
        raise ValueError("Expected exactly 24 unique predeclared questions")
    expected = {"cross_reference", "conditions_exceptions", "cross_document", "independent_controls"}
    if set(s["group"] for s in specs) != expected or any(sum(s["group"] == g for s in specs) != 6 for g in expected):
        raise ValueError("Expected six questions per predeclared group")
    records, hashes = read_artifact(artifact)
    bound = [bind(s, records["units"], records["edges"]) for s in specs]
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "gold.jsonl": b"".join(canonical(s) + b"\n" for s in bound),
        "inference.jsonl": b"".join(canonical({k:s[k] for k in ("id", "question", "query_date")}) + b"\n" for s in specs),
        "corpus.jsonl": b"".join(canonical(u) + b"\n" for u in records["units"])}
    for name, payload in payloads.items():
        destination = output / name
        if destination.exists() and destination.read_bytes() != payload:
            raise ValueError(f"Frozen output differs; use a NEW experiment directory: {destination}")
    manifest = {"schema_version": 1, "questions": len(bound), "artifact_files_sha256": hashes,
        "spec_sha256": digest(raw_specs), "outputs_sha256": {k:digest(v) for k,v in payloads.items()},
        "label_status": "ARTIFACT_VERIFIED_DRAFT", "legal_status": "PROVISIONAL",
        "reviewer": None, "reviewed_at": None, "partition": "DEVELOPMENT",
        "query_date": "2026-09-15", "graph_support_counts": {s["id"]:s["graph_support"]["direct_reference_count"] for s in bound},
        "limitations": ["Artifact coverage is not legal human approval.", "No independent held-out generalization claim.",
            "Queries authored before measuring Graph ON/OFF scores; not selected by score gains.",
            "Temporal/source catalog review remains provisional; dates describe artifact metadata.",
            "No identical-text equivalence between consolidated and original versions is presumed."]}
    manifest_bytes = canonical(manifest) + b"\n"
    destination = output / "manifest.json"
    if destination.exists() and destination.read_bytes() != manifest_bytes:
        raise ValueError("Frozen manifest differs; use a NEW experiment directory")
    for name, payload in payloads.items(): (output / name).write_bytes(payload)
    destination.write_bytes(manifest_bytes)
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args(); print(json.dumps(build(args.artifact, args.output), ensure_ascii=False, indent=2))
