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
