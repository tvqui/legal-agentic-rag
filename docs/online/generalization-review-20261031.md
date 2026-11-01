# Rà soát khả năng tổng quát và bản sửa ONLINE v14 — 31/10/2026

## Kết luận

Đã xác nhận backend v13 chạy và kết nối được; đo trọn 41 yêu cầu, gồm 31 tình huống mới và 10 câu Gold cũ. Bản đang chạy vẫn có lỗi nội dung, lặp ý và một yêu cầu hết thời gian. Không đủ bằng chứng tuyên bố hệ thống trả lời đúng mọi câu thuộc pháp luật lao động Việt Nam.

Đã áp dụng bản sửa v14 vào đúng dự án `D:/data_thô/legal-agentic-rag`, giữ Fact Graph, Ontology Graph, Rule Graph và các agent Researcher, Auditor, Adjudicator. Bản sửa có **827/827 kiểm thử ONLINE PASS**, gồm 58 kiểm thử mới, và **57/57 kiểm thử bộ đo PASS**. Đây là kiểm thử cơ chế và hồi quy local; **chưa phải kết quả inference v14 trên Kaggle**. Chưa commit/push hoặc đổi backend đang chạy trong lượt rà soát này.

## 1. Phạm vi và phương pháp

- Baseline Git: `dc60381730120a2316bddff9bab2ecfee324587c`; backend `labor-subissues-v13`.
- Backend thực tế dùng Gemini `gemini-3.5-flash-lite` cho Researcher và reviewer; Ollama `qwen3:8b` cho Auditor và Adjudicator. Giữ hạn mức 13 RPM, kiểm nghĩa câu trả lời và các kiểm tra nguồn.
- Corpus build: `3e43d1d43b966e8100ba187e69a21fcd8f885b2586a1584b58c428c31851877e`.
- Chụp `/ready`, nhận diện code/config/model/corpus trước, định kỳ và sau lần đo; chữ ký triển khai không đổi. Chạy tuần tự; lỗi được giữ lại, không thay bằng lần thử thành công.
- Gồm tra cứu, nhiều vấn đề, cách diễn đạt mới, phủ định, ngoại phạm vi, dữ kiện thiếu/chưa rõ, ngày không hợp lệ, sự kiện quá khứ, mặc định ngày hiện tại, dự báo tương lai, hội thoại nhiều lượt/đính chính/mâu thuẫn/đổi chủ đề.
- Không thêm đáp án mẫu vào pipeline, không sửa Gold để hợp output. Những câu đã dùng tìm lỗi là dữ liệu phát triển, chưa phải tập kiểm định độc lập.
- Đã xem các nhánh thực thi trọng yếu của API, phân tích, ngữ cảnh, Researcher, BM25/Dense/RRF/reranker, bộ quản lý bằng chứng, Graph, Auditor, Adjudicator, hậu kiểm và artifact. Không tuyên bố đã chứng minh đúng từng dòng hoặc mọi tổ hợp của toàn bộ repository.

## 2. Kết quả đo thật — baseline v13

| Chỉ số | Kết quả |
|---|---:|
| Tổng yêu cầu | 41 |
| HTTP 200 | 40 |
| HTTP 504 | 1 |
| Trung bình gửi → nhận HTTP | 64.379 giây |
| P50 | 65.968 giây |
| P95 | 169.297 giây |
| Nhanh nhất | 0.641 giây |
| Chậm nhất | 180.657 giây |
| Chênh HTTP so với tổng backend, trung bình trên phản hồi có đủ số đo | 0.712 giây |

Phần chênh cuối không chỉ là mạng: còn serialization, proxy và chi phí ngoài đồng hồ pipeline. Số liệu cho thấy phần lớn thời gian nằm trong backend/model. Không lấy chênh lệch của hai giá trị cực đại khác mẫu để quy cho đường truyền.

| Trạng thái trả về | Số câu |
|---|---:|
| error | 1 |
| INSUFFICIENT_EVIDENCE | 8 |
| PARTIAL_ALLOWED | 25 |
| ABSTAIN | 1 |
| NEED_MORE_FACTS | 6 |

