# Kiểm tra phản biện V4 và sửa ONLINE — 2026-10-10

## Kết luận và phạm vi kiểm chứng

Đánh giá của người góp ý đúng về nhiều lỗi nội dung quan trọng. Tôi đã đọc báo cáo góp ý, đọc JSONL của 285 phản hồi V4, kiểm tra source hiện tại và đối chiếu các locator với retrieval units trong ZIP V8.1. Không lấy HTTP 200, citation hợp lệ hoặc nhãn PARTIAL_ALLOWED làm bằng chứng rằng câu trả lời đúng pháp luật.

Phân bố V4 được xác nhận: 128 PARTIAL_ALLOWED, 121 INSUFFICIENT_EVIDENCE, 31 NEED_MORE_FACTS, 5 ABSTAIN. Đây là trạng thái hệ thống, không phải 128 câu đúng/157 câu sai. Điểm 5,5/10 là nhận định của người góp ý, chưa phải một phép đo accuracy với qrels/đáp án được chuyên gia duyệt.

Lần sửa này ưu tiên điều kiện áp dụng, đủ phần được hỏi và quan hệ claim → nguồn. Không chạy lại pipeline OFFLINE, không sửa ZIP V8.1, production source catalog, Gold approvals hoặc Aura. Chưa có lượt inference mới 285 câu trên backend Kaggle đã cập nhật; không tuyên bố đã chữa khỏi mọi lỗi nội dung chỉ vì unit tests PASS.

## Những nhận xét được xác nhận và điểm cần điều chỉnh

| Câu/nhóm | Kết quả đối chiếu | Cách xử lý trong bản sửa |
| --- | --- | --- |
| NEW-16.1, thời hạn báo trước | Đúng: trộn nghĩa vụ của NLĐ, NSDLĐ, sửa hợp đồng và công việc đặc thù; thiếu bảng thời hạn thông thường đầy đủ. | Kế hoạch NLĐ phải bao phủ các nhánh Điều 35; actor/điều kiện được kiểm trước kết luận. Ngoại lệ và ngành nghề đặc thù phải được phân biệt. |
| NEW-8.5, cơ cấu lương | Đúng: các yếu tố điều chỉnh lương tối thiểu không chứng minh rằng cộng mọi phụ cấp là hợp pháp. | Cần quy định áp dụng mức tối thiểu và cấu phần lương, theo ngày áp dụng; semantic audit phải kiểm kết luận với nội dung thật. |
| NEW-21.1, hình thức kỷ luật | Đúng: đưa hành vi bị cấm đối với người đình công vào danh mục kỷ luật là đảo nghĩa. | Giữ ngữ cảnh cha; yêu cầu đủ danh mục Điều 124, chặn biến cấm thành cho phép. Corpus V8.1 còn thiếu locator của ba mục rất ngắn. |
| NEW-40.1, đình công hợp pháp | Đúng: thiên tai/điều kiện hoãn, ngừng đình công không phải điều kiện làm đình công hợp pháp. | Chuỗi quy định về chủ thể, trình tự, lấy ý kiến, quyết định và đình công bất hợp pháp; kiểm riêng việc đảo điều kiện dừng thành cho phép. |
| NEW-28.1, lao động cao tuổi | Đúng: điều kiện riêng cho công việc nặng nhọc không được biến thành định nghĩa chung. | Tách định nghĩa/tuổi nghỉ hưu khỏi điều kiện sử dụng vào công việc cụ thể; audit phạm vi của từng claim. |
| NEW-11.1, các mức nghỉ; NEW-11.2, thâm niên | Đúng về bỏ sót chế độ và thâm niên. Cần bổ sung: không kết luận vô điều kiện 15 ngày nếu chưa xác lập điều kiện của mức nền và thời gian làm việc trong năm. | Nhận diện nghỉ hằng năm qua nội dung, hỗ trợ số năm viết bằng chữ với source span thật; nối Điều 113 và 114; thiếu dữ kiện thì giải thích có điều kiện. |
| NEW-6.1, nội dung hợp đồng đào tạo | Đúng: nghĩa vụ hoàn trả không thay thế danh mục nội dung hợp đồng. | Yêu cầu đủ các điểm của khoản 2 Điều 62; thiếu điểm a trong retrieval units hiện có phải được phát hiện, không tự điền từ trí nhớ. |
| NEW-2.1, thông tin khi tuyển dụng | Đúng về thiếu recall của cách diễn đạt thông thường. | Bổ sung nhận diện và yêu cầu căn cứ về thông tin khi giao kết; không dùng điều về chấm dứt làm câu trả lời thay thế. |
| NEW-3.2/3.3, ký lại hợp đồng | Đúng về chuỗi quy tắc và ngoại lệ chưa đủ. | Bao phủ các nhánh khoản 2 Điều 20 và các điều được dẫn chiếu; không coi tìm thấy một đoạn là đã trả lời đủ. |
| NEW-18.1, khái niệm chấm dứt trái pháp luật | Đúng: câu hỏi khái niệm không đòi hỏi dữ kiện vụ việc. | Phân biệt EXPLAIN với ASSESS_LEGALITY. |
| NEW-12.1/27.1/39.1/43.1 | Các câu hỏi giải thích quy định có nguồn liên quan trong corpus không nên bị hỏi thêm dữ kiện vụ việc một cách máy móc. | Requirements cụ thể khi có cơ chế được nhận diện; đánh giá các candidate theo batch; không đồng nhất UNKNOWN với điều kiện đã được đáp ứng. |
| NEW-44.1, BHYT; NEW-50.1, dữ liệu cá nhân | Đúng: định nghĩa quan hệ lao động/ứng dụng hợp đồng điện tử không đủ để kết luận về quyền, nghĩa vụ chuyên ngành. | Cần nguồn chuyên ngành trực tiếp. Báo thiếu nguồn khi corpus chưa có, thay vì viện dẫn một nguồn chỉ liên quan từ khóa. |
| M1, chậm lương và đào tạo | Đúng: phải giải quyết quyền nghỉ, ngoại lệ chậm lương và yêu cầu hoàn trả; trả lời riêng đào tạo là thiếu. | Researcher tách nhiều nhiệm vụ; kiểm completeness trên toàn bộ câu hỏi sau khi soạn, không chỉ kiểm các nguồn đã chọn. |
| M3, thực tập có trả công/quản lý | Đúng: dữ kiện đã có không nên bị hỏi lại; tên “thực tập” không tự quyết định bản chất quan hệ. | Trích dữ kiện trả công và quản lý có provenance; giải thích tiêu chí và chỉ kết luận khi nguồn, dữ kiện đủ. |
| M4/M8, kỷ luật và xâm phạm người lao động | Đúng: cần phân tích phần pháp luật lao động, không loại toàn bộ câu hỏi do có yếu tố hình sự; cũng không tự coi cáo buộc là sự kiện đã được chứng minh. | Cho phép tra cứu phần lao động của câu hỏi hỗn hợp; giữ điều kiện/giả định khi đánh giá. Phần ngoài phạm vi không được tự tạo kết luận. |
| M9/M10, thời điểm và văn bản mới | Đúng: quy định riêng về trọng tài thương mại/BHXH không chứng minh nguyên tắc chung. Cần phân biệt nội dung, thủ tục, chuyển tiếp, hồi tố và thứ bậc văn bản; không phải mọi vấn đề đều dùng cùng một ngày. | Thêm yêu cầu nguồn về áp dụng VBQPPL và audit temporal/scope. Corpus thiếu nguồn cần thiết; chưa tuyên bố giải quyết được mọi xung đột thời gian. |

