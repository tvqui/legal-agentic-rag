# Rà soát và hoàn thiện ONLINE ngày 29/10/2026

## Kết luận sau kiểm tra báo cáo Copilot

Các sửa trước đó về log, index, fact gate, phép tính và hội thoại có thật. Baseline chạy lại 640 kiểm thử ONLINE PASS. Tuy nhiên chưa thể coi đề xuất đã hoàn tất hoặc chất lượng pháp lý đã được chứng minh chỉ từ số test. Rà soát độc lập tìm được thêm các lỗi chưa có trong test cũ.

## Những lỗi tái hiện và đã sửa tiếp

1. **Phép tính bị gán sang task khác:** một câu vừa hỏi lương thử việc vừa hỏi nghỉ phép có thể buộc task nghỉ phép chứa số tiền. Nguyên nhân là dùng toàn câu hỏi để xác định scope cho từng task. Bản sửa dùng subissue và mô tả/retrieval query của task; request_quote toàn câu không còn quyết định scope.
2. **Hỏi cả tỷ lệ và số tiền:** nhắc “phần trăm” có thể làm mất yêu cầu tính tiền. Giữ riêng yêu cầu monetary khi người dùng hỏi cả hai.
3. **Nhiều mức lương mâu thuẫn:** parser trước chọn mức đầu tiên. Nay không tự chọn; hỏi mức và đơn vị áp dụng. Lương 0 không được làm cơ sở tính tự động. Không tính chỉ từ một nguồn trùng số Điều/85% nhưng không phải quy tắc tiền lương thử việc.
4. **Gộp ý làm mất điều kiện:** hai claim cùng nguồn/cùng 45 ngày nhưng điều kiện “đã thanh toán” và “chưa thanh toán” có thể bị gộp. Giới hạn gộp ngữ nghĩa vào các diễn đạt đơn giản hiểu được; giữ đầy đủ điều kiện và phân biệt mức tối đa/tối thiểu. Câu trùng nguyên văn vẫn được gộp.
5. **Xác nhận sau mâu thuẫn:** không phải lúc nào người dùng nói “Tôi xác nhận...” cũng thoát được vòng hỏi lại. Nay xác nhận tường minh giải quyết đúng trường được xác nhận; giữ provenance, không biến lời assistant thành dữ kiện. Theo dõi tiếp giữa chủ đề hợp đồng và nghỉ việc; loại thời hạn hợp đồng cố định cũ khi đã xác nhận hợp đồng không xác định thời hạn.
6. **Nguy cơ trộn run:** câu hỏi giống nhau chưa đủ để resume. Bổ sung hash source ONLINE và effective config (không chứa giá trị key) trên `/ready` và signature của remote runner. Runner local khóa thêm source/config.
7. **Plan chỉ nằm ở artifacts bị Git bỏ qua:** đưa bộ 28 câu/tình huống chỉ có input vào `benchmarks/online_upgrade/questions.json` và có hướng dẫn chạy lại.

Không hardcode ID câu benchmark vào suy luận. Các unit test kiểm tra thêm biến thể và reviewer trả verdict sai dù JSON hợp lệ.

## Đề xuất sáu nhóm đang ở đâu?

| Đề xuất | Trạng thái sau đợt này | Giới hạn |
|---|---|---|
| Ngữ cảnh vụ việc | Có kế thừa từ user, provenance, sửa/xác nhận mâu thuẫn và tách tình huống; sửa thêm ở đợt này | Vẫn là lịch sử ngắn phía trình duyệt, không phải hồ sơ server/bộ nhớ dài hạn kiểu Clio |
| Độ đủ từng task | Có task/evidence/claim; bổ sung scope phép tính và chặn bù kết quả trong reason | Cơ chế đã test local; chưa chứng minh mọi loại câu hỏi đúng/đủ |
| Điều kiện và phản bác | Có fact gate, tri-state audit, bổ sung ngoại lệ có giới hạn và Graph theo gap | Không thêm một agent phản biện trùng chức năng; chưa đo bao phủ toàn luật |
| Phân luồng | Có exact/profile/hybrid, hỏi sớm và từ chối ngoài phạm vi; index giảm quét dữ liệu | Không tắt hậu kiểm để đạt thời gian đẹp; lợi ích model thật chưa đo |
| Bằng chứng rõ | Giữ claim → evidence, locator, trích đoạn, phiên bản/trạng thái và source drawer hiện có | Không tự phê duyệt nguồn/hiệu lực; không thêm UI chưa cần thiết |
| Tái sử dụng | Đã thêm cache raw BM25/Dense trong request, có bounds/isolation/cancel; **tắt mặc định** | Microbenchmark BM25 cho kết quả chậm hơn; không tuyên bố tăng tốc; chưa đo Dense |

