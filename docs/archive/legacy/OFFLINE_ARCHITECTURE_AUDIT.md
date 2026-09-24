# Đối chiếu code OFFLINE với mô tả kiến trúc

Ngày kiểm tra: 14/09/2026  
Đặc tả đối chiếu: tệp mô tả “Phần OFFLINE — Data & Knowledge Construction...” do người dùng cung cấp.  
Artifact kiểm chứng: `C:\Users\Acer\Downloads\vn_labor_results_V5.zip`, SHA-256 `5aeeea227c13f7ee5c3d3a8c903bc1ef3276db365ff0b9a1eb4165e749d10121`.

## Kết luận

Code **đã hoàn thành đúng mốc OFFLINE v1 theo bộ kiểm tra bốn đầu ra hiện hành**: registry, structure, graph và indexes đều PASS; Aura khớp chính xác graph export. Tuy nhiên, code **chưa thực hiện đầy đủ toàn bộ kiến trúc trong đoạn mô tả**. Điểm khác biệt quan trọng là mô tả kết thúc bằng các artifact sẵn sàng cho ONLINE, trong khi V5 ghi rõ:

```text
ready_for_offline_v1 = true
offline_ready_for_online = false
legal_quality_evaluation.status = NOT_EVALUATED
```

Vì vậy cần phân biệt hai kết luận:

- **OFFLINE — Data & Knowledge Construction v1 theo tiêu chí bốn đầu ra:** hoàn tất.
- **Toàn bộ kiến trúc trong mô tả, bao gồm temporal/version chi tiết và trạng thái ONLINE-ready:** chưa hoàn tất.

## Ma trận đối chiếu

