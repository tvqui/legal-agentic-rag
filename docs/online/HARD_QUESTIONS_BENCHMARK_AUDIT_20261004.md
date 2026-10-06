# Kiểm toán benchmark câu hỏi khó ngày 2026-10-04

## Kết luận

Đánh giá của người phản biện phần lớn đúng. Benchmark chứng minh transport ổn định và các gate cơ bản hoạt động, nhưng chưa chứng minh hệ thống đã đạt độ chính xác pháp lý cao. Các lỗi trọng yếu trong nhóm phép năm và chấm dứt hợp đồng đều có bằng chứng trực tiếp trong JSONL.

## Số liệu đã kiểm lại từ JSONL

- 25/25 request nhận HTTP 200, không có transport failure.
- Tổng thời gian: 789,658 giây.
- Trung bình: 31,586 giây; trung vị: 32,936 giây.
- P95 theo nearest-rank: 66,829 giây; P95 nội suy tuyến tính: 65,416 giây.
- Nhanh nhất: 3,413 giây; chậm nhất: 99,794 giây.
- Trạng thái: 13 PARTIAL_ALLOWED, 5 NEED_MORE_FACTS, 5 ABSTAIN, 2 INSUFFICIENT_EVIDENCE.

HTTP 200 chỉ xác nhận request được xử lý ở tầng giao thức; nó không xác nhận nội dung pháp lý đúng.

## Các nhận xét đúng

1. **Câu 2.1 sai nghiêm trọng.** Facts đã có age=17, minor=true, worked_months=12, service_years=6, nhưng answer dùng mức 12 ngày ở điểm a thay vì mức 14 ngày ở điểm b. Kết quả đúng theo dữ kiện là 14 + 1 = 15 ngày.
2. **Câu 2.2 thiếu kết luận số học rõ ràng.** Phải chọn mức 16 ngày phù hợp nhất rồi cộng 2 ngày thâm niên, thành 18 ngày. Không cộng 14 và 16.
3. **Câu 2.3 có lỗi citation-to-text.** Answer nói khoản 2 Điều 66 trong khi nội dung công thức chưa đủ 12 tháng nằm tại khoản 1. Hệ thống cũng gọi 18/VBHN-VPQH là “Nghị quyết”, sai loại văn bản. Khi evidence không có quy tắc làm tròn, phải trình bày kết quả phân số/thập phân và nói rõ chưa kết luận cách làm tròn.
4. **Câu 2.5 chưa trả lời trực tiếp đúng/sai.** Theo dữ kiện, cách cộng 12 + 2 + 2 + 1 là sai; mức đúng là 14 + 1 = 15 ngày.
5. **Câu 3.3 có fact corruption.** Cụm “không báo trước 45 ngày” bị parser ghi thành notice_days=45; giá trị thực tế phải là 0.
6. **Câu 3.4 và 3.5 là false negative.** Evidence đúng đã vượt applicability nhưng claim do mô hình sinh bị Reference Audit loại; pipeline sau đó hạ toàn bộ câu trả lời thành INSUFFICIENT_EVIDENCE.
7. **Câu 4.5 thiếu dữ kiện chi phí đào tạo.** Muốn tính tổng nghĩa vụ tiền theo Điều 40 còn phải biết có khoản hoàn trả chi phí đào tạo theo Điều 62 hay không.
8. **Phân tích latency đúng.** Nút thắt không nằm ở graph; thời gian lớn nằm ở researcher, applicability/adjudication LLM và seed retrieval/audit.

## Các điểm cần diễn đạt lại

