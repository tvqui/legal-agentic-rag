# OFFLINE V7 Completion Report

## Ground truth

V7 was implemented incrementally from `vn_labor_results_V6.zip`, SHA-256:

`d613f694f5e2d7f7dc49184367af26c93d919e9dae1a845ca79eb57f08088f10`

V6 is the last remote execution result. Its registry/structure/graph/indexes and Aura comparison remain the baseline only; they do not certify the new V7 artifacts.

## Implemented changes

- Added pre-extraction source catalog resolution and review queue.
- Added explicit segment/document/page coordinate fields and `provision_spans.jsonl`.
- Added stable `ProvisionIdentity` and `ProvisionVersion` artifacts while preserving V6 provision IDs.
- Added `legal_changes.jsonl` for resolved and unresolved AMEND/REPEAL/REPLACE/IMPLEMENT candidates.
- Added evidence/provenance fields to DiagnosticItems and LegalIssue assignments.
- Propagated V2 identity, temporal, source SHA and provenance metadata to retrieval units.
- Added approved-only gold schema/gate and `scripts/evaluate_gold.py`.
- Added V7 package fallback for a locked package produced by another Windows identity.
- Updated Kaggle notebook/runbook for two private inputs and V6 checkpoint restore.

## Schema and migration

Schema advances from V6 to V7. Extraction/page caches are reusable only when their existing fingerprints and page provenance are present. Structure, legal knowledge, graph, retrieval units, BM25, Dense, Aura and gold reports are downstream-invalidated when their schema/fingerprint changes. No local corpus OCR, Dense rebuild or Aura load was run.

## Source catalog status

The V6 corpus has 95 manifest records. The curated catalog contains 61 explicit URL/SHA entries and no explicit provider or collected-at fields. Therefore V7 records remain `UNVERIFIED` unless provider and other required provenance are explicitly supplied; no provider or collection date was inferred. The resolver emits one record per manifest file and places incomplete records in `source_review_queue.jsonl`. SHA mismatches fail closed before extraction.

## Provenance and temporal status

Accepted provisions receive segment, document and page coordinate fields. PDF page ranges are resolved only from existing `page_provenance.text_start/text_end`; non-paginated sources use `page_status=NOT_APPLICABLE`. Ambiguous segment-to-document matches remain unresolved rather than using a silent first match.

Provision identities are stable from `instrument_id + canonical path`. Existing occurrence/version IDs remain unchanged. Document-derived dates are labelled `INHERITED_DOCUMENT`; no provision-level legal interval is promoted to `VERIFIED` without evidence.

## Legal changes and derived knowledge

`legal_changes.jsonl` preserves candidates including unresolved records. Graph edges are emitted only through the existing confidence and endpoint checks. `IMPLEMENTS=0` in V6 remains a valid corpus result; V7 does not manufacture one. Diagnostic and issue evidence is marked `VERIFIED`, `AMBIGUOUS` or `UNRESOLVED`.

## Tests and local verification

- Full unittest suite: **85 tests PASS**.
- Kaggle bundle tests: **10 tests PASS**.
- `git diff --check`: PASS (only normal CRLF conversion warnings).
- Pylance syntax checks for changed Python modules: PASS.
- Isolated V6 review: started against the supplied ZIP in a separate review output; remote review result must be recorded when it completes.
- Full `compileall` encountered Windows access-denied errors writing existing `__pycache__` files under `scripts` and `tests`; source syntax checks and unittest compilation succeeded.

## Package

Generated package report:

- `kaggle_upload/vn_labor_kaggle_v7.zip`
- SHA-256: `14e165c3ca156518086a038817523a57e58a7135c0d8d32766b015d40d5269fd`
- Size: 229.79 MB
- Files: 154
- Corpus files: 96
- ZIP CRC: PASS
- Notebook code syntax: PASS
- `uploaded=false`
- `remote_execution_tested=false`

The pre-existing `vn_labor_kaggle.zip` could not be replaced because it is owned/locked by another Windows identity; the V7 package is therefore written under the explicit V7 filename.

## Remote and gold status

Kaggle V7 has not been executed. Dense/BM25 must be rebuilt if the retrieval fingerprint changes, and Aura must be reloaded if the graph fingerprint changes. No approved legal gold set exists; `scripts/evaluate_gold.py` returns `NOT_EVALUATED`, and `offline_ready_for_online=false`.

## Final state for this workspace

```text
ready_for_offline_v1 = chưa xác nhận cho build mới cho đến khi Kaggle audit xong
offline_ready_for_online = false
legal_quality_evaluation = NOT_EVALUATED
Kaggle V7 run required
Dense/BM25 rebuild required nếu retrieval fingerprint đổi
Aura reload required nếu graph fingerprint đổi
```

## Remaining P1/P2

- Human source provenance review for the 34 incomplete records.
- Human review of quarantined canonical paths and short provisions.
- Approved gold queries/qrels and metric evaluation.
- Optional OCR backend factory and structured table artifacts after benchmark.
- Expansion and legal review of the judicial corpus.
