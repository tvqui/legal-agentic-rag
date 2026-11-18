# Coding Team — Qwen/Groq Writer, Executor, Gemini Reviewer

Công cụ phát triển do Codex điều phối, độc lập với pipeline Pháp Điển AI. Không tự áp dụng bản vá, chạy lệnh model, commit hoặc push.

| Vai trò | Cấu hình mặc định |
|---|---|
| Writer | Groq `qwen/qwen3.8-27b` |
| Writer dự phòng | Google `gemini-3.5-flash` |
| Executor | `local-static` hoặc Antigravity remote như trước |
| Reviewer | Google `gemini-3.5-flash-lite` |

`--role writer` và `--role gemma` gọi cùng vai trò viết. Key manifest `gemma` và file `gemma.md` giữ cho script cũ; xem `actual_model` để xác định model thật. Run Gemma lịch sử vẫn đọc được, nhưng run mới mặc định Qwen và không fallback về Gemma.

## Cài đặt và key trên Windows

Từ gốc `legal-agentic-rag`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools/coding_team/requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tools/coding_team -p "test_*.py"
```

Groq dùng API tương thích OpenAI qua `httpx`, endpoint cố định `https://api.groq.com/openai/v1/chat/completions`; không cần cài thêm Groq/OpenAI SDK. Tài liệu chính thức: https://console.groq.com/docs/openai và https://console.groq.com/docs/model/qwen/qwen3.8-27b .

Người dùng đã cho phép dùng file riêng `tools/coding_team/.env` (có `.env.example` để tham khảo):

```dotenv
GROQ_API_KEY=YOUR_GROQ_KEY
CODING_TEAM_GOOGLE_API_KEY=YOUR_GOOGLE_KEY
```

Cũng nhận `CODING_TEAM_GROQ_API_KEY` (ưu tiên hơn `GROQ_API_KEY`). Giá trị trong môi trường tiến trình được ưu tiên hơn helper `.env`. Chỉ đọc ba tên key trên từ file helper; không đọc `.env` Backend/Frontend, không nội suy biến hay thực thi nội dung .env. File thật được Git-ignore. Không gửi key vào chat, task, argv hoặc source.

## Probe từng nhánh

Chọn output mới cho mỗi lần kiểm tra:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py probe --run-dir tools/coding_team/runs/groq_probe_NEW --role writer --executor local-static --no-writer-fallback
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py probe --run-dir tools/coding_team/runs/groq_json_NEW --role writer --executor local-static --writer-format json --no-writer-fallback
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py probe --run-dir tools/coding_team/runs/google_writer_NEW --role writer --executor local-static --writer-model gemini-3.5-flash
```

Để thử sinh code mà không gửi source dự án:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/check_writer.py --output tools/coding_team/runs/smoke_NEW --model qwen/qwen3.8-27b
```

Smoke chỉ gửi yêu cầu giả lập cố định về hàm xử lý list, lưu JSON và kiểm cú pháp. Nó KHÔNG chạy code sinh ra. Codex phải đọc và kiểm thử độc lập trước khi dùng.

## Tác vụ thực tế

Đặt task trong `runs/`, chọn source tracked cần thiết và được phép gửi ra provider ngoài:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py prepare --task-file tools/coding_team/runs/task_NEW.txt --files src/vn_labor_online/query_clock.py --run-dir tools/coding_team/runs/task_NEW --executor local-static --writer-format json
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py run --run-dir tools/coding_team/runs/task_NEW --role all --allow-partial --call-timeout-seconds 60 --retries 1
```

Có thể gọi riêng `writer`, `antigravity`, `reviewer`. Không bắt buộc gọi cả ba cho mọi task. Nếu automatic approval review chặn gửi source, dừng lượt gửi và xin xác nhận cụ thể; không đổi cách gọi để né. Không gửi .env, corpus, Gold, cache hay cả repo. Mỗi file tối đa8KB UTF-8, task3KB, context writer12KB; source dài dùng `file.py@10:30` nhưng static sẽ bỏ qua excerpt.

JSON mode chỉ bảo đảm object parse được, không bảo đảm nội dung đúng. Client chặn JSON trùng key, số không hữu hạn, Markdown ngoài JSON và output bị cắt. Đọc `writer_attempts`, `actual_model`, `fallback_used`, `output_validation` trong manifest. Reviewer biết model thật từ metadata thay vì suy đoán theo tên vai trò cũ.

## Lỗi, fallback và resume

- Generation/GET retry rõ ràng408/500/502/503/504, mặc định1 lần, tối đa2. HTTP client không retry lồng.
- Route Groq → Gemini3.5Flash được ghim khi prepare. Có fallback sau lỗi provider rõ ràng, model/key thiếu hoặc output không hợp lệ; không fallback do429 hoặc lỗi mạng chưa rõ kết quả. `--no-writer-fallback` tắt nhánh này khi cần đo riêng.
- 429: dừng và ghi lỗi, không tự retry/đổi key/model né hạn mức. Sau khi quota reset, người điều phối quyết định lần chạy mới.
- Không tự quay lại Gemma. Không thay model/format/fallback trong manifest đã có; tạo run mới. Biến `CODING_TEAM_WRITER_MODEL` trỏ Gemma cũ bị chặn.
- Cache lỗi không tự gửi lại. COMPLETE là kết thúc xử lý, không phải bằng chứng code đúng. Exit0 hoàn tất, exit1 lỗi/partial/kiểm không đạt, exit2 job còn pending.

## Executor giữ nguyên

Local-static chỉ AST-parse **snapshot gốc**, không phải AI, không kiểm proposal, import hay hành vi. Nó chạy riêng không cần writer/API:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/coding_team/team.py probe --run-dir tools/coding_team/runs/static_NEW --role antigravity --executor local-static
```

Để kiểm file thật, prepare với `--executor local-static` rồi run `--role antigravity`. Đọc checked/skipped/error và `static_validation_status`; probe không có file không phải PASS cú pháp.

Remote Antigravity dùng `--executor remote` khi prepare/probe mới. Không retry POST tạo job; giữ ID và poll cùng run. Deadline ghim qua resume; CANCEL_REQUESTED phải được server xác nhận trước khi nói CANCELLED. Có khóa `.controller.lock` chống hai CLI cùng thao tác. Nếu crash, kiểm PID/process/job trước khi xử lý stale lock, không xóa khóa tự động. Chi tiết trong CODEX_INTEGRATION.md.

## File và bằng chứng

- `team.py`: CLI/snapshot/state machine; `writer.py`: Groq + Google writer/contract/env loader.
- `test_writer.py`: kiểm thử provider, fallback,429,JSON và credentials; các test cũ vẫn kiểm legacy/state/static.
- `check_writer.py`: smoke source-free; `.env.example`: tên key, không có key thật.
- `AGENTS.md` gốc repo và `CODEX_INTEGRATION.md`: hướng dẫn Codex chọn công cụ, kiểm chứng và xử lý lỗi.
- `WRITER_GROQ_20261114.md`: kết quả thay writer mới; `VALIDATION.md`: mốc tích hợp trước đó và liên kết cập nhật.
- `runs/`: metadata/snapshot/đề xuất/test local; được ignore. Không commit key, runs hoặc kết quả nặng.
