# Chạy ablation riêng trên Kaggle

File: `Kaggle_Ablation_Evaluation.ipynb`. Không cần chạy retrieval hay naive_qa trước. Backend phục vụ website không cần mở; hãy dừng workload khác dùng GPU/quota.

## Chuẩn bị

1. Đưa code mới lên GitHub, import notebook này vào Kaggle; bật Internet và GPU T4 ×2.
2. Add Input artifact OFFLINE cuối. Bật `GEMINI_API_KEY` (hoặc tên Secret đã chọn); `HF_TOKEN` tùy chọn. Không cần ngrok/Neo4j/Groq.
3. Giữ `BACKEND_GEMINI_MODEL='gemini-3.1-flash-lite'` và `JUDGE_GEMINI_MODEL='gemini-3.5-flash-lite'`. Qwen3:8b/Ollama vẫn là model sinh chính; 3.1 dùng cho những vai trò Gemini được bật trong pipeline. 3.5 chỉ chấm sau.
4. Có thể dùng cùng Secret hoặc chọn riêng `BACKEND_GEMINI_SECRET_NAME`, `JUDGE_GEMINI_SECRET_NAME`. Chỉ nhập tên, không nhập key. Không tự xoay key khi quota hết.
5. Mặc định `RUN_CONFIGURATIONS=['full']`, `JUDGE_CONFIGURATIONS=[]`, mỗi cell xử lý tối đa 20 lượt mới. Run All không chạy cả 600 lượt.

## Chạy từng cấu hình

Chạy các cell chuẩn bị 1–4, sau đó cell tương ứng. Run All mặc định giữ Ollama hoạt động để có thể chạy tiếp từng cell; khi kết thúc, đặt CLEANUP_OLLAMA=True và chạy cell dọn dịch vụ cuối. Sửa RUN_CONFIGURATIONS trong cell cấu hình, chạy lại cell cấu hình trước khi chọn cell chạy.

| Giá trị | Nội dung |
|---|---|
| `full` | Đủ thành phần |
| `without_graph` | Bỏ Graph và các kênh graph thuộc phép ablation |
| `without_reranker` | Bỏ reranker |
| `without_auditor` | Bỏ Auditor theo adapter thí nghiệm, không giả lập PASS |
| `without_review` | Bỏ hậu kiểm trong pipeline; vẫn được AI judge chấm sau |

Mỗi cấu hình có `runs/<tên>/` riêng, 120 câu dự kiến, một lần lặp. Chạy lại cùng cell để làm tiếp tối đa 20 câu chưa lưu. `MAX_NEW_QUESTIONS=None` mới chạy hết phần còn lại. **20 câu không đồng nghĩa 20 API request**: Researcher, soạn, hậu kiểm, sửa và retry có thể gọi nhiều lần. Chia lô không làm giảm tổng request; nó giúp chủ động dừng và giữ tiến độ.

Dừng theo lô là `BATCH_LIMIT`, không phải lỗi. Nếu quota/dịch vụ lỗi: checkpoint vẫn được xuất; không tiếp tục gọi các cấu hình khác để thử vận may. Khi dịch vụ phục hồi, có thể bật `RETRY_ERRORS=True` để đo lại lượt ERROR (lịch sử giữ trong attempt_history), sau đó tắt lại. Không thay code/model/dữ liệu trong run đã chốt.

## Chấm riêng bằng 3.5

Đặt `RUN_CONFIGURATIONS=[]`, ví dụ `JUDGE_CONFIGURATIONS=['full']`; chạy cell cấu hình rồi cell “Chấm Full”. Model được lấy từ settings đã chốt trước generation, không lấy nhầm model backend. Mỗi lần chấm tối đa `MAX_NEW_JUDGMENTS=20` đáp án đã lưu và chưa chấm; chạy lại cell để tiếp tục. Không sinh lại đáp án. Có thể chấm từng phần, nhưng chỉ diễn giải bảng cuối sau khi kiểm tra đủ lượt generation và AI_JUDGED.

## Checkpoint, phiên khác và kết quả

- Sau mỗi cell chạy/chấm đều có link ZIP `..._ablation_results.zip`. Tải xuống ngay; lưu trong /kaggle/working không bảo đảm sống sau khi session kết thúc.
- Sang phiên mới: Add Input ZIP checkpoint và artifact, đặt CHECKPOINT_ARCHIVE tới ZIP, giữ RUN_NAME/PROFILE và CODE_REF là SHA code đã dùng. Notebook kiểm hash/settings trước resume; không sửa fingerprint để ép chạy.
- Notebook chốt `GPU_SPEC`: có thể khác UUID GPU nhưng phải cùng loại GPU, VRAM, driver và các điều kiện CPU/package/code/model được kiểm soát. UUID thật vẫn nằm trong manifest/môi trường phiên resume. Đây không phải khẳng định cùng thiết bị vật lý hay latency cloud giống hệt. Chạy cấu hình khác trong cùng phiên khi có thể; công bố phiên đo khi báo cáo.
- Khác điều kiện kiểm soát thì tạo RUN_NAME mới; report tách comparison_key không tương đương. Không gộp điểm bằng tay để tạo kết luận.
- Cell “Tổng hợp” ghép các cấu hình tương thích đã có, xuất JSON/CSV/bảng/biểu đồ. Gold v0.2 vẫn DRAFT; AI judge không phải phê duyệt pháp lý.

## Lệnh tương đương

```text
python đo/evaluate_project.py run --bundle BUNDLE --config SETTINGS --out OUT/runs/full --task qa --methods full --repeats 1 --k 10 --allow-draft --allow-llm --max-new-questions 20
```

Lần sau thêm `--resume`; đừng dùng `--limit 20` để chia lô standard vì limit thay đổi tập câu hỏi. Chấm tiếp:

```text
python đo/evaluate_project.py judge --run OUT/runs/full --allow-llm --max-new-judgments 20
```

Các lệnh cần đúng biến môi trường và settings model; notebook đã cô lập và khôi phục chúng theo từng giai đoạn.
