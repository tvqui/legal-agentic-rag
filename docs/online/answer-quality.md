# Kiểm tra chất lượng câu trả lời ONLINE

ONLINE làm sạch bản sao dùng để trình bày, không sửa OFFLINE artifacts, nguồn gốc,
SHA, source span, số điều, số tiền, ngày hoặc thời hạn. Không cần API mới.

- Bỏ dòng chỉ chứa dấu trang trí và dòng `Kính gửi:`/`Nơi nhận:` ở đoạn dùng để
  trả lời. Giữ chúng nếu câu hỏi hỏi về các mục này. Giữ nguyên văn trong dấu
  ngoặc kép và block quote, kể cả khoảng trắng.
- Không thay toàn bộ `1` thành `l`. Phát hiện một số từ OCR đáng ngờ, locator
  `Điều l`/`Khoản l`, ký tự hỏng, đoạn chỉ có dấu và từ lặp ba lần.
- Mô hình đang có được hướng dẫn viết câu rõ ràng, tránh lời chào hành chính và
  thuật ngữ nội bộ. Câu trả lời theo quy tắc cố định không in dữ kiện kỹ thuật.
- Nếu câu trả lời còn lỗi phát hiện được nhưng nguồn không lỗi: tối đa một lượt
  sửa bằng mô hình đang cấu hình. Không thêm lời khẳng định pháp lý, đổi claim/
  evidence IDs, phiên bản, giả định, số, URL, nguyên văn, chủ thể hay các từ thể
  hiện nghĩa vụ/ngoại lệ/phủ định. Chỉ render claims đã kiểm tra; bỏ prose tự do.
- Nếu sửa không an toàn hoặc provider timeout: dùng bản theo quy tắc cố định.
  Nếu vẫn lỗi hoặc nguồn dùng cho claim có OCR/encoding đáng ngờ: trả
  `INSUFFICIENT_EVIDENCE`, không đưa claims/citations thành kết luận.
- Reference audit vẫn chạy sau bước sửa để kiểm nội dung và trích dẫn.

Warnings/trace: `ANSWER_LAYOUT_CLEANED`, `SOURCE_TEXT_QUALITY:*`,
`ANSWER_TEXT_QUALITY:*`, `ANSWER_LANGUAGE_REPAIRED`,
`ANSWER_LANGUAGE_REPAIR_REJECTED:*`, `ANSWER_LANGUAGE_SAFE_FALLBACK`,
`ANSWER_QUALITY_BLOCKED`. Khi bị chặn, limitations có `source_text_quality`.

Kiểm thử: `run.bat test`. Khởi động lại backend sau cập nhật; nếu backend chạy
Kaggle, cập nhật checkout và khởi động lại backend ở đó. Frontend không cần API
Gemini hoặc thay đổi cấu hình. Không cần chạy lại OFFLINE để dùng bước này.

Giới hạn: đây là kiểm tra lỗi có thể nhận diện, không phải bộ kiểm ngữ pháp đầy
đủ hay cam kết chính xác pháp lý. Các quy tắc bảo vệ ngữ nghĩa không chứng minh
hai câu hoàn toàn tương đương; reference audit và human review vẫn cần thiết.
Lỗi OCR không rõ ràng, thiếu chữ hoặc một chữ `l` đứng riêng có thể không bị
phát hiện. Muốn sửa nguồn thật phải đối chiếu PDF/OCR và sinh lại OFFLINE riêng.

Kiểm chứng ngày 2026-10-06: **268/268 repository tests PASS** (15 test chất lượng
câu trả lời mới), frontend lint và build PASS. Đường sửa bằng LLM được kiểm
bằng mocked provider; chưa kiểm chứng inference thực tế trên Kaggle. Báo cáo:
`artifacts/reports/online_answer_quality_validation.json`.
