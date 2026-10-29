from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vn_labor_online.config import load_config
from vn_labor_online.analysis import analyze, intake
from vn_labor_online.models import ExplicitReference, QueryRequest
from vn_labor_online.pipeline import OnlinePipeline
from vn_labor_online.retrieval import Retriever
from vn_labor_online.deployment import source_fingerprint


def _rss_bytes() -> tuple[int, str]:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            wintypes.DWORD(counters.cb),
        )
        if not ok:
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.WorkingSetSize), "windows_working_set"
    if sys.platform.startswith("linux"):
        resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE"), "linux_resident_set"
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024
    return int(peak * scale), "process_peak_rss"


def _request(row: dict) -> QueryRequest:
    allowed = {
        "question",
        "query_date",
        "conversation_context",
        "facts",
        "conversation_id",
        "conversation_turns",
    }
    return QueryRequest.model_validate({key: value for key, value in row.items() if key in allowed})


def _write_summary(path: Path, summary: dict) -> None:
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalized_reference(value: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper().replace("Đ", "D"))


def _naive_exact_ids(store, references) -> list[str]:
    result = []
    for reference in references:
        desired_level = "POINT" if reference.point else "CLAUSE" if reference.clause else "ARTICLE" if reference.article else None
        candidates = []
        for unit in store.units:
            number = unit.get("instrument_number") or unit.get("document_number")
            if reference.instrument_number and _normalized_reference(number) != _normalized_reference(reference.instrument_number):
                continue
            if reference.article and _normalized_reference(unit.get("article_number")) != _normalized_reference(reference.article):
                continue
            if reference.clause and _normalized_reference(unit.get("clause_number")) != _normalized_reference(reference.clause):
                continue
            if reference.point and _normalized_reference(unit.get("point_number")) != _normalized_reference(reference.point):
                continue
            if desired_level and unit.get("level") != desired_level:
                continue
            candidates.append(unit)
        candidates.sort(key=lambda unit: (-int(unit.get("authority_rank") or 0), unit["unit_id"]))
        result.extend(unit["unit_id"] for unit in candidates[:5])
    return list(dict.fromkeys(result))


