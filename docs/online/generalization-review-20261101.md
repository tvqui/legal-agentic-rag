# Rà soát ONLINE, dữ liệu và khả năng tổng quát — 01/11/2026

Đã chạy **53 yêu cầu thực tế trên Kaggle v14**: 41 câu đối chứng và 12 câu mới, gồm hội thoại ba lượt. Cả 53 nhận HTTP 200; HTTP 200 không chứng minh câu trả lời đúng hoặc đầy đủ. Đã áp dụng bản sửa **v15 vào D:/data_thô/legal-agentic-rag**; 899/899 kiểm thử ONLINE và 57/57 kiểm thử bộ đo PASS. V15 chưa được đo inference trên Kaggle, chưa commit/push trong lượt sửa này.

## 1. Môi trường và phương pháp

- Giữ Fact Graph, Ontology Graph, Rule Graph; Researcher, Retriever, Auditor, Adjudicator và hậu kiểm. Không thêm đáp án theo ID/câu hỏi, không sửa Gold để khớp output.
- Backend đo: `labor-subissues-v14`; Gemini `gemini-3.5-flash-lite` cho Researcher/reviewer, Ollama `qwen3:8b` cho Auditor/Adjudicator. Giữ giới hạn chung 13 RPM và deadline yêu cầu 180 giây.
- Artifact build `3e43d1d43b966e8100ba187e69a21fcd8f885b2586a1584b58c428c31851877e`, snapshot 2026-09-15. Kiểm trước/sau xác nhận code/config/model/corpus không đổi giữa hai bộ câu hỏi.
- Bộ 41 dùng đúng câu cũ để đối chứng v13/v14. Bộ 12 được soạn mới sau khi phát hiện lỗi ở lượt 41; sau khi dùng tìm lỗi, chúng là tập phát triển, không còn là tập giữ kín độc lập.
- Câu có query_date 2026-09-15 được cố định để đối chứng corpus. Các câu hỏi hiện tại không truyền ngày riêng đã được kiểm tra ngày nhận theo giờ Việt Nam; FRESH-10 dùng 2026-11-01 và cảnh báo chưa xác minh thay đổi sau snapshot.
- Đi qua các nhánh trọng yếu của intake, phân tích, ngữ cảnh, lập kế hoạch, BM25/Dense/RRF/reranker, nguồn/hiệu lực, Graph, Auditor, gói chứng cứ, Adjudicator, hậu kiểm và trích dẫn. Artifact được đối chiếu theo fingerprint và đơn vị truy xuất; chưa duyệt thủ công toàn bộ PDF.

## 2. Kết quả đo thật

| Bộ câu hỏi | Số yêu cầu | HTTP 200 | Có nội dung một phần | Hỏi bổ sung | Ngoài phạm vi | Chưa đủ căn cứ | Trung bình (giây) | P50 | P95 | Chậm nhất |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 41 câu đối chứng | 41 | 41 | 26 | 9 | 2 | 4 | 32.008 | 4.563 | 106.109 | 120.734 |
| 12 câu mới | 12 | 12 | 6 | 2 | 0 | 4 | 74.148 | 83.179 | 138.122 | 144.938 |

Tổng có 32 phản hồi một phần, 11 hỏi bổ sung, 2 từ chối ngoài miền và 8 chưa đủ căn cứ. Câu hộ chiếu mới thực tế chưa bị từ chối ngoài miền sớm; không tính nó là xử lý phạm vi đúng. Câu thiếu thông tin được hỏi lại có thể là hành vi đúng, cần đọc từng câu.

Đã đối chiếu 94 lượt trích dẫn với artifact: ID, URL, tên/số văn bản, Điều/Khoản/Điểm và interval trong metadata không phát hiện sai lệch. Kết quả này không chứng minh văn bản đã được duyệt, nguồn đủ mới hoặc mệnh đề được nguồn suy ra đầy đủ. Bộ kiểm nội dung hiện có cũng có thể bỏ lọt sai sót.

Trên đúng bộ 41, v13 từng có 40 HTTP 200 và 1 HTTP 504; v14 là 41 HTTP 200. Trung bình quan sát từ 64.379 xuống 32.008 giây; P50 từ 65.968 xuống 4.563 giây. Cùng câu/corpus/tên model nhưng cache, tải và quota khác nhau; đây chưa phải phép đo cô lập đóng góp từng thành phần. Độ đúng/đủ pháp lý không được suy ra từ mức giảm thời gian hay trạng thái PARTIAL.

Chênh lệch trung bình giữa HTTP và backend ở hai bộ khoảng 0.701 và 0.709 giây. Các câu chậm chủ yếu nằm ở Auditor, tạo/kiểm/sửa câu trả lời và chờ Gemini; câu đầu còn tải index/model. Giá trị này gồm proxy, truyền dữ liệu và overhead; không phải phép đo thuần đường truyền.

Trace ghi nhận vòng Graph (retrieval_rounds > 0) trong 2/53 yêu cầu (CHAT-04, FRESH-09); chưa chứng minh vòng đó bổ sung căn cứ hữu ích hoặc làm đáp án tốt hơn. Số node ban đầu không tự chứng minh đã mở rộng đồ thị. Các câu tra nguyên văn/đủ căn cứ có thể dừng sớm. Chưa đo lợi ích Fact Graph/án lệ hoặc ablation trong lượt này.

