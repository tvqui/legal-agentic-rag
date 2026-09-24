# Kiểm tra kết quả Kaggle V7.2

Nguồn: `C:\Users\Acer\Downloads\vn_labor_results_V7.2.zip`, SHA-256 `2efb261c7ba7c7197cf93df76bd9589bdffa8446b7de62dc28e26ed40e2aa71f`. ZIP CRC PASS; tôi chỉ đọc ZIP, không sửa artifacts đầu vào hoặc code trong đợt kiểm tra này.

## Kết quả bốn đầu ra

| Đầu ra | Audit V7.2 | Bằng chứng |
| --- | --- | --- |
| Document Registry | PASS | 95 documents, manifest coverage, metadata và machine-text checks đạt. |
| Structured Provisions | PASS | 18.449 provisions; hierarchy parent, article coverage và ID uniqueness đạt. File `provisions.jsonl` hiện có 18.449/18.449 `provision_identity_id`. |
| Versioned Hierarchical Graph | PASS local | 50.272 nodes/80.912 edges; ID, hierarchy, version anchors, endpoints và semantic checks đạt. 15.312 `ProvisionIdentity` nodes vẫn có trong graph. |
| Graph DB + Dense + BM25 indexes | FAIL tổng hợp | Dense load/count/dimension/ID order/normalized vectors/query và BM25 ID order/query **đều PASS**. Chỉ `Neo4j live verification` FAIL vì Notebook chạy `LOAD_AURA=False`; không có `neo4j_validation.json` mới. |

`run_all_offline.log` exit 0, preflight exit 0; `kaggle_audit.log` exit 1 do four-output audit đòi Graph DB live. **Không cần chạy lại toàn pipeline để sửa dữ liệu cấu trúc V7.2.** Instance AuraDB Free cũ đủ quota theo inspect; bước kế tiếp là nạp nguyên graph và kiểm tra live.

## Xác nhận các lỗi V7 đã hết

- `MISSING_PROVISION_IDENTITY` và `INVALID_NONPAGINATED_PAGE_STATUS` không còn trong validation. **18.449/18.449** provisions có identity và `provenance_status=RESOLVED`; 17.091 có page span `RESOLVED`, 1.358 `NOT_APPLICABLE`. Retrieval units có document/page offsets trong `provenance_span`.
- `STALE_NEO4J_BUILD` không còn. Báo cáo mới ghi `NEO4J_BUILD_NOT_VERIFIED: 1` mức INFO vì chưa nạp DB, đúng với `LOAD_AURA=False`.
- Còn `CASE_CORPUS_SMALL: 1` (INFO), `AMBIGUOUS_CANONICAL_PATH_QUARANTINED: 32` và `SHORT_PROVISION_QUARANTINED: 4` (WARN). Không có ERROR cấu trúc trong summary V7.2.

## Đã sửa kết luận về AuraDB Free

**Kết luận 50.000 nodes/175.000 relationships ở phiên bản đầu của báo cáo này là sai đối với instance hiện tại.** Neo4j còn một [trang Free ghi mức cũ](https://neo4j.com/free-graph-database/), nhưng [FAQ AuraDB hiện tại](https://neo4j.com/cloud/platform/aura-graph-database/faq/) và [hướng dẫn Neo4j tháng 5/2026](https://neo4j.com/blog/auradb/get-started-with-neo4j-auradb/) đều ghi **200.000 nodes/400.000 relationships**. Inspect trên instance `vn-labor-offline` của người dùng hiển thị 34.960 nodes (17%) và 62.463 relationships (16%), khớp mức mới sau khi làm tròn.

Full graph V7.2 có **50.272 nodes (~25%)** và **80.912 relationships (~20%)** theo mức 200k/400k. Nó nằm trong giới hạn AuraDB Free; **không cần projection, không bỏ 772 checklist nodes và không cần tier trả phí vì số lượng node/relationship**. Cần nạp nguyên graph V7.2 vào instance cũ rồi chạy Neo4j live verification. Lần nạp vẫn chưa được thực hiện; quota đủ không chứng minh import/audit sẽ thành công.

## Giới hạn chất lượng pháp lý

- Source Catalog: **95/95 `UNVERIFIED`**, 0 có `source_provider`, 0 có `collected_at`. Điều này không thể được giải quyết bằng chạy lại pipeline hoặc tự gán ngày chạy thành ngày thu thập nguồn.
- Gold evaluation: `NOT_EVALUATED`, 0 approved queries; `offline_ready_for_online=false`. Four-output technical PASS sau khi DB được xác minh vẫn chưa đồng nghĩa ONLINE-ready theo mô tả kiến trúc.
- Cần xác minh metadata nguồn và bộ Gold được chuyên gia duyệt; các warning quarantine/case corpus phải được đánh giá theo phạm vi sử dụng.

**Trạng thái hiện nay:** `registry/structure/graph = PASS`, `Dense/BM25 = PASS`, `Graph DB = CHƯA XÁC MINH`. Không cần rerun OCR/Dense/BM25; bước tiếp theo là nạp **nguyên graph** vào AuraDB Free đang dùng rồi chạy Neo4j live verification.
