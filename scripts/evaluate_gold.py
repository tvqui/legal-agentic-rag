"""Evaluate only human-approved gold records; never creates legal answers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from vn_labor_offline.gold import evaluate_gold, fingerprint_json
from vn_labor_offline.util import read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    result = evaluate_gold(args.artifacts)
    result["build_fingerprints"] = {}
    for name in ("00_manifest/source_catalog_resolved.jsonl", "00_manifest/files.jsonl",
                 "05_graph/nodes.jsonl", "05_graph/edges.jsonl", "06_indexes/retrieval_units.jsonl"):
        path = args.artifacts / name
        result["build_fingerprints"][name] = fingerprint_json(list(read_jsonl(path))) if path.exists() else None
    target = args.artifacts / "07_evaluation/evaluation_summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
