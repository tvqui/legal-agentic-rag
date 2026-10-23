# Kiểm tra Gold candidate 100 — 23/10/2026

Kết luận: dùng được cho thử nghiệm và so sánh có ghi giới hạn; **chưa phải Gold
pháp lý đã duyệt**. ZIP nguyên gốc được giữ nguyên, không cần giải nén thủ công.

Đã đọc đủ 100 câu và đối chiếu 83 mã nguồn với `result_14-10`:

| Hạng mục | Kết quả |
|---|---|
| 100 ID và câu hỏi nguyên văn | Không trùng |
| 83 mã bằng chứng | Đều có trong retrieval units |
| Document ID, Điều/Khoản/Điểm/cấp, URL | Khớp 83/83 |
| Nguyên văn catalog | Khớp 83/83 sau NFC/khoảng trắng; không sửa nội dung |
| Trích đoạn trong từng câu | Khớp catalog |
| Bộ nhập mới | 85 câu retrieval, 100 câu QA |
| Nhãn riêng TD003 | Giữ để chạy, tạm không chấm tự động; xem ghi chú và nguồn |
| Human legal review | Chưa hoàn tất; không nâng lên APPROVED |
| Snapshot OFFLINE | 2026-09-15, khác cutoff Gold tự ghi 2026-10-23 |

SHA256 ZIP Gold:
`03d4aff611026fe4e1be4b27d5522af3bc501c242d2be37b37dd871bf318b4ab`.
Build OFFLINE:
`9a615f1927162fe63e73b734b6a48759596984fbf2d004ce76bc2eb94e0e5da0`.

Các vấn đề nội dung/phương pháp đã ghi trong `gold100_annotation_notes.json`
và `GOLD100_GUIDE.md`: TD003 chưa có nhãn chắc chắn; một số qrels chỉ là căn cứ
tối thiểu; ngoại lệ, ngày chốt, phiên bản khác và thiếu phủ miền/hội thoại cần
được duyệt tiếp. Mapping thành công không chứng minh mọi kết luận pháp lý đúng.

Kiểm tra đã chạy thật:

- 25/25 unit/integration fixture tests PASS; không gọi API trong tests.
- `suite.py prepare` trên ZIP Gold và artifact thật PASS, kiểm tra đủ 100 câu.
- BM25 CPU chạy đủ 85/85 câu một lần, không lỗi. Group Recall@10 = 0,8176;
  MRR@10 = 0,5670; group nDCG@10 = 0,6169; tìm đủ nhóm qrels ở 68/85 câu.
  Các điểm này là so **ID đã gán nhãn nháp**, không phải độ đúng của chatbot.
- Độ trễ BM25 sau warmup trung bình khoảng 4,21 ms, nhỏ nhất 2,01 ms, lớn nhất
  9,89 ms trên máy chạy kiểm tra. Không gồm nạp artifact/model, LLM hay frontend;
  không dùng số này để ước lượng toàn bộ QA hoặc so với phép đo Kaggle khác máy.

Chưa chạy inference thật của Dense/Hybrid/Graph/QA ablation/Zalo/VLSP trong lượt
kiểm tra này. Không có kết quả Kaggle đầy đủ được suy diễn từ tests. Các bảng
chưa đo giữ NOT_EVALUATED/N/A.

Thay đổi chỉ trong bộ benchmark; không sửa pipeline production để khớp 100 câu.
Đáp án và nhãn không được đưa vào facts/prompt câu hỏi. AI judge chỉ được gọi
sau khi agent trả lời, có cung cấp nguồn để chấm và ghi rõ đây là đánh giá AI.

Hướng dẫn chạy: [GOLD100_GUIDE.md](GOLD100_GUIDE.md).
