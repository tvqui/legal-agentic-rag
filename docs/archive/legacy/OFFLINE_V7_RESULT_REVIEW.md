# Kiểm tra kết quả Kaggle V7 và bản sửa V7.2

Nguồn kiểm tra: `C:\Users\Acer\Downloads\vn_labor_results_V7.zip`, SHA-256 `1a6538e9b271f6b37dd6bba6243b07b351ea65ac51604d1868b7a49f2b1d6f7b`; ZIP CRC PASS. Tôi không thay đổi ZIP đầu vào hoặc artifacts sản xuất trong lần kiểm tra này.

## Kết quả thực tế trong ZIP V7

| Đầu ra | Kết quả audit | Điều đã xác minh |
| --- | --- | --- |
| Document Registry | PASS | 95 documents, manifest coverage và machine text đạt. |
| Structured Provisions | PASS theo four-output audit | 18.449 provisions, hierarchy parent và article coverage đạt; **file provision thiếu trường enrichment V7**, nên summary validation vẫn FAIL. |
| Versioned graph | FAIL | Graph có 50.272 nodes/80.912 edges và 15.312 `ProvisionIdentity` nodes, 18.449 `HAS_PROVISION_VERSION` edges. Các kiểm tra ID/endpoints/hierarchy/version anchor trong four-output audit PASS; pipeline/semantic validation FAIL vì đọc file provision cũ và báo Neo4j build cũ. |
| Dense/BM25/Graph DB indexes | FAIL | 18.624 retrieval units. Dense load/count/ID order/normalized vectors/query và BM25 ID order/query **đều PASS**. Chỉ kiểm tra Neo4j live FAIL vì Notebook dùng `LOAD_AURA=False`, không yêu cầu truy vấn DB. |

`run_all_offline.log` trả mã 0 và preflight PASS; `kaggle_audit.log` trả mã 1 vì validation. `OFFLINE v1: CHƯA ĐẠT` là đánh giá đúng cho cả bốn đầu ra khi Aura chưa được kiểm tra.

## Nguồn gốc các lỗi báo hàng loạt

1. `MISSING_PROVISION_IDENTITY: 18.449` là lỗi **artifact persistence**. `parse_all()` ghi `03_structure/provisions.jsonl` trước khi `enrich_provenance()` và `materialize_provision_versions()` bổ sung trường. V7 ZIP cho thấy file này có 0/18.449 `provision_identity_id`, nhưng `provision_versions.jsonl` có 18.449/18.449 identity và graph đã có node/edge identity. `kaggle/remote.py::refresh_summary()` đọc lại file provision cũ nên thay báo cáo bằng 18.449 lỗi giả. V7.2 ghi lại provision rows sau enrichment.
2. `INVALID_NONPAGINATED_PAGE_STATUS: 18.449` có cùng nguyên nhân. File provision cũ có 0/18.449 `page_status`, nên quality gate diễn giải tất cả là tài liệu không phân trang nhưng status sai. Artifact `provision_spans.jsonl` thực sự có 17.091 `PDF_PAGE` và 1.358 `DOCUMENT`; 16.050 page spans đã `RESOLVED`, 1.041 còn `UNRESOLVED`. V7.2 ghi lại page/source fields cùng provision.
3. **1.041 spans unresolved là vấn đề thật**, tập trung trong **một** PDF hợp nhất `legal_corpus/consolidated/2026_133_19_VBHN-VPQH.pdf`. Segment 187.140 ký tự khác extracted text bởi một dòng trống ở segment offset 139.591; vì vậy phép tìm nguyên văn cả segment không thành công. Mapper V7.2 ánh xạ whitespace edit với độ lệch +1, rồi xác nhận **1.041/1.041 source slices của provision trùng nguyên văn** trong extracted document. Không thay đổi ký tự pháp lý được chấp nhận; case không khớp/lặp vẫn để unresolved.
   Kiểm tra cô lập trên **toàn bộ 18.449 provisions V7** bằng mapper V7.2 (không OCR/model/DB) hoàn thành trong khoảng 0,28 giây: **18.449/18.449 `RESOLVED`**, 17.091 page spans `RESOLVED`, 1.358 `NOT_APPLICABLE`; tất cả đều có document offsets. Điều này xác nhận mapper, chưa xác nhận toàn pipeline sau khi build lại.
