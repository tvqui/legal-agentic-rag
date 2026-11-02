# Đánh giá bộ dữ liệu result_28-10 — ngày 28/10/2026

## Kết luận để quyết định chốt dữ liệu

**Nên giữ result_28-10 làm bản dữ liệu nền cho giai đoạn hoàn thiện, kiểm thử ONLINE và báo cáo cuối kỳ. Chưa đủ bằng chứng để gọi đây là bộ dữ liệu pháp lý hoàn thiện hoặc đã được kiểm duyệt đầy đủ.** Bản này chạy được về kỹ thuật, có cải thiện đo được; vẫn còn thiếu ở chất lượng nguồn, trích xuất, hiệu lực, AI và Gold. Việc có đạt yêu cầu chấm điểm cuối kỳ phụ thuộc tiêu chí giảng viên, phạm vi đã công bố và kết quả kiểm thử cuối, không thể suy từ một nhãn PASS.

Không cần xóa dữ liệu hoặc chạy lại toàn bộ OFFLINE ngay. Giữ một bản bất biến, hoàn tất các bước duyệt/đo có mục tiêu rồi mới quyết định cần rebuild hay chỉ tiếp tục AI. Mọi bản đã dùng trong báo cáo phải ghi SHA và ngày snapshot; kết quả không thay thế thẩm định pháp lý.

## Phạm vi đã kiểm tra trực tiếp

- Đọc notebook đã chạy `offline-27-10.ipynb`: đúng revision `20261027-source-links-v3`, Quality Refresh bật, AI-resume tắt, bật Aura, tối đa 250 provisions và không có cell output lỗi. Chạy thành công không tự chứng minh nội dung đúng.
- Kiểm CRC cả ZIP kết quả cuối và technical checkpoint: đạt, không member trùng, không đường dẫn thoát thư mục. Không sửa hai ZIP đầu vào.
- Đọc validation, AI quality, page quality, summary, Neo4j/dense; tính lại kiểm tra link bằng config hiện tại, so với bản result_14-10.
- Chạy công cụ pin/ArtifactStore thật trên ZIP mới: **compatible=true**, kiểm build graph/Neo4j/fingerprints đạt. Đây là kiểm tra tương thích dữ liệu; chưa chạy lại trả lời 100 câu hay gọi LLM, GPU/Aura trong lượt kiểm tra này. Aura được xác nhận qua báo cáo của job Kaggle, không phải kiểm live lần thứ hai.
- Dựng hồ sơ đối chiếu nguồn/hiệu lực/Gold trên ZIP mới trong thư mục evidence; không tự tạo phê duyệt.

## So sánh với result_14-10

| Hạng mục | result_14-10 | result_28-10 | Đánh giá |
|---|---:|---:|---|
| Tài liệu | 95 | 95 | Cùng document IDs và SHA của file nguồn; chưa bổ sung corpus mới |
| Mục Điều/Khoản/Điểm | 18.871 | 18.855 | Chênh lệch 16 mục đều thuộc NĐ 140/2018/NĐ-CP sau refresh extraction/structure; cần đối chiếu phần sửa, không tự suy ít hơn là mất dữ liệu hay tốt hơn |
| Bản án/án lệ | 24 | 24 | Tập còn nhỏ, chưa thể khái quát toàn bộ tranh chấp lao động |
| Checklist AI hoàn tất theo kiểm tra nguồn | 6/250 | 128/250 | Tiến bộ rõ; 51,2% của 250 mục được chọn, không phải 51,2% toàn corpus và không phải độ chính xác pháp lý |
| Bản án AI hoàn tất | 0/24 | 0/24 | Chưa hoàn thành; 18 bản có kết quả AI một phần, 6 dùng fallback |
| Trang cần đối chiếu | 174 | 173 | Giảm 1, chưa phải giải quyết hết OCR |
| Thay đổi pháp luật chờ duyệt | 25 | 28 | Cần kiểm thêm; tăng số phát hiện không tự chứng minh chất lượng giảm |