`PARTIAL_ALLOWED` không đồng nghĩa đúng/đủ; `NEED_MORE_FACTS` hoặc `ABSTAIN` có thể là hành vi đúng. Lần này tìm được 85 lượt trích dẫn; kiểm ID, URL, Điều/Khoản/Điểm và khoảng hiệu lực **theo metadata corpus** không phát hiện sai khớp. Tuy nhiên có ít nhất 4 phản hồi bị phát hiện lỗi ngữ nghĩa bởi guard mới: mở rộng kết luận thành tuyệt đối, biến dữ kiện chưa xác nhận thành phủ định hoặc thêm mức phạt thiếu nguồn xử phạt. Chưa có điểm độ chính xác pháp lý do chuyên gia chấm.

Ví dụ tích cực: META-03 tra Điều 1 trong 0,781 giây; TIME-01 chọn Bộ luật 2012 tại 15/12/2020; NEW-05 tách thời gian thử việc và lương theo diễn đạt mới. Ví dụ chưa đạt: NEW-01 hết 180 giây tại Auditor; NEW-06 có câu vượt phạm vi nguồn; META-01 sai về dữ kiện chưa xác nhận; CHAT-06 lạc vào liệt kê thay vì hỏi rõ.

## 3. Thay đổi đã thực hiện

| Nhóm | Nguyên nhân được xác nhận | Thay đổi cơ chế |
|---|---|---|
| Căn cứ tổng quát | Độ phức tạp bị hiểu thành bắt buộc có liên kết dẫn chiếu; từ khóa nếu/trường hợp bị dùng thay điều kiện pháp lý | Không tự đặt dẫn chiếu bắt buộc chỉ vì có nhiều chủ đề. Điều kiện/ngoại lệ thực sự vẫn qua Auditor và yêu cầu phát sinh từ nguồn |
| Dẫn chiếu | Tra ngoại lệ chỉ hỗ trợ cùng điều | Hỗ trợ điểm/khoản/điều khác khi nguồn nói rõ cùng văn bản; giữ đúng edition, không tự gán luật khác |
| Hội thoại | Lượt bổ sung không nhắc lại thử việc bị bỏ sót; mất số ngày cũ; nhãn nội bộ tạo yêu cầu liệt kê giả | Nhận cách bổ sung nhóm công việc; lưu số và đơn vị thử việc có đoạn gốc; dùng mô tả task trung tính; kiểm số với giới hạn đọc từ nguồn |
| Mâu thuẫn | Chỉ một số trường được hỏi xác nhận | Mở rộng tuổi, tình trạng khuyết tật/chưa thành niên, nhóm công việc, thời gian, thỏa thuận và mốc giao kết; đính chính rõ ràng vẫn thay dữ kiện cũ |
| Câu mơ hồ | Tự suy nội dung của “vậy có được như thế không” | Hỏi việc/điều kiện cần kiểm tra trước model; không lấy lời assistant làm sự thật |
| Hiểu câu hỏi | Thiếu diễn đạt ca đêm/giờ đêm, ép dùng một phần lương; tạo task làm thêm từ phủ định | Bổ sung nhận diện khái niệm và phân biệt ngữ cảnh với yêu cầu. Nghỉ bù không tự biến thành yêu cầu liệt kê mọi ngày lễ |
| Dữ kiện thiếu | Câu cá nhân hỏi số cụ thể vẫn truy xuất rất lâu để liệt kê mọi nhánh | Hỏi dữ kiện quyết định trước; vẫn giữ giải thích có điều kiện cho câu hỏi quy định chung |
| Hỏi thừa dữ kiện | Câu hỏi quy định của một nhóm lao động bị coi là đánh giá tình trạng thai sản cá nhân | Không đòi thông tin thai sản riêng cho câu quy định chung; đánh giá cá nhân hoặc hành vi đơn phương của công ty vẫn giữ cổng dữ kiện bảo vệ |
| Dữ kiện chưa rõ | Chưa xác nhận tình trạng bị coi là đã loại khỏi nhóm | Hỏi làm rõ khi cần kết luận cụ thể; chặn claim suy từ chưa biết thành phủ định |
| Số và đơn vị | Researcher chỉ cần thấy số giống nhau trong quote | Kiểm cả vai trò và đơn vị bằng parser; không lấy số ngày báo trước làm tuổi/tháng làm việc; không coi tuổi theo khoảng là tuổi chính xác |
| Thời gian | Ngày tương đối dựa vào đồng hồ lúc xử lý; ngày giao kết đầy đủ chưa tạo dữ kiện chuyển tiếp | Neo ngày vào timestamp tiếp nhận theo múi giờ Việt Nam; tách ngày giao kết/ngày sự kiện; invalid date không thành ngày hôm nay; dự báo thay đổi chưa ban hành được chặn |
| Đồ thị | Không có nguồn PASS thì không còn frontier để tìm quy định làm rõ | Nguồn qua kiểm xuất xứ, còn UNRESOLVED nhưng relevant/support có thể làm điểm tìm kiếm. Không được đưa vào pack/câu trả lời trước khi PASS; FAIL và nguồn lỗi không được dùng |
| Giới hạn đồ thị | Thời gian chuẩn bị hàng đợi chưa bị kiểm | Kiểm thời gian và hủy ngay khi chuẩn bị hàng đợi, giữ giới hạn node/cạnh/hop |
| Nguồn lỗi chữ | Tiêu đề cha hỏng bị phát hiện muộn, nguồn sạch bị lẫn nguồn phụ hỏng | Kiểm cả ancestor trước model; tính chất lượng ngữ cảnh khi chọn nguồn; không gộp đoạn con giống nhau nhưng khác phạm vi cha; không sửa đoán OCR |
| Trích dẫn | Claim thừa nhắc một điều không có trong nguồn làm hậu kiểm chặn cả câu | Kiểm locator của từng claim trước reviewer, bỏ claim không có locator được nguồn hỗ trợ, giữ phần độc lập và vẫn hậu kiểm độ đủ; không miễn kiểm chỉ vì số điều xuất hiện trong câu hỏi |
| Chế tài | Có trích nguồn nghĩa vụ nhưng tự thêm số tiền phạt | Claim mức phạt tiền phải có nguồn chứa căn cứ xử phạt và số tiền; nguồn chỉ nêu nghĩa vụ không đủ. Guard này chưa chứng minh mọi số tiền, hệ số tổ chức hoặc tình tiết đều đúng |
| Tính ổn định | Auditor có thể tiêu hết 180 giây | Ngân sách cộng dồn mặc định 90 giây cho các lần gọi Auditor trong request, tối đa 45 giây mỗi lần, dành 60 giây còn lại cho bước sau. Giữ kết quả đã kiểm; phần chưa xử lý vẫn UNRESOLVED, không tự PASS. Hủy request luôn được truyền tiếp |

