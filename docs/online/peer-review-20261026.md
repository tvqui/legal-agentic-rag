# Thẩm định góp ý và nâng cấp ONLINE — 26/10/2026

## 1. Phạm vi và kết luận

Đối chiếu source ở commit `1f4d536` (`26-10`) với nhận xét được cung cấp và archive `gold_dataset/result/evaluation_20261023T121029Z.zip`. Archive là một lượt đo lịch sử, không phải lượt chạy lại code hiện tại. SHA-256 archive: `3514bb3a59e14502de5901bb643caec14fcc37d9c75447bf4632b8ff405161d2`.

Nhận xét xác định đúng ba rủi ro: mất ứng viên qua bộ lọc phạm vi, lỗi đối soát claim khi hậu kiểm và thiếu ngoại lệ của quy tắc chung. Tuy nhiên, chưa thể kết luận các đề xuất đều tăng chất lượng hoặc tốc độ. Đặc biệt, không được biến lỗi reviewer thành kết luận pháp lý được phép hiển thị, hoặc coi thứ hạng cao là chứng minh điều luật áp dụng.

Bản này sửa ONLINE và thêm công cụ chẩn đoán. Không đổi dữ liệu OFFLINE, nhãn Gold, kết quả đo cũ, model, API key, quota hoặc giới hạn thời gian. Không cần build lại OFFLINE để dùng các sửa đổi dưới đây.

## 2. Số liệu đã tính lại

Archive chứa 100 câu QA, trong đó 85 câu đủ điều kiện đo retrieval; 84 câu có trace dùng được. `HD004` thiếu trace do lỗi kỹ thuật. Gold vẫn là DRAFT, không phải phán quyết của chuyên gia.

| Bước | Còn ít nhất một nhóm căn cứ Gold | Còn đủ tất cả nhóm căn cứ Gold |
| --- | ---: | ---: |
| Ứng viên được ghi trong trace | 74 | 73 |
| Có PASS của Auditor trong trace | 56 | 55 |
| Được chọn cuối | 52 | 49 |
| Trích dẫn công khai | 25 | 24 |

Mẫu số của bảng là 84 câu có trace và nhóm căn cứ. Trace có thể giới hạn số ứng viên được ghi; PASS ở bất kỳ lượt audit nào không đồng nghĩa với lựa chọn cuối cùng. Khớp ID Gold cũng chưa chứng minh kết luận đúng. Có 27 câu còn ít nhất một nhóm Gold trong selection nhưng trả `INSUFFICIENT_EVIDENCE`; không thể suy ra cả 27 câu chỉ cần bỏ hậu kiểm là sẽ đúng.

Các số đếm `PROFILE_LOCATION_MISMATCH=519`, `ISSUE_OR_QUERY_MISMATCH=255`, `MODEL_APPLICABILITY_FAIL=395` khớp archive. Đây là số lần xuất hiện lý do, không phải số câu hỏi hay tổng quyết định độc lập: một quyết định có thể có nhiều lý do.

Các nhãn của 100 câu: 40 `PARTIAL_ALLOWED`, 49 `INSUFFICIENT_EVIDENCE`, 10 `NEED_MORE_FACTS`, một lỗi kỹ thuật. Trong **12** câu Gold mong đợi hỏi lại: thực tế 1 hỏi lại, 5 partial, 6 insufficient. Nhận xét đếm 11 câu thiếu dữ kiện chưa chính xác; nhãn Gold nháp vẫn cần rà soát từng câu và xem phần trả lời có kết luận trường hợp cụ thể hay chỉ giải thích có điều kiện.

Với **99 lượt không lỗi kỹ thuật**, trung vị 55,479 giây, trung bình 61,689 giây, tối đa 239,495 giây; tính cả lượt lỗi thì trung bình 63,473 giây, tối đa 240,130 giây. Đây là thời gian QA trong archive, không phải thời gian render frontend hay thời gian gồm AI judge. Các con số này không mô tả bản sửa mới.

`HD001` là lỗi nội dung có thật: kết quả đã khẳng định hợp đồng 20 ngày cho công việc thông thường phải bằng văn bản từ khoản 1 Điều 14, nhưng không xét ngoại lệ tại khoản 2. Nhãn partial và trích dẫn thật không khắc phục kết luận khái quát sai.

## 3. Đánh giá từng đề xuất

