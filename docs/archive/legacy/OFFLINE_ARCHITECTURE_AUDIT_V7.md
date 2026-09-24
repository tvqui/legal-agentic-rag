# Đối chiếu kiến trúc OFFLINE với code hiện tại

Đối chiếu với mô tả kiến trúc người dùng gửi ngày 15/09/2026. Đây là **kiểm tra code và bằng chứng chạy**, không phải chứng nhận độ chính xác pháp lý của corpus. Tôi không sửa code trong đợt kiểm tra này.

**Cập nhật sau audit:** gói `kaggle_upload/vn_labor_kaggle_v7_1.zip` đã sửa lỗi thiếu label `ProvisionIdentity` trong Neo4j loader và lỗi gán document span bằng segment span ở nguồn không phân trang. Mapper cũng chỉ tìm vị trí một lần cho mỗi segment thay vì một lần cho mỗi provision; trường hợp không khớp/khớp lặp được để `UNRESOLVED`. Bốn regression tests mới và toàn bộ 89 tests PASS. Notebook mặc định `LOAD_AURA=False` để xem output V7.1 trước khi thay dataset trên Aura. Các thiếu sót Source Catalog, temporal versioning, exact relation evidence và Gold/ONLINE quality gate phía dưới **vẫn còn**; gói V7.1 chưa chạy Kaggle/Aura.

**Cập nhật khi nhận output V7:** V7 đã chạy Kaggle. Báo cáo [OFFLINE_V7_RESULT_REVIEW.md](OFFLINE_V7_RESULT_REVIEW.md) chỉ ra 18.449 lỗi identity/page status là do file provision được ghi trước enrichment; 1.041 span chưa map do một dòng trống trong một PDF hợp nhất; `STALE_NEO4J_BUILD` đến từ checkpoint V6 trong khi `LOAD_AURA=False`. Tôi đã sửa và đóng gói V7.2, 93/93 tests PASS; **chưa có kết quả Kaggle V7.2**. Các thiếu sót Source Catalog/Gold/temporal bên dưới vẫn giữ nguyên.

**Cập nhật khi nhận output V7.2:** xem [OFFLINE_V7_2_RESULT_REVIEW.md](OFFLINE_V7_2_RESULT_REVIEW.md). Registry, structure, graph local, Dense và BM25 đã PASS; 18.449/18.449 provision spans/identities đạt, không còn lỗi cấu trúc V7. Graph DB live chưa nạp. Source Catalog 95/95 `UNVERIFIED`, Gold `NOT_EVALUATED` và ONLINE-ready vẫn `false`. Các nhận định “V7 chưa chạy” bên dưới ghi lại **mốc audit trước khi có output**, không phải trạng thái mới nhất.

