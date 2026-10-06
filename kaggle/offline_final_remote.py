"""Build current OFFLINE artifacts from a trusted extraction checkpoint.

The workflow creates a complete technical checkpoint before optional AI work.
Consequently, a later Kaggle/Ollama failure cannot erase the last complete
technical build, and the AI cache can be resumed from a recovery export.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "artifacts/reports"
STATE = REPORTS / "offline_final_run.json"
RUN = REPORTS / "kaggle_run.json"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _state(stage: str, status: str = "RUNNING", **details) -> dict:
    previous = {}
    if STATE.exists():
        try:
            previous = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    value = {
        **previous,
        "schema_version": 1,
        "status": status,
        "stage": stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    _write_json(STATE, value)
    print("OFFLINE_FINAL_STATE " + json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)
    return value


def _run(arguments: list[str], *, check: bool = True) -> int:
    print("RUN:", " ".join(arguments), flush=True)
    result = subprocess.run([sys.executable, *arguments], cwd=ROOT)
    if check and result.returncode:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(arguments)}")
    return result.returncode


def _configure_ai(config: Path, max_provisions: int) -> None:
    import yaml

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    knowledge = raw.setdefault("knowledge", {})
    knowledge.update({
        "checklist_mode": "hybrid_ai",
        "case_ontology_mode": "ai",
        "ai_provider": os.getenv("VN_LABOR_OFFLINE_AI_PROVIDER", "ollama"),
        "ai_url": os.getenv("VN_LABOR_OFFLINE_AI_URL", "http://127.0.0.1:11434/api/chat"),
        "ai_model": os.getenv("VN_LABOR_OFFLINE_AI_MODEL", "qwen3:8b"),
        "ai_timeout_seconds": int(os.getenv("VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS", "120")),
        "ai_cache_dir": "artifacts/04_knowledge/ai_cache",
        "ai_max_provisions": max_provisions,
    })
    config.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _technical_audit() -> dict:
    # Without --neo4j the only expected failed construction check is the live
    # Neo4j check. All local registry/structure/graph/Dense/BM25 checks must pass.
    _run(["scripts/validate_outputs.py", "--config", "config/kaggle.yaml"], check=False)
    report_path = REPORTS / "final_outputs_validation.json"
    if not report_path.is_file():
        raise RuntimeError("Audit did not create final_outputs_validation.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures = [
        row for row in report.get("checks", [])
        if not row.get("passed") and row.get("check") != "Neo4j live verification"
    ]
    local_stages = {
        stage: all(row.get("passed") for row in report.get("checks", [])
                   if row.get("stage") == stage and row.get("check") != "Neo4j live verification")
        for stage in ("registry", "structure", "graph", "indexes")
    }
    if failures or not all(local_stages.values()):
        examples = [f"{row.get('stage')}/{row.get('check')}: {row.get('detail')}" for row in failures[:8]]
        raise RuntimeError("Local technical validation failed: " + " | ".join(examples))
    return {"passed": True, "stages": local_stages,
            "offline_ready_for_online": bool(report.get("offline_ready_for_online"))}


def _export(name: str) -> None:
    _run(["kaggle/remote.py", "export", "--archive-name", name])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/kaggle.yaml")
    parser.add_argument("--ai-max-provisions", type=int, default=250)
    parser.add_argument("--skip-ai", action="store_true")
    parser.add_argument("--load-aura", action="store_true")
    parser.add_argument("--refresh-extraction", action="store_true",
                        help="Run page-v5 selective OCR and page-quality audit before rebuilding")
    args = parser.parse_args()
    if args.ai_max_provisions < 0:
        raise ValueError("--ai-max-provisions cannot be negative")

    config = ROOT / args.config
    technical_name = "vn_labor_results_technical_checkpoint.zip"
    recovery_name = "vn_labor_results_recovery.zip"
    final_name = "vn_labor_results.zip"
    started = datetime.now(timezone.utc).isoformat()
    _write_json(RUN, {"pipeline_exit_code": 1, "stage": "starting", "started_at": started})
    _state("starting", started_at=started, ai_enabled=not args.skip_ai,
           ai_max_provisions=args.ai_max_provisions, load_aura=args.load_aura)

    try:
        if args.refresh_extraction:
            _state("extraction_quality_refresh")
            _run(["-m", "vn_labor_offline.cli", "extract", "--config", str(config)])
        _state("technical_rebuild")
        _run(["-m", "vn_labor_offline.cli", "rebuild", "--config", str(config), "--mode", "heuristic"])
        technical = _technical_audit()
        _write_json(RUN, {"pipeline_exit_code": 0, "stage": "technical_checkpoint",
                          "started_at": started, "technical_validation": technical})
        _state("technical_checkpoint", technical_validation=technical)
        _export(technical_name)

        ai_enabled = not args.skip_ai and args.ai_max_provisions > 0
        if ai_enabled:
            _state("ai_enrichment", technical_checkpoint=technical_name)
            _configure_ai(config, args.ai_max_provisions)
            _run(["-m", "vn_labor_offline.cli", "enrich", "--config", str(config), "--mode", "hybrid_ai"])
            technical = _technical_audit()
            _state("ai_complete", technical_validation=technical)
        else:
            _state("ai_skipped", technical_validation=technical)

        if args.load_aura:
            _state("aura_load")
            _run(["kaggle/remote.py", "aura"])
        else:
            _run(["kaggle/remote.py", "audit"], check=False)

        validation_path = REPORTS / "final_outputs_validation.json"
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        neo_path = REPORTS / "neo4j_validation.json"
        neo = json.loads(neo_path.read_text(encoding="utf-8")) if neo_path.exists() else {}
        if args.load_aura and (not validation.get("ready_for_offline_v1") or neo.get("passed") is not True):
            raise RuntimeError("Final four-output/Aura validation did not pass")

        completed = datetime.now(timezone.utc).isoformat()
        run_report = {
            "pipeline_exit_code": 0,
            "stage": "complete",
            "started_at": started,
            "completed_at": completed,
            "technical_validation": technical,
            "ai_enabled": ai_enabled,
            "ai_max_provisions": args.ai_max_provisions if ai_enabled else 0,
            "aura_loaded": args.load_aura,
            "build_id": neo.get("build_id"),
        }
        _write_json(RUN, run_report)
        _state("complete", status="PASS", completed_at=completed,
               final_archive=final_name, build_id=neo.get("build_id"))
        _export(final_name)
        return 0
    except BaseException as exc:
        failed = datetime.now(timezone.utc).isoformat()
        _write_json(RUN, {"pipeline_exit_code": 1, "stage": "failed", "started_at": started,
                          "failed_at": failed, "error_type": type(exc).__name__, "error": str(exc)})
        _state("failed", status="FAILED", failed_at=failed,
               error_type=type(exc).__name__, error=str(exc),
               technical_checkpoint=technical_name, recovery_archive=recovery_name)
        try:
            _export(recovery_name)
        except Exception as export_error:
            print("Recovery export also failed:", repr(export_error), flush=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
