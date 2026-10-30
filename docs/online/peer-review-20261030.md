# Đối chiếu báo cáo ONLINE và bản sửa v12 — 30/10/2026

## Kết luận kiểm duyệt

Báo cáo có hai lỗi tái hiện đúng: lấy ngày ký hợp đồng thay ngày sa thải và cho tham chiếu Điều/Khoản đi qua cổng phạm vi dù hỏi luật hình sự. Kiểm tra thêm xác nhận hợp đồng dân sự cũng có thể bị nhầm miền; một task Researcher sau task thứ 12 bị bỏ. Bộ tái hiện ban đầu có 5 phép thử: 4 FAIL, 1 PASS; câu đảo thứ tự ngày đã đúng từ trước, cho thấy không nên kết luận mọi câu nhiều ngày đều sai.

Các nhận xét về dữ liệu/Gold phù hợp với artifact result_28-10 và Gold120 v0.2: 95 tài liệu, 19.144 đơn vị và vector, 53.227 node, 80.559 cạnh; Gold120 gồm 108 câu có căn cứ, 12 câu cần hỏi thêm và 110 căn cứ phân biệt. Đây vẫn là dữ liệu provisional và tập phát triển DRAFT, không phải hold-out hoặc chuẩn được chuyên gia duyệt. Không sửa cờ nguồn/hiệu lực/Gold để tạo PASS pháp lý.

## Đánh giá từng đề xuất

| Nhận xét | Kết luận sau đối chiếu | Hành động |
|---|---|---|
| P0: ngày đầu tiên được chọn thay ngày sự kiện | Đúng, tái hiện được; sửa mẫu sa thải nhưng cần tổng quát theo sự kiện | Thêm vai trò ngày có span nguồn, ưu tiên sự kiện/hiệu lực rõ ràng; nhiều sự kiện khác ngày chưa gắn được một mốc thì hỏi lại |
| A1: có Điều/Khoản là vượt cổng phạm vi | Đúng, tái hiện hình sự và dân sự | Tham chiếu không còn quyền bỏ qua kết luận ngoài miền; nhận diện văn bản ngoài miền và tránh coi mọi hợp đồng là hợp đồng lao động |
| A2: quá 12 task mất kiểm tra riêng | Đúng; không mất nguyên câu nhưng mất đơn vị kiểm tra, merge còn bỏ task mới | Giữ toàn bộ task nội bộ/parts; giới hạn từng batch sinh và kiểm độ đủ, không cắt danh sách gốc |
| A3: Adjudicator dựng lại kế hoạch làm rơi bổ sung | Đúng với prompt LLM; một số đường profile còn có thể đi tắt khi thêm task | Pack mang kế hoạch đã xác nhận; prompt có đầy đủ task/nhóm căn cứ; tắt profile shortcut khi còn task bổ sung chưa được profile bao phủ |
| A4: cảnh báo stale không chứng minh hiện hành | Đúng; cảnh báo cũ là trung thực nhưng chưa đủ rõ ở kết luận | Báo ngày chốt ngay trong câu trả lời khi thiếu coverage; kiểm theo từng nguồn được dẫn; không coi văn bản chưa có ngày hết hiệu lực là đã được cập nhật đến hôm nay |
| B1: top-k có thể thiếu nhóm căn cứ | Đúng khi hạn mức nhỏ hơn số nhóm; không có thuật toán nào giữ đủ mọi nhóm trong hạn mức quá nhỏ | Phân bổ nhóm theo vòng giữa các yêu cầu, giữ báo cáo phần chưa đại diện; không tăng hạn mức lặng lẽ |
| B2: profile loại mọi hỗ trợ ngoài vị trí đã biết | Đúng khi có task độc lập ngoài profile; không đúng nếu coi mọi đoạn liên quan đều phải đưa vào | Giữ tối đa hai nguồn đã qua Auditor cho mỗi task chưa có profile khi còn chỗ; đây là xếp ưu tiên, không phải chứng minh task đã hoàn tất |
| B3: Auditor bỏ ứng viên vượt batch | Đúng là chưa kiểm hết; code cũ đã ghi UNRESOLVED, không phải tự chứng nhận sai | Ưu tiên nhóm căn cứ còn thiếu trước bản trùng, giữ trạng thái UNRESOLVED và giới hạn model calls |
| B4: điều nhiều khoản vượt hạn mức | Rủi ro đúng; `resolve_article_requirements` vốn đã giữ đầy đủ các nhánh và phần thiếu | Giữ cách này, phân bổ công bằng hơn và báo `REQUEST_SCOPE_EXCEEDS_EVIDENCE_BUDGET`; không giả vờ đủ bằng cách cắt yêu cầu |
| C1: nhiều lần encode/retrieval | Có căn cứ code; không có số liệu chứng minh mức chậm end-to-end | Khử trùng lặp query bằng Unicode/khoảng trắng/case, không xóa phủ định/ngày; batch Dense; task bị hoãn được tìm tiếp theo chỗ thiếu |
| C2: đặc trưng Graph tính lại | Đúng, có thể đo tại chỗ | Tính query terms/quan hệ một lần mỗi vòng; cache đặc trưng node trên artifact bất biến, không cache ngữ nghĩa câu hỏi giữa các request |
| C3: byte khác token | Đúng là có thể chặn bảo thủ, nhưng gọi nó là chứng minh vượt context thật thì sai | Dùng chung một hàm tính budget; chỉ nới khi có tokenizer khai báo đúng model. Thiếu tokenizer vẫn giữ cận byte, không chia byte cho 4 để đoán |
| C4: nhiều model steps gây chậm | Đúng về khả năng; không đủ để kết luận nên bỏ Reviewer ở câu thông thường | Giữ direct/literal, các profile đúng vai trò và hậu kiểm bắt buộc; batch task/coverage, không tự duyệt bằng lexical match hoặc đáp án mẫu |
| C5: FAISS nạp qua bytes/copy | Đúng về bản sao RAM; `read_index` không đảm bảo nhanh trên mọi đường dẫn | Dùng native I/O khi hỗ trợ; giữ fallback cho Windows Unicode. Không khởi tạo thêm pipeline/worker và không bật cache truy xuất đại trà |
| Cần hold-out và benchmark thật | Đúng | Ghi riêng việc còn lại; không gọi test local, Gold phát triển hoặc phép đo CPU là chứng nhận chất lượng pháp lý |

