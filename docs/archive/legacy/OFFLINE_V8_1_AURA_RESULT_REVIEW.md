# Kết quả V8.1 sau nạp Aura

Ngày 16/09/2026. Đã kiểm trực tiếp `C:\Users\Acer\Downloads\vn_labor_results_v8.1(aura).zip` (264.141.628 byte; SHA-256 `afb456c552f6122101e4c92dd9c7d8240cf3f093483266b14aa0d111417ddf5a`; 3.627 entries; ZIP CRC PASS). `neo4j_load.log` exit 0 và audit sau nạp đạt; `kaggle_audit.log` exit 1 trong giai đoạn **trước nạp Aura** là kết quả dự kiến, không phải trạng thái cuối.

**OFFLINE v1 đạt kỹ thuật trên đúng build V8.1.** `final_outputs_validation.json` có cả bốn stage PASS và không có failed check:

| Đầu ra | Kết quả |
| --- | --- |
| Document Registry | PASS: 95 documents |
| Structured Provisions | PASS: 18.449 provisions |
| Versioned Hierarchical Graph | PASS: 50.118 nodes, 76.844 edges |
| Graph DB + Dense + BM25 | PASS: Neo4j live node/edge IDs khớp, 18.624 retrieval units, Dense và BM25 hợp lệ |

`neo4j_validation.json` xác nhận dataset `vn-labor-offline`, 50.118 nodes, 76.844 edges và transactional replace. Build ID `7b33c8206124e32d423ddfc02adbf58ad26cce68e8ac0154329d51b5dd667d38` được tính độc lập lại từ chính hai graph JSONL trong ZIP và **khớp** report. Graph JSONL, retrieval units, FAISS index và BM25 params trong ZIP V8 trước/sau Aura giống hệt nhau, nên không có rebuild hoặc đổi nội dung âm thầm. `validation_issues.jsonl` có 0 ERROR; còn 32 cảnh báo ambiguous path, 4 short provision và 1 thông tin case corpus nhỏ.

`ONLINE-ready` vẫn **CHƯA ĐẠT** theo đúng gate: Source Catalog 0/95 được duyệt (61 nguồn authoritative chưa xác minh), 25 temporal LegalChange pending, 18.449 provision versions chưa review interval, Gold 0 query APPROVED và chưa có đánh giá citation/retrieval pháp lý được duyệt. Các review queue và 837 dòng quarantine từ ZIP V8.1 cần người có chuyên môn xem xét; bản nháp nguồn/change/quarantine mới nhất nằm ở `review_inputs/v8_1` và không tạo approval nào. `gold_build_id` của graph + retrieval + Dense + BM25 **hiện tại** là `0c4d82edb5e23df65490b5b2eb9cb5623c2d5f1a8baf75693acf6329af9a92cc`. Nếu review nguồn/temporal làm thay đổi graph hoặc retrieval units, phải dựng lại downstream, kiểm Aura trên build mới và lấy `gold_build_id` mới trước khi phê duyệt Gold/ngưỡng.

Không cần chạy lại pipeline hoặc Dense/BM25 để xác nhận OFFLINE v1 hiện tại. Có thể giữ ZIP V8.1 làm checkpoint kỹ thuật. Để đạt mục tiêu 100% theo `OFFLINE_100_PERCENT_PLAN.md`, mốc tiếp theo là review nguồn chính thức, ngày/phạm vi sửa đổi và hiệu lực provision, các dòng quarantine/issue ambiguous có ảnh hưởng câu trả lời, cùng bộ Gold và citation quality trên build cuối cùng sau review. Hiện chưa có người duyệt pháp lý, nên không thể tự đánh dấu các mục đó `VERIFIED` hoặc tuyên bố ONLINE-ready.
