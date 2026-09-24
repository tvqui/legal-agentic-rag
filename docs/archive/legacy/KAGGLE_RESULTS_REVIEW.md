# Kiểm tra độc lập kết quả Kaggle V5

Nguồn: `C:\Users\Acer\Downloads\vn_labor_results_V5.zip`  
SHA-256: `5aeeea227c13f7ee5c3d3a8c903bc1ef3276db365ff0b9a1eb4165e749d10121`  
Thời điểm audit trong ZIP: `2026-09-14T10:52:48.456743+00:00`  

## Kết luận

**OFFLINE — DATA & KNOWLEDGE CONSTRUCTION v1: HOÀN TẤT.**

ZIP qua CRC, pipeline có mã thoát 0, Aura được nạp thành công và cả bốn đầu ra cuối đều PASS khi kiểm tra độc lập.

| Đầu ra | Kết quả | Bằng chứng chính |
|---|---|---|
| Document Registry | PASS | 95/95 tài liệu; ID duy nhất; manifest bao phủ đầy đủ; 0 metadata pháp lý chưa giải quyết; toàn bộ có machine text |
| Structured Provisions | PASS | 18.445 provisions; ID duy nhất; 0 parent sai; 0 văn bản pháp luật thiếu Article |
| Versioned HierarGraph | PASS | 34.430 node, 62.061 cạnh; ID duy nhất; 0 cạnh đứt; đủ hierarchy và version anchors |
| Graph / Dense / BM25 indexes | PASS | 18.621 retrieval units; Dense 18.621 × 1.024; FAISS và BM25 đều nạp/truy vấn thành công; Aura khớp tuyệt đối |

## Kiểm tra độc lập ngoài báo cáo có sẵn

- ZIP có 3.902 thành phần và không có lỗi CRC.
- Dense metadata khớp đúng thứ tự toàn bộ retrieval units.
- Tất cả vector Dense hữu hạn và có chuẩn L2 bằng 1 trong sai số cho phép.
- FAISS round-trip và truy vấn mẫu thành công.
- BM25 corpus khớp toàn bộ unit ID và truy vấn mẫu thành công.
- Fingerprint graph tự tính lại là `bc6fb902a7e7f03280b3739728aa834984107baec736c0fb82bd45dc8230686c`, trùng `build_id` trong `neo4j_validation.json`.
- Aura xác nhận đúng 34.430 node và 62.061 cạnh ở chế độ `transactional_replace`.
- `validation_issues.jsonl` có **0 ERROR**, 36 WARN và 1 INFO.

## Các thông báo còn lại

- `CASE_CORPUS_SMALL`: 1 INFO — corpus án lệ/tư pháp hiện có 24 mục; nên mở rộng trước khi đánh giá chất lượng truy hồi ở quy mô lớn.
- `AMBIGUOUS_CANONICAL_PATH_QUARANTINED`: 32 WARN — các nhánh nguồn có đường dẫn mơ hồ đã được cách ly và không làm hỏng graph xuất.
- `SHORT_PROVISION_QUARANTINED`: 4 WARN — các provision quá ngắn đã được cách ly.

Các thông báo này không phải lỗi cấu trúc nghiêm trọng và không chặn OFFLINE v1.

## Phạm vi chưa hoàn thành

`legal_quality_evaluation` vẫn là `NOT_EVALUATED`, nên `offline_ready_for_online` còn `false`. Đây là bước đánh giá gold set về citation/retrieval trước khi đưa hệ thống sang giai đoạn online; không thuộc tiêu chí hoàn tất **OFFLINE — DATA & KNOWLEDGE CONSTRUCTION v1** đã thống nhất.

Các cảnh báo dependency của pip trong log liên quan tới những package hệ thống Kaggle như Colab, MoviePy và ydata-profiling. Môi trường riêng của pipeline vẫn vượt qua preflight, OCR, Dense, BM25, validation và Aura audit nên chúng không ảnh hưởng kết quả V5 này.
