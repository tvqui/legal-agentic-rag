# ONLINE implementation plan

## Audited baseline

ONLINE is pinned to technical archive `vn_labor_results_v8.1(aura).zip`, SHA-256
`afb456c552f6122101e4c92dd9c7d8240cf3f093483266b14aa0d111417ddf5a`.

- Graph build: `7b33c8206124e32d423ddfc02adbf58ad26cce68e8ac0154329d51b5dd667d38`.
- Retrieval units: 18,624; fingerprint `20c9d1c76bd250eda9067322c58b46e8210df0637f59f6f5a5a45911afcdd3f7`.
- Dense fingerprint: `05ae8fe99f3e430125be53f85db65f5796ceb9584ef9975f13ade452dc0574d6`.
- Evaluation build: `0c4d82edb5e23df65490b5b2eb9cb5623c2d5f1a8baf75693acf6329af9a92cc`.
- Registry, structure, graph, Dense, BM25 and Aura passed technical validation on that build.
- Human review remains DRAFT. Source authority is 0/95 final; 25 changes and all
  18,449 provision intervals remain unreviewed. The AI precheck is advisory only.
- The repository-local `artifacts/` directory is not the V8.1 technical build and must
  not be selected automatically for ONLINE.

## Reusable OFFLINE contracts

- `retrieval_units.jsonl` is the canonical evidence metadata/order for Dense and BM25.
- `dense/faiss.index` and `dense/metadata.jsonl` provide cosine/IP lookup.
- BM25S persisted files and `bm25/corpus.jsonl` provide lexical lookup.
- `nodes.jsonl`/`edges.jsonl` provide the portable graph; Neo4j remains an optional backend.
- `temporal.temporal_eligible` defines conservative, end-exclusive filtering.
- Gold/evaluation build fingerprints remain authoritative; DRAFT Gold can only produce
  provisional metrics.

## New modules and contracts

`vn_labor_online` will provide typed Pydantic query, evidence, answer and trace contracts;
a read-only artifact adapter with exact compatibility checks; exact/BM25/Dense retrieval;
RRF; conservative temporal/authority policy; bounded typed graph expansion with hub
penalty; evidence slots, gap/stopping policy; deterministic/applicability/reference audits;
a provider-independent grounded generator; orchestration; structured JSONL traces; CLI,
FastAPI, benchmark and evaluation entry points.

The default generator is deterministic and extractive so tests and demos do not require a
paid service. Optional OpenAI-compatible and Ollama providers may be configured later and
must return structured output without exposing chain-of-thought.

## Priorities

### P0

1. Compatibility/fingerprint gate and ZIP materialization.
2. Typed schemas/config/errors.
3. Query analysis, fact and freshness gates.
4. Exact + BM25 + Dense + RRF normalized evidence.
5. Temporal/authority policy.
6. Bounded typed graph expansion, evidence state, gaps and stopping.
7. Deterministic audit, extractive adjudication, reference audit and abstention.
8. End-to-end DIRECT/STANDARD/COMPLEX orchestration.
9. API/CLI, traces, tests and runbook.

### P1

- Approved-Gold benchmark, baseline/adaptive comparison, ablations and latency metrics.
- Optional Neo4j backend, reranker and external LLM providers.

### P2

- Additional Vietnamese retrievers only after approved Gold demonstrates improvement.
- Persistent multi-process cache and production authentication/rate limiting.

## Fail-closed rules

- Mixed build/index artifacts raise `OfflineArtifactMismatch`.
- Current-law queries receive a freshness warning while legal review is incomplete.
- An explicit historical date excludes unreviewed provision timelines; no current version
  is fabricated.
- URLs are copied only from retrieval-unit/source-catalog metadata.
- The generator may cite only verified evidence IDs supplied to it; reference audit removes
  unsupported references or abstains.
- DRAFT Gold never sets research evaluation to PASS.

## Validation order

Implement each layer with unit fixtures, then run all repository tests. Run the real V8.1
compatibility gate and smoke queries against the materialized archive. Finally publish the
architecture, runbook, research-evaluation and completion reports with separate technical,
research and human-legal statuses.
