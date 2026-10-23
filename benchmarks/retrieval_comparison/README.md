# So sánh BM25 → Dense → Hybrid → Hybrid + Graph

Đây là **bộ đo truy xuất độc lập**, có thể chạy lại khi đổi code hoặc dữ liệu.
Không gọi Gemini/Ollama, không thay cấu hình triển khai, không chạy lại OCR hoặc
AI OFFLINE. Cần cài project với nhóm thư viện `retrieval` trước khi chạy.

## Chuẩn bị gì?

1. Bộ dữ liệu đã xử lý `vn_labor_results.zip` (hoặc thư mục artifacts đã giải nén).
2. Bộ câu hỏi có căn cứ chuẩn gắn với **đúng bộ dữ liệu**. Chưa có Gold duyệt thì
   dùng lệnh `prepare` để tạo sáu câu mẫu **DRAFT**, chỉ kiểm tra công cụ.
3. Để đo Dense/Hybrid/Graph: model BGE-M3 và chỉ mục Dense tương thích. Nên chạy
   trên Kaggle GPU; công cụ không tự chuyển Dense lỗi thành BM25.

Các model có thể tải lần đầu và chiếm nhiều RAM/VRAM. Không cần API key mới.
Không chạy bộ đo GPU đồng thời với backend đang chiếm GPU trên Kaggle.
Chỉ tạo chỉ mục mới nếu model/index không tương thích; không cần build OFFLINE
toàn bộ để chạy đối chứng trên gói dữ liệu hiện tại.

## Chạy trên Windows (từ gốc legal-agentic-rag)

Ví dụ dùng result_14-10; thay đường dẫn nếu dữ liệu ở nơi khác.

```powershell
.\.venv\Scripts\python.exe benchmarks/retrieval_comparison/run.py prepare `
  --artifact "D:\data_thô\result\result_14-10\vn_labor_results.zip" `
  --gold artifacts/retrieval_comparison/gold_draft.jsonl

# Đo thử BM25, không tải embedding model:
.\.venv\Scripts\python.exe benchmarks/retrieval_comparison/run.py run `
  --artifact "D:\data_thô\result\result_14-10\vn_labor_results.zip" `
  --gold artifacts/retrieval_comparison/gold_draft.jsonl `
  --methods bm25 --repeats 3 `
  --out artifacts/retrieval_comparison/bm25_smoke
```

Không ghi đè Gold hay thư mục kết quả có sẵn. Mỗi lần chạy hãy dùng thư mục
`--out` mới. Nếu muốn giữ các tệp trong Git, chỉ chọn code, Gold đã rà soát và báo
cáo cần chia sẻ; không commit cache/model hoặc toàn bộ artifacts.

## Đo đủ bốn cấu hình trên Kaggle

Sau khi code đã được đưa lên Git và cài project trong notebook, đặt `ARTIFACT`
là **đường dẫn đúng dataset kết quả của bạn**. Ví dụ:

```python
import subprocess, sys
from pathlib import Path
ROOT = Path('/kaggle/working/legal-agentic-rag')
ARTIFACT = '/kaggle/input/datasets/TEN-TAI-KHOAN/TEN-DATASET/artifacts'
GOLD = '/kaggle/working/gold_draft.jsonl'
assert Path(ARTIFACT).exists(), 'Thay ARTIFACT bằng đường dẫn Input thực tế'

subprocess.run([sys.executable, 'benchmarks/retrieval_comparison/run.py',
    'prepare', '--artifact', ARTIFACT, '--gold', GOLD], cwd=ROOT, check=True)

subprocess.run([sys.executable, '-u', 'benchmarks/retrieval_comparison/run.py',
    'run', '--artifact', ARTIFACT, '--gold', GOLD,
    '--device', 'cuda:0', '--repeats', '3',
    '--cache', '/kaggle/working/retrieval_cache',
    '--out', '/kaggle/working/retrieval_comparison_run1'], cwd=ROOT, check=True)
```

Nếu đã có Gold được duyệt, bỏ lệnh `prepare` và trỏ `--gold` đến file đó. Không
chỉ đổi DRAFT thành APPROVED; phải kiểm tra câu hỏi, ngày, từng nhóm căn cứ,
người rà soát và ngày rà soát. Bộ sáu câu mẫu không đại diện toàn luật lao động.

## Bốn cấu hình đo cái gì?

| Cấu hình | Thao tác |
|---|---|
| bm25 | Tìm từ khóa bằng đúng BM25 của project |
| dense | BGE-M3 + chỉ mục Dense hiện có |
| hybrid | Hai nhánh trên, hợp nhất RRF |
| hybrid_graph | Cùng kết quả Hybrid, lấy 5 seed hợp lệ, mở rộng cố định tối đa 2 hop/50 nút/150 cạnh/1.500 ms; lọc rồi RRF kết quả gộp |