Giới hạn thời gian là cơ chế hợp tác với timeout provider; không phải cam kết mọi phép tính native/transport sẽ dừng đúng một mili giây cụ thể. Không tăng điểm bằng cách tắt kiểm nguồn, bỏ hiệu lực, duyệt tự động metadata hoặc ép mọi câu dùng cả ba đồ thị.

## 4. Dữ liệu thực tế và giới hạn pháp lý

| Thành phần | Số lượng |
|---|---:|
| Tài liệu trong summary | 95 |
| Đơn vị Điều/Khoản/Điểm | 18.855 |
| Trong đó ARTICLE / CLAUSE / POINT | 3.355 / 10.023 / 5.477 |
| CASE / ANNEX / FORM | 24 / 91 / 174 |
| Tổng đơn vị truy xuất | 19.144 |
| Node / cạnh | 53.227 / 80.559 |

Bản hợp nhất 18/VBHN-VPQH có đủ số điều 1–220; Bộ luật 2012 có 1–242. Bản 45/2019/QH14 riêng thiếu 20 số điều khi xét tập các số điều hiện có, dù bản hợp nhất có các điều tương ứng. Không tự dùng bản hợp nhất để lấp một giai đoạn lịch sử khi chưa xác minh thay đổi và thời điểm.

Không có text rỗng trong 19.144 đơn vị. Guard hiện tại đánh dấu **68 đơn vị truy xuất** có lỗi OCR/locator đáng ngờ, gồm 13 dấu hiệu từ OCR và 55 dấu hiệu locator; đây không phải 68 trang và không thay thế hàng đợi duyệt trang. Nguồn không bị xóa hoặc sửa chữ; v14 loại các đoạn lỗi khỏi nhánh trả lời và có thể chọn căn cứ sạch khác.

Giới hạn vẫn còn: 0/95 nguồn được duyệt theo trạng thái pháp lý của artifact, 18.855 phiên bản điều khoản chưa duyệt, 28 thay đổi pháp luật chờ duyệt, Gold chưa được phê duyệt, 33 mục mơ hồ và 9 mục ngắn cách ly. Dữ liệu chốt 15/09/2026; câu hỏi ngày hiện tại vẫn phải công khai giới hạn sau ngày chốt. Không tự nâng `PROVISIONAL` thành chứng nhận pháp lý.