1. retrieval_rounds=0, edges_visited=0 không tự động là lỗi. Nếu policy anchor và seed retrieval đã phủ đủ evidence bắt buộc, adaptive graph dừng sớm là hành vi đúng. Benchmark này chỉ cho thấy chưa kiểm chứng được graph expansion khi seed thiếu, nên chưa được dùng để chứng minh năng lực GraphRAG thích ứng.
2. Câu 4.1 đúng là response cuối có worked_months=12, dù dữ kiện gốc chỉ nói đã làm cho công ty 6 năm. Đây là suy diễn không được bảo đảm và đã được loại bỏ.
3. Điểm số ước lượng trong nhận xét là đánh giá chủ quan, không phải metric tái lập. Kết luận kỹ thuật nên dựa trên pass/fail theo từng expected claim, expected citation, fact consistency và latency threshold.

## Hiệu chỉnh đã thực hiện

- Parser phủ định: “không/chưa báo trước N ngày” và “nghỉ ngay” được ghi nhận là notice_days=0.
- Không còn tự suy diễn worked_months=12 chỉ từ số năm thâm niên.
- Fact gate khi hỏi tổng tiền bồi thường bổ sung câu hỏi về chi phí đào tạo theo Điều 62.
- Applicability deterministic cho các statutory chain đã chứng minh không còn bị LLM ghi đè.
- Các bài toán xác định được ưu tiên renderer deterministic sau evidence audit: Điều 34/35/38/39/40; ngoại lệ trả lương chậm, thông tin không trung thực, quấy rối tình dục; phép năm 12/14/16 ngày, thâm niên, tỷ lệ chưa đủ 12 tháng.
- Phép năm trả kết luận số cụ thể, nêu rõ các mức không cộng chồng, và không tự đặt quy tắc làm tròn.
- Trace bổ sung timing riêng: seed_retrieval, deterministic_audit, applicability_audit, selection, adjudication, reference_audit.
- Thêm regression tests cho các lỗi nêu trên.

## Kết quả xác minh

- Targeted regressions: 14/14 PASS.
- Toàn repository: 246/246 PASS.
- online-check: compatible, không có issue cấu trúc.
- Smoke end-to-end bằng build thật: 6/6 câu lỗi trọng yếu đạt kỳ vọng:
  - 2.1 = 15 ngày, dẫn điểm b khoản 1 Điều 113 và Điều 114;
  - 2.2 = 18 ngày, không cộng chồng mức 14 và 16;
  - 2.3 = 28/3 ngày, dẫn khoản 1 Điều 66 và không tự làm tròn;
  - 2.5 kết luận cách tính 17 ngày là sai, kết quả 15 ngày;
  - 3.4 trả đúng chuỗi điểm g khoản 2 Điều 35 → khoản 1 Điều 16;
  - 3.5 áp dụng khoản 3 Điều 34 và không tự động coi là đơn phương trái luật.
- Smoke deterministic/BM25 sau sửa có tổng thời gian khoảng 0,14–1,05 giây/câu trên máy local; cần chạy lại cấu hình full Ollama để đo latency thực tế của mô hình.
- Build vẫn provisional vì source catalog, provision temporal review và Gold approval chưa hoàn tất.

## Tiêu chí cho lần benchmark kế tiếp

- 2.1 trả 15 ngày và dẫn Điều 113 khoản 1 điểm b + Điều 114.
- 2.2 trả 18 ngày, không cộng 14 với 16.
- 2.3 dẫn Điều 66 khoản 1 và không tự đặt quy tắc làm tròn.
- 2.5 nói rõ cách tính 17 ngày là sai; kết quả 15 ngày.
- 3.3 có notice_days=0.
- 3.4 và 3.5 không còn INSUFFICIENT_EVIDENCE do CLAIM_CONTENT_UNSUPPORTED.
- Nhóm 4 vẫn dừng sớm đúng, riêng 4.5 hỏi thêm chi phí đào tạo.
- Nhóm 5 tiếp tục ABSTAIN.
- Có một benchmark seed-ablation riêng buộc graph tìm evidence còn thiếu; chỉ benchmark đó mới dùng để đánh giá graph expansion.
- Báo cáo latency dùng các timing mới để xác định chính xác tầng chậm.
