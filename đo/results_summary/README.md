# Kết quả đo đã lưu

`runs.csv` trích nguyên các trường từ bảng CSV trong các ZIP đã nhận, không chạy lại và không sửa điểm. Mỗi dòng có tên ZIP, SHA-256 và đường dẫn bảng gốc để truy vết. ZIP và câu trả lời chi tiết được lưu ngoài repository ở kho lưu trữ riêng của chủ dự án. Không có ZIP gốc thì người đọc chỉ kiểm tra được bảng tổng hợp này.

Chỉ so các tác vụ tương đương, cùng comparison_key và cùng điều kiện. Không lấy các ablation khác phiên bản code làm bằng chứng nhân quả. Gold hiện là DRAFT/tập phát triển; điểm AI không phải kiểm duyệt pháp lý. Giá trị trống nghĩa bảng nguồn không cung cấp, không phải điểm 0. Độ trễ là phép đo của lần chạy, không phải cam kết hiệu năng.

Một số dòng còn lỗi; xem successes/errors/expected và số được AI chấm trước khi diễn giải. Graph QA dùng bộ 24 câu riêng, không gộp với Gold 120; kết quả và câu trả lời vẫn được bảo quản trong kho lưu trữ.
