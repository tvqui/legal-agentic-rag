# ONLINE runbook

## Install and check

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[retrieval,online]"
.\.venv\Scripts\python.exe -m vn_labor_online.cli --config config/online.yaml check
```

`config/online.yaml` uses hybrid BGE-M3 + BM25. For a low-RAM/fast startup use
`config/online_bm25.yaml`. Both are pinned to the V8.1 ZIP SHA and graph build ID. Change
`artifact_source` when moving the archive, but do not change expected fingerprints unless
the replacement build has been independently validated.

To keep the YAML portable across machines, override the local archive and cache paths:

```powershell
$env:VN_LABOR_ARTIFACT_SOURCE = "D:/path/to/vn_labor_results.zip"
$env:VN_LABOR_ONLINE_CACHE = ".cache/online"
```

## Ask and serve

```powershell
.\.venv\Scripts\python.exe -m vn_labor_online.cli --config config/online.yaml ask "Điều 1 của 145/2020/NĐ-CP quy định gì?"
.\.venv\Scripts\python.exe scripts/serve_online.py --config config/online.yaml --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`. Use `GET /health`, `GET /ready`, then:

```json
{"question":"Điều 1 của 145/2020/NĐ-CP quy định gì?","query_date":null,"facts":{},"conversation_context":[]}
```

Với câu hỏi đánh giá tình huống, điền facts mà người dùng đã xác nhận, ví dụ:

```json
{
  "question": "Công ty chấm dứt hợp đồng với tôi vào tháng 6/2020 và báo trước 10 ngày có đúng luật không?",
  "facts": {
    "contract_type": "FIXED_TERM",
    "termination_reason": "thay đổi cơ cấu",
    "protected_status": "NONE"
  },
  "conversation_context": []
}
```

Nếu thiếu một trong các dữ kiện làm thay đổi kết quả (gồm loại hợp đồng, lý do, ngày,
thời gian báo trước hoặc tình trạng được bảo vệ), hệ thống chủ động trả
`NEED_MORE_FACTS` và không chạy retrieval. `facts` phải là dữ kiện thực tế người dùng xác
nhận; API không nhận cờ tự khai đã được người có chuyên môn duyệt để bỏ qua bước này.

After changing ONLINE code, stop the existing Uvicorn process with `Ctrl+C` and start it
again. The normal command does not enable automatic reload.

With `provisional_mode` enabled, a dated request may return `PARTIAL_ALLOWED` with
`DOCUMENT_LEVEL_TEMPORAL_FALLBACK_USED`. The cited document interval matches the requested
date, while provision-level temporal review is still pending. Setting `provisional_mode:
false` preserves strict fail-closed behaviour.

The applicability auditor and adjudicator default to deterministic mode. Optional Ollama
or HTTP JSON-schema providers are configured independently with
`VN_LABOR_APPLICABILITY_*` and `VN_LABOR_ADJUDICATION_*` from `.env.example`. Keep them
deterministic until evaluated against approved Gold data. Invalid provider output is
rejected; adjudication then falls back to the grounded deterministic response.

The first Dense request loads BGE-M3. On CPU this takes about one minute on the current
machine; subsequent requests reuse it. Use Kaggle/server GPU by setting
`embedding_device: cuda:0`. Traces are written to `artifacts/online_traces/`.

## Test and provisional evaluation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\online -t tests -q
.\.venv\Scripts\python.exe scripts/benchmark_retrieval.py --config config/online.yaml --gold review/inputs/v8_1/ai_precheck_return/gold_queries.jsonl
.\.venv\Scripts\python.exe scripts/evaluate_online_ablation.py --config config/online.yaml --gold review/inputs/v8_1/ai_precheck_return/gold_queries.jsonl
```

Until Gold is human-approved, reports must remain `PROVISIONAL_DRAFT_GOLD`.

Run the bounded local smoke plan without loading credentials or calling a model:

```powershell
$run = "artifacts/online_benchmarks/local_upgrade_candidate_$(Get-Date -Format yyyyMMddTHHmmss)"
.\.venv\Scripts\python.exe scripts\run_local_online_smoke.py `
  --questions artifacts\online_benchmarks\online_upgrade_smoke.questions.json `
  --config config\online_bm25.yaml --out $run
```

