# Automatic Legal Source Resolver — Implementation Report

> **Archive note (2026-09-23):** The paths in the historical sections below
> describe earlier smoke runs and may no longer exist after repository cleanup.
> The canonical resolver state is now
> `artifacts/00_manifest/source_resolution_p2_3_full_v3.sqlite` with its
> matching `source_resolution_p2_3_full_v3_export/` directory.

## Current status: P2.3 deterministic readiness gate

P2.3 adds the strict, read-only `source-resolver audit` command, deterministic
gate JSON, fail-closed override validation, selected-evidence aggregation, and
browser cleanup hardening. The current readiness decision is
**NOT_READY_EXTERNAL** until a fresh four-record live smoke is available; the
offline implementation gates and tests are the acceptance criteria and must not
be bypassed. The required V8.1 seed inputs are not present in this checkout
under `review/inputs/`, so a fresh 95-record seed audit was not fabricated.

The audit command writes `artifacts/reports/source_resolution_p2_3_readiness.json`
and returns non-zero when any strict gate fails. It does not mutate SQLite,
exports, catalogs, corpus files, or downstream artifacts.

### Historical results

#### P2.2 browser trust and VBPL gate

P2.2 remains **NOT_READY** for a limited provider batch. Candidate state
consistency is now enforced in both SQLite columns and metadata, identity
mismatch/shell pages become `NEEDS_REVIEW`, and evidence selection is shared
between live and resume paths. Browser controls retain their immutable
candidate and create a derived `BINARY` candidate keyed by the observed
download URL, with parent linkage and separate page/download URL evidence.
Binary trust now requires authority verification in addition to valid bytes.
VBPL probes controlled routes and classifies the legacy homepage/loading shell
without clicking it. Record-specific fallbacks are in
`config/source_candidate_overrides.yaml`.

Fresh P2.2 smoke artifacts:

- DB: `artifacts/00_manifest/source_resolution_p2_2b.sqlite`
- export: `artifacts/00_manifest/source_resolution_p2_2b_export/`
- cache: `.cache/source_resolver_p2_2b/`

| record | provider | state | SHA | identity source | final binary URL | blocking reasons | warnings |
|---|---|---|---|---|---|---|---|
| `f7b2a95453d4d6b6` | ILO/NATLEX | `AUTO_EXACT_SHA` | `YES` | `BINARY_CONTENT` | official PDF download | none | identity page 403 |
| `cbd1f72df7f0d08f` | Công báo | `NEEDS_REVIEW` | `NO` | `IDENTITY_PAGE` | official g7 stream | old VBPL 404, Playwright disabled | identity mismatch, SHA mismatch, VBPL shell |
| `114cafe0807308bb` | VBPL | `BLOCKED` | `NOT_DOWNLOADED` | `IDENTITY_PAGE` | empty | old route 404 | identity mismatch, VBPL shell |

Network execution was limited to these three records, concurrency one and
one-second rate limiting. Playwright was **not run** in network smoke because
the VBPL pages were detected as homepage/loading shells and no proven selector
was available. The mocked browser trust path is covered offline. No 76-record
batch, catalog merge, corpus change, or downstream pipeline was run.

Validation commands and actual results:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m unittest tests.test_source_resolver -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Results: **24/24 resolver tests**, **125/125 repository tests**, compile
successful. No important tests were skipped.

P2.1 is **NOT_READY** for a limited provider batch. The resolver now keeps
seed provenance separate from resolver results, selects the best independent
binary/identity evidence, applies role-specific provider routes, and treats
JavaScript download controls as controls rather than binary files. The
official Công báo pages for the 06/2020 and 24/2022 instruments now yield the
observed `g7.cdnchinhphu.vn/api/download/stream` PDF/DOC candidates; those
files are fetched and verified as real binaries, but their SHA-256 values do
not match the corpus, so both records remain `NEEDS_REVIEW` with
`resolved_sha_match=NO`. The HTML identity pages are never written to
`final_binary_url`.

