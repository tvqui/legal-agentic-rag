# ONLINE dated-query failure — correction report

## Original behaviour

Both `Điều 1 của Nghị định 145/2020/NĐ-CP quy định gì?` and the annual-leave question
returned HTTP 200 with `INSUFFICIENT_EVIDENCE`, no citations and route `COMPLEX` when
`query_date=2025-01-01`.

HTTP 200 was correct transport behaviour; the failure was the legal evidence decision.

## Root causes

1. The reference parser did not accept an instrument type between `của` and the number,
   so `Nghị định 145/2020/NĐ-CP` was lost.
2. Any past query date forced `COMPLEX` routing.
3. Every provision interval is still awaiting human review, so strict temporal filtering
   removed nearly all candidates.
4. Bracketed legal formulae were treated as citation markers.
5. Broad lexical overlap admitted unrelated labour provisions and duplicate consolidated
   versions.

## Corrected behaviour

- Exact dated lookup: `DIRECT`, one Article citation, zero graph edges,
  `PARTIAL_ALLOWED` with an explicit document-level temporal fallback warning.
- Annual leave: `STANDARD`, cited evidence from Article 113 of the 2019 Labour Code and
  Article 66 of Decree 145/2020, bounded to six distinct provision identities.
- Strict/non-provisional mode continues to abstain when provision-level temporal review
  is incomplete.
- Invalid dates return HTTP 422.
- Swagger exposes the complete `AnswerResponse` schema.

The full JSON responses are written to `artifacts/online_fixed_examples.json`.

## Validation

- `compileall`: PASS.
- Repository test suite: **159/159 PASS**.
- `/ready`: HTTP 200, `ready=true`.
- OpenAPI `/v1/answer` response schema: `AnswerResponse`.
- `git diff --check`: no whitespace errors; only pre-existing line-ending warnings.

The running Uvicorn process must be restarted to load these changes.
