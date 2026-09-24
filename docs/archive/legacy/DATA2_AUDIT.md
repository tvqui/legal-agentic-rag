# Audit data(2).zip — 2026-09-12

## Inventory
- 96 raw files in uploaded ZIP.
- 84 PDF, 6 HTML, 4 DOC, 1 DOCX, 1 JSON sidecar.
- No SHA256 duplicates detected.
- 11 laws, 21 decrees, 10 circulars, 4 resolutions, 4 consolidated, 11 historical.
- 12 judgments, 9 cassation decisions, 3 precedents.
- 2 official-guidance pages, 6 social-insurance guidance files, 3 ILO supplementary files.

`SOURCE_AUTHORITY.json` is intentionally treated as sidecar metadata, not as a retrievable legal document, so the pipeline processes 95 content documents.

## Smoke test without OCR
The updated parser was run against the exact corpus with OCR deliberately disabled:
- 95 content documents
- 8,429 legal provisions parsed
- 24 judicial items
- 6,029 diagnostic checklist items
- 14,206 graph nodes
- 30,087 graph edges

The remaining `NO_ARTICLE_PARSED` / `NO_MACHINE_TEXT` items are mainly scanned/low-text PDFs; `RUN_0_SETUP_FULL.bat` + Docling OCR is the intended fix.

## Decision
**Stop collecting current-law files for now. Begin OFFLINE construction.** Historical pre-2021 coverage and a larger judgment corpus can be expanded after the v1 pipeline is stable.