| Góp ý | Đánh giá sau đối chiếu | Quyết định |
| --- | --- | --- |
| A1: reviewer cùng Qwen 8B, JSON sai nên mất đáp án | **Sai về cấu hình đã chạy.** `full_config.json` dùng Researcher Gemini 3.1 Flash Lite, Auditor Qwen3:8b, Adjudicator Qwen3:8b, reviewer **Gemini 3.1 Flash Lite**. `CLAIM_ACCOUNTING_MISMATCH` xuất hiện 16 lần; `UNSUPPORTED_SEMANTIC_PASS` còn có thể là thiếu grounding hoặc mâu thuẫn kiểm tra cứng, không chỉ sai JSON. | Siết hợp đồng đầu ra reviewer; không tự công nhận bản nháp khi kiểm tra thất bại. Giữ phần đã được duyệt riêng nếu cơ chế hiện có xác minh được phần đó. |
| A1: cần server constrained decoding thay Ollama format | Ollama `format: schema` **đã** là structured output phía server; code hiện gửi schema. Ràng buộc JSON không chứng minh ý nghĩa pháp lý. | Không thêm vLLM chỉ vì nhận định này. Sửa cách đối soát ID và giữ kiểm tra nguyên văn/ngữ nghĩa ở local. |
| A2: profile/keyword loại nhầm | Hợp lý: không có trong profile chưa phải bằng chứng điều luật không áp dụng. Nhưng reranker hoặc Gold không được quyền ghi đè kết quả audit. | Hai lý do heuristic chuyển sang `UNRESOLVED`, để Auditor hybrid kiểm tra độc lập. Mâu thuẫn dữ kiện/chủ thể/loại hợp đồng vẫn FAIL. |
| A2: relevant=true và supports_claim=true thì cho đi dù unresolved | Chưa đủ: điều kiện/ngoại lệ có thể UNKNOWN và làm đổi kết luận. Hết batch hoặc lỗi provider cũng không phải PASS. | Không triển khai cách cho qua tự động. Chỉ nhận quyết định đạt các điều kiện của hợp đồng Auditor hiện hành. |
| A2: chuyển toàn bộ elif sang YAML | Có thể giúp bảo trì, nhưng chuyển hình thức không tự sửa sai ngữ nghĩa. Nhiều ràng buộc còn liên quan dữ kiện, phiên bản và chủ thể. | Chưa chuyển hàng loạt. Cần tách và kiểm định từng nhóm quy tắc; không dùng Gold làm bảng đáp án runtime. |
| A3: cần ngoại lệ, kéo mọi khoản anh em/NEXT | Đúng về nhu cầu, quá rộng về cách lấy. Các khoản cùng Điều không nhất thiết cùng áp dụng hoặc là ngoại lệ của nhau. | Bổ sung có giới hạn theo **dẫn chiếu ngoại lệ rõ trong nguyên văn**, cùng Điều và cùng bản văn. Không quét mọi sibling/NEXT. |
| A4: cần tách độ đủ câu trả lời và trạng thái duyệt luật | Đúng về nguyên tắc, nhưng code đã có `parts[].answer_status` và `legal_status` độc lập. Trạng thái tổng còn bao gồm mức chứng cứ. | Giữ hợp đồng API. Không thêm `SUFFICIENT_PROVISIONAL` chỉ để tăng tỷ lệ khớp nhãn Gold nháp; đọc độ đủ từng task cùng trạng thái pháp lý. |
| A5: thiếu dữ kiện mà vẫn kết luận | Là rủi ro thật, cần xem từng nội dung. `answer_while_clarifying` cho phép giải thích quy tắc chung, không mặc nhiên cho phép kết luận khi thiếu dữ kiện quyết định. Code hiện có fact gate và trả lời có điều kiện. | Giữ fact gate; kiểm thử hồi quy. Không tắt mọi câu trả lời có điều kiện vì sẽ bỏ mất thông tin hữu ích. |
| A6: thêm fallback phân loại LLM/embedding | Code đã có Researcher LLM và fallback thích nghi; regex không phải lớp phân tích duy nhất. Taxonomy chưa phải danh mục điều luật được chuyên gia duyệt. | Chưa thêm một model phân loại trùng chức năng. Cần đo paraphrase và lỗi routing trước. |
| A7: tách từ tiếng Việt, BGE sparse/multivector | Là giả thuyết đáng thử, chưa phải cải thiện đã chứng minh. BGE-M3 hỗ trợ cả ba kiểu; triển khai hiện tại dùng dense. Tách từ phải đồng bộ lúc lập index và lúc query. | Đưa vào thí nghiệm OFFLINE riêng, cần build index mới và benchmark công bằng. Không đổi tokenizer trên index cũ. |
| A7: breadcrumb reranker và trọng số sau cross-encoder | Có cơ sở để ablate. Thêm breadcrumb có thể cung cấp ngữ cảnh nhưng cũng chiếm cửa sổ đoạn luật; trộn authority/temporal có tradeoff. | Chưa đổi mặc định khi chưa đo recall, ranking, câu dài và trường hợp hiệu lực. |
| A8: graph làm tệ hơn | Đúng với cấu hình **fixed graph retrieval** trong archive: recall .5941/MRR .1161 so với hybrid .9412/.6653. Chưa đủ để kết luận adaptive graph hoặc mọi graph đều tệ. | Giữ benchmark cũ nguyên vẹn. Không append sau toàn bộ danh sách chỉ để đẹp điểm: nếu đủ top-k thì graph không có cơ hội góp vào kết quả. Đo riêng bổ sung căn cứ ở gap và tác động ở top-k. |
| B: giảm Auditor xuống 12, chạy song song | Có thể tiết kiệm nhưng cũng giảm recall hoặc tăng VRAM, tranh chấp Ollama/quota; chưa có đối chứng ổn định. | Không tự cắt ngưỡng hoặc tăng song song. Bản mới có thể kiểm tra thêm ứng viên ngoài profile nên chưa cam kết nhanh hơn. |
| B: fast path, keep_alive, context batches | Nhiều phần đã tồn tại: fast path có điều kiện, keep_alive trong chuẩn bị Ollama, chia batch và cách ly nguồn quá dài. Cắt văn bản tùy tiện có thể mất điều kiện/ngoại lệ. | Không nhân đôi cơ chế hoặc tăng cửa sổ/OOM chỉ để hết lỗi. Warmup neural models có thể thử riêng khi đủ tài nguyên, vẫn phải đo cold/warm. |
| C: ablation lỗi rate limit, Gold và phép đo độc lập | Đúng. Không thể dùng các cấu hình có nhiều lỗi provider để chứng minh đóng góp thành phần; AI judge không phải độ chính xác pháp lý. Quota RPM dùng chung và bounded retry đã có, vẫn có thể hết quota ngày. | Bổ sung chẩn đoán phễu; giữ DRAFT và mẫu số. Chỉ so ablation lại khi các lượt chạy có điều kiện tài nguyên/quota phù hợp; Zalo/VLSP chưa có điểm thì không tạo điểm. |

