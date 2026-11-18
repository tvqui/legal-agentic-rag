> **Cập nhật14/11/2026:** Writer hiện dùng Qwen/Groq, dự phòngGemini3.5Flash; xem [kiểm chứng mới](../../docs/README.md). Nội dung bên dưới là mốc tích hợp trước khi thay writer.

# Kiểm chứng tích hợp Coding Team — 13–14/11/2026

## Phạm vi và kết quả

Đã tích hợp ZIP do người dùng cung cấp vào `tools/coding_team/`, giữ nguyên các thư mục run cũ. Mã cũ và receipt SHA-256 nằm trong `runs/integration_backup_20261113/`. Các lỗi thật được phát hiện trong ZIP đã được sửa trước khi kiểm API; không sửa logic LegalGraphRAG, corpus, Backend hoặc Frontend trong nhiệm vụ này.

| Kiểm tra | Kết quả | Loại bằng chứng |
|---|---|---|
| Dependencies | google-genai 2.31.0 đáp ứng >=2.31,<3; pip check sạch | Kiểm môi trường thật, không nâng phiên bản không cần thiết |
| Toàn bộ unit test coding_team | **66/66 PASS** | Offline: mock provider + Git/temp snapshot + CLI/khóa hai tiến trình thật; không gọi API |
| Cú pháp các file Python của công cụ | PASS | AST, không thay cho unit/integration tests |
| Local-static probe không key | exit 0, NO_SOURCE_PROBE, syntax_passed=null | CLI thật, không kết luận có file đã kiểm |
| Local-static task trên query_clock.py không key | exit 0, checked=1, SYNTAX_OK | CLI thật, snapshot đầy đủ; không thực thi source |
| 2 manifest cũ trước tích hợp | verify PASS, mặc định executor remote giữ nguyên | Đọc/kiểm hash local, không gọi lại dịch vụ |
| Gemma4 31B probe | HTTP500 sau2 attempts giới hạn | API thật; không phải lỗi quota được chứng minh |
| Gemma4 26B probe riêng | HTTP500 sau1 attempt | API thật, không đổi mặc định writer |
| Gemini3.5FlashLite probe | COMPLETE, phản hồi OK | API thật; không phải kiểm thử code |
| Antigravity remote probe | COMPLETE, remote_status=completed, phản hồi OK | API thật, đúng1 job rồi poll cùngID; probe không thực thi code |
| Task query_clock: Gemma | HTTP500 | API thật, writer chưa tạo đề xuất dùng được |
| Task query_clock: local-static | COMPLETE, SYNTAX_OK, checked=1 | Kiểm snapshot gốc, không kiểm proposal |
| Task query_clock: Reviewer | COMPLETE, có cảnh báo thiếu Gemma, đề xuất4 unittest | API thật, review partial, model không tự chạy test |
| Codex chạy test query_clock tự viết | **5/5 PASS** | unittest thực thi local thật |
| Codex review rồi chạy test do Reviewer đề xuất | **4/4 PASS** | Code đã đọc/kiểm trước khi thực thi local, không tự áp dụng vào production |

Không tuyên bố đã thành công một chuỗi đủ ba AI vì Gemma vẫn lỗi dịch vụ. Cơ chế tiếp tục khi writer lỗi đã hoạt động: static và reviewer tiếp tục, giữ cảnh báo partial; Codex kiểm và chạy test thật. Antigravity remote đã kiểm tra kết nối và vòng đời job; **chưa kiểm chứng nó thực thi một task code thật** trong lần tích hợp. Đây không phải benchmark năng lực lập trình của các model.

## Các sửa quan trọng