## Các thay đổi đã thực hiện

**Đúng thời điểm/phạm vi.** `event_time.py` gắn ngày với ký hợp đồng, thông báo, quyết định, sự kiện, mốc áp dụng, ngày sinh và ngày ban hành văn bản. Quote/vị trí ngày được giữ trong trace. Ngày API chỉ định vẫn được tôn trọng; không biến ngày tra cứu thành một sự kiện đã xảy ra. Các câu nhiều timeline chưa giải được thành một khoảng pháp luật an toàn phải hỏi lại, không dùng ngày đầu cho tất cả.

**Kế hoạch thống nhất.** `EvidencePlan` đi qua pack tới Adjudicator; task không bị gộp/xóa khi vượt 12. Mỗi lượt sinh tập trung tối đa 8 task, Reviewer kiểm độ đủ theo các đợt 8 task rồi hợp nhất. Claim grounding, dependency, phiên bản, nguồn và accounting vẫn được kiểm. Hết thời gian/context/batch phải lộ phần thiếu, không biến phần chưa kiểm thành đúng.

**Đủ bằng chứng có mục tiêu.** Các slot có nhiều nhóm không được độc chiếm hết lượt ưu tiên trước slot khác. Auditor dùng cùng kế hoạch để ưu tiên. Task vượt lượt BM25 đầu được tìm tiếp nếu chưa có nhóm căn cứ hoặc chưa có profile; tất cả nguồn bổ sung đi qua lọc ngày, authority, source audit và applicability. Nguồn hỗ trợ ngoài profile chỉ được đưa vào khi có task tương ứng và đã được kiểm; hoàn tất nội dung vẫn do hậu kiểm xác nhận.

**Độ mới.** Với kết luận có trích dẫn, `freshness.py` xem mốc ngày cuối của truy vấn và coverage của từng quy định được dẫn. Nếu chưa chứng minh cập nhật, câu trả lời có ngày chốt rõ ràng, giới hạn `FRESHNESS_UNVERIFIED`, trạng thái tối đa PARTIAL_ALLOWED; cấu hình không cho partial sẽ không trả kết luận chưa xác minh. Không sửa artifact để coi nó đã mới hơn. Trong snapshot cũng không đồng nghĩa đã duyệt pháp lý.

**Hiệu năng.** Dense batch giữ từng danh sách kết quả trước RRF. Query khác nhau về phủ định/thời gian không bị gộp. Node features được cache theo artifact bất biến; đặc trưng truy vấn/quan hệ vẫn riêng mỗi vòng. FAISS đọc trực tiếp trên đường dẫn phù hợp; Windows có Unicode tiếp tục dùng cách cũ. Cache truy xuất theo request vẫn mặc định tắt.

## Bằng chứng hiệu năng và giới hạn

Đo 5 lần trên artifact thật, CPU local, OS cache ấm; không có Gemini/Qwen/BGE inference. Graph đo một vòng fixed traversal, không tính khởi tạo adjacency; cùng 43 cạnh được xét và 25 node được thêm.

| Đo riêng | Trước, median | Sau, median | Đối chiếu kết quả |
|---|---:|---:|---|
| Một vòng Graph mẫu | 9,908 ms | 7,020 ms | Điểm, thứ tự nguồn và đường đi giống nhau |
| Nạp FAISS 19.144 vector, 1.024 chiều trên đường dẫn ASCII | 158,426 ms | 46,102 ms | Top-20 giống nhau trên 10 vector tái dựng |