## 4. Những thay đổi đã thực hiện

### 4.1. Không dùng profile chưa đầy đủ để phủ định điều luật

Trong `applicability.py`, `PROFILE_LOCATION_MISMATCH` và `ISSUE_OR_QUERY_MISMATCH` trở thành `UNRESOLVED`. Chế độ hybrid đưa những ứng viên này vào kiểm tra model trong ngân sách hiện có. Mâu thuẫn cứng vẫn bị loại trước; model không được phục hồi điều luật đã mâu thuẫn dữ kiện. Pure deterministic không tự duyệt những ứng viên chưa giải quyết.

Không tăng `max_items`/`max_batches`; hết lượt vẫn chưa xác minh. Sửa đổi loại bỏ một suy luận phủ định không hợp lệ, không bảo đảm model sẽ duyệt mọi căn cứ bị bỏ trước đây.

### 4.2. Đối soát claim/task bằng khóa bắt buộc trong schema reviewer

Array có đúng độ dài và ID thuộc enum vẫn có thể lặp một ID rồi bỏ ID khác. `answer_review.py` chuyển hợp đồng gửi model thành object có đúng các khóa claim/task yêu cầu; mỗi claim được giới hạn evidence ID theo các nguồn đã dẫn. Sau đó chuẩn hóa về model nội bộ hiện có, tiếp tục kiểm tra:

- Đủ và đúng ID, không lặp/đổi ID, không thêm trường lạ.
- Trích nguyên văn có thật trong đúng nguồn; giữ các kiểm tra chủ thể, lượng, điều kiện và ngữ nghĩa.
- Coverage chỉ được dùng claim đã SUPPORTED; không tự nói đã trả lời đủ.
- Lỗi kỹ thuật/thiếu grounding không được phục hồi bản nháp thành đáp án đã xác minh.