| Thành phần trong mô tả | Hiện trạng code/artifact | Đánh giá |
|---|---|---|
| Raw Legal Data gồm luật, nghị định, thông tư, VBHN, lịch sử, bản án, giám đốc thẩm, án lệ và tài liệu bổ trợ | `scanner.py` nhận diện đủ các nhóm; V5 có 57 văn bản pháp luật, 4 VBHN, 24 tư pháp và 10 bổ trợ | Đạt |
| Source Catalog cho **mỗi** tài liệu, có URL, cơ quan cung cấp, SHA, loại nguồn, thời điểm thu thập | `00_manifest` có SHA, đường dẫn, kích thước và loại; `source_catalog.yaml` chỉ có 61/95 tài liệu, chủ yếu nhóm pháp luật. V5 còn 34 tài liệu không có `source_url`; không tài liệu nào có trường provider hoặc collected/retrieved timestamp | Chưa đầy đủ |
| Source Catalog đứng trước extraction | Pipeline thực tế là `scan → extract → build_registry`; `source_catalog.yaml` chỉ được áp dụng trong `build_registry` sau extraction. Extraction chỉ đọc catalog riêng `source_attachments.yaml` | Sai thứ tự so với mô tả |
| PDF native text và OCR theo trang chất lượng thấp, có page provenance | 87/87 PDF/text attachment trong V5 có page provenance; quyết định OCR theo native chars, ảnh phủ trang và ký tự lỗi | Đạt |
| Docling hỗ trợ nhiều OCR backend | Code cấu hình cố định `EasyOcrOptions`; không có lựa chọn RapidOCR hoặc Tesseract | Chỉ EasyOCR |
| Đọc PDF/DOCX/HTML | Có PDF, DOCX, HTML; bổ sung cả DOC cũ, TXT và JSON | Đạt và mở rộng |
| Chuẩn hóa Unicode, khoảng trắng và cấu trúc dòng | Có NFC, loại ký tự vô hình, chuẩn hóa khoảng trắng, giữ ranh giới dòng và loại header/footer lặp | Đạt cơ bản |
| Bảo toàn cấu trúc bảng | Docling đặt `do_table_structure = False`; bảng DOCX được làm phẳng thành dòng phân cách bằng `|` | Chưa có cấu trúc bảng |
| Legal Metadata gồm số hiệu, tên, loại, issuer, ngày ban hành, hiệu lực, trạng thái, version role và URL | 61 văn bản luật/VBHN trong V5 đã được catalog SHA-bound và vượt validation. Các trường này có trong registry | Đạt cho văn bản pháp luật của corpus hiện tại |
| Segmentation thân chính, phụ lục, biểu mẫu, chữ ký, quy định đính kèm | Có `PREAMBLE`, `MAIN_BODY`, `SIGNATURE`, `ANNEX`, `FORM`, `ATTACHED_REGULATION`; V5 có 61 main bodies, 91 annex và 174 form | Đạt cơ bản |
| Hierarchy `Document → Chapter/Section → Article → Clause → Point`, mỗi đơn vị có ID | Article/Clause/Point là node có ID. Chapter/Section chỉ là chuỗi thuộc tính trên Article; không có node, ID, `PART_OF` hay `NEXT` riêng. V5 không có label Chapter/Section | Chưa đầy đủ |
| Mỗi đơn vị giữ liên kết tới vị trí trong tài liệu gốc | Provision có `segment_id`, nhưng cả 18.445 provision không có page, line range hoặc character offsets. Segment chỉ có line range cho cả vùng lớn; không định vị chính xác từng provision | Chưa đầy đủ |
| Temporal and Version Resolution giữa bản gốc, sửa đổi, hợp nhất và phiên bản theo thời điểm | Có `LegalInstrument`, `DocumentVersion`, `ConsolidatedDocumentVersion`, `VERSION_OF`, `effective_from/to` và helper `temporal_eligible` | Một phần |
| `valid_from`/`valid_to` và phiên bản có hiệu lực tại từng thời điểm | Không có trường/edge `valid_from` hoặc `valid_to`; helper dùng `effective_from/to` ở cấp document và không được gọi trong pipeline/index build. Không có timeline đã materialize hay hiệu lực theo từng provision | Thiếu |
| Phạm vi hết hiệu lực/sửa đổi một phần | `PARTIALLY_EXPIRED` chỉ cho phép document tiếp tục đủ điều kiện; không lưu Điều/Khoản/Điểm nào đã bị sửa đổi hoặc hết hiệu lực ở giai đoạn nào | Thiếu |
| Resolver `REFERENCES`, `CITES` | Có resolve tới Article/Clause/Point; V5 có 2.046 REFERENCES, 7 CITES và lưu 2.501 citation UNRESOLVED riêng | Đạt cơ bản |
| Resolver `AMENDS`, `REPEALS`, `REPLACES` tới đơn vị pháp luật cụ thể | Có 5 AMENDS, 1 REPEALS, 1 REPLACES, nhưng các cạnh tác nghiệp hiện nối document → document. Nội dung đích Điều/Khoản/Điểm chưa được biểu diễn trong cạnh sửa đổi/bãi bỏ/thay thế | Chưa đầy đủ |
| Resolver `IMPLEMENTS` | README khai báo loại cạnh nhưng `relations.py` không có pattern/logic phát sinh; V5 có 0 edge IMPLEMENTS | Thiếu |
| Quan hệ không chắc chắn lưu unresolved thay vì nối sai | Có `04_knowledge/citations.jsonl` với trạng thái, confidence, method và candidate count; chỉ cạnh RESOLVED vượt threshold mới vào graph | Đạt cho citation |
| Authoritative graph có hierarchy, order, version và cross-reference | Có `PART_OF`, `NEXT`, `VERSION_OF`, REFERENCES/CITES và các quan hệ tác nghiệp; graph V5 không trùng ID, không dangling | Đạt về kỹ thuật, thiếu ngữ nghĩa temporal nêu trên |
| Derived Knowledge tách riêng, có confidence và evidence span | Checklist/LegalIssue được lưu ở `04_knowledge` và graph layer riêng; 15.314 checklist đều có `source_text` và confidence | Một phần |
| Evidence span truy ngược chính xác | Checklist và issue edge chỉ giữ đoạn chữ/từ khóa; 0 checklist có page hoặc start/end offset. Không thể xác định duy nhất vị trí nếu cùng câu xuất hiện nhiều lần | Thiếu |
| Retrieval units cho Điều/Khoản/Điểm kèm breadcrumb, version, temporal, source, provenance | V5 có 18.621 units; tất cả có breadcrumb và document-level provenance; gồm 18.333 provision, 24 case, 91 annex, 173 form | Đạt cơ bản |
| Provenance của retrieval unit tới đúng trang/span | 0/18.621 unit có page, line range hoặc character offsets | Thiếu |
| BM25 + BGE-M3/FAISS | Cả hai index nạp và truy vấn được; Dense đúng 18.621 × 1.024 và model revision được ghi lại | Đạt |
| BGE-M3 sparse, multi-vector và reranking | Encoder được gọi với `return_sparse=False`, `return_colbert_vecs=False`; không có reranker hoặc hybrid fusion trong repo OFFLINE | Chưa triển khai; có thể thuộc ONLINE |
| Neo4j load toàn bộ graph | Có transaction thay dataset, kiểm tra ID/count/type/endpoints và build fingerprint; V5 Aura khớp 34.430 node, 62.061 cạnh | Đạt |
| Quality Gate metadata/OCR/structure/ID/temporal/dangling/provenance/index/graph | Có kiểm tra kỹ thuật và semantic tương ứng; V5 có 0 ERROR | Đạt phần kỹ thuật |
| Chỉ xuất `OFFLINE_READY_FOR_ONLINE = TRUE` khi đủ chất lượng | Code có `offline_ready_for_online`, nhưng V5 là false vì chưa có gold evaluation citation/retrieval. Không có pipeline tạo gold metrics; gate chỉ kiểm tra một báo cáo review bên ngoài | Chưa hoàn tất |

