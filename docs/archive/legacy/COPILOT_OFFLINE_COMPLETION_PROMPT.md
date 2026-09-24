# Prompt dành cho Copilot — hoàn thiện OFFLINE sau mốc V6

Sao chép toàn bộ nội dung từ phần **BẮT ĐẦU PROMPT** đến **KẾT THÚC PROMPT** và gửi cho Copilot trong workspace hiện tại.

---

## BẮT ĐẦU PROMPT

Bạn hãy đóng vai **Senior Software Engineer + Legal NLP / GraphRAG Engineer** và trực tiếp tiếp tục hoàn thiện phần:

**OFFLINE — DATA & KNOWLEDGE CONSTRUCTION**

của dự án hỏi đáp pháp luật lao động Việt Nam trong workspace hiện tại.

### 1. Cách làm việc bắt buộc

- Đọc code, config, tests và báo cáo hiện có trước khi sửa. Không suy đoán kiến trúc chỉ từ prompt này.
- Đây là công việc tiếp nối mốc V6. Không viết lại project từ đầu và không hoàn tác các sửa đổi đang có trong working tree.
- Tiến hành theo hướng incremental. Giữ tương thích với artifact/schema V6 khi hợp lý; nếu cần migration phải ghi rõ schema version, lý do và cache nào bị vô hiệu.
- Không dừng ở việc viết kế hoạch. Sau khi audit, tiếp tục triển khai, chạy test nhẹ, kiểm tra artifact cô lập, cập nhật gói Kaggle và viết báo cáo.
- Không sửa validator để che lỗi, không hard-code PASS, không hạ threshold chỉ để đạt chỉ số.
- Không bịa URL, provider, ngày thu thập, metadata pháp lý, temporal interval, target relation hoặc gold answer.
- Không dùng LLM output làm nguồn pháp luật authoritative.
- Không đưa adaptive retrieval, query router, graph expansion policy, multi-agent reasoning, Researcher/Auditor/Adjudicator hoặc evidence sufficiency loop của ONLINE vào OFFLINE.
- Không tự chạy pipeline nặng trên máy local. Máy local chỉ dùng cho unit/regression tests, compile/package checks và isolated review không OCR/không Dense/không Aura.
- Không tự upload Kaggle, dùng Kaggle Secrets, nạp Aura hoặc commit Git nếu người dùng chưa giao quyền rõ ràng. Hãy chuẩn bị đầy đủ file để người dùng chạy.
- Nếu một phần phụ thuộc dữ liệu hoặc legal review của con người, hãy hoàn thiện framework, tạo review queue/template, giữ trạng thái trung thực và ghi blocker. Không giả kết quả để tuyên bố hoàn thành.

### 2. Ground truth phải dùng

Mốc kết quả mới nhất là:

`C:\Users\Acer\Downloads\vn_labor_results_V6.zip`

SHA-256:

`d613f694f5e2d7f7dc49184367af26c93d919e9dae1a845ca79eb57f08088f10`

V6 đã chạy trên Kaggle T4, nạp Aura và có kết quả thật:

