# Ablation: một lần chạy = một cấu hình = một ZIP

Notebook: `Kaggle_Ablation_Evaluation.ipynb`. Cách chọn giống PHASE trong notebook retrieval/ablation/naive_qa, nhưng ở đây dùng **ABLATION_CONFIG**. Không có danh sách chạy nhiều cấu hình cùng lúc.

## 1. Chọn một cấu hình rồi Run All

```python
ABLATION_CONFIG = 'full'
ACTION = 'run_and_judge'
```

| ABLATION_CONFIG | Nội dung | Kết quả tải riêng |
|---|---|---|
| `full` | Đủ thành phần | `full_ablation_results.zip` |
| `without_graph` | Bỏ Graph và các kênh graph thuộc phép ablation | `without_graph_ablation_results.zip` |
| `without_reranker` | Bỏ reranker | `without_reranker_ablation_results.zip` |
| `without_auditor` | Bỏ Auditor theo adapter thí nghiệm, không giả lập PASS | `without_auditor_ablation_results.zip` |
| `without_review` | Bỏ hậu kiểm trong pipeline; vẫn chấm bằng AI judge sau | `without_review_ablation_results.zip` |

Mỗi cấu hình dự kiến 120 câu, một lần lặp. Mặc định MAX_NEW_QUESTIONS=None và MAX_NEW_JUDGMENTS=None: chạy hết DUY NHẤT cấu hình đã chọn, rồi chấm cấu hình đó. Chạy xong Full, tải ZIP; lần tiếp theo đổi ABLATION_CONFIG sang without_graph và Run All, v.v. Mỗi cấu hình ở thư mục riêng, không ghi đè cấu hình trước. Chưa gom so sánh trong lượt đo riêng này.

### Lần đo mới sau sửa timeout

- Dùng `RUN_NAME='labor120_ablation_timeoutguard_v2'`; không resume kết quả cũ sau thay code/config.
- Commit/push bản sửa trước khi Run All. Notebook sẽ dừng sớm nếu code/config trên GitHub chưa có ngưỡng thời gian và cấu hình context mới.
- Trước khi đo, notebook gọi một yêu cầu JSON tổng hợp cố định để làm nóng Qwen context 32K và kiểm tra có dùng GPU. Không gửi Gold; thời gian khởi động ghi riêng trong `ollama_preflight.json`.
- Auditor chia đợt theo kích thước đầu vào, giữ nguyên toàn văn và ngữ cảnh cha; không gửi primary khi cửa sổ còn dưới 25 giây. Bước sinh không gửi primary khi cửa sổ còn dưới 20 giây. Tổng ngân sách request và thời gian dành cho hậu kiểm vẫn được giữ.
- Nếu đã lưu đủ lượt nhưng còn ERROR, notebook vẫn chấm các lượt OK. Lỗi còn nguyên trong ZIP; `complete=false` không tự đổi thành true.
- Đổi model judge giữa các thí nghiệm khiến điểm không thể gộp trực tiếp. Nếu so với Naive đã chấm bằng 3.1, cần một đợt chấm thống nhất; không sửa manifest cũ để ép cùng điều kiện.

## 2. Model và Secrets

- Gemini trong pipeline: `BACKEND_GEMINI_MODEL='gemini-3.1-flash-lite'`.
- AI judge: `JUDGE_GEMINI_MODEL='gemini-3.5-flash-lite'`.
- Qwen3:8b/Ollama vẫn giữ vai trò sinh chính/Auditor theo cấu hình; không phải toàn bộ backend đổi sang Gemini.
- Chọn BACKEND_GEMINI_SECRET_NAME và JUDGE_GEMINI_SECRET_NAME; mặc định cùng tên GEMINI_API_KEY, có thể chọn GEMINI_API_KEY.2, .3... Chỉ nhập tên Secret, không nhập giá trị. Không tự luân phiên key.
- GPU T4 ×2, Internet, Add Input artifact OFFLINE cuối; HF_TOKEN tùy chọn. Không cần chạy backend website; dừng workload khác dùng GPU/quota.

## 3. Nếu chỉ muốn chạy hoặc chấm

```python
ACTION = 'generate_only'  # chỉ tạo câu trả lời của cấu hình đã chọn
# hoặc
ACTION = 'judge_only'     # chỉ chấm đáp án đã lưu, bỏ qua khởi động Ollama
```

Chốt cả model backend và judge từ đầu; không đổi settings sau khi đo. Đổi ACTION không đổi model hay tập câu hỏi. Run All mặc định dọn Ollama do notebook sở hữu sau khi cấu hình kết thúc; có thể CLEANUP_OLLAMA=False nếu muốn giữ dịch vụ.

## 4. Quota và checkpoint

120 câu không đồng nghĩa 120 API request: mỗi câu có thể gọi Gemini nhiều lần. Hết quota/dịch vụ lỗi thì dừng, giữ checkpoint; không bảo đảm một cấu hình nằm dưới 500 request. Không tự gọi cấu hình khác để thử quota.

Sau mỗi bước chạy/chấm đều có ZIP checkpoint. Tải ngay trước khi Kaggle hết session. Có quota lại: giữ cùng ABLATION_CONFIG, RUN_NAME, PROFILE, model, code/data/settings; chạy tiếp bỏ qua câu đã lưu. Chỉ bật RETRY_ERRORS=True nếu cần đo lại ERROR, lịch sử được giữ.

Có thể đặt MAX_NEW_QUESTIONS hoặc MAX_NEW_JUDGMENTS thành số dương để tạm chia lô nếu muốn; đây là tùy chọn, không phải cách chạy mặc định. Đừng dùng --limit để chia lô standard vì limit thay tập câu hỏi.