def _corpus_exact_equivalence(store, retriever, maximum_probes: int = 64) -> dict:
    reference_keys = sorted(
        {
            (
                unit.get("instrument_number") or unit.get("document_number"),
                str(unit.get("article_number") or ""),
                str(unit.get("clause_number") or ""),
                str(unit.get("point_number") or ""),
            )
            for unit in store.units
            if unit.get("kind") == "PROVISION"
            and unit.get("level") in {"ARTICLE", "CLAUSE", "POINT"}
            and unit.get("article_number")
            and (unit.get("instrument_number") or unit.get("document_number"))
        }
    )
    stride = max(1, len(reference_keys) // maximum_probes)
    sample = reference_keys[::stride][:maximum_probes]
    mismatches = []
    probe_durations = []
    scan_durations = []
    for instrument, article, clause, point in sample:
        reference = ExplicitReference(
            instrument_number=instrument,
            article=article,
            clause=clause or None,
            point=point or None,
        )
        started = time.perf_counter()
        actual = [item.unit_id for item in retriever.exact([reference])]
        probe_durations.append(time.perf_counter() - started)
        started = time.perf_counter()
        expected = _naive_exact_ids(store, [reference])
        scan_durations.append(time.perf_counter() - started)
        if actual != expected:
            mismatches.append(
                {
                    "instrument": instrument,
                    "article": article,
                    "clause": clause,
                    "point": point,
                    "indexed": actual,
                    "scan": expected,
                }
            )
    subsequent_durations = sorted(probe_durations[1:])
    subsequent_scan_durations = sorted(scan_durations[1:])
    return {
        "available_reference_keys": len(reference_keys),
        "probes": len(sample),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "first_probe_seconds": round(probe_durations[0], 6) if probe_durations else None,
        "subsequent_probe_median_seconds": (
            round(statistics.median(subsequent_durations), 6) if subsequent_durations else None
        ),
        "subsequent_probe_p95_seconds": (
            round(subsequent_durations[max(0, math.ceil(len(subsequent_durations) * 0.95) - 1)], 6)
            if subsequent_durations
            else None
        ),
        "first_scan_probe_seconds": round(scan_durations[0], 6) if scan_durations else None,
        "subsequent_scan_median_seconds": (
            round(statistics.median(subsequent_scan_durations), 6) if subsequent_scan_durations else None
        ),
        "subsequent_scan_p95_seconds": (
            round(
                subsequent_scan_durations[
                    max(0, math.ceil(len(subsequent_scan_durations) * 0.95) - 1)
                ],
                6,
            )
            if subsequent_scan_durations
            else None
        ),
    }


def run(args: argparse.Namespace) -> dict:
    question_path = args.questions.resolve()
    out = args.out.resolve()
    rows = json.loads(question_path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Question file must contain a nonempty JSON list")
    if len({row.get("id") for row in rows if isinstance(row, dict)}) != len(rows):
        raise ValueError("Question IDs must be present and unique")
    if args.only_ids:
        selected_ids = set(args.only_ids)
        unknown_ids = selected_ids - {row["id"] for row in rows}
        if unknown_ids:
            raise ValueError(f"Unknown question IDs: {', '.join(sorted(unknown_ids))}")
        rows = [row for row in rows if row["id"] in selected_ids]
        if not rows:
            raise ValueError("The selected question IDs produced an empty plan")

    out.mkdir(parents=True, exist_ok=True)
    planned_path = out / "questions.json"
    result_path = out / "responses.jsonl"
    if planned_path.exists():
        if not args.resume or json.loads(planned_path.read_text(encoding="utf-8-sig")) != rows:
            raise ValueError("Output already contains a different or non-resumable question plan")
    else:
        if result_path.exists() and result_path.stat().st_size:
            raise ValueError("Responses exist without a matching question plan")
        planned_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.resume and result_path.exists() and result_path.stat().st_size:
        raise ValueError("Responses already exist; use --resume or choose a new output directory")

    completed = []
    if result_path.exists():
        completed = [
            json.loads(line)
            for line in result_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    done = {item["id"] for item in completed}
    if done - {row["id"] for row in rows}:
        raise ValueError("Existing responses contain IDs outside the question plan")

    cfg = load_config(args.config.resolve())
    cfg = cfg.model_copy(
        update={
            "retrieval": cfg.retrieval.model_copy(update={"dense_enabled": False}),
            "reranker": cfg.reranker.model_copy(update={"enabled": False}),
            "researcher": cfg.researcher.model_copy(
                update={"mode": "deterministic", "url": None, "model": None, "api_key": None, "health_url": None}
            ),
            "applicability": cfg.applicability.model_copy(
                update={"mode": "deterministic", "url": None, "model": None, "api_key": None, "health_url": None}
            ),
            "adjudication": cfg.adjudication.model_copy(
                update={"mode": "deterministic", "url": None, "model": None, "api_key": None, "health_url": None}
            ),
            "trace_dir": str(out / "traces"),
        }
    )

    # A question plan alone cannot bind resumed answers to the same code/data.
    identity={'online_source_fingerprint':source_fingerprint(),
        'config':cfg.model_dump(mode='json')}
    identity_path=out/'run_identity.json'
    if result_path.exists() and result_path.stat().st_size:
        if not identity_path.exists() or json.loads(identity_path.read_text(encoding='utf-8'))!=identity:
            raise ValueError('Code/configuration changed or identity is missing; use a fresh output directory')
    identity_path.write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    index_metrics = []
    original_init = Retriever.__init__

    def measured_retriever_init(self, store, config):
        before, memory_method = _rss_bytes()
        started = time.perf_counter()
        try:
            original_init(self, store, config)
        finally:
            after, _ = _rss_bytes()
            index_metrics.append(
                {
                    "elapsed_seconds": round(time.perf_counter() - started, 6),
                    "rss_delta_bytes": after - before,
                    "memory_method": memory_method,
                }
            )

    Retriever.__init__ = measured_retriever_init
    pipeline = None
    try:
        rss_before, memory_method = _rss_bytes()
        startup_started = time.perf_counter()
        pipeline = OnlinePipeline(cfg)
        startup_seconds = time.perf_counter() - startup_started
        rss_after, _ = _rss_bytes()
    finally:
        Retriever.__init__ = original_init

    providers = [
        pipeline.researcher.provider,
        pipeline.applicability.provider,
        pipeline.adjudicator.provider,
        getattr(pipeline.adjudicator, "review_provider", None),
    ]
    if any(provider is not None for provider in providers):
        pipeline.close()
        raise RuntimeError("Local smoke must not initialize any model provider")

    equivalent_queries = 0
    equivalent_references = 0
    index_mismatches = []
    corpus_index_equivalence = _corpus_exact_equivalence(pipeline.store, pipeline.retriever)
    for row in rows:
        history = [turn["content"] for turn in row.get("conversation_turns", [])]
        history.extend(row.get("conversation_context", []))
        analysis = analyze(intake(row["question"], history, row.get("query_date"), row.get("facts", {})))
        if not analysis.explicit_references:
            continue
        actual = [item.unit_id for item in pipeline.retriever.exact(analysis.explicit_references)]
        expected = _naive_exact_ids(pipeline.store, analysis.explicit_references)
        equivalent_queries += 1
        equivalent_references += len(analysis.explicit_references)
        if actual != expected:
            index_mismatches.append({"id": row["id"], "indexed": actual, "scan": expected})
    durations = [item["elapsed_seconds"] for item in completed]
    try:
        with result_path.open("a", encoding="utf-8") as handle:
            for row in rows:
                if row["id"] in done:
                    continue
                started = time.perf_counter()
                response = pipeline.ask(_request(row))
                elapsed = time.perf_counter() - started
                result = {
                    "id": row["id"],
                    "batch": row.get("batch"),
                    "question": row["question"],
                    "elapsed_seconds": round(elapsed, 6),
                    "response": response.model_dump(mode="json"),
                }
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
                durations.append(elapsed)
                completed.append(result)
                done.add(row["id"])

        retrieval_paths = {
            item["id"]: next(
                (
                    event.get("path")
                    for event in item["response"].get("trace", {}).get("events", [])
                    if event.get("event") == "retrieval_execution"
                ),
                None,
            )
            for item in completed
        }
        warm_probe_id = next(
            (
                item["id"]
                for preferred_path in ("EXACT", "HYBRID", "PROFILE")
                for item in completed
                if retrieval_paths[item["id"]] == preferred_path
            ),
            rows[0]["id"],
        )
        warm_probe_path = retrieval_paths[warm_probe_id] or "NO_RETRIEVAL"
        probe_row = next(row for row in rows if row["id"] == warm_probe_id)
        probe = _request(probe_row)
        warm_durations = []
        for _ in range(max(0, args.warm_repeats)):
            started = time.perf_counter()
            pipeline.ask(probe)
            warm_durations.append(time.perf_counter() - started)
    finally:
        pipeline.close()

    status_counts = Counter(item["response"]["status"] for item in completed)
    task_counts = Counter(
        part["answer_status"]
        for item in completed
        for part in item["response"].get("parts", [])
    )
    sorted_durations = sorted(durations)
    p95 = sorted_durations[max(0, math.ceil(len(sorted_durations) * 0.95) - 1)] if sorted_durations else 0
    summary = {
        "run_id": out.name,
        "mode": "LOCAL_DETERMINISTIC_NO_MODEL_INFERENCE",
        "artifact_build_id": completed[0]["response"]["build_id"] if completed else None,
        "planned": len(rows),
        "attempted": len(completed),
        "status_counts": dict(status_counts),
        "task_answer_status_counts": dict(task_counts),
        "pipeline_startup_seconds": round(startup_seconds, 6),
        "retriever_index_initialization": index_metrics[0],
        "retriever_indexed_units": pipeline.retriever._indexed_unit_count,
        "retriever_indexed_nodes": pipeline.retriever._indexed_node_count,
        "retriever_indexed_edges": pipeline.retriever._indexed_edge_count,
        "exact_lookup_equivalence": {
            "questions_compared": equivalent_queries,
            "references_compared": equivalent_references,
            "mismatch_count": len(index_mismatches),
            "mismatches": index_mismatches,
        },
        "corpus_exact_lookup_equivalence": corpus_index_equivalence,
        "process_rss_before_pipeline_bytes": rss_before,
        "process_rss_after_pipeline_bytes": rss_after,
        "process_rss_delta_bytes": rss_after - rss_before,
        "memory_measurement": memory_method,
        "first_request_seconds": completed[0]["elapsed_seconds"] if completed else None,
        "median_seconds": statistics.median(durations) if durations else None,
        "p95_seconds": p95,
        "warm_repeat_probe_id": warm_probe_id,
        "warm_repeat_retrieval_path": warm_probe_path,
        "warm_request_repeat_seconds": [round(value, 6) for value in warm_durations],
        "model_calls": 0,
        "effective_modes": {
            "researcher": cfg.researcher.mode,
            "applicability": cfg.applicability.mode,
            "adjudication": cfg.adjudication.mode,
            "dense": cfg.retrieval.dense_enabled,
            "reranker": cfg.reranker.enabled,
        },
        "legal_accuracy": "NOT_CERTIFIED_NO_APPROVED_GOLD",
        "output_files": ["questions.json", "responses.jsonl", "summary.json", "traces/"],
    }
    _write_summary(out / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded deterministic ONLINE smoke plan without model calls")
    parser.add_argument("--questions", type=Path, default=ROOT / "benchmarks/online_upgrade/questions.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/online_bm25.yaml")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--only-ids", nargs="+", help="Run a focused subset of question IDs")
    parser.add_argument("--warm-repeats", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