- pipeline exit code: 0
- preflight: 0
- audit trước Aura: 1; đây là trạng thái trung gian vì graph build mới chưa được xác minh trên live Neo4j
- Neo4j load + audit cuối: 0
- `ready_for_offline_v1 = true`
- `offline_ready_for_online = false`
- `legal_quality_evaluation.status = NOT_EVALUATED`
- registry/structure/graph/indexes: PASS
- documents: 95
- provisions: 18.449
- retrieval units: 18.624
- cases: 24
- diagnostic items: 15.284
- graph nodes: 34.960
- graph edges: 62.463
- Dense: 18.624 × 1.024, BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`
- Dense device: `cuda:0`, FP16, validation PASS
- BM25S: build/load/query PASS
- Aura exact graph comparison: PASS
- Aura build ID: `bbafae464889a9235093655fba582400456bcb3d5a6bbe3837d1dc6ddaadd106`
- warnings còn lại: `CASE_CORPUS_SMALL=1`, `AMBIGUOUS_CANONICAL_PATH_QUARANTINED=32`, `SHORT_PROVISION_QUARANTINED=4`
- regression tests hiện tại: 81/81 PASS bằng `unittest`

V6 hiện có các relation trong graph:

- REFERENCES: 2.030
- CITES: 7
- AMENDS: 13, gồm document-level và provision-level
- REPEALS: 3
- REPLACES: 1
- IMPLEMENTS: 0 trong corpus thật

V6 có 2.448 citation candidates UNRESOLVED và 2.040 RESOLVED. Không được tự resolve các candidates mơ hồ.

### 3. Những phần đã hoàn thành — phải giữ

Các phần sau đã có code và đã được V6 xác nhận. Không triển khai lại từ đầu:

- scan corpus và SHA manifest
- stable IDs
- native extraction và page-level EasyOCR
- replacement PDF/source attachment được khóa bằng SHA
- page review cho trang trắng/trang xoay
- page/document/layout cache, timeout và retry
- hỗ trợ PDF, DOCX, DOC legacy, HTML, TXT, JSON
- Unicode/line normalization
- Document Registry và curated legal metadata cho 61 legal/consolidated documents
- segmentation: PREAMBLE, MAIN_BODY, SIGNATURE, ANNEX, FORM, ATTACHED_REGULATION
- Article/Clause/Point parsing
- canonical path quarantine và short provision quarantine
- provision có `segment_id`, `char_start`, `char_end`, `line_start`, `line_end`, `span_scope=SEGMENT_TEXT`
- provision có alias `valid_from`/`valid_to` đồng bộ với document `effective_from`/`effective_to`
- retrieval unit provision đã mang `chapter`, `section`, `valid_from`, `valid_to` và `provenance_span`
- Chapter/Section đã là graph nodes thật; V6 có 308 Chapter và 248 Section
- PART_OF và NEXT đã dùng hierarchy parent đúng
- Neo4j loader đã chấp nhận Chapter/Section
- REFERENCES/CITES resolver bảo thủ và citation unresolved artifact
- provision-level AMENDS/REPEALS/REPLACES đã có khi target đủ rõ
- pattern IMPLEMENTS và regression fixture đã tồn tại; corpus V6 chưa sinh edge IMPLEMENTS
- Diagnostic Checklist heuristic/Ollama, LegalIssue, case parser, case features
- kNN + Leiden/Louvain case communities
- BM25S, BGE-M3 Dense, FAISS IndexFlatIP, normalized vectors
- Dense checkpoint/resume và fingerprint
- Neo4j transactional dataset replacement, rollback, exact IDs/endpoints/types và graph fingerprint
- Kaggle bootstrap, private dataset bundle, checkpoint restore, GPU preflight, Aura Secrets và results ZIP export
- technical gate `ready_for_offline_v1`
- build-bound external gold gate hiện giữ `offline_ready_for_online=false` khi chưa có review

Không được làm mất hoặc làm yếu các invariant trên.

### 4. Khoảng trống thực tế sau V6

Hãy giải quyết theo dependency và mức ưu tiên bên dưới.

#### P0-A — Source catalog resolved 95/95, nhưng không giả provenance

Hiện 95 documents gồm:

- 57 LEGAL_DOCUMENT
- 4 CONSOLIDATED
- 24 JUDICIAL
- 10 SUPPLEMENTARY

Chỉ 61/95 documents có `source_url` và `metadata_verified`; đây chủ yếu là legal/consolidated documents.

Tạo bước source catalog resolution trước extraction và artifact:

`artifacts/00_manifest/source_catalog_resolved.jsonl`

Mỗi file manifest phải có đúng một record, tối thiểu:

```json
{
  "file_id": "...",
  "relative_path": "...",
  "sha256": "...",
  "source_group": "LEGAL_DOCUMENT | CONSOLIDATED | JUDICIAL | SUPPLEMENTARY",
  "source_provider": null,
  "source_url": null,
  "collected_at": null,
  "official_source": false,
  "binding": false,
  "language": "vi",
  "catalog_status": "VERIFIED | UNVERIFIED",
  "missing_fields": []
}
```

Quy tắc:

- coverage record phải là 95/95 và SHA/path/file_id phải khớp manifest.
- `VERIFIED` chỉ được dùng nếu metadata có evidence thực và SHA binding hợp lệ.
- `official_source=true` hoặc `binding=true` chỉ được dùng khi nguồn đủ điều kiện authoritative.
- `source_provider`, `source_url`, `collected_at` không biết thì để null, thêm `missing_fields`, đặt UNVERIFIED.
- Không dùng file mtime làm `collected_at` nếu không có bằng chứng đó là thời điểm thu thập.
- Không suy issuer/provider từ tên folder rồi đánh dấu VERIFIED.
- Mọi authoritative citation source phải có URL và provider đã xác minh.
- Tạo review queue cho 34 record chưa đủ provenance, thay vì bịa dữ liệu.
- Legal metadata và source metadata phải là hai lớp riêng.
- Bất kỳ catalog entry có SHA mismatch phải fail closed trước extraction.

Acceptance:

- resolved source records = manifest records = 95
- duplicate file_id/path = 0
- missing SHA/path/file_id = 0
- catalog SHA mismatch = 0
- authoritative source thiếu URL/provider = 0
- mọi record chưa xác minh được liệt kê trung thực trong review queue

#### P0-B — Exact page/source provenance

V6 đã có span ký tự/dòng trong `SEGMENT_TEXT`, nhưng chưa có mapping hoàn chỉnh về trang nguồn. Không được mô tả V6 là “không có span”; phần còn thiếu là page/document coordinate và evidence mapping.

Thiết kế coordinate spaces rõ ràng. Không dùng một tên `char_start` mơ hồ cho nhiều hệ tọa độ. Có thể dùng:

- `segment_char_start/end`: half-open trong `segment.text`
- `document_char_start/end`: half-open trong cleaned extracted document text
- `page_text_char_start/end`: half-open trong normalized page text
- `page_start/end`: physical PDF page khi có
- `document_line_start/end`
- `page_line_start/end`
- `coordinate_space`
- `source_unit_type = PDF_PAGE | DOCUMENT | HTML`

Đối với PDF/OCR:

- mapping phải nối được provision → segment → cleaned document text → `page_provenance` → page number → extraction method → page/source SHA.
- Không tuyên bố raw-PDF-byte offsets. OCR không có character offset vật lý trong PDF; nếu có layout/bounding boxes thì tham chiếu layout artifact rõ ràng.
- Nếu header/footer bị loại, giữ transformation/mapping hoặc tạo line map trước/sau normalization có thể kiểm tra.

Đối với HTML/DOC/DOCX/TXT không có khái niệm trang vật lý:

- không bịa page 1.
- dùng `source_unit_type` thích hợp, page null và `page_status=NOT_APPLICABLE`.
- vẫn bắt buộc document/line/character mapping.

Có thể tạo:

- `artifacts/01_extracted/page_line_map.jsonl`
- `artifacts/03_structure/provision_spans.jsonl`

hoặc representation ít trùng lặp hơn nếu hợp với code hiện tại.

Mapping phải áp dụng cho:

- segments
- Article/Clause/Point
- retrieval units
- resolved relations/citations
- LegalChange evidence
- DiagnosticItem và issue assignment evidence khi locate duy nhất được

Không dùng `str.find` rồi nhận match đầu tiên một cách im lặng. Nếu cùng evidence xuất hiện nhiều lần, dùng source provision/span để giới hạn; nếu vẫn mơ hồ thì đánh dấu provenance unresolved.

Acceptance:

- provision thiếu segment span = 0
- PDF provision không resolve được page range = 0, trừ record bị quarantine có lý do
- non-paginated provision thiếu explicit NOT_APPLICABLE page status = 0
- retrieval provision unit không kế thừa span = 0
- resolved authoritative relation/change không có evidence span = 0
- span out of bounds = 0
- normalized source slice không khớp provision/evidence theo transformation rules = 0

#### P0-C — Hoàn thiện Chapter/Section metadata

Chapter/Section nodes đã tồn tại và hierarchy đã PASS. Chỉ bổ sung phần còn thiếu:

- heading
- order
- parent_id
- segment_id
- exact provenance span theo model P0-B

Không tạo Chapter/Section giả khi nguồn không có heading tương ứng. Giữ stable IDs hiện tại nếu identity không đổi. Kiểm tra NEXT chỉ nối siblings cùng parent và theo source order.

#### P0-D — Provision identity và version thật

Hiện Article/Clause/Point IDs phụ thuộc `document_id`, nên chúng là provision occurrences/versions của một DocumentVersion. `valid_from/valid_to` hiện chỉ là alias kế thừa document-level, chưa phải provision timeline đã materialize.

Triển khai theo cách tương thích:

1. Giữ các node Article/Clause/Point và `provision_id` hiện tại làm **provision version/occurrence** để không phá graph/retrieval IDs.
2. Tạo `ProvisionIdentity` ổn định theo:
   - `instrument_id`
   - canonical article/clause/point path
3. Thêm vào provision:
   - `provision_identity_id`
   - `provision_version_id`, mặc định bằng `provision_id` nếu không cần ID mới
   - `source_document_version_id`
   - `valid_from`, `valid_to`
   - `temporal_status = VERIFIED | INHERITED_DOCUMENT | INFERRED | UNKNOWN`
   - `temporal_evidence`
   - `introduced_by_change_id`, `ended_by_change_id`
4. Tạo artifact:
   - `artifacts/03_structure/provision_identities.jsonl`
   - `artifacts/03_structure/provision_versions.jsonl`
5. Thêm `ProvisionIdentity` nodes vào graph và edge `HAS_PROVISION_VERSION` hoặc tên tương đương nhất quán.

Quy tắc temporal:

- interval là half-open: `valid_from <= query_date < valid_to`.
- ngày kế thừa từ document phải ghi `INHERITED_DOCUMENT`, không tự nâng thành VERIFIED provision-level.
- nếu có legal change riêng cho provision, interval phải dựa vào evidence change.
- không tự ghép hai văn bản có title giống nhau thành một instrument.
- không tạo version mới chỉ vì text normalization thay đổi.
- không để hai VERIFIED versions của cùng identity overlap.
- UNKNOWN phải giữ UNKNOWN.

Acceptance:

- duplicate ProvisionIdentity = 0
- mỗi accepted provision version có đúng một identity = 100%
- invalid/negative interval = 0
- overlapping VERIFIED intervals = 0
- VERIFIED timeline without evidence = 0
- point-in-time selector có deterministic unit tests

#### P0-E — LegalChange và relation evidence

V6 đã có một số AMENDS/REPEALS/REPLACES provision-level, nhưng chưa có LegalChange artifact, resolution scope đầy đủ hoặc evidence span. V6 cũng chưa có IMPLEMENTS edge trong corpus thật.

Tạo `artifacts/04_knowledge/legal_changes.jsonl` với schema tối thiểu:

```json
{
  "change_id": "...",
  "operation": "AMEND | REPEAL | REPLACE | ADD | IMPLEMENT",
  "source_document_id": "...",
  "source_provision_id": "...",
  "target_instrument_id": null,
  "target_provision_identity_id": null,
  "target_article": null,
  "target_clause": null,
  "target_point": null,
  "resolution_scope": "DOCUMENT | ARTICLE | CLAUSE | POINT | UNRESOLVED",
  "effective_from": null,
  "temporal_status": "VERIFIED | INFERRED | UNKNOWN",
  "evidence_text": "...",
  "evidence_span": {},
  "method": "...",
  "confidence": 0.0,
  "resolution_status": "RESOLVED | UNRESOLVED | BELOW_THRESHOLD",
  "candidate_count": 0
}
```

Quy tắc:

- lưu cả candidate unresolved/below-threshold để review, nhưng chỉ đưa edge authoritative vào graph khi resolved duy nhất và confidence đạt threshold.
- source của provision-level operation phải là provision chứa câu tác nghiệp.
- target granularity phải đúng Article/Clause/Point nếu evidence nêu rõ.
- giữ document-level compatibility edge khi cần, nhưng không dùng nó thay cho target provision rõ ràng.
- relation IDs phải ổn định và không phụ thuộc thứ tự duyệt.
- relation/change evidence phải có P0-B span.
- IMPLEMENTS phải hỗ trợ các phrasing rõ như “quy định chi tiết…”, “hướng dẫn thi hành…”, kể cả khi có tiền tố Điều/Khoản hoặc “Nghị định/Thông tư này”.
- Không bắt buộc corpus phải có `IMPLEMENTS > 0`. Nếu scan corpus không có candidate đủ điều kiện thì 0 resolved là hợp lệ, nhưng report phải ghi số candidate và lý do unresolved. Fixture phải chứng minh resolver hoạt động.

#### P0-F — Derived knowledge provenance

DiagnosticItem và LegalIssue vẫn là derived knowledge, không phải authoritative law.

Bổ sung:

- `source_provision_id`
- `evidence_text`
- `evidence_span`
- `provenance_status = VERIFIED | AMBIGUOUS | UNRESOLVED`
- method/confidence hiện có

Nếu evidence chỉ là keyword tổng hợp và không map duy nhất được, không bịa exact span; đánh dấu AMBIGUOUS/UNRESOLVED.

Graph nên bảo toàn đường dẫn derived item → source provision version bằng `DERIVED_FROM` hoặc một edge tương đương có semantics rõ. Có thể giữ `HAS_DIAGNOSTIC_ITEM` để backward compatibility.

#### P0-G — Retrieval Unit V2 và indexes

Sau khi identity/version/provenance ổn định, mở rộng provision retrieval unit:

- `document_version_id`
- `instrument_id`
- `provision_identity_id`
- `provision_version_id`
- chapter/section/article/clause/point
- breadcrumb
- source text và ancestor context
- valid_from/valid_to/temporal_status
- legal_status, issuer, authority_rank, binding
- structured provenance span từ P0-B
- source URL và source SHA
- provenance status

Giữ `unit_id` hiện tại nếu semantic unit không đổi. Không duplicate descendant text không cần thiết.

Giữ nguyên:

- BM25S
- BGE-M3 dense
- FAISS IndexFlatIP
- vector normalization
- checkpoint/resume
- model revision và fingerprints

Không thêm BGE sparse, ColBERT, RRF, reranker hay production hybrid retrieval trong phase này. Dense và BM25 phải rebuild nếu retrieval-unit fingerprint/schema/metadata thay đổi.

#### P0-H — Gold framework và evaluator trung thực

Đây là blocker cuối của `offline_ready_for_online`. Copilot không được tự tạo legal truth rồi tự APPROVE.

Tạo:

- schema/validator cho gold queries và qrels
- template hoặc seed records ở trạng thái DRAFT
- review workflow/queue
- `scripts/evaluate_gold.py`
- evaluator chạy BM25 và Dense độc lập trên approved qrels
- build-bound evaluation reports

Gold query classes:

- DIRECT_PROVISION
- SCENARIO
- CROSS_REFERENCE
- MULTI_HOP
- TEMPORAL
- AMENDMENT_REPEAL
- CASE_LAW
- ANNEX_TABLE
- INSUFFICIENT_FACTS

Gold record phải chứa ít nhất query ID, question, query type, query date nếu có, mandatory/supporting evidence, invalid versions, qrels/unit IDs, review status và reviewer.

Chỉ record `APPROVED` với reviewer rõ ràng mới được dùng cho final gate. DRAFT/REVIEWED chưa approved không được tính để PASS.

Evaluator tối thiểu tính:

- Recall@5
- Recall@10
- MRR@10
- nDCG@10
- citation/relation precision, recall, F1 và unresolved rate khi gold tương ứng tồn tại
- temporal correct-version accuracy và wrong-version rate
- traceable evidence rate

Mỗi evaluation phải bind với:

- corpus/manifest fingerprint
- source catalog fingerprint
- graph fingerprint
- retrieval-unit fingerprint
- Dense fingerprint/model revision
- BM25 fingerprint
- config fingerprint
- gold-set fingerprint

Không reuse report cũ khi bất kỳ fingerprint nào đổi.

Nếu chưa có gold APPROVED:

- evaluator/report phải trả `NOT_EVALUATED`
- `ready_for_offline_v1` vẫn có thể PASS
- `offline_ready_for_online` bắt buộc false
- completion report phải nói rõ cần người có chuyên môn duyệt gold records nào

Khi có đủ gold APPROVED, target gate đề xuất:

- Recall@10 >= 0.90
- nDCG@10 >= 0.80
- gold relation precision >= 0.95
- wrong temporal version rate = 0 trên approved temporal gold
- traceable authoritative evidence rate = 100%

Không tự hạ các threshold này.

### 5. P1/P2 không được làm chậm P0

Các mục sau chỉ triển khai sau P0 hoặc khi code hiện tại cho phép thay đổi nhỏ, có benchmark rõ:

1. OCR backend interface/factory; EasyOCR vẫn là default.
2. RapidOCR/Tesseract chỉ thêm khi dependency, Kaggle Python 3.12 và T4 đã được kiểm chứng.
3. Structured Table → Row → Cell artifact, giữ flattened text hiện tại.
4. Corpus judicial lớn hơn 24 items.
5. Review/phục hồi 32 canonical paths và 4 short provisions đang quarantine.

Không bật Docling table structure hoặc thêm OCR backend hàng loạt nếu việc đó làm invalidate toàn bộ extraction checkpoint mà chưa có test/benchmark cụ thể.

### 6. Graph/Neo4j V2

Giữ transactional replacement hiện tại và mở rộng labels có kiểm soát:

- LegalInstrument
- DocumentVersion / ConsolidatedDocumentVersion
- Chapter / Section
- ProvisionIdentity
- Article / Clause / Point hiện đóng vai provision version/occurrence
- LegalChange nếu materialize thành node
- Judgment / CassationDecision / Precedent
- DiagnosticItem / LegalIssue / CaseFeature / Community

Edges cần nhất quán:

- VERSION_OF
- HAS_PROVISION_VERSION
- PART_OF
- NEXT
- REFERENCES / CITES
- AMENDS / REPEALS / REPLACES / IMPLEMENTS
- DERIVED_FROM
- HAS_DIAGNOSTIC_ITEM / RELATES_TO_ISSUE / HAS_ISSUE
- HAS_FEATURE / SIMILAR_TO / BELONGS_TO

Neo4j validation phải so sánh exact:

- node IDs và types
- edge IDs, types, source, target
- counts
- graph fingerprint/build ID

Không để stale nodes/edges. Không dùng `--replace-legacy` trong Aura notebook. Không xóa database thủ công; loader chỉ thay dataset `vn-labor-offline` theo transaction hiện có.

### 7. Quality gates

Giữ hai trạng thái riêng:

1. `ready_for_offline_v1`: technical construction gate.
2. `offline_ready_for_online`: P0 semantic + approved gold gate.

Technical gate phải kiểm tra thêm:

- source resolved coverage 95/95 và SHA binding
- accepted hierarchy/provisions có valid parent/order/span
- temporal aliases và provision intervals không mâu thuẫn
- relation target/endpoints/confidence/evidence spans
- retrieval units và index metadata đồng bộ
- Dense/BM25 query/load validation
- Neo4j exact graph validation
- no stale build-bound evaluation

`offline_ready_for_online=true` chỉ khi:

- technical gate PASS
- P0 provenance/temporal/relation invariants PASS
- có approved gold đủ điều kiện
- metrics đạt threshold
- evaluation fingerprints khớp đúng build

Không hard-code kết quả true.

### 8. Tests và local verification

Không phụ thuộc pytest vì môi trường local hiện không cài pytest. Dùng:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Giữ 81 tests hiện tại và thêm regression tests có ý nghĩa cho:

- resolved source catalog 95/95 và SHA mismatch fail closed
- coordinate-space/page mapping và out-of-bounds
- normalization/header removal vẫn trace được source
- Chapter/Section metadata, parent và NEXT
- ProvisionIdentity ổn định qua DocumentVersions
- non-overlap và half-open temporal intervals
- AMENDS/REPEALS/REPLACES/IMPLEMENTS exact target granularity
- unresolved change candidates không tạo graph edge
- relation/derived evidence spans
- Retrieval Unit V2 propagation
- graph labels/endpoints/fingerprint
- gold schema, approved-only evaluation và stale fingerprint rejection
- Kaggle package completeness, notebook syntax và secret forwarding

Ưu tiên mở rộng test modules hiện tại nếu hợp lý; không cần tạo một file test cho từng bullet.

Chạy thêm:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts kaggle tests
git diff --check
```

