# ONLINE

ONLINE uses exact lookup, BM25, BGE-M3 Dense retrieval, issue anchors, and
bounded graph traversal. Evidence must pass temporal, authority,
applicability, and reference audits before it can support an answer.

The runtime is pinned to `build/releases/vn_labor_results_v8_1_aura.zip` and
its SHA-256 in `config/online*.yaml`. This immutable release contains the
registry, structured provisions, graph, Dense index, BM25 index, and matching
Neo4j validation report. The working `artifacts/` directory remains reserved
for pipeline output and runtime traces.

See the [detailed runbook](online/runbook.md) and
[ONLINE architecture](online/architecture.md).