## Những phần còn thiếu hoặc chưa đúng, theo mức ưu tiên

### P0 — cần có trước khi tuyên bố artifact sẵn sàng cho ONLINE

1. **Gold evaluation thực tế chưa tồn tại.** Cần bộ câu hỏi/citation được chuyên gia duyệt, runner tính retrieval metrics và citation precision trên đúng build, rồi tạo `reviewed_quality_evaluation.json`. Hiện code chỉ xác minh nội dung khai báo của file đánh giá ngoài và build fingerprint.
2. **Temporal/version mới ở cấp document và mới là helper.** Cần materialize timeline, quan hệ giữa bản gốc–sửa đổi–hợp nhất, và hiệu lực của từng Article/Clause/Point. Cần dùng temporal filter trong đường truy hồi thay vì chỉ cung cấp hàm chưa được gọi.
3. **Source Catalog chưa bao phủ toàn bộ 95 nguồn.** Cần URL/provider/collection timestamp cho 24 tài liệu tư pháp và 10 tài liệu bổ trợ, đồng thời validate catalog trước extraction.
4. **Provision/retrieval provenance chưa định vị chính xác.** Cần ánh xạ page + character/line span cho từng provision và evidence span cho derived item/citation.
5. **Quan hệ pháp lý chưa đủ theo mô tả.** Cần `IMPLEMENTS` và cạnh AMENDS/REPEALS/REPLACES tới đúng provision/range có hiệu lực, kèm unresolved record khi đích không xác định duy nhất.

### P1 — cần để mô hình dữ liệu khớp đầy đủ mô tả

6. **Chapter và Section chưa phải đơn vị graph.** Cần node có stable ID, hierarchy và NEXT nếu mô tả `Document → Chapter/Section → Article` là yêu cầu bắt buộc.
7. **Derived knowledge chưa có tọa độ evidence.** Source text và confidence đã có nhưng thiếu offset/page, loại chủ thể, đối tượng, điều kiện và phạm vi áp dụng chuẩn hóa.
8. **Table structure bị tắt.** Các bảng/phụ lục/biểu mẫu hiện chủ yếu là plain text; nên lưu cell/row/column provenance nếu ONLINE cần trả lời từ biểu mẫu hoặc bảng.
9. **Backend OCR không linh hoạt như mô tả.** Chỉ EasyOCR được cấu hình. Chỉ cần bổ sung RapidOCR/Tesseract nếu đây là yêu cầu của dự án, không cần làm chỉ vì Docling có hỗ trợ.
10. **Hybrid/reranking chưa có.** BM25 và Dense artifacts đã sẵn sàng, nhưng fusion, BGE-M3 sparse/ColBERT và reranker chưa có trong repo này. Có thể đặt rõ thành trách nhiệm của phần ONLINE.