Để kiểm tra V6 mà không OCR/Dense/Aura, dùng isolated review và không ghi đè `artifacts` chính:

```powershell
.\.venv\Scripts\python.exe scripts\review_kaggle_extraction.py "C:\Users\Acer\Downloads\vn_labor_results_V6.zip"
```

Nếu script review cần nâng cấp cho schema mới, sửa nó để đọc V6 và ghi vào thư mục review riêng. Không giải nén V6 đè lên artifacts chính.

Không chạy local:

- `RUN_ALL_OFFLINE.bat`
- OCR toàn corpus
- Dense toàn corpus
- Docker/Neo4j toàn graph

### 9. Kaggle là execution target bắt buộc

Mọi thay đổi phải chạy được trên Kaggle Linux, Python 3.12 và Tesla T4. Đây là phần bắt buộc của deliverable.

Giữ và cập nhật:

- `kaggle/bootstrap.py`
- `kaggle/remote.py`
- `kaggle/constraints.txt`
- `scripts/package_kaggle.py`
- `scripts/review_kaggle_extraction.py`
- `scripts/validate_outputs.py`
- `KAGGLE_GUIDE.md`
- tests của Kaggle bundle

Yêu cầu Kaggle:

- không gọi BAT/PowerShell trong notebook
- không dùng absolute Windows paths trong code được đóng gói
- package phải chứa mọi module/config/schema/gold template/script mới
- không đóng gói `.venv`, `.python312`, `.cache` model, `.env`, Git, secrets hoặc artifacts/report cũ
- bundle manifest phải có SHA cho mọi file và verify trước bootstrap
- Internet On để tải model; cảnh báo unauthenticated Hugging Face là non-fatal
- `HF_TOKEN` chỉ là optional secret, không được bắt buộc
- OCR và Dense có thể dùng `cuda:0`; không giả định code đã dùng được cả hai T4
- giữ preflight model/OCR trước pipeline
- giữ streaming log ra file để tránh Notebook output/RAM tăng không giới hạn
- giữ process-group cleanup khi cell bị interrupt
- export phải giữ checkpoint cần thiết, evaluation artifacts và logs nhưng loại model/secrets/temp
- audit trước Aura có thể exit 1 do live Neo4j chưa khớp; audit cuối sau Aura phải quyết định kết quả
- Aura dùng `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
- không đổi `NEO4J_USER` thành `NEO4J_USERNAME`

Checkpoint mới phải là V6:

```python
RUN_PIPELINE = True
LOAD_AURA = True
RESTORE_ARCHIVE = "AUTO"
```

Notebook phải dùng đúng hai private inputs:

1. Dataset code/corpus chứa bundle mới.
2. Dataset checkpoint chứa `vn_labor_results_V6.zip` hoặc thư mục `artifacts` do Kaggle giải nén.

Không gắn đồng thời V5 và V6 vì AUTO phải tìm đúng một checkpoint.

Checkpoint migration:

- tái sử dụng extraction V6 nếu raw extracted text/page provenance vẫn đủ và fingerprint tương thích.
- rebuild mọi downstream artifact có schema/fingerprint thay đổi.
- nếu extraction schema thực sự đổi, invalidate đúng cache cần thiết; không tái sử dụng cache sai và cũng không bắt OCR lại toàn corpus nếu có thể migrate trung thực từ V6.
- Dense phải rebuild khi Retrieval Unit V2 đổi.
- graph phải load lại Aura sau khi node/edge model đổi.
- gold report cũ phải bị reject khi build fingerprint đổi.

Sau khi code hoàn tất, chạy:

```powershell
.\.venv\Scripts\python.exe scripts\package_kaggle.py
```

Xác minh và báo:

- `kaggle_upload/vn_labor_kaggle.zip` tồn tại
- `kaggle_upload/VN_Labor_Kaggle.ipynb` tồn tại
- ZIP CRC PASS
- notebook code cells compile
- package manifest chứa đủ files mới
- package SHA-256 và size
- `uploaded=false`, `remote_execution_tested=false` cho đến khi người dùng thực sự chạy Kaggle

Cập nhật hướng dẫn người mới theo đúng thứ tự:

1. tạo version mới cho private code Dataset
2. tạo/gắn private V6 checkpoint Dataset
3. import notebook mới
4. Add Input đúng hai Dataset
5. bật T4 x2 và Internet
6. cấp quyền bốn Aura secrets
7. đặt RUN_PIPELINE/LOAD_AURA/RESTORE_ARCHIVE
8. Save Version → Save & Run All
9. không cancel saved-version run; có thể tắt Draft Session khi background version đã Running
10. tải `vn_labor_results.zip`, đổi tên thành V7 và kiểm tra reports

### 10. Artifact structure ưu tiên

Giữ convention hiện tại và chỉ thêm artifact cần thiết:

```text
artifacts/
├── 00_manifest/
│   ├── files.jsonl
│   ├── source_catalog_resolved.jsonl
│   └── source_review_queue.jsonl
├── 01_extracted/
│   ├── documents.jsonl
│   └── page_line_map.jsonl
├── 02_registry/
│   └── documents.jsonl
├── 03_structure/
│   ├── segments.jsonl
│   ├── provisions.jsonl
│   ├── provision_spans.jsonl
│   ├── provision_identities.jsonl
│   └── provision_versions.jsonl
├── 04_knowledge/
│   ├── citations.jsonl
│   ├── legal_changes.jsonl
│   ├── relation_edges.jsonl
│   ├── diagnostic_checklists.jsonl
│   ├── issue_edges.jsonl
│   └── communities.json
├── 05_graph/
│   ├── nodes.jsonl
│   └── edges.jsonl
├── 06_indexes/
│   ├── retrieval_units.jsonl
│   ├── bm25/
│   └── dense/
├── 07_evaluation/
│   ├── gold_queries.jsonl
│   ├── gold_qrels.jsonl
│   ├── retrieval_results.jsonl
│   ├── retrieval_metrics.json
│   ├── citation_metrics.json
│   ├── temporal_metrics.json
│   └── evaluation_summary.json
└── reports/
    ├── validation_issues.jsonl
    ├── final_outputs_validation.json
    ├── offline_readiness.json
    └── build_fingerprints.json
