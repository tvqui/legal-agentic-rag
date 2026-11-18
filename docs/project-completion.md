# Kiểm chứng bản bàn giao

Repository chứa mã nguồn, cấu hình, notebook, kiểm thử, Gold và tài liệu để nghiên cứu/chạy lại. Artifact, corpus PDF, model, khóa API và kết quả lớn được cấp riêng, không được suy ra là đã có sau `git clone`.

## Trước khi chạy demo

- Cài dependency theo README, cung cấp artifact và model đúng cấu hình.
- Chạy `run.bat online-check`, kiểm đường dẫn và fingerprint thực tế.
- Kiểm tra câu tra cứu, tình huống, thiếu dữ kiện, ngoài phạm vi, thời điểm quá khứ và câu nối tiếp.
- Đọc cả nội dung, trích dẫn, cảnh báo và lỗi; không chỉ nhìn HTTP 200.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests/online -t tests -q
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests/offline -t tests -q
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s benchmarks/graph_qa -q
```

Frontend: `npm test`, `npm run lint`, `npm run build` tại `frontend/`. Bộ đo được hướng dẫn ở [đo/README.md](../đo/README.md).

## Giới hạn phải công bố

Gold DRAFT/tập phát triển, hiệu lực hoặc nguồn chưa duyệt và điểm AI không chứng minh độ đúng pháp lý toàn diện. Bảng tổng hợp lưu cả code/comparison_key và số lỗi để tránh so sánh không công bằng. Chưa có phép đo thì ghi chưa đo; không điền kết quả giả để hoàn thiện báo cáo.

Dọn repository không đồng nghĩa đã chạy lại toàn bộ OFFLINE, API hoặc Kaggle. Những kiểm tra nào thực sự chạy trong lần dọn được ghi tại [submission-check.md](submission-check.md).