Fresh smoke artifacts (not the earlier P2/direct8 databases) are:

- DB: `artifacts/00_manifest/source_resolution_p2_1d.sqlite`
- export: `artifacts/00_manifest/source_resolution_p2_1d_export/`
- cache: `.cache/source_resolver_p2_1d/`

| record | provider | state | resolved SHA | identity source | final identity URL | final binary URL | reasons |
|---|---|---|---|---|---|---|---|
| `f7b2a95453d4d6b6` | ILO/NATLEX | `AUTO_EXACT_SHA` | `YES` | `BINARY_CONTENT` | binary URL | official PDF URL | identity page 403 retained as warning |
| `cbd1f72df7f0d08f` | Công báo | `NEEDS_REVIEW` | `NO` | `IDENTITY_PAGE` | official `.htm` page | official g7 stream URL | `SHA_MISMATCH` |
| `ebd563a10f4e9b84` | Công báo | `NEEDS_REVIEW` | `NO` | `IDENTITY_PAGE` | official `.htm` page | official g7 stream URL | `SHA_MISMATCH` |
| `114cafe0807308bb` | VBPL | `BLOCKED` | `NOT_DOWNLOADED` | `IDENTITY_PAGE` | official history page | empty | attachment/control still requires deterministic browser handling |

The focused resolver suite passes **21/21** tests and the repository suite
passes **122/122** tests. The full repository command also exercises existing
integration tests; no resolver batch, catalog merge, corpus replacement, or
downstream production run was initiated. Playwright is opt-in through
`resolve --browser`; missing package/browser support is reported as an
explicit blocker. The 76-record batch remains intentionally unrun.

The remaining release blockers are fixture coverage for the complete
Playwright verification path and a provider-specific VBPL fixture for the
10/2020 download control. Therefore the implementation must not yet be
labelled `READY_FOR_LIMITED_PROVIDER_BATCH`.

## 1. Kiến trúc

Resolver được đặt trong `src/vn_labor_offline/source_resolver/` và tách các lớp:

- `import_seed.py`: đọc CSV có header bắt buộc, kiểm path/SHA/source group và ánh xạ trạng thái seed.
- `normalizer.py`, `models.py`: chuẩn hóa identifier, `ItemID` VBPL và model trạng thái.
- `provider_registry.py`: allowlist HTTPS/domain/route, vai trò identity/binary/status và phân loại official/secondary.
- `providers/`: adapter VBPL và các ranh giới adapter Công báo, Chính phủ, Tòa án, ILO.
- `fetchers/`: HTTP mặc định; Playwright là optional boundary, không được import bắt buộc.
- `verification/`: authority, identity, binary magic/MIME/SHA, content và decision rules.
- `store.py`, `evidence.py`: SQLite schema version 3, idempotent records/candidates, parent-child browser provenance và deterministic JSONL.
- `cli.py`: `import-seed`, `resolve`, `export` và `merge --dry-run`.

## 2. Files and dependency changes

Added the resolver package, `config/source_provider_registry.yaml`, deterministic tests, and this report. The existing CLI and `pyproject.toml` now expose `source-resolver` and `vn-labor-source-resolver`. No mandatory dependency was added; HTTP uses the standard library and browser support remains optional.

## 3. P1 review fixes and validation performed

The review blockers were fixed in code:

- `resolve --network` now fetches identity/binary candidates, validates redirects,
  extracts HTML identity, verifies binary magic/MIME/SHA, writes evidence, and
  updates candidate and record state.
- A SHA mismatch is always `NEEDS_REVIEW` unless an independently supplied,
  verified content comparator is present; the default binary verifier never
  emits `AUTO_CONTENT_MATCH`.
- HTTP uses manually bounded redirects, allowlist checks before every request and
  after the final response, retries/backoff/rate limiting, streaming size limits,
  temporary files, atomic rename, and cleanup.
- Candidate roles preserve separate `identity_url`, `binary_url`, and
  `status_url`; VBPL normalization only changes the identity route.