```

Không bắt buộc tạo file rỗng hoặc duplicate dữ liệu chỉ để giống cây trên. Nếu representation khác tốt hơn, giải thích và giữ schema nhất quán.

### 11. Thứ tự triển khai

Trước tiên tạo `IMPLEMENTATION_PLAN_OFFLINE_V7.md`, nhưng sau đó tiếp tục code:

1. Audit current tree, V6 schema và invariants.
2. Source catalog resolved + review queue + pre-extraction validation.
3. Coordinate/page/source mapping.
4. Hoàn thiện Chapter/Section metadata từ mapping mới.
5. ProvisionIdentity/ProvisionVersion + temporal validation.
6. LegalChange + relation evidence + unresolved candidates.
7. Derived knowledge evidence provenance.
8. Retrieval Unit V2.
9. Graph/Neo4j labels, edges và exact validator.
10. Fingerprint-bound gold framework/evaluator.
11. Local unit/regression/compile/package tests.
12. Isolated V6 review không model/database.
13. Tạo lại `kaggle_upload` và cập nhật runbook.
14. Viết completion report trung thực.

Sau mỗi phase, chạy test liên quan và kiểm tra artifact mẫu. Không tạo commit tự động.

### 12. Báo cáo bắt buộc

Tạo `OFFLINE_V7_COMPLETION_REPORT.md`, ghi:

- V6 ground truth và ZIP SHA
- files changed/added
- schema version/migrations
- cache invalidation/reuse behavior
- tests trước/sau và kết quả thật
- isolated-review counts/issues
- source catalog coverage: VERIFIED và UNVERIFIED tách riêng
- provision/page/source provenance completeness
- ProvisionIdentity/Version counts và temporal issues
- LegalChange/relation stats theo type/status/scope
- derived knowledge provenance stats
- Retrieval Unit V2 counts
- graph labels/edges và integrity
- BM25/Dense/Aura trạng thái: local chưa chạy hay Kaggle đã xác minh
- gold status/metrics; nếu chưa có APPROVED gold thì ghi NOT_EVALUATED
- remaining P1/P2 items
- exact Kaggle files và SHA cần upload
- trạng thái cuối:

```text
ready_for_offline_v1 = true/false
offline_ready_for_online = true/false
```

Nếu chưa chạy Kaggle V7, không được dùng kết quả V6 để tuyên bố các artifacts mới đã PASS. Hãy ghi rõ:

```text
Kaggle V7 run required
Dense/BM25 rebuild required nếu retrieval fingerprint đổi
Aura reload required nếu graph fingerprint đổi
```

Nếu chưa có gold được chuyên gia/người nghiên cứu APPROVED, trạng thái đúng là:

```text
ready_for_offline_v1 = chưa xác nhận cho build mới cho đến khi Kaggle audit xong
offline_ready_for_online = false
legal_quality_evaluation = NOT_EVALUATED
```

Kết thúc công việc bằng hướng dẫn ngắn, chính xác cho người mới chạy package mới trên Kaggle bằng V6 checkpoint và gửi lại `vn_labor_results_V7.zip` để nghiệm thu.

## KẾT THÚC PROMPT

