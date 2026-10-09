# Đối chiếu đánh giá v3 và hiệu chỉnh ONLINE v4

Đã kiểm tra hai bản đánh giá do người dùng cung cấp, source hiện tại ở commit gốc `8e75e36`, và JSONL gốc `labor_285_v3_20261008T113105Z.jsonl`. Các nhận xét trong tài liệu được coi là giả thuyết cần kiểm chứng. Đợt này sửa ONLINE; không chạy lại OFFLINE, thay corpus, xác nhận reviewer hoặc nạp lại Aura.

## Kết luận về hai bản đánh giá

Phần chỉ ra lỗi nội dung cụ thể là có cơ sở. Tuy nhiên, không thể suy ra điểm chất lượng của toàn bộ 285 câu chỉ từ vài ví dụ, hoặc coi tỷ lệ câu có profile là tỷ lệ đúng pháp lý. Một câu trả lời từ chối vì thiếu bằng chứng và một câu trả lời khẳng định sai là hai lỗi khác nhau.

Các số liệu sau được tính lại từ JSONL gốc:

| Nhận xét | Kết quả đối chiếu |
| --- | --- |
| 199/285 câu không có subissue | Đúng ở v3; chưa có subissue không tự chứng minh câu trả lời sai |
| 56/285 câu dùng profile fast path | Đúng; chỉ bằng khoảng 19,6%, không phải đánh giá độ chính xác |
| LLM tạo câu trả lời là phần chậm chính | Có bằng chứng: trung bình adjudication 18,139 giây; researcher 5,309 giây; seed retrieval + audit 3,028 giây; neural rerank 0,402 giây; graph 0,110 giây. Một số stages chồng thời gian, không cộng tất cả như các khoảng độc lập |
| Median profile nhanh hơn phần còn lại | V3 backend median profile 0,015005 giây, các câu còn lại 33,56589 giây. Hai nhóm có câu hỏi khác nhau; không thể quy toàn bộ chênh lệch cho một thay đổi code |
| JSON chuẩn và trích dẫn đồng nghĩa câu trả lời đúng | Sai. JSON schema chỉ kiểm cấu trúc, các source IDs chỉ kiểm liên kết; vẫn phải kiểm nội dung và applicability |
| Điểm 7/10, 8/10 hoặc phần trăm hoàn thiện | Nhận xét định tính, chưa phải số đo bằng Gold pháp lý đã duyệt |

## Lỗi nội dung đã xác nhận và sửa

| Ca v3 | Lỗi được xác nhận | Xử lý v4 |
| --- | --- | --- |
| NEW-2.2 | Giữ bản gốc bằng đại học bị hiểu thành câu nghỉ việc, dẫn Điều 35/36 | Nhận các cách nói bản gốc/bản chính văn bằng; chọn khoản 1 Điều 17. Mốc “đến khi nghỉ việc” không tự tạo câu hỏi chấm dứt; câu hỏi chấm dứt độc lập vẫn được giữ |
| NEW-4.5 | Khẳng định không có quy định cấm thử việc nhiều lần cho cùng công việc | Bổ sung PROBATION_REPEAT và đoạn mở đầu Điều 25; lịch sử dùng Điều 27 năm 2012. Chỉ kết luận theo điều kiện lần hai thực chất là thử việc cùng công việc; thêm guard chặn khẳng định ngược |
| NEW-4.4 | Chưa nhận diện thử việc 60 ngày | Có profile thời gian, đủ bốn nhánh hiện tại và ba nhánh lịch sử. Nêu điều kiện, hỏi nhóm công việc còn thiếu. Khi nhóm công việc được nêu rõ, so sánh cùng đơn vị; không lấy bằng cấp cá nhân thay yêu cầu của công việc |
| NEW-4.2 | Chỉ nhắc 85%, không áp dụng 80%; còn câu hỏi về hai tháng | Kiểm cả lương và thời gian. So sánh theo đúng mức lương của công việc; “lương chính thức” được nêu như điều kiện cần đối chiếu. Không đổi hai tháng thành 60 ngày |
| NEW-4.3 | Bỏ mất văn bản xử phạt dù câu hỏi yêu cầu | Bắt buộc Điều 26 + Điều 10 khoản 2/điểm c, khoản 3 điểm a và Điều 6 khoản 1 Nghị định 12/2022. Trước ngày 17/01/2022 không dùng nghị định này thay chế tài cũ |
| OLD-3.3 | Ngoại lệ quấy rối đã có dữ kiện nhưng vẫn đòi căn cứ kết luận trái luật | Planner và auditor thống nhất ngoại lệ điểm d khoản 2 Điều 35. Không mặc nhiên kích hoạt Điều 40 khi không có trigger trái luật |
| OLD-3.4 | Bỏ sót dữ kiện ảnh hưởng thực hiện HĐLĐ, hỏi lại không cần thiết | Nhận HĐLĐ/hợp đồng lao động, “đến”/“tới”; giữ kiểm tra phủ định và câu nghi vấn. Nêu điểm g khoản 2 Điều 35, khoản 1 Điều 16 và hệ quả đối với yêu cầu bồi thường do thiếu báo trước |
| OLD-3.5 | Thỏa thuận công ty cho nghỉ sớm bị nhập lại vào đơn phương trái luật | Cơ chế khoản 3 Điều 34; không đòi đủ bộ Điều 39–40 như thể hành vi trái luật đã được xác lập |
| NEW-1.2, NEW-1.5 | Thiếu nhận diện hợp đồng cộng tác viên/tuyên bố không phải HĐLĐ; dẫn nguồn thừa | Nhận diện relationship qualification, ưu tiên khoản 1 Điều 13; giải thích điều kiện theo nội dung thực tế, không chỉ tên gọi |
| NEW-5.2 | Gắn sinh viên thực tập với tập nghề mà chưa rõ quan hệ | Hỏi phân loại quan hệ cả khi câu hỏi dạng EXPLAIN. Làm sản phẩm chưa đủ để áp mọi quy tắc của Điều 61 cho mọi sinh viên thực tập |
| NEW-5.3 | Chỉ trả lời Điều 61, bỏ thử việc và HĐLĐ; researcher gán PROBATION từ tên trong phép so sánh | Profile so sánh cần đủ Điều 13, 24, 26 và các nhánh liên quan của Điều 61. Không gán hợp đồng thực tế từ một danh sách cơ chế đang được so sánh |

