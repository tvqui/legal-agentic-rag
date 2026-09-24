# LegalGraphRAG adaptation review

## Scope reviewed

Local reference repository: `D:/data_thô/legalgraphrag/LegalGraphRAG`.

The review covered its main pipeline, preprocessing, feature graph, direct and
community retrieval, reranking prompts, provision applicability judging and model
provider boundaries. The repository targets Chinese criminal judgment prediction;
it is not a drop-in engine for Vietnamese labour-law question answering.

## Useful design ideas

- Separate fact/feature extraction from retrieval.
- Combine direct semantic retrieval with graph/community retrieval.
- Deduplicate candidates after merging retrieval paths.
- Rerank retrieved cases before legal judgment.
- Check whether a retrieved provision actually applies to the supplied facts.

## Reasons it was not copied directly

- Its law, prompts, labels and evaluation targets are Chinese criminal-law specific.
- It predicts charges and imprisonment rather than answering versioned labour-law questions.
- It does not enforce Vietnamese source authority, provision version intervals, build
  fingerprints, source spans or citation/URL integrity.
- Several key decisions depend on free-form LLM output. The current project needs a
  deterministic safe path while human review and approved Gold data are incomplete.
- Community construction performs expensive all-pairs case similarity and is unsuitable
  for the current online request path.

## Improvements adopted in this project

1. Query feature routing now treats a date as a filter instead of automatically making
   every historical request complex.
2. Explicit references accept Vietnamese instrument labels, for example
   `Điều 1 của Nghị định 145/2020/NĐ-CP`.
3. Issue-guided applicability filters lexical false positives before generation.
4. Retrieval candidates are deduplicated by stable provision identity and answer size is
   bounded by route.
5. Graph expansion stops when the only unresolved gap is human provision-level temporal
   review, because graph traversal cannot resolve that review state.
6. Provisional mode may use a verified document-level interval and returns
   `PARTIAL_ALLOWED` with an explicit warning. Strict/non-provisional mode still fails
   closed when provision-level temporal review is missing.
7. Citation parsing distinguishes evidence IDs from bracketed legal formulae and requires
   every response citation to appear in the answer.
8. FastAPI now publishes the real `AnswerResponse` schema, and invalid dates return HTTP
   422 instead of reaching the pipeline.

## Deferred ideas

An LLM feature extractor, community summarizer and applicability judge can be evaluated
later as optional P2 components. They should only be promoted after approved Vietnamese
Gold queries exist and must never bypass temporal, authority, provenance and reference
audits.