Phiên mới: thêm ZIP checkpoint cùng artifact làm Input, đặt CHECKPOINT_ARCHIVE tới ZIP. Pin CODE_REF bằng SHA đã dùng. Notebook chốt GPU_SPEC: cùng loại GPU/VRAM/driver và các điều kiện CPU/package/code/model; cho phép khác UUID nhưng vẫn lưu UUID thật và môi trường phiên resume. Không khẳng định cùng GPU vật lý hoặc latency cloud giống hệt. Khác điều kiện thì bộ đo chặn resume/tách comparison_key; không sửa fingerprint để ép gộp.

## 5. Gom sau khi các cấu hình đã chạy xong

Đặt năm ZIP vào một thư mục, chạy trên máy local (không gọi API/model, không sinh lại đáp án):

```powershell
.\.venv\Scripts\python.exe -X utf8 đo/compare_ablation_results.py --inputs full_ablation_results.zip without_graph_ablation_results.zip without_reranker_ablation_results.zip without_auditor_ablation_results.zip without_review_ablation_results.zip --out comparison_ablation_final
```

Có thể chỉ đưa hai ZIP để so trước. Output có bảng Markdown/CSV/JSON, paired deltas, biểu đồ và SHA256 ZIP đầu vào. Chỉ so sánh các run cùng comparison_key; khác model/điều kiện sẽ tách nhóm. Không trộn hai checkpoint của cùng cấu hình trong cùng nhóm; dùng đúng một ZIP cuối. File lỗi hoặc kết quả chưa hoàn tất không được biến thành điểm 0 hay bị âm thầm xóa. Chọn thư mục output mới để giữ nguyên kết quả gốc.

Gold vẫn DRAFT; AI judge không phải phê duyệt pháp lý. Đọc số câu hoàn tất, số câu được chấm và lỗi trước khi đưa bảng vào báo cáo.


## Tự thử lại lỗi sau lượt đầu (retry v3)

`RUN_NAME='labor120_ablation_retry_v3'`. Mặc định `AUTO_RETRY_ROUNDS=2`, `RETRY_BACKOFF_SECONDS=10`: sau khi lưu đủ lịch, chỉ chạy lại các lượt ERROR có mã lỗi hạ tầng cho phép; không chạy lại câu OK hoặc câu hỏi bổ sung/từ chối hợp lệ. Có thể đặt số vòng bằng 0 để tắt.

- `failed_questions.json` là danh sách lỗi generation hiện còn; `failed_judgments.json` là lỗi chấm. Danh sách rỗng nghĩa không còn lỗi ở phần đó, không chứng minh nội dung đúng luật.
- `first_pass_generation.jsonl` và `first_pass_judge.jsonl` giữ kết quả trước vòng phục hồi; lịch sử ở `attempt_history.jsonl` / `judge_attempt_history.jsonl`. `retry_costs.json` cộng cả thời gian generation thất bại; `*_retry_state.json` ghi số vòng và thời gian vòng phục hồi.
- Giới hạn vòng được lưu qua lần chạy lại cell; không tự đặt lại số vòng hoặc đổi key/model. Lỗi quota/cấu hình API hoặc lịch đang gián đoạn thì dừng, xuất checkpoint. Lỗi không có mã hạ tầng rõ ràng được giữ để kiểm tra thủ công.
- Ollama timeout chỉ tự thử lại khi notebook sở hữu server: dừng đúng server đó, khởi động và làm nóng lại trước khi gửi câu lỗi; không tắt server bên ngoài. Nếu không xác nhận được quyền sở hữu hoặc restart lỗi, giữ checkpoint để tiếp tục sau.
- Phải dùng cùng chính sách retry khi so các cấu hình. Kết quả sau nhiều lần thử không tương đương baseline chỉ một lần; đối chiếu cả snapshot lượt đầu và tổng chi phí. Không trộn v3 với run cũ vì mã nguồn/cấu hình đã đổi.


## Bản contract v4: chạy lại without_auditor

Run mới: `labor120_ablation_contract_v4`. Chọn `ABLATION_CONFIG='without_auditor'`, chạy `PROFILE='smoke'` trước, sau đó `PROFILE='standard'`. Giữ model backend, judge và dữ liệu giống nhau giữa các cấu hình.

Bản cũ có lỗi adapter: căn cứ được giữ ở bước lựa chọn nhưng bị pack loại vì tất cả quyết định là UNRESOLVED, dẫn đến enum trích dẫn rỗng và Ollama 400. Không diễn giải các lỗi đó thành đóng góp chất lượng của Auditor.

Ở v4, chỉ DisabledAuditor có hook đóng gói nguồn đã qua kiểm tra cứng, giữ nguyên quyết định UNRESOLVED/supports_claim=False và nhãn EXPERIMENT_APPLICABILITY_NOT_CHECKED. Không giả PASS, không tắt semantic reviewer hay kiểm tra trích dẫn. Full vẫn dùng builder nghiêm ngặt như trước. Khi không có căn cứ, không gọi mô hình với schema trích dẫn rỗng.

Notebook in AUDITOR_ABLATION_CONTRACT_VERIFIED sau khi thực thi cả đường thí nghiệm và đường Full trên dữ liệu tổng hợp. Nếu xảy ra lỗi yêu cầu Ollama/HTTP JSON 400/401/403/404, runner giữ checkpoint và dừng sớm thay vì tốn thêm hàng chục lượt. Đây không phải lỗi transient để tự lặp.

Giữ ZIP lỗi cũ để chẩn đoán, không resume nó bằng code mới. Chỉ gộp ablation theo cùng comparison_key; việc sửa hợp đồng thí nghiệm làm source fingerprint thay đổi, không sửa manifest để ép gộp.