### P2 — giới hạn dữ liệu và đánh giá

11. Corpus tư pháp hiện chỉ có 24 mục; validation báo `CASE_CORPUS_SMALL`.
12. 32 nhánh canonical mơ hồ và 4 provision ngắn đang được cách ly. Cách ly giúp graph sạch về kỹ thuật nhưng nội dung đó chưa được phục hồi/xác minh.
13. Coverage lịch sử chưa chứng minh đủ cho mọi câu hỏi point-in-time; việc metadata hiện tại PASS không chứng minh coverage pháp luật đầy đủ.

## Những phần đã được thêm nhưng không được nêu trực tiếp trong mô tả

Các phần dưới đây là cơ chế bổ trợ hoặc mở rộng, không mâu thuẫn với kiến trúc:

| Phần bổ sung | Mục đích |
|---|---|
| `00_manifest/files.jsonl` và ID dựa trên SHA + relative path | Theo dõi chính xác input và giữ identity ổn định |
| `source_attachments.yaml` và PDF toàn văn SHA-bound | Thay landing page/scan khó đọc bằng bản chính thức mà không đổi document identity |
| `page_reviews.yaml` | Ghi quyết định thủ công cho trang trắng và trang cần xoay |
| Page cache, layout cache, document cache, timeout và retry | Khôi phục OCR, tránh chạy lại tài liệu đã hoàn tất |
| Serializer OCR bảo toàn marker pháp lý và tọa độ OCR cell | Tránh tự sinh số danh sách hoặc làm sai thứ tự chữ |
| Chuyển đổi DOC cũ qua Word/LibreOffice/antiword | Hỗ trợ nguồn legacy ngoài PDF/DOCX/HTML được nêu |
| Quarantine canonical path mơ hồ/provision ngắn | Không đưa cấu trúc đáng ngờ vào graph/index nhưng vẫn giữ để review |
| Diagnostic Checklist heuristic và Ollama tùy chọn | Biểu diễn nghĩa vụ, cấm đoán, điều kiện, ngoại lệ, quyền và thời hạn dưới dạng câu hỏi |
| Case parser: facts/reasoning/decision, money/percent features | Chuẩn hóa riêng tài liệu tư pháp |
| kNN + Leiden/Louvain, Community và SIMILAR_TO | Nhóm các vụ án tương tự; không được nêu trong đoạn kiến trúc |
| LegalIssue ontology theo từ khóa | Thêm lớp chủ đề pháp lý và liên kết case/provision |
| `PolicySeries` tùy chọn | Gom văn bản theo chuỗi chính sách đã curate, tách khỏi legal-instrument identity |
| Dense checkpoint/resume và model revision fingerprint | Chống mất tiến độ và index sai phiên bản model |
| Neo4j transactional dataset replacement | Tránh node/cạnh cũ, rollback khi lỗi và bảo vệ dữ liệu ngoài dataset |
| JSONL + CSV graph export | Cho phép kiểm tra/import ngoài Neo4j |
| Kaggle bootstrap, checkpoint restore, GPU profile, ZIP export | Chuyển tải CPU/GPU/RAM khỏi máy local |
| SHA-bound external quality report | Không cho smoke test tự đóng vai trò đánh giá pháp lý được chuyên gia duyệt |

## Kết luận nghiệm thu phù hợp

Không nên sửa lại kết luận V5: bốn đầu ra OFFLINE v1 đã PASS đúng theo validator hiện hành. Tuy nhiên, câu cuối của mô tả nên đổi từ “ONLINE-ready artifacts” thành “artifacts kỹ thuật sẵn sàng để thực hiện gold evaluation và tích hợp ONLINE”, hoặc tiếp tục xây các mục P0 trước khi đặt `offline_ready_for_online = true`.
