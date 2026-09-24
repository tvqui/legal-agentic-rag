# Tiến độ hoàn thiện OFFLINE từ kết quả 7.3

> **Kết quả mới nhất 16/09/2026:** [V8.1 sau Aura](OFFLINE_V8_1_AURA_RESULT_REVIEW.md) đã PASS cả bốn đầu ra OFFLINE v1, gồm kiểm Neo4j live trên đúng build. ONLINE-ready vẫn chưa đạt vì chưa có review pháp lý và Gold.

> **Candidate trước Aura:** [kết quả V8](OFFLINE_V8_RESULT_REVIEW.md) có Dense/BM25 và ba đầu ra đầu PASS; `indexes` chỉ chờ kiểm Neo4j live lúc đó.

Ngày 15/09/2026. Baseline được đọc trực tiếp từ `C:\Users\Acer\Downloads\vn_labor_results_7.3.zip` (SHA-256 `c30617777423ad4ef497e33dd6b947362050d11f941c499f867ae1347fb0a543`, CRC PASS). Pipeline và Aura load đều có exit code 0. Bốn đầu ra registry, structure, graph và indexes PASS kỹ thuật trên build `e9db2fa14ef3b8accd2cccc1f6f0b9df364976c367a6f1ddb3d822ec482062b9`: 95 documents, 18.449 provisions, 50.272 graph nodes, 80.912 graph edges. `offline_ready_for_online=false` vì chưa có review nguồn/pháp lý và Gold.

## Phần đã triển khai trong code V8

- Source Catalog chỉ xác nhận nguồn khi SHA, URL, provider, ngày thu thập và review record khớp; metadata cũ tự khai `metadata_verified` không đủ để qua gate. Đã xuất review draft cho 95 nguồn mà không phê duyệt thay ai.
- Chapter/Section có title, order và source span riêng. Provenance của provision, case/annex retrieval và bằng chứng relation/checklist/issue được kiểm bằng lát cắt chính xác từ segment → cleaned document → page text range. Tọa độ này là cleaned-text coordinates, không phải tọa độ PDF gốc.
- Legal change có hàng review với target/scope/effective date, SHA nguồn và bằng chứng. Change chưa giải được giữ trong queue; review EXCLUDED có lý do chặn candidate edge. Provision versions hỗ trợ review từng version hoặc instrument coverage, từ chối interval xung đột; temporal selector không dùng version chưa kiểm chứng.
- Derived DiagnosticItem được đánh dấu layer `derived`. Evidence không khớp bị đưa vào review queue thay vì gắn `VERIFIED`; graph chỉ nhận relation có evidence được giải.
- Retrieval units có source/temporal/provenance metadata mới. Dense và BM25 phải được dựng lại trên cùng units. Gold runner thực sự truy vấn Dense/BM25 và đo union recall@k sau khi có qrels/ngưỡng APPROVED cho đúng build; DRAFT hoặc build cũ trả `NOT_EVALUATED`/FAIL.
- Pipeline summary, final four-output validator và Kaggle audit đều xét source, semantic, legal quality và Gold khi quyết định `offline_ready_for_online`. Aura phải được kiểm live trên graph fingerprint mới.

## Kiểm chứng hiện tại

101 regression tests PASS; Python compile PASS; `git diff --check` PASS. Gói Private `kaggle_upload/vn_labor_kaggle_v8.zip`: 165 file, 96 corpus file, 4 DOCX chuyển đổi, 229,82 MB; SHA-256 `657e01744126d3f3e21c99307f6c28205169624ab89c6980efe4c630963cb413`; ZIP CRC và cú pháp các cell trong `VN_Labor_Kaggle_V8.ipynb` đều PASS. Gói đã chạy trên Kaggle; build V8.1 đã được nạp và kiểm Aura live thành công. Báo cáo V8.1 là bằng chứng mới nhất thay cho trạng thái graph Aura 7.3 trước đó.

## Điều kiện còn thiếu để đạt 100% theo kế hoạch

Không có người duyệt pháp lý ở thời điểm này. Baseline 7.3 có 95/95 nguồn `UNVERIFIED`, 25 candidate legal change (14 unresolved; 0 có effective_from được xác minh), 0 Gold query APPROVED. `review_inputs/v7_3` chứa 25 change và **837 dòng provision quarantine** để xem xét; các cảnh báo tóm tắt 32 ambiguous path và 4 short provision là số warning, không phải số dòng quarantine. Nội dung/những trang OCR rủi ro, phạm vi sửa đổi/bãi bỏ, hiệu lực provision, ví dụ Gold và các ngoại lệ có thể ảnh hưởng câu trả lời cần người có chuyên môn đánh giá. Code không thể tự chứng minh tính đúng pháp lý từ chính output của nó.

Gold runner V8 đo độ liên quan retrieval bằng union recall@k. Citation precision và tính đúng của câu trả lời pháp lý vẫn do `reviewed_quality_evaluation.json` được duyệt độc lập kiểm tra; chưa có bộ nhãn citation/answer để tính chúng tự động. Mức phủ của 24 vụ án và rủi ro OCR/quarantine cũng chưa được review. Đây là các phần chưa đạt trong kế hoạch M2/M5/M7, không thể kết luận 100% chỉ từ 101 test hoặc PASS kỹ thuật V7.3.

Mốc kỹ thuật M8 đã đạt với ZIP V8.1: cả bốn đầu ra PASS và Aura live khớp build. Mốc tiếp theo là source/temporal/quarantine/Gold review và legal quality gate để đạt ONLINE-ready. Không cần chạy lại từ đầu chỉ để xem báo cáo V8.1; nếu review làm đổi graph/retrieval, phải rebuild downstream và kiểm Aura trên build mới.