Việc thêm thật nhiều tài liệu hoặc tăng số vòng truy xuất không tự chữa lỗi suy luận. Ngược lại, nhận xét “hỏi bổ sung/từ chối luôn là sai” cũng không đúng: đó là cách xử lý cần thiết nếu dữ kiện quyết định kết luận chưa có hoặc nguồn đang thiếu. Mục tiêu là giảm từ chối nhầm và kết luận nhầm cùng lúc.

Về lương, Điều 4 Nghị định 293/2025/NĐ-CP đặt yêu cầu đối với mức lương theo công việc hoặc chức danh trong điều kiện luật định; không thể chứng minh tuân thủ bằng một đoạn chỉ nói về yếu tố điều chỉnh mức tối thiểu. [Toàn văn trên Cổng Chính phủ](https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-293-2025-nd-cp-quy-dinh-muc-luong-toi-thieu-doi-voi-nguoi-lao-dong-lam-viec-theo-hop-dong-lao-dong-119251110172808433.htm).

Đối chiếu nguyên tắc áp dụng văn bản phải dùng nguồn có phạm vi phù hợp, gồm Điều 58 Luật 64/2025/QH15 và quy định sửa đổi/chuyển tiếp liên quan, thay vì lấy quy tắc riêng của một lĩnh vực khác. [Toàn văn Luật 64/2025/QH15](https://xaydungchinhsach.chinhphu.vn/toan-van-luat-so-64-2025-qh15-ban-hanh-van-ban-quy-pham-phap-luat-119250311155839688.htm).

## Những thay đổi có tính tổng quát

1. Researcher tạo `answer_tasks` từ các phần được hỏi, với đoạn yêu cầu trích đúng từ câu hỏi. Tasks không phải facts hay nguồn pháp lý. Mô hình kiểm độ đầy đủ luôn nhận cả câu hỏi gốc, không chỉ tasks; một task bị bỏ sót không cho phép bỏ luôn yêu cầu đó. Kaggle bật researcher cho các câu trong phạm vi, thay vì bỏ qua toàn bộ câu đã khớp profile.
2. Catalogue là yêu cầu tìm **quy phạm/locator theo cơ chế và thời điểm**, không chứa đáp án, mã câu benchmark hoặc câu hỏi cố định. Có thể bổ sung cơ chế mới; đường phân tích và kiểm ngữ nghĩa vẫn áp dụng cho câu hỏi không có profile. Catalogue hiện không bao phủ mọi quy phạm trong toàn bộ pháp luật lao động và lĩnh vực liên quan.
3. Giữ `ancestor_context` đến evidence pack và giữ nội dung nguồn hoàn chỉnh. Bỏ cắt câu theo điểm từ khóa vì có thể mất phủ định, điều kiện hoặc ngoại lệ. Nguồn/ZIP/SHA/span không bị sửa.
4. Applicability đánh giá nhiều batch trong giới hạn công khai, thay vì chỉ xét nhóm đầu rồi bỏ phần còn lại. EXPLAIN có thể trình bày quy định có điều kiện; ASSESS không được coi điều kiện UNKNOWN là đúng. Khi chưa đủ facts, production có thể trả phần giải thích đã kiểm và hỏi thêm, không kết luận vụ việc vô điều kiện.
5. Sau bước soạn và sửa câu chữ, `answer_review.py` kiểm từng claim: đúng actor, scope, norm polarity, số/ngày, điều kiện, ngoại lệ, hệ quả và nội dung nguồn thực sự chứng minh được. Mỗi verdict cần hạch toán claim; claim SUPPORTED phải có đoạn trích thật từ nguồn được viện dẫn. Checker kiểm riêng tất cả phần câu hỏi và loại nội dung lạc đề.
6. Có tối đa một lượt sửa nội dung trong cấu hình production rồi kiểm lại. Không thể dùng citation đúng để cứu claim sai. Nếu sửa thất bại, chỉ giữ phần đã kiểm được và báo thiếu; auditor lỗi/JSON sai/trích dẫn bịa thì không phục hồi draft chưa kiểm. Mọi đường soạn câu trả lời, kể cả mẫu cố định, đi qua bước này khi adjudication chạy LLM và semantic review bật.
7. Đầu ra thiếu phần câu hỏi giữ PARTIAL_ALLOWED; structural/reference repair không được nâng thành SUFFICIENT hoặc thêm claim chưa qua semantic audit. Câu lặp/không liên quan được yêu cầu loại ở bước review/repair. Đây là kiểm soát bằng mô hình và các guard, chưa phải bằng chứng loại được mọi dạng lặp ngữ nghĩa.
8. Ollama có `num_ctx` rõ ràng và kiểm dung lượng prompt bảo thủ trước request. Review lớn tách kiểm từng claim với nguồn đầy đủ, rồi kiểm coverage; không cắt nguồn để vừa cửa sổ. Một claim vẫn quá lớn sẽ báo lỗi thay vì âm thầm cắt. Semantic review là request riêng nhưng dùng cùng provider được cấu hình; không phải một chuyên gia hay một mô hình thứ hai độc lập.

Các kiểm tra mới không biến nhãn PASS thành xác nhận pháp lý tuyệt đối: mô hình có thể hiểu sai đoạn trích, và dữ liệu hiệu lực/human review vẫn còn provisional. Cần đánh giá lại bằng inference mới và bộ Gold đã duyệt.

## Kiểm chứng thực hiện

- Toàn repository: **415 tests PASS**, gồm 33 kiểm thử mới về semantic review, phạm vi nguồn, batch/context, provenance, repair và tích hợp pipeline. Không có lời gọi live AI trong các kiểm thử này.
- Đối chiếu lại kế hoạch và nguồn cho **285 câu** trên retrieval units của V8.1: phát hiện 12 câu có ít nhất một nhóm locator bắt buộc chưa hiện diện. Đây không phải “12 câu sai”, không phải tỷ lệ đúng của bản sửa và chưa xét hết hiệu lực/authority.
- 16 claim của output V4 bị các guard mới phát hiện dấu hiệu sai trên ngữ cảnh nguồn thật. Đây là tín hiệu cần kiểm, không phải một bảng phân loại pháp lý đã được chuyên gia ký duyệt.
- Báo cáo máy: `artifacts/reports/online_v4_review_source_replay.json` giữ các kế hoạch, phần nguồn thiếu và các claim bị guard phát hiện. Đây là replay phân tích/source coverage, không phải benchmark inference mới.

## Phần dữ liệu chưa thể giải quyết bằng ONLINE

Trong corpus V8.1 **đã có** 293/2025/NĐ-CP và 41/2024/QH15. Không kết luận nhầm rằng thiếu cả hai văn bản đó.

Chưa thấy 91/2025/QH15, 51/2024/QH15 và 64/2025/QH15 trong retrieval units. Cần thu thập bản chính thức, metadata/hiệu lực và các sửa đổi/hướng dẫn liên quan theo ngày áp dụng; kiểm nguồn rồi chạy OFFLINE tạo build đồng bộ. Đây chỉ là ba thiếu hụt xác định qua review này, không phải danh sách tất cả văn bản còn thiếu. Nguồn tham khảo để thu thập: [quy định dữ liệu cá nhân trong lao động](https://xaydungchinhsach.chinhphu.vn/doanh-nghiep-phai-xoa-du-lieu-ca-nhan-nguoi-lao-dong-khi-cham-dut-hop-dong-119250728094419409.htm), [bản Công báo Luật 51/2024/QH15](https://congbao.chinhphu.vn/tai-ve-van-ban-so-51-2024-qh15-43559-53646), [Luật 64/2025/QH15](https://xaydungchinhsach.chinhphu.vn/toan-van-luat-so-64-2025-qh15-ban-hanh-van-ban-quy-pham-phap-luat-119250311155839688.htm).

V8.1: retrieval units của 18/VBHN-VPQH Điều 124 chỉ có đầu điều và khoản 2; thiếu locator khoản 1/3/4. Điều 62 khoản 2 có b/c/d/đ/e nhưng thiếu điểm a. Không thấy các locator tương ứng dưới số 45/2019/QH14. Cần kiểm PDF gốc, parser/quarantine và index: thiếu locator không tự chứng minh PDF thiếu chữ. Không tự tạo câu trích hoặc phê duyệt nguồn để làm gate PASS. [Bộ luật Lao động trên Cổng Chính phủ](https://chinhphu.vn/?docid=198540&pageid=27160).

## Cách dùng và kiểm chứng bản sửa trên Kaggle

1. Chạy `run.bat test` ở repo. Commit/push các thay đổi khi bạn sẵn sàng; tôi chưa tự commit/push.
2. Dừng backend Kaggle hiện tại; cập nhật checkout từ `origin/main`, cài editable dependencies bằng cell cài đặt đang dùng, chạy lại `kaggle/online_remote.py`. Giữ input V8.1 trong lần kiểm thử ONLINE này; không cần chạy OFFLINE để kích hoạt thay đổi code.
3. Gọi `/ready` với header API đang cấu hình. Kiểm `taxonomy_version = labor-subissues-v5` và `quality_policy.semantic_review = true`, `semantic_repair_attempts = 1`, `answer_while_clarifying = true`. `/ready` chỉ xác nhận cấu hình/sẵn sàng, không xác nhận chất lượng pháp lý.
4. Nếu ngrok đổi URL thì cập nhật `frontend/.env`, khởi động lại frontend. Frontend đã có nhãn tiếng Việt cho các trạng thái kiểm nội dung/thiếu nguồn mới. Không cần thêm API Gemini để sử dụng bản sửa.
5. Đo lại 285 câu và thêm câu chưa xuất hiện trong benchmark: thay chủ thể, loại hợp đồng, năm trước/sau ranh giới hiệu lực, điều kiện/ngoại lệ, diễn đạt đồng nghĩa và câu có nhiều vấn đề. Chấm riêng đúng quy phạm, đúng applicability, đủ ý, đủ source và phần không được hỗ trợ; không chấm bằng HTTP/status.
6. Giữ cả JSONL và traces. `semantic_answer_audit` cho biết claim bị loại/phần còn thiếu; `MISSING_REQUIRED_RULE:*` cho biết yêu cầu nguồn chưa được thỏa; `ANSWER_SEMANTIC_REVIEW_ERROR:*` cho biết checker không hoàn tất. Cửa sổ lớn, nhiều batch và review lại có thể tăng thời gian/RAM; bản sửa chưa được đo tài nguyên thực trên T4. Không tăng giới hạn vô hạn để ép trả lời.

Sau khi nguồn mới và cấu trúc được sửa ở OFFLINE, chạy validation/indexes/graph/Aura cùng build và thay input ONLINE. Không trộn graph/indexes cũ với corpus mới. Quyết định human review và Gold vẫn phải do người có thẩm quyền thật hoàn tất.
