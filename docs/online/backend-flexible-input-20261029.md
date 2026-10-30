# Notebook backend: đổi tên và đổi bộ kết quả OFFLINE

Notebook `kaggle/ONLINE_Backend.ipynb` nhận diện Input bằng cấu trúc dữ liệu, không dựa vào tên dataset hay tên ZIP. Bản sửa đi kèm cũng được cung cấp dưới tên `backend-1-2.ipynb`.

## Cách dùng

1. Thay notebook backend trên Kaggle bằng bản đã sửa. Giữ GPU T4 x2, Internet ON và quyền dùng các Secrets hiện tại.
2. Add Input một bộ kết quả OFFLINE cuối: ZIP hoặc thư mục đã giải nén. Không cần upload lại PDF hay gói mã OFFLINE.
3. Để `ARTIFACT = ''`, giữ model và các thông số mong muốn rồi Run All.
4. Khi có `VITE_BACKEND_TARGET=https://...`, cập nhật URL trong `frontend/.env` nếu thay đổi và khởi động lại frontend.

Đổi tên dataset, ví dụ từ `vn-labor-results-28-10` sang tên khác, không cần sửa code. Khi thay nội dung bằng kết quả OFFLINE mới, dừng backend cũ, thay Input và Run All để kiểm tra và pin lại.

Nếu gắn nhiều bộ kết quả cuối hợp lệ, notebook dừng và liệt kê các lựa chọn. Xóa Input không dùng, hoặc đặt `ARTIFACT` thành đường dẫn chính xác trong `/kaggle/input` của ZIP/thư mục cần dùng. Notebook không tự đoán bản mới nhất. Thư mục dataset chứa trực tiếp `artifacts/` cũng được chấp nhận khi chọn rõ đường dẫn.

## Kiểm tra được giữ lại

- Bước nhận diện chỉ đọc cấu trúc và báo cáo nhỏ; yêu cầu bốn bước registry/structure/graph/indexes đều đạt. ZIP tên bất kỳ được xét; gói source, ZIP hỏng hoặc checkpoint chưa hoàn chỉnh không được chọn chỉ vì tên giống kết quả.
- Script pin kiểm tính tương thích bằng ArtifactStore: CRC và đường dẫn ZIP, mã graph, căn chỉnh retrieval/BM25/dense, báo cáo dense/Neo4j. Với ZIP, lưu SHA-256; với thư mục giải nén, kiểm build và fingerprint, không tạo SHA-256 ZIP giả.
- So sánh build/fingerprint/SHA-256 với cấu hình vừa pin, thay cho việc so với mã result_14-10 còn lưu trong cấu hình gốc. Không xóa kiểm tra toàn vẹn dữ liệu.
- Kiểm đường dẫn thực tế để phát hiện biến môi trường cũ trỏ sang bộ dữ liệu khác; giữ kiểm profile, Gemini, GPU và cổng đang được dùng.
- Tương thích kỹ thuật không tự nâng dữ liệu thành đã được duyệt pháp lý. Các cảnh báo PROVISIONAL giữ nguyên. Đổi Input cũng không có nghĩa đã rà soát Gold hay cập nhật ngày chốt pháp luật; các thông tin đó cần được kiểm tra riêng khi phát hành bản dữ liệu mới.

## Giới hạn kiểm chứng

Đã kiểm thử các nhánh nhận diện/đổi tên/đổi build và tính tương thích với dữ liệu result_28-10 thực tế ở local. Không khởi chạy Kaggle, không gọi Gemini, không tải model và không chạy lại OFFLINE trong lần sửa này.