## 5. Kết quả kiểm thử và việc chưa thể kết luận

- 827 kiểm thử ONLINE và 57 kiểm thử bộ đo PASS; cú pháp Python và `git diff --check` PASS.
- 58 kiểm thử cơ chế mới có các biến thể từ vựng, dữ kiện số/đơn vị, hội thoại, ranh giới thời gian, nguồn tổng hợp thử nghiệm và một phép thử tích hợp pipeline tìm tiếp qua Graph mà không trích nguồn UNRESOLVED.
- Đã chạy đối chứng local trên source v13 lưu từ Git trước sửa: các kiểm thử mới tái hiện lỗi và thiếu cơ chế. Những API mới chưa tồn tại gây lỗi import trong kiểm thử đối chứng, không được biến thành tỷ lệ sai câu trả lời pháp luật.
- Đo thật 41/41 là **baseline v13**. Chưa có phép đo trước–sau inference v14 cùng model và corpus; không tuyên bố đã giảm latency hoặc tăng độ chính xác từ số unit test.
- Chưa hoàn thiện so sánh tự động nhiều phiên bản theo nhiều mốc thời gian trong cùng một câu. TIME-05 hiện chọn hỏi rõ để tránh áp sai luật, nhưng chưa đáp ứng đủ yêu cầu phân biệt từng giai đoạn.
- Còn nguy cơ lặp ý, trả nguồn thay cho kết luận áp dụng, hoặc reviewer chấm nhầm. Các guard bổ sung giảm những loại lỗi đã tái hiện, không chứng minh mọi diễn đạt mới đều được xử lý đúng.
- Chưa đo lại đủ Gold120 hay bài đo ablation trong lượt này; chưa có tập giữ kín, chuyên gia duyệt hoặc chứng minh lợi ích nhân quả của từng thành phần. Graph nên được đánh giá ở câu cần nối điều kiện/ngoại lệ; không ép chạy ở câu tra nguyên văn.

## 6. Áp dụng và đo tiếp

Không cần chạy lại OFFLINE để dùng các sửa ONLINE này. Giữ artifact result_28-10 hiện tại. Bản sửa local có `labor-subissues-v14`; cần commit/push riêng ONLINE, tài liệu và bộ câu hỏi, sau đó Run All notebook backend lấy `origin/main`. Các 49 thay đổi OFFLINE đang stage đã được giữ nguyên, không gộp vào commit thường.

Kiểm `/ready` phải báo `labor-subissues-v14`, feature `auditor_budget=cumulative-reserved-v1`, `generic_evidence_plan=source-driven-dependencies-v1`; ghi cả fingerprint code/config/model/corpus. Không thay model hoặc corpus giữa hai bản khi so sánh.

Tệp câu hỏi tái sử dụng: `benchmarks/evaluation_suite/datasets/generalization_smoke_41.json`. Không cần frontend để đo API:

```powershell
.venv\Scripts\python.exe scripts/benchmark_online_reliability.py --questions benchmarks/evaluation_suite/datasets/generalization_smoke_41.json --out artifacts/online_benchmarks/generalization_v14 --require-taxonomy labor-subissues-v14 --require-reviewer gemini --require-feature auditor_budget=cumulative-reserved-v1
```

Dùng thư mục kết quả mới, giữ cả lỗi và trace. Sau vòng đối chứng v14, rà soát từng ý trả lời, phần cần hỏi lại, nguồn, hiệu lực và dư thừa; sau đó bổ sung tập câu hỏi giữ kín được người có chuyên môn duyệt. Chỉ công bố mức bao phủ và cải thiện trên phạm vi thực sự đã đo.

## 7. Tệp bằng chứng

- `artifacts/online_benchmarks/generalization_20261031_v13/responses.md`: toàn bộ câu hỏi và phản hồi.
- `question_by_question_review.md`, `question_review.csv`: rà soát từng yêu cầu.
- `baseline_review.json`: đối chiếu trích dẫn và guard nội dung, chưa phải legal accuracy.
- `corpus_audit.json`, `source_quality_audit.json`: số lượng và vấn đề nguồn.
- `preflight.json`, `final_preflight.json`, `deployment_signature.json`: nhận diện bản đo.
- `verification.json`: kiểm thử local v14.

Các file benchmark không chứa `.env`, API key, token, model weights hoặc cache. Artifact OFFLINE và Gold gốc giữ nguyên.
