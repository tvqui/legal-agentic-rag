# Đo với Gold đã đối chiếu corpus — v0.2

Đọc [RUN_GUIDE_V2.md](RUN_GUIDE_V2.md) để cài và chạy từ đầu đến cuối; đọc [GOLD_V0_2_REVIEW.md](GOLD_V0_2_REVIEW.md) để biết phạm vi, thay đổi và giới hạn.

## Chọn đúng file

| File | Cỡ mẫu | Dùng để làm gì |
|---|---:|---|
| `gold_dataset/PhapDienAI_Gold_100_Labor_v0_2.zip` | 100: 88 ANSWERABLE + 12 NEED_MORE_FACTS | Mặc định cho hai notebook mới |
| `gold_dataset/PhapDienAI_Gold_120_Labor_v0_2.zip` | 120: thêm 20 câu có căn cứ | Tùy chọn đo rộng hơn, tăng thời gian/quota QA |
| `gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip` | Bộ cũ 100 câu | Tái lập số liệu cũ, không bị sửa đè |

Không cần giải nén. Gold là câu hỏi, đáp án và nhãn **để chấm**, tuyệt đối không nhập đáp án vào artifact hoặc gửi gợi ý căn cứ cho agent khi hỏi.

## Trước khi chạy

1. Code bộ đo và ZIP v0.2 cần có trên GitHub để notebook clone được. Chưa có commit/push tự động trong lượt rà soát này.
2. Add Input đúng một bản kết quả cuối result_28-10, ZIP hoặc thư mục `artifacts/`; không thêm recovery/checkpoint.
3. Import lại notebook mới nếu notebook Kaggle của bạn còn đường dẫn v0.1. Hoặc đổi riêng dòng `LABOR_GOLD = 'gold_dataset/PhapDienAI_Gold_100_Labor_v0_2.zip'` trong notebook hiện có sau khi cập nhật code.
4. Chạy smoke trước. `gold_import_validation.json` phải có `mapping_status=PASS`, `questions=100`, `retrieval_questions=88`, `evidence_records=93`, `query_after_snapshot_ids=[]`. Với bản 120, các số tương ứng là 120, 108 và 110.
5. `legal_approval=NOT_APPROVED` là trạng thái thật: không đổi nó thành APPROVED để làm đẹp báo cáo.

## Ngày và khả năng trả lời

V0.2 hỏi tại **15/09/2026**, đúng ngày chốt đã khai báo của corpus; không giả định artifact biết hết thay đổi sau ngày này. Ba câu dự báo năm 2028–2029 đã được thay bằng câu có nguồn thực chất trong artifact; bản gốc vẫn lưu trong member `future_challenges_NOT_IN_MAIN_SCORE.jsonl` để có thể kiểm tra từ chối riêng.

12 câu thiếu dữ kiện vẫn cần giữ để kiểm tra hỏi lại: chúng thuộc miền lao động và có quy tắc tương ứng trong corpus, nhưng người dùng chưa cung cấp đủ tình tiết. Không ép hệ thống kết luận cụ thể cho các câu này.

Có căn cứ không đồng nghĩa model sẽ luôn tìm đúng, xử lý đúng điều kiện hoặc vượt qua hậu kiểm. Câu nào BM25 không tìm được vẫn được giữ nếu căn cứ thực sự có: đó là phép đo truy xuất, không phải lỗi Gold để xóa câu khó.

## Khi đổi dữ liệu hoặc code

ZIP mới ghim build và retrieval fingerprint. Nếu đổi OFFLINE, công cụ dừng khi Gold không khớp; cần đối chiếu lại và xuất phiên bản Gold mới. Không bỏ kiểm fingerprint. Đổi ONLINE không đòi chạy lại OFFLINE hoặc tạo lại Gold nếu corpus giữ nguyên.

V0.1 và v0.2 có thay đổi câu hỏi, căn cứ và ngày đo, vì vậy **không lấy chênh lệch điểm hai bản làm mức tăng chất lượng hệ thống**. So các cấu hình trên cùng Gold SHA, artifact, model và giao thức. Tạo run mới sau khi đổi Gold/code; không resume kết quả cũ sang v0.2.