- Sửa parser local-static vốn nhận literal `\n` thay vì xuống dòng thật: không còn checks=[] giả thành kiểm cú pháp thành công.
- Kiểm framing/hash từng source, số file checked/skipped/error, report SHA/protocol; cached report từ phiên bản lỗi phải dùng run mới.
- Phân biệt SYNTAX_OK, SYNTAX_ERROR, PARTIAL_SYNTAX_CHECK, NO_PYTHON_CHECKED và NO_SOURCE_PROBE; CLI1 khi task không đạt. COMPLETE chỉ nghĩa phân tích hoàn tất.
- Không cho đổi nhầm task thành probe để bỏ qua nguồn. Static-only task không phụ thuộc Gemma hoặc API key.
- Chặn POST lặp khi ID rỗng hoặc outcome chưa rõ; khóa độc quyền run giữa các CLI, không tự xóa stale lock.
- Ghim deadline qua resume, giữ ID/status pending khi poll hoặc cancel lỗi; unknown status không bị giả thành terminal.
- Remote đã completed nhưng không có output hợp lệ thành INCOMPLETE, không polling mãi.
- CANCEL_REQUESTED chỉ thành CANCELLED khi server xác nhận; pending trả exit2, không bị che thành lỗi terminal.
- Retry có giới hạn cho408/500/502/503/504 ở generation/GET; không tự retry429, lỗi mạng không rõ hoặc POST tạo job.
- Allowlist metadata lỗi và chặn echo exact key hiện cấu hình; không ghi SDK message/exception chain vào log. Không đọc .env của ứng dụng.

## Hồ sơ kiểm chứng thực tế

Tất cả trong `tools/coding_team/runs/integration_20261113/` (được Git ignore):

- `validation_summary.json`: kết quả, metadata và hash mã đã kiểm.
- `probe_gemma31/`, `probe_gemma26/`, `probe_reviewer/`, `probe_remote/`: manifest API thật.
- `clock_task/`: snapshot, static report và phản biện thật; Gemma ERROR, các bước còn lại COMPLETE.
- `static_no_key_probe/`, `static_no_key_task/`, `keyless_validation.json`: CLI không key.
- `trusted_clock_checks.py`, `reviewer_clock_checks.py`, `*.log`, `project_task_validation.json`: test local thật và mã thoát.

Không có job Antigravity còn pending trong các run mới của nhiệm vụ này; remote probe đã completed. Nếu các phiên sau bị ngắt, chỉ poll/cancel ID đã lưu, không tự gửi job mới.

## Giới hạn còn lại

1. HTTP500 của Gemma31B và26B chưa được phía client khắc phục; không tăng retry vô hạn, không khẳng định do quota. Có thể dùng static + Reviewer + Codex khi writer lỗi.
2. Remote Antigravity vẫn phụ thuộc quyền truy cập/dịch vụ/độ trễ của Google. Deadline chỉ được thực thi khi controller đang poll; không có daemon nền tự hủy job.
3. Khóa có thể còn sau crash. Kiểm PID và trạng thái đã lưu trước khi xử lý khóa thủ công.
4. local-static chỉ parse Python bằng interpreter local; không kiểm import, hành vi, file không phải Python, excerpt hoặc bản vá Gemma. Agent output không tự được áp dụng.
5. Secret detection là phòng vệ theo pattern và exact key hiện có, không phải hệ thống DLP bảo đảm phát hiện mọi dạng bí mật. Chỉ chọn source cần thiết và không gửi dữ liệu nhạy cảm.
6. Nhiệm vụ chưa commit/push/deploy. Mã helper đã được bỏ ignore có chọn lọc để có thể đưa lên Git; runs/cache/key vẫn ignore. Những thay đổi khác có sẵn của người dùng được giữ nguyên.

## Lệnh xác minh Windows

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tools/coding_team -p "test_*.py"
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py probe --run-dir tools/coding_team/runs/static_NEW --executor local-static --role antigravity
```

Lệnh chạy task và remote job đầy đủ ở README.md; hướng dẫn điều phối ở CODEX_INTEGRATION.md và AGENTS.md. Dùng thư mục run mới cho lần thử mới; không sửa manifest/model/executor cũ.
