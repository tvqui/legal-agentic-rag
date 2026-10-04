# Kiểm thử 25 câu hỏi khó

Ngày kiểm tra: 2026-10-04.

## Kết quả

- 25/25 câu đạt điều kiện tự động của bộ kiểm thử do người dùng cung cấp.
- Nhóm 1–3 trả lời bằng đúng chuỗi Điều/Khoản/Điểm bắt buộc.
- Nhóm 4 trả `NEED_MORE_FACTS` trước retrieval.
- Nhóm 5 trả `ABSTAIN` và không công bố citation.
- Toàn repository: 239/239 tests pass.
- Frontend production build: pass.

Báo cáo máy đọc được nằm tại `artifacts/reports/hard_question_regression_latest.json`.

## Các lỗi đã được sửa

1. Phân loại phạm vi ưu tiên mục tiêu pháp lý chính, nên từ “công ty”, “nhân viên” hoặc “giờ làm việc” không làm câu hỏi hình sự/đất đai lọt vào miền luật lao động.
2. Fact gate hỏi đúng dữ kiện còn thiếu cho nghỉ việc, chậm lương, phép năm và tính bồi thường.
3. Evidence plan và policy anchors bảo toàn các chuỗi quy tắc:
   - Điều 35 khoản 2 điểm b → Điều 97 khoản 4;
   - Điều 35 khoản 2 điểm g → Điều 16 khoản 1;
   - Điều 39 → Điều 40 khoản 1–3;
   - Điều 113 → Điều 114 → Điều 66 Nghị định 145/2020/NĐ-CP;
   - Điều 34 khoản 3 cho trường hợp hai bên thỏa thuận chấm dứt.
4. Applicability không còn nhầm điểm b khoản 2 Điều 35 với điểm b khoản 1.
5. Phép năm chọn một mức nền 12/14/16, sau đó mới cộng thâm niên và tính tỷ lệ tháng; không cộng chồng các nhóm.
6. Frontend chịu được `document_number = null`, không còn lỗi `Cannot read properties of null (reading 'includes')`.

## Giới hạn của kết quả

Bộ 25 câu được chạy thành công khi tắt Dense và dùng các lớp deterministic. Điều này chứng minh các đường luật trọng yếu không phụ thuộc vào LLM hoặc Dense để hoạt động đúng. Nó không chứng minh mọi câu hỏi pháp lý ngoài benchmark đều đúng.

Build vẫn ở chế độ provisional vì source catalog, hiệu lực cấp provision và Gold set chưa được người có chuyên môn duyệt xong. `PARTIAL_ALLOWED` trong nhóm 1–3 là trạng thái đúng với metadata hiện tại.

Chế độ local `config/online.yaml` chưa dùng toàn bộ mô hình tùy chọn. Dense cần model BGE-M3 cục bộ; reranker đang tắt; Researcher, Auditor và Adjudicator dùng deterministic. `config/online_kaggle.yaml` là cấu hình đầy đủ hơn: Dense, reranker, Ollama Researcher, Hybrid Auditor và Ollama Adjudicator. Các lớp deterministic, applicability gate và reference audit vẫn phải được giữ khi bật mô hình.

Các sửa đổi trong báo cáo này chỉ thuộc ONLINE và frontend; không cần chạy lại OFFLINE để áp dụng.