Hình thức mảng cũ vẫn chịu validator chặt khi được trả bởi adapter nội bộ; các provider có kiểm tra schema sẽ nhận hợp đồng object mới. Không thêm lượt suy luận hoặc tăng số retry. Đây là giảm cơ hội sai accounting, **chưa phải số liệu chứng minh giảm lỗi Gemini thực tế**.

### 4.3. Đóng dẫn chiếu ngoại lệ cụ thể, có giới hạn

`exception_references.py` nhận dạng các cụm dạng “trừ trường hợp … khoản N Điều này” trong `source_text` ưu tiên hơn bản hiển thị. Retriever bổ sung đúng khoản được dẫn chiếu, cùng `document_id`, số Điều và văn bản; mặc định tối đa 8 đơn vị, cấu hình `retrieval.exception_context_top_k` từ 0 đến 32 (0 tắt bổ sung ứng viên).

Đây là ứng viên **chưa được duyệt**: vẫn qua lọc thời gian, nguồn, provenance và Applicability Auditor. Khi quy tắc đã qua audit dẫn đến ngoại lệ này, evidence plan yêu cầu **locator thực** của ngoại lệ. Chỉ gặp chữ “trừ trường hợp” trong quy tắc chung không còn đủ để lấp yêu cầu mới. Cập nhật cả khi phát hiện yêu cầu trong vòng graph.

Đổi `exception_context_top_k=0` tắt bước bổ sung ứng viên, không tắt yêu cầu đủ căn cứ khi nguyên văn đã dẫn ngoại lệ. Trace có sự kiện `explicit_exception_context` cho biết số dẫn chiếu, số ứng viên thêm và số còn lại sau lọc. Gói evidence hiện có và hậu kiểm ngữ nghĩa vẫn chịu trách nhiệm đánh giá ngoại lệ có thực sự áp dụng.

Giới hạn được giữ rõ: chỉ xử lý dẫn chiếu ngoại lệ cùng Điều theo dạng trên; chưa giải quyết mọi liên kết chéo sang luật khác, bảng, phụ lục hoặc nội dung OCR thiếu. Không thể tuyên bố đã bao phủ toàn bộ ngoại lệ lao động.

### 4.4. Công cụ phân tích lại archive

`benchmarks/evaluation_suite/diagnose_labor.py` tính các tầng retrieval → auditor → selection → public; phân biệt khớp bất kỳ nhóm và khớp toàn bộ nhóm, thiếu trace, lỗi kỹ thuật, lỗi reviewer, cấu hình model đã lưu và các câu còn Gold nhưng bị chặn. Không gọi API, không giải nén ra thư mục, không sửa archive hoặc đưa Gold vào runtime. Cấu hình xuất ra chỉ có các trường allowlist, không có API key/token.

Chạy tại thư mục dự án:

```powershell
.\.venv\Scripts\python.exe benchmarks/evaluation_suite/diagnose_labor.py `
  --archive gold_dataset/result/evaluation_20261023T121029Z.zip `
  --variant full `
  --output artifacts/online_benchmarks/peer_review_20261026/funnel.json