**Đính chính giới hạn AuraDB Free:** kết luận trước đây rằng graph vượt mức 50.000 đã bị bác bỏ bởi inspect của instance và [FAQ AuraDB Neo4j hiện tại](https://neo4j.com/cloud/platform/aura-graph-database/faq/). Mức Free hiện công bố 200.000 nodes/400.000 relationships; V7.2 50.272/80.912 **có thể nạp nguyên graph**. Cần kiểm tra live DB sau khi nạp; Source Catalog và Gold vẫn chưa đạt ONLINE-ready.

## Kết luận

**Chưa thể coi implementation hiện tại là đầy đủ và đúng theo toàn bộ mô tả.** Kết quả Kaggle V6 đã đạt bốn kiểm tra kỹ thuật `registry / structure / graph / indexes = PASS` và nạp Aura thành công. Nhưng những sửa đổi V7 trong workspace chưa được chạy trọn pipeline trên Kaggle; V7 còn một lỗi chắc chắn làm Neo4j load thất bại, hai vấn đề provenance đã tái hiện, và phần hiệu lực theo từng provision, bằng chứng quan hệ, đánh giá chất lượng pháp lý vẫn chưa hoàn chỉnh. `OFFLINE_READY_FOR_ONLINE` vì thế chưa có bằng chứng đạt `TRUE`.

V6 và V7 phải được phân biệt: ZIP V6 có 95 documents, 18.449 provisions, 18.624 retrieval units, 34.960 graph nodes, 62.463 edges, Dense CUDA T4 và BM25 chạy được. Nó có `ready_for_offline_v1=true` nhưng `offline_ready_for_online=false`, `legal_quality_evaluation=NOT_EVALUATED`. Các số trên **không chứng minh V7 chạy được**.

## Đối chiếu từ đầu vào tới đầu ra

| Thành phần trong mô tả | Code hiện tại | Đánh giá / bằng chứng |
| --- | --- | --- |
| Raw corpus, danh mục file, SHA | `scanner.py`, manifest, metadata config | Có. V6 xử lý 95 tài liệu. |
| Source Catalog: URL chính thức, cơ quan cung cấp, SHA, source type, thời điểm thu thập | `scanner.py::resolve_source_catalog`, `config/source_catalog.yaml` | **Chưa đạt chất lượng nguồn**. Chạy resolver hiện tại trên 95 manifest V6 tạo đủ 95 record nhưng **95/95 `UNVERIFIED`**, 95 thiếu provider, 95 thiếu `collected_at`, 0 có `official_source=true`. Việc 61 tài liệu V6 có metadata/source URL đã xác minh là kiểm tra khác, không xác minh được toàn bộ Source Catalog V7. |
| PDF/DOCX/HTML extraction, OCR trang scan, page provenance | `extraction.py`, `scanner.py`, pipeline | Có nhánh native text/OCR và page method. Chưa có kiểm chứng độc lập rằng mọi trang OCR giữ đủ nội dung pháp lý; V6 có kết quả kỹ thuật PASS. Docling/multiple OCR backend trong mô tả là ví dụ kiến trúc, không phải nghĩa vụ cài đủ RapidOCR/Tesseract; code chủ yếu dùng EasyOCR. |
| Chuẩn hóa Unicode/space/line; legal metadata | `cleaning.py`, `metadata.py`, overrides | Có. V6 metadata nghiêm trọng được xử lý để qua gate kỹ thuật; xác thực pháp lý từng trường vẫn dựa catalog/overrides. |
| Segmentation body/annex/form/attachment | `segmentation.py`, `legal_structure.py` | Có và có quarantine trường hợp mơ hồ. V6 vẫn quarantine 32 canonical paths và 4 short provisions; nghĩa là không phải mọi nội dung đều được parse thành căn cứ truy xuất. |
| Hierarchy Document → Chapter/Section → Article/Clause/Point, stable ID và vị trí nguồn | `legal_structure.py`, `graph_builder.py`, `provenance.py` | Có node/cạnh và ID. V6 provisions đều có span ký tự/dòng **trong segment**. V7 document/page mapping còn sai hoặc chưa giải được ở các trường hợp nêu dưới. Chapter/Section node chưa lưu heading/thứ tự/span gốc đủ để truy vết độc lập. |
| Temporal và version cho văn bản gốc/sửa đổi/hợp nhất, point-in-time provisions | `metadata.py`, `temporal.py`, `provision_versions.py`, `relations.py` | **Mới một phần**. V7 có `ProvisionIdentity`, version row và `valid_from/to` kế thừa từ tài liệu; chưa tính thời điểm bắt đầu/kết thúc của từng Điều/Khoản/Điểm theo `LegalChange`, chưa kiểm tra timeline overlap hay dựng đầy đủ version chain. `LegalChange.effective_from` hiện luôn `None`. |
| REFERENCES/CITES/IMPLEMENTS/AMENDS/REPEALS tới provision cụ thể; mơ hồ để unresolved | `relations.py` | Có resolver và một số provision target. V6: REFERENCES 2.030, CITES 7, AMENDS 13, REPEALS 3, REPLACES 1, IMPLEMENTS 0; 2.448 citations unresolved. V7 vẫn phát cạnh document→document khi document target rõ nhưng provision target chưa rõ; không nên diễn giải cạnh đó là sửa đổi provision đã xác minh. Bằng chứng span hiện là toàn provision hoặc rỗng, không phải đoạn ngôn ngữ tạo quan hệ. |
| Authoritative graph với hierarchy, order, versions, cross-reference | `graph_builder.py` | V6 graph kỹ thuật đạt. V7 thêm `ProvisionIdentity`/`HAS_PROVISION_VERSION` nhưng **Neo4j loader chưa chấp nhận label mới**, nên nhánh graph→Aura hiện hỏng. Phiên bản có hiệu lực theo provision chưa được dựng từ thay đổi pháp lý. |
| Derived Knowledge riêng, confidence, evidence span | `issues.py`, `checklists.py`, graph derived nodes | Có tách layer và lưu confidence/status. Các span có trường nhưng thường phủ toàn provision; checklist còn có thể lệch tọa độ khi normalize whitespace. Không chứng minh được span chính xác tới câu/đoạn chứng cứ. |
| Retrieval units với breadcrumb, hiệu lực, nguồn, version, provenance | `indexes.py` | Có các metadata chính, V7 thêm identity/version/source SHA. Nhưng `provenance_span` của unit provision vẫn là tọa độ segment V6, chưa chuyển document/page mapping V7; breadcrumb thiếu Section dù có metadata Section. Case/annex unit chưa có nguồn page/span tương đương provision. |
| BM25 và BGE-M3/FAISS Dense | `indexes.py`, Kaggle V6 | V6 cả hai PASS; Dense 18.624 × 1024 trên T4, BM25 hoạt động. BGE-M3 hiện chỉ tính dense (`return_sparse=False`, `return_colbert_vecs=False`); BM25 là engine riêng. Việc hybrid/rerank ở ONLINE như mô tả, không phải lỗi thiếu của OFFLINE. |
| Neo4j graph load | `neo4j_loader.py` | V6 Aura load PASS. V7 graph mới không load được vì thiếu `ProvisionIdentity` trong tập `LABELS`: `validate_export()` báo `Unsupported semantic label` trên fixture có node đó. |
| Offline Quality Gate, `OFFLINE_READY_FOR_ONLINE` | `quality.py`, `validation.py`, `gold.py`, `scripts/validate_outputs.py` | Gate kỹ thuật hiện có nhưng chưa kiểm đủ source status/SHA/collection date, document/page span bounds và text match, timeline provision, relation evidence. `gold.py` chưa thực hiện retrieval hay tính qrels/metrics; mẫu Gold DRAFT tự bị validator báo `missing:reviewer`. `scripts/validate_outputs.py` chưa đưa Gold evaluator vào cách tính readiness như `validation.py`, tạo nguy cơ hai báo cáo readiness khác nhau. |

## Các lỗi và việc còn thiếu cần ưu tiên

1. **Chặn chạy Kaggle/Aura V7:** thêm `ProvisionIdentity` vào semantic labels của `neo4j_loader.py`, rồi thử `validate_export` trên graph V7 và chạy nạp Aura. Bằng chứng hiện tại: `graph_builder.py` tạo node này nhưng `neo4j_loader.py::LABELS` thiếu nó.
2. **Sửa document provenance trước khi tin các evidence span:** `provenance.py` ở nguồn không phân trang đặt `document_char_start/end = segment_char_start/end`. Fixture `PREAMBLE\nĐiều 1...` cho thấy slice document được chỉ tới khác text provision. Với PDF, segment phải trùng nguyên văn và duy nhất trong extracted text; case lặp/đã làm sạch thành unresolved. Mapper dùng tìm mọi vị trí trong cả document cho mỗi provision, làm kiểm tra cô lập V6 chạy CPU nhiều phút và tôi đã dừng, chưa có số unresolved V7. Cần map segment→document→page có kiểm tra slice, bounds và hiệu năng.
3. **Xác minh Source Catalog thật:** cập nhật provider, `collected_at`, official URL/flag và binding SHA theo từng bản nguồn; gate phải phân biệt record tồn tại với nguồn đã được xác minh. Code hiện có thể cho 95 records `UNVERIFIED` mà chỉ báo thiếu metadata khác, chưa chặn `ready_for_offline_v1` theo tiêu chí Source Catalog.
4. **Hoàn thành versioning ở cấp provision:** xác định affected target, ngày hiệu lực change, thời gian hiệu lực của version provision và kiểm tra xung đột. Validity kế thừa ở cấp document chưa đủ để ONLINE lọc đúng căn cứ tại ngày hỏi cho các văn bản sửa đổi một phần.
5. **Lưu chứng cứ chính xác cho relation/derived knowledge:** citation và amendment evidence cần span của chính câu/chuỗi dẫn chiếu, source document/page coordinate và trạng thái xác minh. Hiện relation/citation và issue/checklist span thường là toàn provision hoặc rỗng; confidence/status có thể bị hiểu lầm là đã xác minh span.
6. **Hoàn thành kiểm thử Gold và thống nhất readiness:** template DRAFT phải hợp lệ; record APPROVED phải được kiểm nguồn, ngày hỏi, qrels và version; chạy BM25/Dense trên query, tính metric và quality threshold. Hiện `evaluate_gold()` chỉ báo `READY_FOR_EVALUATION` nếu có mẫu approved, `passed=false`, và `scripts/evaluate_gold.py` có thể exit 0 dù chưa đánh giá. Một quality report bên ngoài được reviewer ký không tự thay thế kiểm thử retrieval.
7. **Mở rộng structural quality gate:** kiểm page/document span có nằm trong text và khớp đoạn nguồn, `ProvisionIdentity`/version orphan/overlap, relation evidence và unresolved target, source SHA/URL/collection time, Neo4j label compatibility; cùng một định nghĩa readiness ở pipeline, validator CLI và Kaggle audit.

## Phần code hiện có nhưng mô tả không nêu trực tiếp

Đây là các bổ sung về triển khai, không phải mâu thuẫn kiến trúc:

- Manifest/file fingerprint, source attachment binding và metadata overrides, cơ chế fail-closed/quarantine cho đường dẫn pháp lý mơ hồ hoặc provision ngắn.
- Parser cho tài liệu bổ trợ/case, `CaseFeature`, `PolicySeries`, `LegalIssue`, community và checklist chẩn đoán; Ollama enrichment tùy chọn cho checklist.
- OCR retry/page quality, lưu artifacts trung gian, log và báo cáo để chạy lại có checkpoint.
- Source review queue, provision span queue, provisional Gold query template và khung evaluation V7. Các phần này hiện chỉ là khung, chưa phải bằng chứng đạt chất lượng.
- Nạp Neo4j theo transaction/dataset, xác nhận đúng node/edge; FAISS/model cache, BM25S artifacts; gói private Kaggle, restore checkpoint và xuất ZIP kết quả.
- Các kiểu file/segment phụ trợ như DOC/TXT/JSON, annex/form và retrieval units cho case/annex/form, rộng hơn phần cốt lõi Điều/Khoản/Điểm trong mô tả.

## Phạm vi kiểm tra và giới hạn

- Tôi chạy độc lập `python -m unittest discover -s tests`: **85/85 PASS**. Bộ test hiện chưa bắt lỗi Neo4j label và non-PDF document span kể trên. `git diff --check` PASS.
- Tôi tái hiện `validate_export()` từ chối node `ProvisionIdentity`; tái hiện sai slice document bằng fixture có lời mở đầu; mẫu Gold trả `['missing:reviewer']`.
- Gói `kaggle_upload/vn_labor_kaggle_v7.zip` kiểm CRC PASS, có các module V7 và Notebook code compile; **chưa có execution Kaggle V7 hoặc Aura V7**. `package_report` cũng ghi `uploaded=false`, `remote_execution_tested=false`.
- Tôi không tự chấm độ đúng pháp lý của 95 tài liệu và không coi nghiên cứu NitiBench/FourCorners là bằng chứng corpus Việt Nam đã chuẩn. Chúng chỉ hỗ trợ lựa chọn hierarchy/cross-reference như mô tả; việc đánh giá phải dùng Gold set có chuyên gia duyệt.

**Trạng thái nên báo hiện nay:** V6 `OFFLINE v1 technical PASS`; V7 `implementation chưa đạt`, `ONLINE-ready chưa đạt/chưa được chứng minh`. Sau khi sửa các chặn trên, phải chạy Kaggle V7 mới, kiểm đủ bốn outputs, Gold/quality gate, rồi nạp Aura và đối chiếu graph đúng với artifacts mới.
