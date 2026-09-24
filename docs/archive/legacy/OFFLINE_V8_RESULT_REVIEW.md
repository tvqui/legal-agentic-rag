# Đánh giá ZIP kết quả OFFLINE V8

Ngày 16/09/2026. Đã đọc trực tiếp `C:\Users\Acer\Downloads\vn_labor_results_v8.zip` (251,9 MiB; SHA-256 `4f13b05a75542464b0c5ad6f111ca7283e70e2a8ac764fcaec6101dd5552a6a0`; 3.626 entries; ZIP CRC PASS). `kaggle_preflight.log` và `run_all_offline.log` đều exit 0. `kaggle_audit.log` exit 1 vì đúng **một** check còn FAIL: `Neo4j live verification` chưa được yêu cầu (`LOAD_AURA=False`). Không thấy lỗi cấu trúc nghiêm trọng: `validation_issues.jsonl` có 0 ERROR, 36 WARN, 2 INFO.

| Đầu ra | Kết quả V8 |
| --- | --- |
| Document Registry | PASS, 95 documents |
| Structured Provisions | PASS, 18.449 provisions |
| Versioned Hierarchical Graph | PASS, 50.118 nodes và 76.844 edges; không duplicate/dangling |
| BM25 và Dense | PASS local, 18.624 retrieval units, ID order/query đều đạt |
| Neo4j Graph DB live | CHƯA KIỂM TRA trên build V8; đây là lý do duy nhất `indexes=FAIL` |

Dense V8 dùng BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181` trên `cuda:0`, 18.624 vector × 1.024 chiều, FP16; FAISS round-trip, chuẩn hóa vector, self-search và text queries đều PASS. BM25 ID order và query PASS. **Không cần chạy lại OCR, Dense hay BM25** để xử lý lỗi hiện tại. `gold_build_id` của graph + units + Dense + BM25 V8 là `0c4d82edb5e23df65490b5b2eb9cb5623c2d5f1a8baf75693acf6329af9a92cc`.

Graph V8 ít hơn 154 nodes và 4.068 edges so với baseline 7.3. Chênh lệch edges khớp đúng 3.864 issue + 154 diagnostic + 50 relation candidates bị filter bởi kiểm tra bằng chứng mới; cần review tác động retrieval/issue trước khi coi chất lượng ngữ nghĩa đạt. V8 có 2.004 relation edges được nhận, 50 relation candidates bị giữ lại; 15.130 diagnostic items được nhận, 154 trong queue; 7.736 issue edges được nhận và 3.864 issue candidates trong queue. Cả 3.864 issue candidates này mang trạng thái `AMBIGUOUS` vì câu bằng chứng xuất hiện nhiều lần; không thể tự chọn vị trí đầu tiên. Những queue này không phải lỗi cấu trúc và không được tự ép qua validation.

`offline_ready_for_online=false` là đúng: Source Catalog 0/95 được duyệt (61 authoritative source chưa xác minh), 25/25 temporal LegalChange còn pending, 18.449 provision versions chưa được review interval, Gold 0 query APPROVED và citation/retrieval legal quality chưa được người chuyên môn đánh giá. Quarantine vẫn có 837 dòng provision. Bản nháp review từ ZIP V8 nằm trong `review_inputs/v8`; script không tạo approval nào.

## Bước tiếp theo

Đưa **chính ZIP V8 này** lên một Dataset Kaggle Private mới để làm checkpoint. Trong Notebook V8 giữ Dataset code V8, bỏ checkpoint 7.3 và gắn checkpoint V8. Đặt `RUN_PIPELINE=False`, `LOAD_AURA=True`, `RESTORE_ARCHIVE="AUTO"`, cấp lại bốn Kaggle Secrets Neo4j (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`), rồi Save & Run All. Loader sẽ thay dataset dự án trong instance Aura hiện có và audit trực tiếp graph build V8; không cần xóa instance bằng tay. Tải ZIP xuất sau lần nạp và kiểm `neo4j_validation.json`, `final_outputs_validation.json`, `kaggle_audit.log`. Nếu audit exit 0 và cả bốn stage PASS, có thể gọi OFFLINE v1 **đạt kỹ thuật**; ONLINE-ready vẫn chưa đạt cho đến khi các review và Gold ở trên hoàn tất.