```

Có thể dùng lại với archive cùng định dạng sau mỗi lần đo. Không so trực tiếp hai archive khác Gold/corpus/config chỉ bằng một tỷ lệ tổng.

## 5. Kiểm chứng và giới hạn kết luận

- 596/596 tests ONLINE đạt; 28/28 tests evaluation suite đạt. Bổ sung 25 tests cho heuristic Auditor, hợp đồng reviewer, ngoại lệ và công cụ chẩn đoán; hai fixture pipeline cũ được cập nhật cho bước retrieval mới, không bỏ assertion cũ.
- Các ca bảo vệ gồm: model không được đảo mâu thuẫn hợp đồng/dữ kiện; relevant/support=true nhưng điều kiện UNKNOWN chưa đủ kết luận; sai trích dẫn hoặc thiếu grounding vẫn bị chặn; nguồn khác edition không được kéo vào vì trùng số Điều; từ khóa ngoại lệ không lấp được locator còn thiếu.
- Smoke integration trước/sau trên artifact thật `result_14-10`, sáu câu, cấu hình không gọi model: 4 câu hợp đồng vẫn `INSUFFICIENT_EVIDENCE`, câu lương thử việc 70% vẫn có trả lời partial kèm căn cứ, câu hình sự vẫn `ABSTAIN`. Không có exception runtime. Một ca đã thêm được một khoản ngoại lệ và qua lọc nguồn/thời gian; điều này không chứng minh Auditor LLM hay đáp án cuối trên Kaggle đã tốt hơn.
- Không chạy lại 100 câu bằng Gemini/Qwen trên Kaggle trong lượt sửa này; chưa có tỷ lệ đúng mới hay cải thiện độ trễ được đo. Bộ đo cũ và phần OFFLINE chưa được thay đổi.

Lệnh kiểm thử local (cần venv dự án đã cài thư viện):

```powershell
$env:PYTHONPATH = 'src;.;tests'
.\.venv\Scripts\python.exe -m unittest discover -s tests/online
.\.venv\Scripts\python.exe -m unittest discover -s benchmarks/evaluation_suite
```

## 6. Đưa lên Kaggle và bước tiếp theo

Các sửa đổi nằm trong **dự án chính `D:\data_thô\legal-agentic-rag`**, không chỉ trong bản staging kiểm tra. Trước khi đưa lên, xem đúng danh sách file:

```powershell
cd D:\data_thô\legal-agentic-rag
git diff --check
git diff --stat
git status --short
git add src/vn_labor_online/answer_review.py src/vn_labor_online/applicability.py src/vn_labor_online/config.py src/vn_labor_online/evidence.py src/vn_labor_online/exception_references.py src/vn_labor_online/pipeline.py src/vn_labor_online/retrieval.py tests/online/test_auditor_heuristics.py tests/online/test_exception_reference_closure.py tests/online/test_output_precision.py tests/online/test_review_decoder_contract.py benchmarks/evaluation_suite/diagnose_labor.py benchmarks/evaluation_suite/test_diagnostics.py docs/online/peer-review-20261026.md
git diff --cached --stat
git commit -m "Improve applicability review and explicit exception evidence closure"
git push
```

Sau đó Run All notebook backend đang lấy `origin/main`; giữ nguyên artifact `result_14-10`, model và Secrets. **Không cần chạy lại OFFLINE** cho bản này. Đối chiếu commit Kaggle in ra với commit vừa push. Không đổi taxonomy/version chỉ để phân biệt một bản sửa không đổi taxonomy.

Đo trước các ca từng hỏng accounting, hợp đồng ngắn hạn, nhiều task, câu thiếu dữ kiện và paraphrase chưa có trong Gold; xem trace rồi mới mở rộng 100 câu. Giữ cùng corpus, model, qrels, quota và chế độ cold/warm khi so sánh. Dùng `funnel.json`, các câu trả lời thực và số lỗi để đánh giá; không chỉ đếm câu hệ thống chịu trả lời.

Nếu tiếp tục OFFLINE, ưu tiên human review nguồn/hiệu lực và Gold. Tách từ tiếng Việt/BGE sparse/contextual indexing là các nhánh thử nghiệm cần build và đo riêng; chúng chưa nằm trong thay đổi này.

## 7. Nguồn kỹ thuật đã đối chiếu

- [Ollama structured outputs](https://ollama.com/blog/structured-outputs): schema JSON được hỗ trợ ở phía model server; vẫn cần kiểm tra nội dung.
- [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/): một lựa chọn serving/decoding, không phải chứng minh thay engine sẽ sửa suy luận pháp lý.
- [CRAG](https://arxiv.org/abs/2401.15884): đánh giá và sửa retrieval là hướng tham khảo; không đồng nghĩa bỏ kiểm chứng câu trả lời khi checker lỗi.
- [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3): hỗ trợ dense, sparse và multi-vector; cần cách lập index và đo riêng cho từng dạng.
- [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval): thêm ngữ cảnh khi chuẩn bị đoạn/index; không chỉ là thay prompt ONLINE.
- [LegalBench-RAG](https://arxiv.org/abs/2408.10343): tham khảo đánh giá truy xuất pháp lý, không thay thế Gold lao động Việt Nam được duyệt.
- [Self-RAG](https://arxiv.org/abs/2310.11511) và [Lost in the Middle](https://arxiv.org/abs/2307.03172): phân biệt nghiên cứu có huấn luyện/chế độ thực nghiệm với một prompt phản tư hoặc thao tác cắt context đơn thuần.

Các nguồn hỗ trợ quyết định thiết kế, không cung cấp bằng chứng thực nghiệm rằng bản sửa đã tăng độ chính xác của Pháp Điển AI.
