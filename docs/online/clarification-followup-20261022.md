# Sửa hỏi lặp sau khi bổ sung dữ kiện — 22/10/2026

## Lỗi đã tái hiện

Lượt đầu: “Tôi ký hợp đồng không xác định thời hạn. Tôi chỉ báo trước 20 ngày rồi nghỉ. Tôi nghỉ như vậy có trái pháp luật không?”

Lượt bổ sung: “Tôi không làm ngành, nghề hoặc công việc đặc thù. Tôi nghỉ vì lý do cá nhân, không thuộc trường hợp được nghỉ không cần báo trước. Ngày dự kiến nghỉ chính thức là 30/09/2026, tôi chỉ báo trước 20 ngày và công ty chưa đồng ý cho nghỉ sớm. Với những dữ kiện này, tôi nghỉ như vậy có đúng không và có thể phải chịu hậu quả gì?”

Trước sửa, lượt bổ sung có `used_turns=[]`, mất `contract_type`, không nhận `special_occupation`, rồi hỏi lại cả hai thông tin.

Hai nguyên nhân:

1. Bộ nối hội thoại chưa nhận tiền tố “Tôi không làm…” như một lượt bổ sung dữ kiện.
2. Bộ trích xuất chỉ nhận một số chuỗi cố định, chưa nhận cách liệt kê “ngành, nghề hoặc công việc đặc thù”.

Frontend hiện gửi các lượt người dùng trong cùng cuộc trò chuyện. Lỗi được tái hiện ngay cả khi request đã có lịch sử; thay đổi này nằm ở backend.

## Thay đổi

- `conversation.py`: nhận thêm lượt bổ sung/phủ định; giữ các hàng rào về đổi chủ đề, tình huống mới, chủ thể và nguồn dữ kiện chỉ từ người dùng.
- `analysis.py`: dùng chung bộ đọc nhóm công việc đặc thù cho trích xuất và định vị bằng chứng; giữ nguyên phần phủ định trong quote. Câu hỏi, giả định và câu chưa rõ không được xác nhận thành dữ kiện.
- `researcher.py`: kiểm tra đề xuất của LLM bằng cùng bộ đọc, ngăn đảo nghĩa câu phủ định.
- `test_clarification_followup.py`: 12 kiểm thử về hội thoại hai lượt, các cách diễn đạt, bằng chứng, đính chính và tránh dùng nhầm dữ kiện cũ.

Kết quả mong đợi tại bước phân tích sau sửa:

```json
{
  "contract_type": "INDEFINITE",
  "special_occupation": false,
  "notice_exception": false,
  "notice_days": 20,
  "termination_date": "2026-09-30",
  "mutual_termination_agreement": false,
  "missing_facts": []
}
```

Hệ thống vẫn phải truy xuất căn cứ, kiểm tra khả năng áp dụng và kiểm tra câu trả lời. Việc vượt qua bước hỏi dữ kiện chưa bảo đảm các dịch vụ LLM hoạt động hay đáp án cuối đã đủ.

## Kiểm chứng

Bản sửa được chạy cùng toàn bộ bộ kiểm thử ONLINE: **555/555 PASS**, gồm **12 kiểm thử mới**. Đây là kiểm thử local, chưa phải đo lại trên backend Kaggle.

Lỗi “Dịch vụ kiểm tra câu trả lời tạm thời không phản hồi hoặc gặp lỗi” thuộc bước reviewer khác với lỗi mất dữ kiện hội thoại này.

## Áp dụng lên Kaggle

1. Xem `git status` trong `legal-agentic-rag`, kiểm tra các thay đổi đang stage từ trước và đưa các file sửa trên cùng tài liệu này vào commit phù hợp.
2. Commit và push lên nhánh notebook dùng. Không chỉ push tài liệu hoặc notebook.
3. Dừng backend cũ; chạy lại cell cập nhật repo, rồi cell khởi động backend. Kiểm tra commit bằng `git log -1 --oneline`.
4. Giữ nguyên artifact `result_14-10`; thay đổi này không yêu cầu xây OFFLINE lại.
5. Tạo cuộc trò chuyện mới và gửi lại đúng hai lượt ở đầu tài liệu trong cùng cuộc trò chuyện. Sau lượt bổ sung, hệ thống không được hỏi lại loại hợp đồng và nhóm công việc đã nêu.

Nếu URL backend đổi, cập nhật `VITE_BACKEND_TARGET` rồi khởi động lại frontend. Lịch sử chỉ tồn tại trong cuộc trò chuyện trình duyệt gửi lên; một cuộc trò chuyện mới không được tự thừa hưởng hợp đồng của cuộc trò chuyện cũ.
