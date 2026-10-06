# PROJECT COMPLETION PLAN

Ngày cập nhật: 2026-10-03

Nguyên tắc: **đúng pháp lý → truy vết được → tái lập được → an toàn → chất lượng truy hồi → độ trễ**.

| Phase | Trạng thái | Kết quả |
|---|---|---|
| 0. Baseline audit | DONE | Đối chiếu kiến trúc, code, test và tài liệu nghiên cứu. |
| 1. Query routing | DONE | Ngày quá khứ không tự biến câu hỏi một vấn đề thành truy vấn graph phức tạp. |
| 2. Notice-period precision | DONE | `special_occupation` là dữ kiện ba trạng thái; thiếu dữ kiện thì hỏi lại; 45/120 ngày phải có evidence đúng. |
| 3. API errors | DONE | Error envelope thống nhất, có `error_id`, không trả exception/path nội bộ. |
| 4. Graph safety | DONE | Tối đa 2 hop, 15 node, 40 edge; cycle guard; allowlist quan hệ pháp lý. |
| 5. Citation audit | DONE | Kiểm citation toàn câu trả lời và kiểm Điều/Khoản/Điểm/URL theo từng claim. |
| 6. Frontend resilience | DONE | Chuẩn hóa base URL, timeout, structured error và thông tin chẩn đoán an toàn. |
| 7. Source resolver | CODE DONE / BUILD PENDING | Canonical URL, adapter chính thức và SearXNG opt-in có giới hạn. Cần chạy OFFLINE để tạo artifact mới. |
| 8. OCR/legal parser | CODE DONE / BUILD PENDING | Nhận `a)`, `đ)` kể cả OCR mất dấu cách; giữ source span. Cần chạy OFFLINE để tạo artifact mới. |
| 9. Temporal partition | DONE | Ranh giới 2021-01-01, interval `[valid_from, valid_to)`, phát hiện hợp đồng chuyển tiếp. |
| 10. Evidence gap expansion | DONE | Khi evidence giao cơ quan hướng dẫn chi tiết, tự thêm slot `implementing_regulation` và chỉ mở rộng graph có giới hạn. |
| 11. Closed-world adjudication | DONE | Out-of-scope trả `ABSTAIN`; claim chỉ được tồn tại khi citation audit PASS. |
| 12. Evaluation harness | CODE DONE / GOLD PENDING | Có JSON + Markdown metrics; kết quả chỉ `OFFICIAL` khi Gold được duyệt và đúng build. |
| 13. Integration verification | DONE LOCALLY | Unit tests ONLINE/OFFLINE pass; cần smoke trên artifact OFFLINE mới sau khi bạn chạy lại. |
| 14. Handover | DONE | README, runbook và báo cáo này mô tả rõ phần đã hoàn tất và phần còn phụ thuộc bên ngoài. |

## Việc bạn cần làm khi có lại tài nguyên OFFLINE

Các thay đổi Phase 7–8 không xuất hiện trong ZIP V8.1 cũ. Khi có Kaggle quota, chạy lại OFFLINE từ đầu hoặc từ checkpoint extraction tương thích, sau đó chạy validation, Dense, BM25 và Aura load. Không dùng lại graph/index cũ với provisions mới.

Sau khi tải ZIP mới về:

1. Đặt ZIP vào `build/releases/`.
2. Cập nhật hash/build ID trong các file `config/online*.yaml` bằng công cụ pin artifact hiện có.
3. Chạy `run.bat test` và `run.bat online-check`.
4. Chạy bộ câu hỏi smoke ở `docs/online/runbook.md`.
5. Chạy Gold evaluation sau khi Gold đã được người có chuyên môn duyệt.

## Điều kiện để tuyên bố hoàn thành chính thức

- OFFLINE artifact mới PASS registry, structure, graph, Dense, BM25 và Neo4j cùng build ID.
- Human review nguồn, temporal, quarantine và Gold hoàn tất.
- `scripts/evaluate_gold_set.py` trả `status=OFFICIAL` và đạt ngưỡng đã duyệt.
- ONLINE tests, frontend lint/build và API smoke đều PASS trên artifact mới.