4. `STALE_NEO4J_BUILD: 1` đến từ `neo4j_validation.json` của checkpoint V6: build ID `bbafae464889a9235093655fba582400456bcb3d5a6bbe3837d1dc6ddaadd106` cho 34.960 nodes/62.463 edges. Graph V7 có hash `0389b832a5fa66ae8bf80780b15f8ab04145140d190106c6922e1532a4b25bdf`; Notebook chưa nạp Aura. V7.2 xóa proof cũ khi rebuild và ghi `NEO4J_BUILD_NOT_VERIFIED` mức INFO cho graph local; mục Graph DB trong four-output audit vẫn FAIL cho tới khi chạy Aura live.

## Những giới hạn không được che bởi bản sửa code

- Source Catalog V7 có đủ 95 records nhưng **95/95 `UNVERIFIED`**, 0 `source_provider`, 0 `collected_at`. Đây là thiếu xác minh nguồn chính thức; không thể tự điền bằng thời điểm chạy hay tên file. Dữ liệu nguồn phải được đối chiếu và bổ sung có căn cứ.
- Gold evaluation `NOT_EVALUATED`, 0 approved queries; `offline_ready_for_online=false`. Các quan hệ sửa đổi và temporal validity theo từng provision chưa được chuyên gia duyệt. Code/V7.2 không biến kết quả kỹ thuật thành xác nhận pháp lý.
- Quarantine còn 32 ambiguous paths và 4 short provisions, corpus judicial mới 24 cases. Các cảnh báo này không phải lỗi cấu trúc mới.
- V7.2 chưa chạy Kaggle/Aura. Việc 1.041 span khớp slice trong kiểm tra cô lập không thay thế xác nhận toàn pipeline V7.2 và quality gate.
- **Sửa kết luận giới hạn AuraDB Free:** nhận định 50.000 nodes trước đây là sai đối với instance hiện tại. [FAQ AuraDB Neo4j](https://neo4j.com/cloud/platform/aura-graph-database/faq/) ghi mức 200.000 nodes/400.000 relationships; inspect 34.960 nodes (17%) và 62.463 relationships (16%) của instance người dùng khớp mức mới. Full graph V7.2 50.272 nodes/80.912 relationships nằm trong quota Free; không cần projection hay tier trả phí chỉ vì số lượng graph.

## Sửa đổi và kiểm tra V7.2

- `provision_versions.py` lưu final `provisions.jsonl` sau khi thêm provenance và identity/version.
- `provenance.py` ánh xạ segment→document theo match duy nhất và các edit chỉ ở whitespace, cache một lần/segment; kiểm tra slice trước khi đánh dấu RESOLVED. `indexes.py` truyền document/page span vào retrieval metadata và thêm Section vào breadcrumb.
- `pipeline.py` vô hiệu hóa Neo4j proof từ checkpoint trước graph rebuild; `quality.py` coi graph local chưa được Aura xác minh là INFO, không phải lỗi cấu trúc.
- Notebook V7.2 mặc định `LOAD_AURA=False`. Sau khi kiểm tra ZIP mới, có thể nạp Aura riêng, xác nhận đúng graph build và các Dense/BM25 indexes.
- Toàn bộ **93/93 tests PASS**; gói `kaggle_upload/vn_labor_kaggle_v7_2.zip` CRC PASS, notebook code compile. Gói local được đóng lại sau khi đính chính tài liệu AuraDB Free, SHA-256 hiện tại `19748927cafdefdf52466f328dd61511bb940fd21890d5d80e664d21279f9cce`. Code xử lý dữ liệu không đổi; output V7.2 của người dùng đến từ package đã upload trước đó.

**Bước tiếp theo:** dùng gói V7.2 với checkpoint chính ZIP V7 ở trên, giữ `RUN_PIPELINE=True`, `LOAD_AURA=False`, tải ZIP kết quả `vn_labor_results_V7_2.zip` và kiểm tra summary/provision spans/four-output audit. Chỉ nạp Aura sau khi kiểm tra graph mới; xác minh Source Catalog và Gold set là công việc riêng để đạt ONLINE-ready.
