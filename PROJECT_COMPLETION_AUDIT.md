# PROJECT COMPLETION AUDIT

Ngày kiểm tra: 2026-10-03

## Kết luận

Các thay đổi do người khác thực hiện ở `analysis.py`, `api.py` và `generation.py` có hướng đúng nhưng chưa hoàn chỉnh. Lỗi quan trọng nhất là nhánh 120 ngày dùng nội dung Điều 7 Nghị định 145/2020/NĐ-CP nhưng evidence chỉ gắn với Điều 35 điểm a; trạng thái chưa biết ngành nghề đặc thù vẫn tính thiếu 25 ngày. Hai lỗi này đã được sửa bằng fact gate và evidence chain bắt buộc.

Tài liệu cũ cũng ghi sai một số đường dẫn (`vn_labor_core`, `adjudication.py`, các test file nhỏ không tồn tại), dùng tên quan hệ graph không có trong artifact (`GUIDED_BY`, `REFERS_TO`) và mô tả `valid_to` theo khoảng đóng. Code thật dùng `vn_labor_offline`, `generation.py`, test suite hợp nhất và khoảng hiệu lực nửa mở `[valid_from, valid_to)`.

## Phần đã xác minh và sửa

- Routing không phụ thuộc ngày chạy test và không mở graph phức tạp chỉ vì ngày hỏi trước 2021.
- Câu hỏi nghỉ việc yêu cầu xác định công việc đặc thù khi thông tin này làm thay đổi thời hạn 45/120 ngày.
- Nhánh 120 ngày phải có cả Điều 35 khoản 1 điểm d và Điều 7 khoản 2 điểm a.
- Evidence plan chỉ bắt buộc Điều 39–40 khi dữ kiện thực sự cho thấy thiếu thời hạn báo trước.
- API không công khai đường dẫn hoặc chuỗi exception nội bộ; frontend đọc đúng error envelope.
- Graph có hard cap 2 hop/15 node/40 edge, visited set và allowlist quan hệ thực tế.
- Reference audit kiểm locator pháp lý theo evidence IDs của từng claim.
- Câu hỏi rõ ràng ngoài pháp luật lao động trả `ABSTAIN` trước retrieval.
- Temporal helper phân biệt chế độ trước/sau 2021 và phát hiện trường hợp chuyển tiếp.
- Source resolver canonicalize URL mà vẫn giữ tham số nhận dạng; SearXNG là opt-in và kết quả chỉ là candidate.
- Parser nhận điểm `a)`/`đ)` khi OCR làm mất khoảng trắng và tiếp tục giữ source span.
- Evaluation harness xuất JSON/Markdown, khóa trạng thái OFFICIAL bằng reviewer và build ID.

## Kết quả kiểm thử trên bản sửa

| Bộ kiểm thử | Kết quả |
|---|---:|
| ONLINE `unittest` | 88/88 PASS |
| OFFLINE `unittest` | 141/141 PASS |
| Tổng Python | 229/229 PASS |
| Frontend lint | PASS |
| Frontend production build | PASS, 1810 modules transformed |

Đây là kiểm thử mã nguồn và fixture. Nó không thay thế full OFFLINE pipeline, Aura load hay human legal review.

## Giới hạn còn lại

- ZIP V8.1 hiện tại vẫn dùng được để phát triển ONLINE, nhưng chưa chứa thay đổi parser/resolver mới.
- Không thể công bố benchmark pháp lý chính thức khi Gold vẫn chưa được reviewer duyệt.
- `provisional_mode` phải giữ `true` cho tới khi source catalog và temporal review hoàn tất.
- Một OFFLINE build mới là bắt buộc trước khi phát hành bản cuối có Phase 7–8.