- SQLite now has foreign keys, schema version 2, evidence/state update methods,
  deterministic ordering, and idempotent upserts.
- `merge --dry-run` renders a unified proposal diff to a separate file and
  never writes the source catalog.
- Playwright remains optional and exposes a deterministic action log; missing
  Playwright is an explicit runtime condition rather than a silent fallback.

Commands run:

```text
python -m compileall -q src/vn_labor_offline/source_resolver
python -m vn_labor_offline.source_resolver.cli import-seed --csv review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv --catalog config/source_catalog.yaml --dry-run
python -m unittest tests.test_source_resolver
python -m unittest discover -s tests -q
```

VBPL fixture normalization was checked for `ItemID=162453`.

The environment does not include `pytest`; the resolver tests use the
standard-library `unittest` runner. Gate A completed with **12/12 resolver
tests passing** and **113/113 repository tests passing**.

## 4. Seed and dry-run results

The real CSV imported with 95 rows and these observed distributions:

| source group | count |
|---|---:|
| LEGAL_DOCUMENT | 57 |
| JUDICIAL | 24 |
| SUPPLEMENTARY | 10 |
| CONSOLIDATED | 4 |

Observed collection results are `ACCESS_BLOCKED=84`, `SOURCE_NOT_FOUND=10`, and `MULTIPLE_CANDIDATES=1`. Initial resolver states are `FETCH_PENDING=84`, `NEEDS_DISCOVERY=10`, and `NEEDS_REVIEW=1`. No seed row has downloaded bytes, so no row is promoted to `AUTO_EXACT_SHA`.

The default tests and dry-run do not use the network. After Gate A, one
opt-in network smoke test was run:

| record | requested/final URL | provider | HTTP/MIME | size | downloaded SHA | corpus SHA | state | reasons |
|---|---|---|---|---:|---|---|---|---|
| `0a5bedfa76589540` | `https://congbobanan.toaan.gov.vn/5ta1115796t1cvn/QD_GDT_Sam__Vien_Y_te_Ma_hoa.pdf` | `toaan` | 200 / `application/pdf` | 288587 | `98b2fbc1ac163ce0629132076830c2591f7c134b0698db6935c7ab6312fb6d6f` | same | `NEEDS_REVIEW` | `IDENTITY_FAILED` |

The binary evidence is an exact SHA match, but the seed supplied no separate
identity page for this direct attachment. The resolver therefore correctly
kept the **record** at `NEEDS_REVIEW`; it did not silently promote the record
to an exact source. Evidence is in
`.cache/source_resolver/downloads/` and
`artifacts/00_manifest/source_resolution_smoke.sqlite`.

## 5. Limits and next steps

The current implementation provides the deterministic P0/P1 network path and
testable verification primitives. Provider-specific attachment extraction
beyond direct URLs, judicial/ILO discovery, and browser execution still require
staged follow-up work. Those paths remain reviewable and cannot infer approval
from `official_source=YES`.

The production `config/source_catalog.yaml` currently contains 61 entries and
no judicial entries, while the review draft contains all 95 seed paths.
Therefore strict import against the production catalog fails with an explicit
missing-record error; this is an integrity conflict, not a reason to weaken
the check. Use the review draft only as an explicit candidate catalog input
until the catalog is reviewed.

## 6. Windows and Kaggle

On Windows, from the repository directory:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m vn_labor_offline.source_resolver.cli import-seed --csv review/inputs\v8_1\source_review_return_v8_1\source_review_tracking.csv --catalog config\source_catalog.yaml --dry-run
```

On Kaggle/Linux, use the environment's Python and POSIX paths with the same module command. Playwright is not required for import, dry-run, export, or unit tests; install browser dependencies only for an explicitly enabled browser smoke test.

Opt-in smoke command:

```bash
PYTHONPATH=src python -m vn_labor_offline.source_resolver.cli resolve \
  --record 0a5bedfa76589540 \
  --csv review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv \
  --registry config/source_provider_registry.yaml \
  --db artifacts/00_manifest/source_resolution_smoke.sqlite \
  --cache .cache/source_resolver --network --resume --rate-limit 1