## Bằng chứng kiểm tra

- Candidate: 656 kiểm thử ONLINE PASS; 46 kiểm thử evaluation suite PASS. Xem log của đợt rà soát để phân biệt bản candidate và lần xác minh trên thư mục dự án.
- Đã chạy 28 câu/tình huống không gọi model trên **đúng result_28-10**, build `3e43d1d43b966e8100ba187e69a21fcd8f885b2586a1584b58c428c31851877e`.
- Lần smoke trước chốt cấu hình cache mặc định: 14 PARTIAL_ALLOWED, 8 NEED_MORE_FACTS, 1 ABSTAIN, 5 INSUFFICIENT_EVIDENCE. Không biến các phản hồi đó thành nhãn đúng luật; task chưa semantic review vẫn NOT_CHECKED.
- Đối chiếu 64 khóa tra vị trí từ 15.635 khóa: không khác kết quả so với scan. Trung vị indexed khoảng 3,46 ms so với scan 62,43 ms, trong cùng process đã nạp dữ liệu. Đây là microbenchmark, không phải latency LLM.
- BM25 cache làm chậm trong cả nhóm lặp và không lặp của microbenchmark local; do đó mặc định false. 28 câu smoke không có cache hit, không dùng smoke đó để chứng minh cache có lợi.
- Không chạy Gemini/Qwen/BGE inference thật trong đợt này; không dùng fixture để tuyên bố độ chính xác pháp lý.

## Chặn còn lại và cách chạy bản mới

HD001/HD002/NP001 còn bị chặn trong smoke; nguyên nhân cần đọc theo trace, không phải chỉ tăng timeout. Kiểm tra trực tiếp result_28-10 thấy các unit được báo vẫn UNVERIFIED, official_source=false và provision_temporal_verified=false. Không sửa metadata để ép PASS. Câu nhiều task mới cũng chưa có đủ chuỗi căn cứ trong đường deterministic; chưa coi hoàn thành.

Gold và corpus còn provisional. Cần đo model thật trên bản triển khai mới với đầu vào/đối chứng được rà soát; model reviewer vẫn có thể sai. Không gán kết quả 473 baseline cũ cho code mới hoặc sửa các phản hồi cũ để cải thiện điểm.

Hướng dẫn có sẵn: `benchmarks/online_upgrade/README.md`. Chỉ phần phê duyệt pháp lý và chạy inference ở môi trường phù hợp còn cần thực hiện ngoài các kiểm tra local này. Không commit/push/deploy tự động và không chạy lại OFFLINE.

## Xác minh sau khi áp dụng vào dự án thật

- Đã áp dụng vào `D:/data_thô/legal-agentic-rag`, không chỉ bản sao rà soát.
- Chạy lại ngay trên thư mục dự án: **656/656 ONLINE PASS** (14,731 giây); **46/46 evaluation-suite PASS** (4,918 giây).
- Smoke 28/28 trên đúng result_28-10 với cache mặc định tắt: 14 partial, 8 hỏi thêm, 1 ngoài phạm vi, 5 thiếu căn cứ; 0 lượt gọi model.
- Đối chiếu 64 khóa: 0 mismatch; trung vị indexed 4,525 ms, scan 85,705 ms trong phép đo này. Không gán mức tăng tốc microbenchmark cho toàn pipeline LLM.
- 49 đường dẫn đã stage trước đó vẫn giữ nguyên; không chạy build OFFLINE, không commit/push/deploy. Các log/xuất smoke nằm trong thư mục rà soát riêng để không ghi đè benchmark cũ.