## 3. Nguyên nhân và sửa ở cấp cơ chế

| Nhóm lỗi | Thay đổi v15 | Giới hạn kiểm chứng |
|---|---|---|
| Auditor timeout làm mất cơ hội kiểm tiếp | Giữ ngân sách cho Gemini thứ hai; chuyển cả ứng viên chưa được đánh giá vì transport/context/budget, giữ mọi hard FAIL. Có thể bổ sung nhóm căn cứ còn thiếu khi nhóm khác đã PASS. | Thử bằng fake clock và provider giả lập; chưa đo inference v15. |
| Provider lặp lỗi và mất mã chẩn đoán | Ngừng lặp cùng lỗi transport; giữ OperationBudgetExceeded qua cả Ollama/HTTP/Gemini, mã timeout/HTTP/connection an toàn, không ghi nội dung lỗi thô. | Không bảo đảm mạng/model luôn đáp ứng deadline. |
| Checklist AI dài đẩy nguồn khỏi context | Bỏ annotation phụ khi quá context trước khi chia batch; giữ nguyên toàn bộ source và ancestor. | Nguồn luật thật quá dài vẫn không được cắt/đoán cho vừa. |
| Phủ định ngoại lệ và loại hợp đồng chưa rõ | Một parser dùng chung cho facts, span và xác minh đề xuất Researcher; giữ “không” ngoài cụm “được miễn”, không khẳng định loại hợp đồng từ “chưa biết/có phải”. | Cần đo thêm cách diễn đạt, các vụ việc có nhiều hợp đồng/chủ thể. |
| Từ bỏ dấu va nhau | Phân biệt dấu đã được người dùng nhập, giữ hỗ trợ không dấu và vị trí dấu chính tả hòa/hoà; tránh topic đình công giả từ “định công ty”. | Không phải mô hình hiểu mọi lỗi chính tả. |
| Nhiều yêu cầu/giai đoạn bị gộp | Giữ phần hình thức HĐLĐ sau thử việc; đọc “cho thử” có bối cảnh lao động; giữ đơn vị ngày/tháng; tách mô tả giờ bình thường khỏi yêu cầu tính lương ban đêm. | Chưa bảo đảm mọi tổ hợp đa tác vụ đều đúng. |
| Nhầm phạm vi và dữ liệu | Phân biệt giao dịch bất động sản riêng với nhà ở/thuế trong lao động; cho Researcher đề xuất ngoài miền qua đoạn trích hợp lệ, bảo vệ vấn đề lao động đã nhận diện. Chỉ yêu cầu luật dữ liệu cá nhân khi thực sự nói về dữ liệu của người lao động. | Phân loại ngữ nghĩa có thể sai; câu hỗn hợp vẫn cần đánh giá theo từng phần. |
| Chế tài thay căn cứ điều chỉnh | Không xem lệnh cấm phạt tiền là bảng mức phạt; với đánh giá hành vi thông thường cần quy tắc điều chỉnh thay vì chỉ chế tài. | Norm role là cơ chế chọn nguồn, không là chứng nhận nội dung. |
| Yêu cầu dư các nhóm không thuộc tình huống | Chọn nhóm phép theo dữ kiện cá nhân khi không yêu cầu liệt kê/so sánh mọi nhóm; giữ đủ trường hợp có căn cứ chồng lấn. | Vẫn phải kiểm điều kiện và giả định trong kết luận. |
| Mệnh đề lặp và một mệnh đề sai làm hỏng toàn bộ | Reviewer giữa các batch thấy các mệnh đề trước đã kiểm. Bác riêng semantic PASS vi phạm hard guard hoặc thiếu grounding đính kèm, hạ coverage và giữ phần độc lập đã chứng minh; sửa trong số lượt hiện có. | ID lạ/trùng, trích dẫn bịa và accounting hỏng vẫn bị chặn. Không tự bỏ citation rồi phê duyệt claim. |

Các cảnh báo UNRESOLVED cũ được tính lại theo quyết định cuối, tránh vừa trích một nguồn PASS vừa báo nguồn đó chưa qua kiểm tra. Không chuyển lỗi dịch vụ thành bằng chứng, không đổi corpus, nguồn, hiệu lực hay trạng thái Gold để xóa lỗi.

## 4. Kiểm thử bản sửa và dữ liệu