Đầu ra hiện có 3.355 mục ARTICLE, 10.023 CLAUSE, 5.477 POINT, tổng 18.855; đây là tổng số node ở các cấp phân cấp, có quan hệ cha–con, không phải 18.855 điều độc lập. Có 19.144 đơn vị truy xuất, 16.114 diagnostic items, 53.227 node và 80.559 cạnh. Không lấy tổng node hoặc số checklist làm thước đo độ đúng.

## Phần đã đạt

Registry, structure, graph, indexes đều PASS trong **ZIP cuối**. Validation ghi không còn lỗi provenance và không có ERROR pipeline; Neo4j khớp build, dense BGE-M3 có 19.144 vectors, 1.024 chiều, kiểm truy vấn dense/BM25 đã đạt trong job. Công cụ pin ONLINE hiện tại cũng xác nhận tương thích.

84/95 tài liệu có URL cấu hình và **84/84 khớp** qua registry, resolved source catalog, graph Document và retrieval units; không có mismatch với source_catalog.yaml hiện tại. Đúng hash cấu hình đã nhập Excel. Còn 11 bản án thiếu URL cấu hình. Đã điền link và link đồng bộ là hai kiểm tra kỹ thuật; không tương đương nội dung nguồn/hiệu lực đã được chuyên gia xác minh.

**Dùng `vn_labor_results.zip` làm dữ liệu ONLINE.** Technical checkpoint là mốc trước khi nạp Aura/kết thúc AI: report bên trong có `indexes=false`, Neo4j chưa chứng nhận build trung gian; không dùng file này thay ZIP kết quả cuối. Nhãn đó không phủ định ZIP cuối đã PASS.

## Những điểm chưa đủ để tuyên bố hoàn thiện

| Phần | Bằng chứng thực tế | Việc cần làm trước khi khẳng định đã chốt chất lượng |
|---|---|---|
| Nguồn | 84 link có cấu hình, 11 còn thiếu; 0/95 hồ sơ đạt quy trình source review được ghi nhận | Đối chiếu số hiệu, toàn văn/file, nguồn; ghi reviewer và bằng chứng thật. Việc Excel đã xác nhận liên kết chưa thay cho toàn bộ quy trình này |
| Trích xuất | 3.116 trang: 2.927 PASS, 16 REVIEWED, 173 REVIEW_REQUIRED, 0 ERROR | Duyệt ảnh các trang còn nghi ngờ, nhất là sai số/ký tự và sửa trang 13 NĐ 140/2018. 33 cảnh báo nhóm mơ hồ + 9 nhóm quá ngắn; audit đếm 847 hàng cách ly thuộc 534 nhóm vị trí, không phải chỉ có 42 hàng |
| Hiệu lực | 28 thay đổi chờ duyệt, 18.855 phiên bản điều khoản chưa được duyệt; legal-ready=false | Kiểm nguồn, quy định sửa đổi/chuyển tiếp và khoảng hiệu lực; không tự gán approved từ ngày của văn bản |
| AI checklist | 128/250 complete; 71 partial nằm trong 122 mục chưa complete, 16 mục skipped | Sửa/kiểm phần quote/nguồn không khớp, tiếp tục phần chưa hoàn tất. Không cộng partial và fallback như hai nhóm độc lập; không nâng số lượng trước khi xem nguyên nhân |
| AI bản án | 0/24 complete; 18 partial, 6 fallback | Đối chiếu trích đoạn và tiếp tục phần thiếu; hoàn tất nếu báo cáo tuyên bố Fact/Ontology được AI xử lý đầy đủ |
| AI chung | AI_DEGRADED; AI_STAGE_BUDGET_EXHAUSTED và AI_ACCOUNTING_SOURCE_MISMATCH xuất hiện | Không chỉ tăng timeout hoặc chạy lại nguyên job: một số phần thiếu vì giới hạn thời gian, một số do output không khớp nguồn bị loại. Việc loại là kiểm soát chất lượng, không nên tắt gate |
| Gold/đánh giá | 0 APPROVED, NOT_EVALUATED; 100 câu có nhóm căn cứ tìm thấy trong build mới nhưng vẫn DRAFT | Rà soát đáp án/căn cứ, duyệt theo quy trình, đo retrieval và ONLINE trên đúng ZIP mới; báo cáo cả từ chối/lỗi/độ đủ thay vì chỉ trích dẫn |
| Phạm vi thời gian | Mốc ONLINE đang khai báo 15/09/2026; corpus file nguồn không đổi | Ngày chạy 28/10 không chứng nhận luật đã cập nhật đến 28/10. Muốn giữ snapshot cũ phải công bố rõ; nếu yêu cầu pháp luật hiện hành đến ngày nộp, rà soát phần thay đổi sau cutoff |