Đây là phép đo **mở rộng graph cố định**, không phải đánh giá toàn bộ pipeline
adaptive/LLM. Không gọi exact lookup, policy anchor, issue anchor, case/community
search hoặc reranker. Không gọi Researcher, Auditor, Adjudicator hay reviewer.
Mọi cấu hình áp dụng cùng bộ lọc temporal/authority ở chế độ provisional; chưa
được xem metadata cấp điều khoản là đã duyệt. Không dùng Gold để chọn seed/gap
hoặc lấy căn cứ chuẩn rồi chèn vào kết quả.

Chỉ thay kênh truy xuất và phần mở rộng graph. Đầu vào mỗi lần là cùng nguyên
văn câu hỏi, cùng ngày, cùng pool 30/nhánh, cùng k mặc định 10. Các trường facts
và hội thoại chưa được runner này sử dụng; hãy viết câu hỏi tự chứa đủ ngữ cảnh.

## Gold và chỉ số

Mỗi dòng JSONL:

```json
{"id":"q1","question":"...","query_date":"2026-10-23","corpus_fingerprint":"...","required_groups":[["ID_ban_goc","ID_hop_nhat"],["ID_can_cu_khac"]],"review_status":"DRAFT","reviewer":null,"reviewed_at":null}
```

Mỗi nhóm là **một căn cứ cần tìm**; các ID trong nhóm là lựa chọn tương đương.
Những nhóm khác nhau là các căn cứ cần đồng thời có. Không trộn hai mốc hiệu lực
khác nhau trong một nhóm. Runner từ chối nhóm rỗng, ID không tồn tại, nhóm chồng
lấn và fingerprint khác dữ liệu. Gold mẫu là nhãn tối thiểu theo locator, không
phải toàn bộ bằng chứng đủ để tư vấn pháp lý; cần bổ sung căn cứ cha/ngoại lệ khi
chấm toàn bộ lập luận.

- `group_recall_at_k`: tỷ lệ nhóm căn cứ tìm được trong top k.
- `mrr_at_k`: nghịch đảo vị trí đầu tiên có căn cứ đúng.
- `group_ndcg_at_k`: ưu tiên các nhóm căn cứ đúng xuất hiện sớm; phiên bản thay
  thế của cùng nhóm không được cộng thêm điểm.
- `novel_group_precision_at_k`: số nhóm mới tìm được / k, không phải precision
  thông thường của mọi bản ghi liên quan.
- `all_groups_found`: tìm được đủ các nhóm của câu hỏi.

Các metric theo nhóm **không đồng nhất trực tiếp** với metric IR chấm từng ID
của bộ dữ liệu ngoài. Chưa có chấm độ đúng nội dung hoặc mức đủ của câu trả lời.

## Đầu ra và cách đọc

- `manifest.json`: fingerprint, hash dữ liệu/Gold/runner, cấu hình, thiết bị,
  thời gian warm-up. Chưa bao gồm hash mọi dependency; lưu thêm commit và môi
  trường Python khi công bố nghiên cứu.
- `responses.jsonl`: câu hỏi, cấu hình, lần lặp, thời gian, ID top k, metric,
  thống kê graph và lỗi. Ghi và flush sau từng lượt; không có chế độ resume.
- `per_question.csv`: bảng dễ mở bằng Excel.
- `summary.json`, `summary.md`: bảng so sánh; số lượt thành công/lỗi ghi riêng.

Warm-up từng phương pháp trước đo, ghi riêng khỏi thống kê; mặc định lặp ba lần,
xoay thứ tự phương pháp để giảm thiên lệch thứ tự. Đây là độ trễ warm ở tầng
retrieval, **không phải** thời gian frontend hay thời gian trả lời của chatbot.
Khởi tạo store/graph không nằm trong độ trễ từng câu. Cache OS/model có thể vẫn
ảnh hưởng. Không khẳng định đo cold start bằng cách chỉ chạy lại một câu.

Nếu warm-up thất bại, chương trình dừng và giữ báo cáo thiếu/lỗi; không công bố
điểm của phương pháp chưa chạy. Trung bình chỉ tính lượt OK, vì vậy phải đọc cả
cột lỗi và cờ `complete`/`all_attempts_succeeded`. Kết quả DRAFT chỉ chẩn đoán,
không tự chọn phương pháp thắng hoặc đổi cấu hình hệ thống.

## Kiểm thử công cụ

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s benchmarks/retrieval_comparison -p test_runner.py -v
```

Để báo cáo nghiên cứu: rà soát Gold đa dạng chủ đề, giữ riêng tập chưa dùng để sửa,
đo đủ bốn cấu hình trên cùng máy, báo cả lỗi/độ trễ/kích thước context và lưu bản
code cố định. Sau đó mới đánh giá end-to-end bằng đáp án được chấm độc lập.
