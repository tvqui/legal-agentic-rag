# ONLINE: nạp artifact và chạy Backend

ONLINE đọc artifact đã xây dựng, không tự crawl lại toàn bộ luật mỗi câu hỏi. Retriever tìm theo từ khóa/ngữ nghĩa và quan hệ; Auditor kiểm nguồn, thời gian và khả năng áp dụng; Adjudicator tạo dự thảo có căn cứ; các kiểm tra cuối xử lý nội dung, độ đủ và trích dẫn.

## Chuẩn bị artifact

Bản Git không kèm ZIP dữ liệu lớn. Dùng `vn_labor_online.zip` của cấu trúc mới hoặc ZIP OFFLINE cũ tương thích. Đặt tệp cục bộ vào `build/releases/`. Không dùng `research_data` hoặc gói `offline_review` làm dữ liệu Backend.

Các YAML hiện có ghim một release cụ thể; không chỉ đổi đường dẫn sang bản khác mà giữ SHA cũ. Tạo bản cấu hình ghim riêng:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/pin_online_artifact.py `
  --artifact build/releases/vn_labor_online.zip `
  --base-config config/online.yaml `
  --output build/online_pinned.yaml
run.bat online-check -Config build/online_pinned.yaml
run.bat online -Config build/online_pinned.yaml
```

Thay đường dẫn bằng tệp thực có. Script kiểm tương thích và ghim fingerprint, không tự xác nhận dữ liệu đã đúng pháp lý. Các biến môi trường/.env có thể ghi đè YAML; `online-check` giúp kiểm cấu hình thực tế. Không nhập khóa vào code hoặc README.

Model và provider phụ thuộc cấu hình: bản local deterministic, bản Ollama và bản Kaggle không mặc định dùng cùng dịch vụ. Với cấu hình cần Ollama, phải cài/chạy Ollama và tải model được cấu hình. Gemini dùng khóa của người chạy. BGE-M3/reranker cần trọng số tương ứng với chỉ mục.

## Chạy giao diện

Sau khi API hoạt động, chạy `run.bat frontend`. Xem [frontend/README.md](../frontend/README.md). API có `/health`, `/ready` và `/docs`.

Chi tiết: [runbook](online/runbook.md), [kiến trúc ONLINE](online/architecture.md), [log demo](online/demo-execution-log.md), [đầu ra OFFLINE](offline/artifact-layout.md).