```

## 7. Corpus/catalog safety statement

The resolver never writes files under `data/` and never modifies
`config/source_catalog.yaml`. `merge --dry-run` now writes a minimal proposal
diff containing only relevant fields for exact matches; it never writes the
catalog. Seed metadata remains candidate evidence; reviewer fields and
`APPROVED` are never generated.

## 8. P1.3 identity, state, evidence, and direct8 results

P1.3 added bounded PDF/DOCX binary text extraction, strict identifier
normalization, binary-derived identity evidence (`identity_source=BINARY_CONTENT`),
per-candidate outcome aggregation, immutable evidence events, missing-corpus
integrity failures, direct-only filtering, and explicit provider matching.
The registry matches all eight direct seed URLs exactly once as `BINARY`:
`toaan` (3), `vbpl` (3), `chinhphu_files` (1), and `ilo` (1).

Offline Gate A remains deterministic: **12/12 resolver tests** and
**113/113 repository tests** pass. The direct-only dry-run selected exactly
8 records and did not access the network.

The direct8 opt-in run used a new database and cache:

* database: `artifacts/00_manifest/source_resolution_direct8.sqlite`
* cache: `.cache/source_resolver_direct8/`
* evidence events: 9 (the first record was intentionally run once before the
  batch and then resumed)

| record | provider | requested URL | final URL | MIME/size | downloaded SHA vs corpus SHA | identity source | state | reasons |
|---|---|---|---|---|---|---|---|---|
| `0a5bedfa76589540` | toaan | official PDF | same URL | application/pdf / 288587 | exact | BINARY_CONTENT | AUTO_EXACT_SHA | — |
| `3cd079702d920169` | toaan | official PDF | official PDF final | application/pdf | exact | BINARY_CONTENT | AUTO_EXACT_SHA | — |
| `1abc1abc4bb092e4` | toaan | official PDF | official PDF final | application/pdf | exact | BINARY_CONTENT | AUTO_EXACT_SHA | — |
| `cbd1f72df7f0d08f` | vbpl | FileData PDF | unavailable after retry | — | — | — | BLOCKED | network/HTTP failure |
| `9653087ff5a0d9f8` | chinhphu_files | datafiles PDF | official PDF final | application/pdf | exact | IDENTITY_PAGE | AUTO_EXACT_SHA | — |
| `114cafe0807308bb` | vbpl | FileData PDF | unavailable after retry | — | — | — | BLOCKED | network/HTTP failure |
| `ebd563a10f4e9b84` | vbpl | FileData PDF | unavailable after retry | — | — | — | BLOCKED | network/HTTP failure |
| `f7b2a95453d4d6b6` | ilo | NATLEX PDF | unavailable after retry | — | — | — | BLOCKED | HTTP 403 |

The database summary was `AUTO_EXACT_SHA=4` and `BLOCKED=4`; no
`AUTO_CONTENT_MATCH` was generated. The four exact results include resumed
evidence already present for the ILO record; all exact decisions still
required official authority, valid PDF bytes, matching SHA, and verified
identity. Network failures were not downgraded to `FETCH_PENDING`.

The earlier smoke database
`artifacts/00_manifest/source_resolution_smoke.sqlite` was not modified by
the direct8 run. Neither the corpus nor
`config/source_catalog.yaml` nor
`review/inputs/v8_1/source_catalog_review_draft.yaml` was modified.

For a Kaggle smoke run, use the review draft and a fresh output location:

```bash
PYTHONPATH=src python -m vn_labor_offline.source_resolver.cli resolve \
  --all --direct-only --limit 8 --network --rate-limit 1 --resume \
  --csv review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv \
  --catalog review/inputs/v8_1/source_catalog_review_draft.yaml \
  --registry config/source_provider_registry.yaml \
  --db artifacts/00_manifest/source_resolution_direct8.sqlite \
  --cache .cache/source_resolver_direct8