100 câu Gold có ngày tra cứu sau mốc 15/09/2026; đây là cờ cần xem lại tính phù hợp thời gian, không tự khẳng định cả 100 đáp án sai. Audit cũng giữ 9 câu có ghi chú quan ngại từ lần review trước. Căn cứ tìm thấy trong corpus không chứng minh đáp án đầy đủ hoặc đúng phiên bản.

## Thứ tự làm tiếp để tránh chạy lặp nhiều giờ

1. **Giữ nguyên ZIP cuối mới + SHA, code revision và báo cáo.** Dùng làm baseline cho các thử nghiệm; giữ result_14-10 để đối chứng. Không ghép graph/index giữa hai build.
2. Upload ZIP cuối 28-10 vào Input backend, bỏ/gỡ Input kết quả cũ nếu notebook auto-detect yêu cầu đúng một dataset, chạy cell pin artifact và backend. Xem compatibility, legal status và cảnh báo; không bỏ pin/hash để ép chạy.
3. Chạy lại Gold100 và các câu trọng yếu về thời điểm, nhiều yêu cầu, thiếu dữ kiện, ngoại lệ và hội thoại. Kết quả benchmark cũ không được gán cho build này. Kiểm tra thật câu trả lời/căn cứ; không dùng technical compatible như bằng chứng QA đúng.
4. Ưu tiên duyệt nguồn, hiệu lực và các trang của những văn bản cốt lõi cho phạm vi bài nộp. Nếu chưa xử lý hết 11 bản án hoặc trang nghi ngờ, công bố phần chưa xác minh, tránh dùng chúng để khẳng định đã có evidence được duyệt.
5. Sau khi xem lỗi AI mới, tiếp tục **AI-resume** từ đúng build mới để hoàn tất phần thiếu nếu giữ nguyên nội dung/cấu hình. Nếu sửa OCR hoặc metadata/hiệu lực, dựng lại các phần phụ thuộc và nạp Aura, đo lại trên build mới. Không chạy Quality Refresh toàn bộ chỉ để chữa nhãn AI_DEGRADED mà chưa xử lý nguyên nhân.
6. Chỉ gọi là bản đã kiểm duyệt hoàn thiện khi các quy trình duyệt và đánh giá tương ứng đã có bằng chứng. Nếu bài cuối kỳ là prototype nghiên cứu, có thể nộp baseline này cùng đánh giá thực nghiệm và giới hạn nêu trung thực; quyết định đạt tiêu chí cuối cùng thuộc giảng viên.

## Định danh để tái lập

- SHA-256 ZIP cuối: `469ac1ef01f527afe2b2176bdae85abbdd59a76037c07de6d16f4d1bb34316fd`.
- Build graph: `3e43d1d43b966e8100ba187e69a21fcd8f885b2586a1584b58c428c31851877e`.
- Snapshot source config: `095b1d16b4adf866cf056f08c9804c2da2b2fc4f9b4fceae6107d04158073b35`.
- Job OFFLINE kết thúc UTC 27/10/2026 21:41, tương đương 04:41 ngày 28/10/2026 giờ Việt Nam. Thời gian runner xấp xỉ 6 giờ 5 phút, không phải độ trễ ONLINE.

Hồ sơ kiểm tra được lưu cùng lượt review: `deep_check.json`, `online_pin_check.log`, `evidence/summary.json`, các báo cáo gốc trích từ ZIP. File `online_technical_check.yaml` chỉ phục vụ kiểm tra, không tự thay cấu hình backend đang chạy.
