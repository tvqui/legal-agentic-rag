# Pháp Điển AI — Modern Frontend (React + Vite)

## Xuất xứ và tích hợp
Được chỉnh từ `legal-agentic-rag-main(8).zip/frontend`, không tạo frontend mới độc lập. Giữ nguyên các hợp đồng API trong `src/services`, quản lý hội thoại, polling và drawer nguồn pháp lý.

## Cài vào dự án
1. Sao lưu `frontend/` hiện tại.
2. Giải nén thư mục `frontend/` từ ZIP này thay thế thư mục cũ (hoặc dùng diff để merge).
3. Trong `frontend/`: chạy `npm ci`, `npm test`, `npm run lint`, `npm run build`.
4. Giữ nguyên `.env` đang dùng; đối chiếu `frontend/.env.example` để trỏ đúng địa chỉ Backend.
5. Chạy `npm run dev`, kiểm tra chat nhiều lượt, dừng yêu cầu, lịch sử, citations, Drawer, dark theme và responsive.

## Những điều KHÔNG làm
- Không chỉnh Backend, retrieval, graph, prompt, endpoint hay schema.
- Không bật các nút giả không có backend.
- Không thêm shader/Three.js nặng.
- Các câu hỏi gợi ý phải gửi lệnh chat thực, không hiển thị câu trả lời giả.

## Style / thiết kế
- Thiết kế nền sáng, xanh ngọc, nét chữ rõ, khung chat rộng để đọc luật.
- Cảm hứng: ThreeUI skeuomorphic (ánh sáng mềm), animated top dock (chuyển động hover nhẹ), shadcn/ui chat patterns.
- File `src/styles/modern.css` ghi đè visual tokens và style cũ nhưng giữ selectors hợp đồng UI.
- Có responsive mobile, theme sáng/tối và reduced-motion.

## Giới hạn
Các tài liệu/kho luật và trạng thái chính xác phụ thuộc dữ liệu trả về từ Backend. Demo giao diện hoặc build frontend thành công không xác nhận khả năng pháp lý của hệ thống.