Nguồn đối chiếu pháp luật gồm [văn bản hợp nhất Bộ luật Lao động trên Công báo](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm) và [bản ký Nghị định 12/2022 của Chính phủ](https://datafiles.chinhphu.vn/cpp/files/vbpq/2022/01/12-2022-nd.signed.pdf). Đây là đối chiếu để viết rule profiles; không thay thế việc duyệt SHA, nguồn và hiệu lực của từng corpus record.

## Những đề xuất cần điều chỉnh

1. **Không giảm mọi câu xuống 4–6 claims hoặc 6–12 ứng viên.** Câu hỏi nhiều vấn đề cần nhiều căn cứ. V4 chỉ giới hạn tối đa 4 claims, mỗi claim 1.000 ký tự, cho câu một profile đơn giản có tối đa hai nhóm căn cứ; cả schema lẫn parser kiểm giới hạn này. Câu phức tạp giữ giới hạn đầy đủ, và không cắt các locator bắt buộc.
2. **Không xóa toàn bộ legacy slots khi có một profile.** Profile chỉ thay các slot chung của phạm vi nó bao phủ. Câu hỏi thêm tranh chấp/tòa án vẫn giữ yêu cầu bổ sung. Các gate nguồn, hiệu lực, chuyển tiếp, xung đột vẫn hoạt động.
3. **Không tự PASS vì trùng chủ đề hoặc confidence cao.** Bỏ DETERMINISTIC_RELEVANCE_MATCH và DETERMINISTIC_NONCONDITIONAL_MATCH. Căn cứ generic chưa có proof cần auditor semantic, kể cả câu hỏi giải thích. Khi model lỗi, giữ UNRESOLVED; không nâng thành PASS. Exact lookup vẫn hỗ trợ nội dung điều luật được yêu cầu.
4. **Không thêm profile hàng loạt chỉ để đạt một tỷ lệ.** Taxonomy v4 có 37 subissues. Phạm vi bảo hiểm, công đoàn, tranh chấp và các ngành khác vẫn cần mở rộng và kiểm chứng; gán nhãn không tạo ra căn cứ thiếu trong corpus.
5. **Không ưu tiên đổi database hoặc thêm API chỉ từ suy đoán.** Trace v3 chỉ ra điểm chậm chính ở gọi LLM. Luồng có đủ rule chain sẽ bỏ inference; câu khác giữ retrieval, graph và semantic auditor. Không cần API mới cho đợt sửa này.

## Chi tiết kỹ thuật và giới hạn

- `taxonomy.py`: ba subissues mới, nhận diện bổ sung, chung hàm coverage cho planner/researcher/auditor.
- `analysis.py`: nhận dữ kiện HĐLĐ, phủ định, yêu cầu nhóm công việc, câu nhiều yêu cầu; giữ source spans cho các fact đã parse.
- `applicability.py`: relevance và support tách riêng; hard actor/fact exclusions đi trước profile; auditor semantic cho các bằng chứng generic.
- `profile_generation.py` và `generation.py`: trả lời có điều kiện, câu so sánh đủ nhánh, lương/thời gian cùng được xét; giới hạn sinh văn bản thích nghi.
- `claim_validation.py`: guard ngược nghĩa ở thử việc nhiều lần theo từng câu; một phủ định ở câu khác không che lỗi khẳng định sai.
- `pipeline.py`: câu trả lời có quy tắc thời gian được phép kèm câu hỏi nhóm công việc, giữ cảnh báo provisional.
- `verify_review_content.py`: mở rộng từ 15 lên 27 câu thực tế; bật researcher/adjudicator Ollama và applicability hybrid, rồi dùng tripwire để chứng minh các ca đã đủ căn cứ không gọi inference/BM25/dense/reranker.

Ba tests cũ đã được điều chỉnh về contract: fixture nghỉ phép phải có đúng vị trí nguồn, kiểm lỗi batch IDs dùng một candidate không thuộc hard exclusion, và deterministic-only generic không còn được phép trả lời chỉ từ lexical relevance. Không xóa các kiểm tra an toàn hoặc hạ threshold của reference audit.

Reference audit dựa trên liên kết, locators, proposition và một số guard ngữ nghĩa còn giới hạn. Kiểm overlap từ vựng không phải phép chứng minh pháp lý phổ quát. Các câu nằm ngoài profile vẫn phụ thuộc mô hình, nguồn và việc duyệt chuyên môn. Chưa có số đo mới về accuracy toàn bộ 285 câu hoặc retrieval recall trên Gold được duyệt.

Khi bổ sung dữ kiện cho một câu đang được hỏi thêm, nên gửi lại cả câu hỏi gốc cùng phần bổ sung. Chưa xác nhận toàn bộ các tình huống hội thoại nhiều lượt chỉ bằng câu trả lời rất ngắn.

## Kiểm chứng

- Trước khi sửa, 26 tests mới tái hiện 22 failures và 1 error (tính cả subtests). Sau đó mở rộng thành 37 tests với biến thể, phủ định, thiếu nguồn, ngày lịch sử và ranh giới model.
- Toàn repository: **382/382 PASS**, thời gian của lần chạy cuối nằm trong `artifacts/online_benchmarks/review_v4_tests.log`.
- Replay 27 câu gốc: **27/27 PASS**, giữ câu hỏi nguyên văn và hash baseline; không đổi ZIP V8.1.
- Provider modes ở replay: `researcher=ollama`, `applicability=hybrid`, `adjudication=ollama`; `forbidden_calls=[]`.
- Kiểm tra compileall và git diff --check được chạy trước bàn giao.

Replay có JSONL đầy đủ, CSV, Markdown từng câu và summary ở `artifacts/online_benchmarks/review_v4_20261009_full.*`. **Thời gian local không gồm startup/mạng/GPU/LLM và không được so trực tiếp với benchmark Kaggle v3.** Tham số đo cụ thể lấy từ summary mới nhất.

## Đưa lên Kaggle và kiểm thử tiếp

1. Commit và push các thay đổi ONLINE/tests/docs lên GitHub. Không đưa `.env` hay secret vào Git. Code hiện được sửa local; backend đang chạy không tự nạp nó.
2. Dừng cell backend đang giữ Ollama/API/tunnel theo notebook. Không mở backend thứ hai trên cùng port.
3. Chạy cell cập nhật checkout mới nhất (`git fetch --prune origin`, `git checkout --detach origin/main`) và cell khởi động backend của notebook hiện tại. Nếu checkout có thay đổi chưa lưu, xử lý chúng trước; không reset/xóa bừa.
4. Kiểm `/ready`: `taxonomy_version=labor-subissues-v4`, đúng build V8.1 và các mode theo cấu hình Kaggle. Nếu tunnel đổi URL, cập nhật `frontend/.env` và khởi động lại Vite.
5. Chạy 27 ca đã sửa trước; sau đó đo lại 285 câu từ đầu, lưu câu hỏi, trả lời, thời gian client, stage timings, source IDs và các lỗi. Đó mới là số đo tốc độ mới trên Kaggle.

Không cần chạy lại OFFLINE, embeddings, BM25 hoặc Aura để dùng các sửa đổi này. Không cần thêm API AI hay chỉnh key vào `.env` cho đợt này. Không tuyên bố ONLINE production-ready hoặc dữ liệu được chuyên gia duyệt chỉ vì tests/replay PASS.
