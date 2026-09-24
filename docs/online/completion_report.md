# ONLINE completion report

## Repository/build

- Graph build: `7b33c8206124e32d423ddfc02adbf58ad26cce68e8ac0154329d51b5dd667d38`.
- Retrieval fingerprint: `20c9d1c76bd250eda9067322c58b46e8210df0637f59f6f5a5a45911afcdd3f7`.
- Dense fingerprint: `05ae8fe99f3e430125be53f85db65f5796ceb9584ef9975f13ade452dc0574d6`.
- Compatibility against the real V8.1 archive: PASS.

## Implementation and validation

Implemented typed contracts, read-only artifact compatibility, exact/BM25/Dense/RRF,
LegalIssue and dedicated case-law retrieval, temporal and authority policy, adaptive typed
graph retrieval, evidence slots/gaps/stopping, compression, deterministic/applicability/
reference audit, Verified Evidence Pack, deterministic and optional structured adjudication,
structured claims/traces,
CLI, FastAPI, retrieval benchmark and extended ablation runner.

- Final repository test run after the architecture completion: **186/186 passed**, with
  0 failures and 0 errors.
- Real exact dated query: `PARTIAL_ALLOWED`, route `DIRECT`, exactly one Article citation,
  zero graph edges and Reference Audit PASS. The partial status is caused only by the
  deliberately deferred human source/temporal review.
- Real BM25 load/query: PASS.
- Real BGE-M3 + FAISS query: PASS, five results, about 60 s cold CPU startup.
- Real STANDARD annual-leave query: `PARTIAL_ALLOWED`, six citations, Reference Audit PASS.
- Real COMPLEX historical termination query: bounded at 50 nodes/55 edges/two rounds and
  correctly abstains with `INSUFFICIENT_EVIDENCE`, zero output citations and zero claims
  when notice/reference slots remain unresolved.
- Fabricated citation invariant: PASS in tests; final IDs/URLs resolve to verified units.
- Explicit historical queries with unreviewed provision intervals abstain.
- Month/year queries that cross a version boundary request an exact date instead of
  misclassifying consecutive versions as conflicting or silently choosing one version.
- The graph wall-clock limit is global across all rounds, and provider-generated narrative
  is rebuilt only from structured, evidence-linked claims before Reference Audit.
- Client requests cannot self-assert human review or bypass the Fact Completeness Gate.
- Client facts cannot contain legal-decision flags such as `conditions_satisfied`; the
  deterministic applicability layer keeps conditional rules unresolved, while the optional
  structured auditor must decide them from actual facts.
- Conflict detection runs before route-level evidence truncation and keeps distinct
  `provision_version_id` values, so overlapping authoritative versions cannot disappear
  during deduplication.
- Research runners pin approved Gold to the OFFLINE evaluation fingerprint and measure the
  compressed Verified Evidence Pack rather than the uncompressed source unit.
- Real V8.1 smoke: exact lookup returns one cited unit with source span; annual-leave query
  returns cited Article 113/Article 66 evidence; incomplete termination scenario returns
  `NEED_MORE_FACTS` before retrieval.

## Dated-query correction

The API originally returned `INSUFFICIENT_EVIDENCE` for the two documented examples
because a past `query_date` forced `COMPLEX` routing and strict provision-level temporal
filtering removed otherwise usable evidence. The corrected policy is:

- a date acts as an applicability filter and does not by itself make the query complex;
- strict/non-provisional mode still requires reviewed provision intervals;
- provisional mode may use a verified document interval, returns `PARTIAL_ALLOWED`, and
  emits `DOCUMENT_LEVEL_TEMPORAL_FALLBACK_USED` plus the `applicable_version` limitation;
- explicit Vietnamese instrument labels are parsed, retrieval is filtered by legal issue,
  provision identities are deduplicated, and graph expansion stops for review-only gaps;
- bracketed formulae are no longer mistaken for citation IDs.
- month/year-only event dates use interval overlap and are not silently treated as the
  first day of the period;
- insufficient evidence always produces an abstention response rather than an incomplete
  legal assessment.

## Research and legal state

Draft retrieval metrics are recorded in `research_evaluation.md`. They are not an
official evaluation because Gold remains DRAFT. The AI precheck is useful annotation but
has no real reviewer identity/date. Source authority and provision-level temporal history
therefore remain provisional.

- `ONLINE_TECHNICALLY_COMPLETE = true`
- `ONLINE_RESEARCH_EVALUATED = false`
- `HUMAN_LEGAL_EVALUATION_COMPLETE = false`
- `READY_FOR_DEMO = true` (must display provisional/freshness warnings)
- `READY_FOR_RESEARCH_EXPERIMENT = false` (official experiment requires approved Gold)

There is no P0 code blocker for a provisional demo. P1 is human legal review, rebuilding
temporal versions and official Gold evaluation. P2 is optional retriever/reranker research.
The full requirement-by-requirement audit is in `architecture_audit.md`.
