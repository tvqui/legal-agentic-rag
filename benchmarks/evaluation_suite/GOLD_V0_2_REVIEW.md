# Rà soát Gold so với result_28-10 — 30/10/2026

## Kết luận và phạm vi

Gold v0.1 có căn cứ khớp ID/nguyên văn nhưng chưa đủ sạch về nội dung để coi là chuẩn: TD003 đặt nghĩa vụ hỏi vùng/ngày quá máy móc; TD012 chỉ có tiêu đề Điều 14; TD002 thiếu nhóm quản lý; TG009/CD007 thiếu một số căn cứ cho điều kiện/nghĩa vụ đã nêu; một số câu thiếu dữ kiện phân nhóm nhưng lại mong một con số cụ thể. 97 câu hỏi ở ngày sau snapshot và ba câu hỏi tương lai làm lẫn việc thiếu corpus với chất lượng trả lời.

Đã đọc đối chiếu từng câu của 100 câu gốc, giữ nguyên ZIP cũ và tạo hai bản:

| Bản | Tổng | Có căn cứ trả lời | Cần hỏi thêm | Căn cứ phân biệt |
|---|---:|---:|---:|---:|
| Gold 100 v0.2, mặc định | 100 | 88 | 12 | 93 |
| Gold 120 v0.2, tùy chọn | 120 | 108 | 12 | 110 |

20 câu bổ sung gồm kỷ luật/nội quy; lao động nữ, chưa thành niên, cao tuổi và nước ngoài; đào tạo; tranh chấp; nghỉ đi đường/việc riêng; nghĩa vụ thông tin; hai câu có hai yêu cầu độc lập. Không tự tăng số lượt QA mặc định.

## Những gì được sửa

- Ngày đo cố định về 15/09/2026, không sửa snapshot hay metadata artifact để giả lập dữ liệu cập nhật tới hiện tại. Câu hỏi cùng đáp án phải được đọc trong mốc ngày này.
- Làm rõ nhóm lao động và điều kiện quyết định trong HD001/HD007/TV004/NP005–NP007/CD001–CD003/CD007–CD008; không suy đoán dữ kiện của người dùng.
- HD009 dẫn đủ các nhóm ngoại lệ về ký/gia hạn hợp đồng; không đồng nhất bảo vệ nhiệm kỳ với quyền ký lại không giới hạn.
- Bổ sung phép tính/điều kiện cho TL005, nghĩa vụ liên quan TG009, căn cứ trực tiếp CD009 và đầy đủ nhóm nghĩa vụ ở CD012. Không yêu cầu câu trả lời lặp nguyên văn đáp án mẫu.
- TD003 hỏi tổng thu nhập gồm thưởng/tăng ca, chưa biết lương công việc: nhãn cần bổ sung dữ kiện có cơ sở. Không lấy 6 triệu đồng làm lý do phải hỏi vùng trong mọi trường hợp. TD009 đổi sang tính số tiền cụ thể khi thiếu giờ/đơn giá; TD012 dùng hai khoản có nội dung thay tiêu đề.
- Giữ 12 tình huống hỏi lại; không gán ANSWERABLE vì tìm thấy điều luật khung. Thay TD013–TD015 trong điểm chính bằng câu có căn cứ; giữ nguyên ba câu gốc trong file thách thức riêng để không mất phép thử từ chối.
- Evidence catalog giữ cả `source_text` và `ancestor_context`. Một điểm/khoản có thể chỉ ghi hành vi; phần cha mới nói đó là hành vi cấm hoặc trường hợp được phép. Hậu chấm được nhận ngữ cảnh cha từ corpus sau inference để tránh đọc ngược ý pháp lý. Không đưa Gold vào prompt tạo câu trả lời.
- Reader kiểm build, retrieval fingerprint, nguyên văn, ngữ cảnh cha, hash văn bản và câu hỏi trùng. Không tự chuyển nhãn thành APPROVED.

