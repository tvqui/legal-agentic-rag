# OFFLINE V7 Implementation Plan

## Ground truth and constraints

- Base checkpoint: `vn_labor_results_V6.zip`
- SHA-256: `d613f694f5e2d7f7dc49184367af26c93d919e9dae1a845ca79eb57f08088f10`
- Preserve V6 IDs and artifacts where their semantics remain valid.
- Local validation is isolated only: no corpus OCR, Dense rebuild, Docker, Aura, or Kaggle upload.

## Incremental phases

1. **Catalog resolution**: validate manifest coverage and SHA bindings before extraction; emit resolved catalog and a truthful review queue.
2. **Coordinate provenance**: formalize coordinate spaces and emit page/document maps plus provision spans without inventing PDF offsets or non-paginated pages.
3. **Structure and temporal identity**: enrich Chapter/Section metadata; materialize stable ProvisionIdentity and ProvisionVersion artifacts with conservative temporal status.
4. **Legal changes and derived provenance**: emit LegalChange candidates, preserve unresolved cases, attach evidence spans to relations, checklists, and issues.
5. **Retrieval and graph compatibility**: propagate V2 metadata, add identity/version nodes and edges, invalidate downstream fingerprints where schema changes.
6. **Gold evaluation framework**: add draft/approved schemas, review queue, fingerprint-bound evaluator, and keep `NOT_EVALUATED` without approved gold.
7. **Packaging and reporting**: update Kaggle notebook/bootstrap/package/runbook, run unit tests, compileall, diff check, isolated V6 review, and write the completion report.

## Migration policy

Schema version advances from V6 to V7. Existing extraction/page caches may be reused when their fingerprints and required provenance fields are present. Structure, knowledge, graph, retrieval, BM25, Dense, Neo4j, and gold evaluation outputs are downstream-invalidated when their schema or fingerprints change. V6 source text and page provenance are not re-OCR'd solely for this migration.