```

## 9. P2 attachment resolution and constrained smoke results

P2 added explicit required/optional candidate capability, deterministic HTML
attachment extraction with URL canonicalization and deduplication, provider
fallback candidates for the three specified VBPL instruments, and separate
seed/resolver export fields. An optional identity-page failure no longer
overrides a successful official binary exact-SHA plus binary-derived identity.
Identity pages that fetch successfully but lack the identifier remain
`NEEDS_REVIEW`; they are not reported as `FETCHED`.

Offline validation after P2 changes:

* `python -m compileall -q src/vn_labor_offline/source_resolver`: PASS
* `python -m unittest tests.test_source_resolver`: **14/14 PASS**
* `python -m unittest discover -s tests -q`: **115/115 PASS**
* direct-only dry-run: 8 records, no network access

The constrained P2 smoke used a new database and cache:

* database: `artifacts/00_manifest/source_resolution_p2.sqlite`
* export: `artifacts/00_manifest/source_resolution_p2_export/`
* cache: `.cache/source_resolver_p2/`
* records attempted: 4 (the three previously blocked direct records plus
  NATLEX); evidence events after retries: 17

| record | provider/path | state | downloaded SHA / corpus SHA | identity source | warnings/reasons |
|---|---|---|---|---|---|
| `f7b2a95453d4d6b6` | ILO/NATLEX binary | `AUTO_EXACT_SHA` | exact | `BINARY_CONTENT` | identity page HTTP 403 retained as warning |
| `114cafe0807308bb` | VBPL ItemID 146696 | `BLOCKED` | not available | `IDENTITY_PAGE` | old attachment HTTP 404; identity not found |
| `cbd1f72df7f0d08f` | VBPL ItemID 143667 -> Công báo fallback | `NEEDS_REVIEW` | HTML/error SHA differs from corpus | `IDENTITY_PAGE` | old URL HTTP 404; fallback identity matched; no valid binary attachment |
| `ebd563a10f4e9b84` | VBPL ItemID 159196 -> Công báo fallback | `NEEDS_REVIEW` | HTML/error SHA differs from corpus | `IDENTITY_PAGE` | old URL HTTP 404; fallback identity matched; no valid binary attachment |

The P2 result is therefore **1 exact, 2 review, 1 blocked**. No
`AUTO_CONTENT_MATCH` was created. The three fallback paths are recorded as
candidate provenance, but no fallback HTML page was treated as a binary.
The direct8 database remains preserved and unchanged. The corpus,
production catalog, and review-draft catalog were not modified.

P2 did not run the 76-record batch: attachment discovery still requires
provider-specific fixtures for pages whose attachment controls are generated
by JavaScript. The next safe step is a fixture-backed sample for each
provider, followed by batches of at most five per provider with concurrency
one and a one-second rate limit. No catalog merge or downstream pipeline was
run.

## P2.3 readiness self-check

| Gate | Expected | Actual | PASS/FAIL | Evidence path |
|---|---:|---:|---|---|
| Resolver unit tests | 0 failures/errors | 24/24 passed | PASS | `tests/test_source_resolver.py` |
| Repository tests | 0 failures/errors | 125/125 passed | PASS | `tests/` |
| Strict readiness audit | exit 0 | exit 1 on protected P2.2 artifact | FAIL (protected historical evidence) | `artifacts/reports/source_resolution_p2_3_readiness.json` |
| V8.1 seed invariants | 95 records | required `review/inputs/` missing | FAIL (missing input) | `review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv` |
| Fresh four-record smoke | live evidence | not run | FAIL (external) | `artifacts/00_manifest/source_resolution_p2_3.sqlite` |

No failed item was converted to PASS by changing expected output. Production
catalogs, corpus files, pipeline artifacts, and Aura data remain untouched.