Chi tiết trước/sau và lý do sửa từng câu nằm trong `gold_dataset/v0_2_review/change_log.json` và Excel `gold_dataset/Gold_v0_2_review.xlsx`. Có thể dùng Excel để người có chuyên môn duyệt tiếp; chương trình không tự đọc cột người duyệt rồi coi là phê duyệt.

## Cách xác minh

Đối chiếu trực tiếp ZIP result_28-10: các căn cứ đều có trong `artifacts/06_indexes/retrieval_units.jsonl`, đúng văn bản, Điều/Khoản/Điểm, nguyên văn và URL. Bộ kiểm còn nạp artifact bằng `ArtifactStore`, kiểm fingerprint, kiểm tra exact lookup theo ngày và chạy BM25 CPU trên câu hỏi thật. Xem `gold_dataset/v0_2_review/actual_corpus_probe_summary.json` và `per_question_corpus_probe.jsonl`.

Kết quả thực tế: **120/120 câu có đủ nhóm căn cứ qua exact lookup theo ngày**. Trong 108 câu có đáp án của bản mở rộng, BM25 lấy đủ mọi nhóm đã gán cho 78 câu ở K=10, 86 câu ở K=20 và 95 câu ở K=100. Đây là kiểm tra chẩn đoán một lần, có cả lần nạp chỉ mục; không dùng thời gian của nó làm bảng latency chuẩn.

BM25 bỏ sót một căn cứ không phải bằng chứng câu hỏi không có trong dữ liệu. Không sửa câu hỏi theo đáp án model hoặc xóa câu khó nhằm nâng điểm. Kết quả probe này không phải benchmark Dense/Hybrid/Graph hay chất lượng trả lời LLM; không có model/API inference trong lượt rà soát dữ liệu.

Nguồn đối chiếu: [Công báo, VBHN 18/VBHN-VPQH](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm). Khi rà TD003 có đối chiếu thêm [nguồn Chính phủ về Nghị định 293/2025/NĐ-CP](https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-293-2025-nd-cp-quy-dinh-muc-luong-toi-thieu-doi-voi-nguoi-lao-dong-lam-viec-theo-hop-dong-lao-dong-119251110172808433.htm); đáp án sửa không phụ thuộc một con số mức lương ngoài qrels.

## Giới hạn phải giữ khi báo cáo

- Nhãn vẫn DRAFT, nguồn/hiệu lực cấp điều khoản vẫn provisional. Đây là đối chiếu kỹ thuật và nội dung, không thay người duyệt pháp lý.
- Bộ 100/120 vẫn dựa một văn bản hợp nhất. Chưa đại diện tất cả 95 văn bản, mọi văn bản hướng dẫn, mọi thời kỳ, án lệ hay tất cả luật lao động.
- Những câu đã dùng để tìm/sửa lỗi là tập phát triển, không phải hold-out độc lập. Cần một tập giữ riêng và người duyệt độc lập nếu công bố độ chính xác cuối cùng.
- Bộ chính không còn câu thiếu corpus có chủ ý; ba câu này được giữ riêng. Ngoài miền, hội thoại nối tiếp, phủ định/mâu thuẫn và lịch sử cần phép đo riêng, không suy ra đã bao phủ vì có 120 câu.
- Không sửa corpus, không chạy lại OFFLINE, không gọi Gemini/Ollama để tạo đáp án chuẩn. Chưa có số liệu chất lượng LLM sau đổi Gold và chưa commit/push trong lượt này.

## Dùng lại về sau

Chạy `build_corpus_gold.py --help` để xem cách xuất lại từ corpus được cung cấp. Script không dự đoán luật mới: nếu đổi corpus/phiên bản pháp luật, phải đọc lại câu hỏi và đáp án trước khi xuất một phiên bản mới. Không chạy script rồi coi máy đã duyệt thay nội dung pháp lý. Giữ v0.1 và SHA của mỗi bản mới; chỉ so cấu hình trên cùng một Gold SHA.
