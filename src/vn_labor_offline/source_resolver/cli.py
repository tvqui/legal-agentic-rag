from __future__ import annotations

import argparse
import csv
import difflib
import json
from pathlib import Path
import yaml

from .evidence import write_jsonl
from .fetchers.http import HttpFetcher
from .import_seed import import_records
from .provider_registry import ProviderRegistry
from .resolver import SourceResolver
from .store import EvidenceStore
from .audit import run_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vn-labor-source-resolver")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-seed")
    imp.add_argument("--csv", required=True)
    imp.add_argument("--catalog")
    imp.add_argument("--corpus-root")
    imp.add_argument("--db", default="artifacts/00_manifest/source_resolution.sqlite")
    imp.add_argument("--dry-run", action="store_true")
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--record")
    resolve.add_argument("--all", action="store_true")
    resolve.add_argument("--csv", required=True)
    resolve.add_argument("--db", default="artifacts/00_manifest/source_resolution.sqlite")
    resolve.add_argument("--registry", default="config/source_provider_registry.yaml")
    resolve.add_argument("--dry-run", action="store_true")
    resolve.add_argument("--network", action="store_true")
    resolve.add_argument("--provider")
    resolve.add_argument("--limit", type=int)
    resolve.add_argument("--direct-only", action="store_true")
    resolve.add_argument("--resume", action="store_true")
    resolve.add_argument("--cache", default=".cache/source_resolver")
    resolve.add_argument("--catalog")
    resolve.add_argument("--corpus-root")
    resolve.add_argument("--rate-limit", type=float, default=1.0)
    resolve.add_argument("--state", action="append", help="restrict seed states")
    resolve.add_argument("--retry-blocked", action="store_true")
    resolve.add_argument("--batch-size", type=int)
    resolve.add_argument("--browser", action="store_true",
                         help="enable deterministic Playwright download controls")
    export = sub.add_parser("export")
    export.add_argument("--db", default="artifacts/00_manifest/source_resolution.sqlite")
    export.add_argument("--out", default="artifacts/00_manifest")
    merge = sub.add_parser("merge")
    merge.add_argument("--db", default="artifacts/00_manifest/source_resolution.sqlite")
    merge.add_argument("--dry-run", action="store_true", required=True)
    merge.add_argument("--catalog", default="config/source_catalog.yaml")
    merge.add_argument("--out", default="artifacts/reports/source_catalog_merge.diff")
    audit = sub.add_parser("audit")
    audit.add_argument("--db", required=True)
    audit.add_argument("--export-dir", required=True)
    audit.add_argument("--registry", default="config/source_provider_registry.yaml")
    audit.add_argument("--overrides", default="config/source_candidate_overrides.yaml")
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import-seed":
        rows = import_records(args.csv, args.catalog, args.corpus_root)
        if args.dry_run:
            print(json.dumps({"records": len(rows), "states": _counts(rows)}, ensure_ascii=True, sort_keys=True))
            return 0
        store = EvidenceStore(args.db)
        try:
            store.upsert_records(rows)
        finally:
            store.close()
        return 0
    if args.command == "resolve":
        rows = import_records(args.csv, args.catalog, args.corpus_root)
        selected = rows if args.all else [r for r in rows if r["record_id"] == args.record]
        if not args.all and not selected:
            raise SystemExit("record not found")
        if args.direct_only:
            selected = [row for row in selected if row.get("direct_download_url")]
        if args.state:
            selected = [row for row in selected if row.get("state") in set(args.state)]
        if args.retry_blocked:
            selected = [row for row in selected if row.get("state") == "BLOCKED"]
        if args.batch_size is not None:
            selected = selected[:max(0, args.batch_size)]
        if args.provider:
            registry = ProviderRegistry.load(args.registry)
            selected = [r for r in selected if any(
                (provider := registry.match(url, role, r["source_group"])) is not None
                and provider.provider_id == args.provider
                for role, url in (("IDENTITY", r.get("exact_source_url", "")),
                                  ("BINARY", r.get("direct_download_url", ""))))]
        if args.limit is not None:
            selected = selected[:max(0, args.limit)]
        if args.dry_run:
            print(json.dumps({"records": len(selected), "record_ids": [r["record_id"] for r in selected],
                              "candidates": [{"record_id": r["record_id"], "provider": (ProviderRegistry.load(args.registry).match(r["direct_download_url"], "BINARY", r["source_group"]).provider_id if r.get("direct_download_url") and ProviderRegistry.load(args.registry).match(r["direct_download_url"], "BINARY", r["source_group"]) else None),
                                             "url": r.get("direct_download_url", "")} for r in selected],
                              "queued_candidates": sum(bool(r.get("exact_source_url") or r.get("direct_download_url") or r.get("current_candidate_url")) for r in selected)}, sort_keys=True))
            return 0
        store = EvidenceStore(args.db)
        results = []
        try:
            store.ensure_records(selected)
            resolver = SourceResolver(
                ProviderRegistry.load(args.registry), store, args.cache,
                fetcher=HttpFetcher(rate_limit=args.rate_limit),
                browser_fetcher=(
                    __import__("vn_labor_offline.source_resolver.fetchers.playwright",
                               fromlist=["PlaywrightFetcher"]).PlaywrightFetcher()
                    if args.browser else None
                ))
            for seed_row in selected:
                row = seed_row | (store.record_for_id(seed_row["record_id"]) or {})
                if args.network:
                    results.append(resolver.resolve_record(row, network=True, resume=args.resume))
                else:
                    resolver.queue_record(row)
        finally:
            store.close()
        if args.network:
            print(json.dumps(results, ensure_ascii=True, sort_keys=True))
        return 0
    if args.command == "export":
        store = EvidenceStore(args.db)
        try:
            rows = store.export_records()
            evidence = store.export_evidence()
        finally:
            store.close()
        target = Path(args.out)
        write_jsonl(target / "source_catalog_auto.jsonl", rows)
        write_jsonl(target / "source_resolution_evidence.jsonl", evidence)
        states = _counts(rows)
        (target.parent / "reports").mkdir(parents=True, exist_ok=True)
        (target.parent / "reports" / "source_resolution_summary.json").write_text(
            json.dumps({"records": len(rows), "states": states, "fetched": states.get("FETCHED", 0),
                        "exact_sha": states.get("AUTO_EXACT_SHA", 0), "content_match": states.get("AUTO_CONTENT_MATCH", 0),
                        "review": states.get("NEEDS_REVIEW", 0), "blocked": states.get("BLOCKED", 0)},
                       ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with (target / "source_resolution_review_queue.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["relative_path", "state", "canonical_identifier"])
            writer.writeheader()
            writer.writerows({key: row.get(key, "") for key in writer.fieldnames} for row in rows if row.get("state") in {"NEEDS_REVIEW", "NEEDS_DISCOVERY", "BLOCKED"})
        return 0
    if args.command == "merge":
        store = EvidenceStore(args.db)
        try:
            records = store.export_records()
        finally:
            store.close()
        catalog_path = Path(args.catalog)
        original_text = catalog_path.read_text(encoding="utf-8")
        original = original_text.splitlines(keepends=True)
        proposed = yaml.safe_load(original_text) or {}
        sources = proposed.setdefault("sources", {})
        for row in records:
            if row.get("state") == "AUTO_EXACT_SHA":
                entry = sources.get(row["relative_path"])
                proposed_url = row.get("identity_url") or row.get("binary_url")
                if entry is not None and proposed_url:
                    entry["source_url"] = proposed_url
        proposed_text = yaml.safe_dump(proposed, allow_unicode=True, sort_keys=False)
        diff = difflib.unified_diff(original, proposed_text.splitlines(keepends=True),
                                    fromfile=str(catalog_path), tofile=f"{catalog_path} (proposal)")
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(diff), encoding="utf-8")
        print(f"merge --dry-run: wrote proposal diff to {output}; catalog was not modified")
        return 0
    if args.command == "audit":
        result = run_audit(args.db, args.export_dir, args.registry, args.overrides)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result["passed"] or not args.strict else 1
    return 2


def _counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