The local runner forces deterministic providers, disables dense retrieval and reranking,
and writes a separate run with request traces, startup/index memory estimates, per-question
timings, 64 corpus-derived indexed-versus-scan equivalence and timing probes, first/subsequent
exact-index and scan timings, and repeated warm timings for a request that actually performs
retrieval when available.
`--resume` continues only the exact saved plan.
These results test local logic and runtime behavior; they are not model-inference latency or
certified legal accuracy.

To re-run only selected regression cases after a code change, add `--only-ids` and always
choose a fresh output directory:

```powershell
$run = "artifacts/online_benchmarks/local_upgrade_regression_$(Get-Date -Format yyyyMMddTHHmmss)"
.\.venv\Scripts\python.exe scripts\run_local_online_smoke.py `
  --questions artifacts\online_benchmarks\online_upgrade_smoke.questions.json `
  --config config\online_bm25.yaml --only-ids smoke-13 smoke-14 smoke-15 smoke-17 `
  --out $run
```

Runner ablation hiện ghi citation precision/recall, wrong-version rate, abstention,
fabricated citations, evidence size, edge types, stop reasons, graph cost và latency.

### Fresh ONLINE upgrade smoke run

`artifacts/online_benchmarks/online_upgrade_smoke.questions.json` is a question-only
evaluation plan for literal lookup, historical law, separate answer tasks, monetary
outputs, exceptions, missing facts, follow-up, correction, contradiction, a new scenario,
actor changes, out-of-scope requests, and the named baseline reproductions
(TD006/TV003/CD001/TV001/TG001/HD001/HD002/NP001). It contains no Gold answers and is not
loaded by the application. The named baseline prompts are kept as questions only; their
DRAFT labels are not treated as legal correctness. Custom rows use isolated conversations
unless a `conversation_id` is explicitly shared by rows in one scenario.

Run from the repository root against an HTTPS backend that has the candidate ONLINE build:

```powershell
$run = "artifacts/online_benchmarks/online_upgrade_smoke_candidate_1"
.\.venv\Scripts\python.exe scripts\benchmark_online_reliability.py `
  --questions artifacts\online_benchmarks\online_upgrade_smoke.questions.json `
  --out $run --preflight-only
.\.venv\Scripts\python.exe scripts\benchmark_online_reliability.py `
  --questions artifacts\online_benchmarks\online_upgrade_smoke.questions.json `
  --out $run --timeout 230 --resume
```

The runner reads credentials through its existing `.env` configuration internally; it
does not print credential values. Check `preflight.json` for the deployed build, model,
reviewer, and feature signature before treating responses as candidate results. Use a new
`--out` directory for every code, artifact, or model change; `--resume` is only for
continuing the same run. `responses.jsonl`, traces/progress, and summary stay separate
from the 2026-10-29 baseline. `responses.jsonl` contains answers, citations, full response
traces, timings, and progress; the exported `quality_review` remains pending independent
review and the summary does not certify legal accuracy. Provider and timeout behavior
must also pass the local synthetic-secret regression tests; this smoke plan does not
force a real provider failure or consume a provider quota.

## Failure meanings

- `OfflineArtifactMismatch`: archive/build/index files are mixed or stale.
- `/health=200`, `/ready=503`: process is alive but artifacts failed initialization.
- `NEED_MORE_FACTS`: answer could change with missing facts; add the requested facts.
- `INSUFFICIENT_EVIDENCE`: verified evidence or a reviewed temporal version is unavailable.
- `CORPUS_MAY_BE_STALE`: current-law coverage has not been human-verified.

API failure logs contain the error ID, request ID, failed execution step, exception
type, and allow-listed error/HTTP/provider diagnostic fields only. Raw exception
messages and exception chains are intentionally omitted because upstream errors can
include credentials, URLs, prompts, or user data. Uvicorn may still print a traceback,
but unhandled ASGI exceptions are replaced with a metadata-only error before reaching
its request cycle. Correlate response `error_id` and `X-Request-ID` with bounded
execution-step diagnostics; do not copy authorization headers or raw provider payloads
into a report.