Không dùng các tỷ lệ này để tuyên bố tổng thời gian trả lời giảm tương ứng. FAISS chủ yếu ảnh hưởng khởi động; local Windows ở đường dẫn Unicode còn dùng fallback. Cache node có thể dùng thêm RAM; chưa đo peak RAM. Batch Dense đã kiểm bằng FAISS thật và encoder fixture; chưa đo Recall@K bằng BGE thật sau thay đổi. Chưa đo latency p50/p95, RPM, số model calls hay chất lượng câu trả lời end-to-end trên bản mới.

Bằng chứng máy: [structural_measurements.json](peer-review-20261030/structural_measurements.json), các test `test_peer_review_contracts.py`, `test_peer_review_mechanisms.py` và log kiểm thử trong cùng thư mục audit. Các kiểm thử model dùng mock, không phải chứng nhận model sẽ trả lời đúng.

Kiểm tra cuối trên chính thư mục dự án: **740/740 kiểm thử ONLINE và 55/55 kiểm thử bộ đo PASS**, cú pháp Python và `git diff --check` đạt. 49 đường dẫn OFFLINE/config đã stage từ trước được giữ nguyên; không commit/push. Chi tiết ở [verification.json](peer-review-20261030/verification.json). Không lấy thời gian chạy test suite làm latency trả lời.

## To-do theo ưu tiên

- [x] P0: tái hiện và sửa sai phạm vi, sai ngày xét sự kiện; bổ sung phản ví dụ đảo thứ tự, hợp đồng dân sự và ngày API chỉ định.
- [x] P1: giữ task/parts; truyền kế hoạch xác nhận; chia lượt sinh/hậu kiểm; không để profile bỏ qua task bổ sung.
- [x] P1: ưu tiên nhóm căn cứ, task còn thiếu và nguồn hỗ trợ; không nới quyền PASS hay xóa gap.
- [x] P1: giới hạn kết luận theo snapshot/coverage của nguồn; giữ cờ provisional.
- [x] P1/P2: khử query trùng, Dense batch, Graph features, native FAISS có fallback; đo CPU riêng và kiểm kết quả tương đương trên mẫu.
- [x] P1: thống nhất accounting và hỗ trợ tokenizer local đúng model, vẫn giữ cận an toàn khi chưa có.
- [ ] P1 trước khi bật tokenizer thật: cung cấp bản tokenizer cùng model/revision với Ollama; đối chiếu token thực tế và full-source batch. Hiện chưa có bằng chứng khớp tokenizer của model đang chạy nên chưa tự bật.
- [ ] P1 nghiệm thu sau triển khai: chạy Gold120 cùng snapshot/model/protocol và tập câu mới, đo groundedness, độ đủ, thời gian từng bước, p50/p95, timeouts, số model calls và Recall@K. Không resume kết quả từ code cũ.
- [ ] P1 đánh giá độc lập: người duyệt tạo/giữ riêng tập chưa dùng chỉnh code; duyệt nguồn/hiệu lực và Gold trước khi công bố độ chính xác pháp lý cuối cùng.
- [ ] P2 mở rộng thực nghiệm: suy luận đồng thời nhiều mốc áp dụng khác nhau cho từng task trong cùng câu hỏi. Bản hiện tại chọn sự kiện rõ ràng hoặc hỏi làm rõ; chưa tuyên bố giải quyết mọi câu hỏi nhiều timeline.

## Dùng bản mới

Bản này là `labor-subissues-v12`. `/ready` thêm các marker `event_date_roles`, `confirmed_task_plan`, `document_freshness`, `dense_query_batching`. Chỉ thấy các marker này sau khi code mới được đưa lên backend và khởi động lại. Lượt này chưa commit/push hay thay backend đang chạy.

Không cần chạy lại OFFLINE hoặc thay Gold/artifact cho sửa ONLINE này. Giữ result_28-10 và Gold v0.2. Nếu đang đo phiên cũ, để phiên đó kết thúc rồi tạo lượt mới với code mới; không trộn hai phiên bản vào một bảng trước/sau. Các thay đổi OFFLINE đã stage từ trước và các sửa Gold ở lượt trước được giữ nguyên.

Tokenizer tùy chọn trong cấu hình `applicability` và `adjudication`: `tokenizer_path` là thư mục tokenizer đã tải, `tokenizer_model` phải bằng chính tên Ollama model (ví dụ `qwen3:8b`). Đường dẫn/tên khai báo là cam kết cấu hình của người vận hành, không tự chứng minh hai tokenizer thật sự giống nhau; cần đối chiếu trước khi dùng. Code chỉ đọc local, không tải model/tokenizer hoặc chạy mã từ xa.

Tài liệu gốc để đối chiếu kỹ thuật: [FAISS Index I/O](https://github.com/facebookresearch/faiss/wiki/Index-IO,-cloning-and-hyper-parameter-tuning), [Ollama context length](https://docs.ollama.com/context-length), [Transformers tokenizers](https://huggingface.co/docs/transformers/main_classes/tokenizer). Những tài liệu này hỗ trợ API/đơn vị kỹ thuật, không xác nhận các con số hiệu năng hoặc độ đúng pháp lý của dự án.