- 899 kiểm thử ONLINE PASS trên đúng thư mục dự án, gồm 72 kiểm thử mới về phạm vi, dấu/phủ định, đoạn trích dữ kiện, độc lập đa tác vụ, ngân sách, hậu kiểm và lỗi provider. Không phải 899 câu hỏi pháp lý được chuyên gia chấm.
- 57 kiểm thử bộ đo PASS; AST và git diff --check PASS. 49 thay đổi OFFLINE đang stage giữ nguyên theo SHA của staged diff; chưa commit/push/deploy v15.
- Kiểm thử trước sửa đã tái hiện lỗi đường phục hồi, ngân sách và chẩn đoán. Các kiểm thử dùng nguồn tổng hợp và biến thể từ vựng/số liệu; không có ID câu hỏi trong logic trả lời.
- Artifact vẫn 95 tài liệu, 18.855 đơn vị Điều/Khoản/Điểm, 24 CASE; tổng 19.144 đơn vị truy xuất, 53.227 node và 80.559 cạnh. Chốt dữ liệu 15/09/2026.
- Trạng thái chưa hoàn tất: 0/95 nguồn được duyệt theo metadata; 18.855 phiên bản điều khoản chưa duyệt, 28 thay đổi chờ duyệt; 33 mục mơ hồ và 9 mục ngắn cách ly; 68 đơn vị truy xuất có cờ chất lượng chữ trong lần audit trước. Không nhầm 68 đơn vị với số trang trong hàng đợi duyệt ảnh.
- Trong file Bộ luật 45/2019/QH14 riêng, audit trước ghi nhận thiếu 20 số điều so với dải 1–220; bản hợp nhất có số điều tương ứng. Không tự dùng bản hợp nhất muộn hơn để lấp bằng chứng của một giai đoạn quá khứ khi chưa kiểm tra phiên bản và hiệu lực.
- Trang [Bộ luật 45/2019/QH14](https://vanban.chinhphu.vn/?classid=1&docid=198540&pageid=27160&typegroupid=3) xác nhận mốc hiệu lực 01/01/2021; [Công báo văn bản hợp nhất 18](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm) được kiểm tra trang nguồn. Việc mở được trang không tự phê duyệt 95 nguồn hoặc toàn bộ nội dung/interval trong corpus.

## 5. Phạm vi thực tế và phần còn lại

Đã đo tra nguyên văn, hỏi quy định và tình huống, nhiều ý, phủ định/không chắc, thiếu dữ kiện, đính chính/mâu thuẫn/đổi chủ đề, ngày hiện tại, lịch sai, quá khứ, dự báo tương lai, quyền tập thể, đình chỉ công việc, an toàn lao động và đầu vào chứa chỉ dẫn bịa nguồn. Phép đo chỉ dùng một phần tài liệu trong corpus; không chứng minh bao phủ mọi văn bản hoặc mọi câu hỏi lao động.

1. Chưa hoàn thiện so sánh tự động nhiều giai đoạn luật trong một câu. TIME-05 vẫn hỏi lại; TIME-02 chưa giải thích độc lập đầy đủ phần chọn thời điểm trước khi cần thêm dữ kiện đánh giá vụ việc.
2. Reviewer vẫn có thể sai, đòi dư điều kiện hoặc bỏ lọt suy luận; v15 cần được đo thật sau khi triển khai. Các câu dài còn nguy cơ lặp/thừa hoặc dẫn luật mà thiếu áp dụng.
3. Sau snapshot cần kiểm tra thay đổi và chuyên gia duyệt nguồn/hiệu lực, không tự giả định corpus đã cập nhật đến ngày hỏi. Gold vẫn DRAFT, chưa có tỷ lệ đúng luật được chứng nhận.
4. Chưa đo lại Gold120, toàn bộ chế định, ablation hoặc holdout có chuyên gia duyệt. Muốn chứng minh Graph/Auditor/reranker giúp gì phải đo theo vai trò và nhóm câu, giữ cùng cấu hình/corpus/model.

## 6. Đo vòng tiếp theo

Đưa riêng code ONLINE v15, các test, tài liệu này và bộ câu hỏi mới lên origin/main; chạy lại notebook backend. Giữ result_28-10 và model khi đối chứng. `/ready` phải có `labor-subissues-v15`, `auditor_recovery=reserved-independent-fallback-v2`, `notice_fact_polarity=negation-span-v2`.

Không cần chạy lại OFFLINE để dùng các sửa ONLINE trên. Chạy cùng bộ 41 và bộ 12 vào thư mục kết quả MỚI; không ghi đè dữ liệu v14. Chưa thể kết luận các lỗi inference đã hết chỉ bằng unit test local. Sau vòng này cần tập kiểm định mới được chuyên gia duyệt, đánh giá đúng/đủ/dư, từng phần, thời gian áp dụng và căn cứ thay vì tối đa hóa tỷ lệ có nội dung.

## 7. Tệp để xem và sửa sau

- `smoke41/responses.md`, `fresh12/responses.md`: câu hỏi, toàn bộ câu trả lời, thời gian và nguồn.
- `*/responses.jsonl`: request, progress, facts, parts, trích dẫn và trace đầy đủ.
- `*/question_by_question_review.md`, `*/question_review.csv`, `*/audit.json`: nhận xét từng câu và kết quả kiểm metadata.
- `paired_v13_v14.json`: đối chiếu đúng 41 ID; không phải điểm pháp lý.
- `verification.json`, `published_code.json`, `v15_online_changes.patch`: kiểm thử, hash và bản sửa cụ thể.
- `final_preflight.json`: xác nhận phiên bản chạy không đổi; `corpus_audit.json`, `source_quality_audit.json`: audit cùng artifact từ lượt trước, không phải kết quả duyệt mới.
