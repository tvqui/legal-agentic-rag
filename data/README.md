# Dữ liệu đầu vào (cấp riêng)

Corpus PDF/DOCX không được đưa vào Git. Để xây OFFLINE từ đầu, đặt bộ nguồn được bàn giao vào `data/` theo cấu hình `config/pipeline.yaml` và danh mục `config/source_catalog.yaml`/`config/source_attachments.yaml`. Giữ các bản sửa trong `review/corrections/` mà YAML tham chiếu.

Để chỉ chạy ONLINE, dùng artifact đã xây dựng tương thích; không cần OCR lại corpus. Artifact lớn và trọng số model cũng được cấp riêng. Xem [hướng dẫn ONLINE](../docs/online.md) và [đầu ra OFFLINE](../docs/offline/artifact-layout.md).

Không có liên kết tải công khai nào được tự tạo trong bước dọn. Người nộp cần gửi kèm nguồn dữ liệu/artifact hoặc cung cấp vị trí truy cập cho giảng viên, kèm quyền truy cập phù hợp.
