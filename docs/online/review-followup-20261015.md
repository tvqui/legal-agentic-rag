# Đối chiếu đánh giá và hiệu chỉnh ONLINE — 15/10/2026

Đã đối chiếu báo cáo `phan_tich_phap_dien_ai_20261015.md`, phần nhận xét được gửi kèm, cấu hình technical-check, source đang dùng và ZIP OFFLINE 14/10 thật. Kết luận: có lỗi cấu hình và khoảng trống kiểm tra từng ý cần sửa; chưa có phép đo đủ để kết luận mô hình nào gây chậm hoặc tuyên bố đã tăng độ chính xác pháp lý.

## 1. Những nhận xét đúng và phần cần phản biện

| Nhận xét | Kết quả đối chiếu |
|---|---|
| `run.bat online` có thể bỏ qua biến chọn cấu hình, đồng thời YAML ghim bản V8.1 | Đúng ở bản trước. Đã sửa chọn cấu hình và cập nhật các pin về đúng ZIP 14/10. |
| Đổi đường dẫn mà giữ fingerprint cũ có thể chặn khởi động | Đúng. Tiếp tục giữ kiểm tra integrity; không xóa pin để chạy cho qua. |
| 96/285 có subissue, 78/285 được profile bao phủ, 189/285 không có subissue | Tái lập đúng bằng analyzer của bản trước khi sửa. Đây là số liệu phân loại, không phải số câu đúng/sai. |
| Những nhóm ngoài thử việc/nghỉ việc/nghỉ phép còn thiếu profile sâu | Đúng về mức độ bao phủ. Tuy nhiên `rule_catalog.py` đã có nhiều nhóm yêu cầu căn cứ theo ngày cho các chủ đề rộng. Không có subissue không đồng nghĩa không có rule/evidence. |
| Source/YAML local mặc định deterministic; chưa thể kết luận Qwen/Gemini là nguyên nhân chính gây chậm | Đúng với cấu hình trong source và đúng khi chưa quy nguyên nhân. Bổ sung từ môi trường thật: `.env` trên Windows đang chọn adjudication `http`, model `qwen3:8b`; researcher/applicability deterministic. Vì vậy khi đo phải tính cả đường gọi LLM, không chỉ BGE/BM25. |
| Kỹ thuật PASS chưa có nghĩa được duyệt pháp lý | Đúng. Dữ liệu 14/10 vẫn chưa được source/temporal/Gold review đầy đủ. |
| Nên giảm Top-K xuống 12 | Là giả thuyết cần thử nghiệm. Chưa thay mặc định khi chưa có required-evidence recall và đánh giá đầu cuối trên Gold được duyệt. |
| Bổ sung streaming an toàn để cải thiện trải nghiệm chờ | Hợp lý về trải nghiệm. Tuy nhiên nếu phải hoàn tất audit mới phát claim thì SSE không giúp căn cứ xuất hiện sớm hơn; còn phát trước audit có nguy cơ phát nội dung bị loại. Bản sửa giữ tiến trình thật, chưa thêm SSE và không phát kết luận pháp lý chưa kiểm chứng. |
| Cần memory ở backend | Hữu ích nếu cần tài khoản, nhiều thiết bị và lưu hội thoại trên máy chủ. Hiện là phạm vi nâng cấp triển khai, không phải lý do tự động thêm cơ sở dữ liệu vào bản demo dùng localStorage. |
| Gemini 3.5 Flash-Lite có thể làm question understanding | Là ứng viên có thật, nhưng phải A/B test. Chưa bật mặc định và chưa gọi API trả phí. [Tài liệu model chính thức](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite). |

## 2. Bộ dữ liệu thực tế được khóa

| Trường | Giá trị |
|---|---|
| Tệp local dùng cho ONLINE | `build/releases/vn_labor_results_20261014.zip` |
| SHA-256 ZIP | `895db689d0cb60f6a76042a70452cedadfb80151bc1d9818b1cb54c182d19071` |
| Graph build | `9a615f1927162fe63e73b734b6a48759596984fbf2d004ce76bc2eb94e0e5da0` |
| Retrieval fingerprint | `2a82928a2968cf5583858c2b56aafb12550c61e304df52b5cdd4262d015d9557` |
| Dense fingerprint | `3c33b60ad0696ddc65006725613281bfee1e419e77be4183311cbde3f584a41a` |
| Quy mô | 95 văn bản; 18.871 provisions; 24 bản án; 19.160 retrieval units; 57.296 nodes; 84.624 edges |
| Tương thích kỹ thuật | PASS qua `ArtifactStore` trên ZIP thật |
| Được duyệt pháp lý đầy đủ | Chưa; `legal_ready=false`, `legal_status=PROVISIONAL` |

Đã sao chép ZIP sang đường dẫn release trên và chỉ chuyển biến artifact trong `.env` nếu nó còn đúng đường dẫn V8.1 cũ. Không thay khóa API hoặc lựa chọn provider của người dùng. Không chạy lại OFFLINE, không sửa corpus, metadata review hoặc nội dung ZIP. ZIP V8.1 cũ vẫn được giữ.

Ngày đóng gói 14/10 không chứng minh pháp luật được cập nhật đến 14/10. `corpus_snapshot_as_of` vẫn là `2026-09-15`, một mốc metadata của corpus; không có nghĩa toàn bộ hiệu lực tại mốc này đã được reviewer xác nhận. Cảnh báo dữ liệu cũ và temporal review vẫn giữ nguyên.

## 3. Cơ chế đã thêm/sửa

- `online`, `online-check`: ưu tiên `-Config` → `VN_LABOR_ONLINE_CONFIG` từ môi trường/`.env` → `config/online.yaml`. CLI check in đường dẫn cấu hình, artifact và chế độ provider **sau ghi đè**.
- `online.yaml`, `online_ollama.yaml`, `online_kaggle.yaml`: cùng ghim bản 14/10. Cấu hình được bạn gửi được giữ thành `config/online_20261014_technical_check.yaml` riêng. Các biến provider trong môi trường vẫn có thể ghi đè YAML; tên technical-check không đồng nghĩa mọi provider đều deterministic.
- Compatibility tách `technical_compatible` với `legal_ready`, đồng thời công khai `archive_sha256` và `legal_status`. `/ready.ready` chỉ nói dịch vụ sẵn sàng vận hành, không phê duyệt tư vấn pháp lý.
- Kaggle nhận ZIP tên mới hoặc thư mục artifacts tự giải nén. Khi có nhiều bộ dữ liệu, runner liệt kê ứng viên và yêu cầu `--artifact`, không tự chọn bản cũ theo tên.
- Registry 50 nhóm chủ đề phục vụ routing, với cách diễn đạt và viết tắt thông dụng. Đây **không phải 50 legal profiles đã được duyệt**. Chủ đề chưa có quy tắc sâu vẫn phải tìm đủ nguồn theo ngày và qua audit. Không thêm số tiền, mức hưởng hoặc điều luật theo ID benchmark vào registry.
- Analyzer deterministic tạo task cho từng subissue và yêu cầu chủ đề chưa được bao phủ. Researcher có thể bổ sung task nhưng không xóa task nền. Các tình tiết ở mệnh đề điều kiện không tự trở thành một yêu cầu pháp lý mới; nghỉ việc riêng không bị đổi thành đơn phương chấm dứt.
- Mỗi phần trả về `evidence_status`, `answer_status`, ID căn cứ, claim được kiểm tra, yêu cầu còn thiếu và `legal_status`. Có căn cứ không đồng nghĩa đã trả lời đầy đủ. Nếu chưa có kiểm tra nội dung độc lập, dùng `NOT_CHECKED`, không tự ghi `ANSWERED`.
- Phần có chuỗi căn cứ theo ngày đầy đủ có thể được trả lời riêng khi phần khác chưa đủ. Kết quả tổng vẫn `PARTIAL_ALLOWED`, vẫn nêu phần thiếu và vẫn phải qua kiểm tra applicability, nguồn, hiệu lực, câu chữ và trích dẫn. Kết luận phụ thuộc phần chưa giải quyết không được đánh dấu hoàn thành.
- Giữ ngữ cảnh user có cấu trúc khi chuyển sang intake/Researcher; không dùng lời trả lời trước của AI làm sự thật của người dùng.
- Trace phân tách import thư viện, nạp index, khởi tạo BGE/reranker, encode, search; cùng các thời gian analysis, Researcher, graph, generation và audit đã có. Chỉ đo thành phần thực sự được gọi.
- Giao diện có mục mở rộng mức độ trả lời từng ý. `/ready.online_features` công bố `routing_topics=labor-topics-v1` và `task_completeness=evidence-and-answer-v1` để phân biệt backend đã cập nhật.

## 4. Kiểm tra và chạy

### Windows

Từ thư mục `D:\data_thô\legal-agentic-rag`:

```powershell
.\run.bat online-check
.\run.bat online-check -Config config/online_20261014_technical_check.yaml
```

Đầu ra đúng với ZIP này: `technical_compatible=true`, graph build bắt đầu `9a615f19`, `legal_ready=false`, `legal_status=PROVISIONAL`. Xem `effective_modes` để biết provider thực tế. Check chỉ kiểm tra artifacts, không gọi LLM và không benchmark BGE.

Nếu chạy backend local thì dùng `run.bat online` với provider phù hợp máy. Nếu backend chạy Kaggle thì không cần bật thêm backend local; frontend tiếp tục đi qua proxy tới URL Kaggle.

### Kaggle

Sau khi tự commit/push thay đổi, cập nhật code và khởi động lại backend. Các cell cài đặt hiện tại vẫn cần giữ git/curl/zstd, dependencies, Ollama và Kaggle Secrets như trước. Add Input chứa **kết quả ngày 14/10**, không phải gói source OFFLINE thay cho kết quả.

Nếu chỉ có một gói kết quả hợp lệ:

```python
%cd /kaggle/working/legal-agentic-rag
!python -u kaggle/online_remote.py --config config/online_kaggle.yaml
```

Nếu Input có cả bản cũ và mới, thay đường dẫn ví dụ dưới bằng đường dẫn thực tế trong thanh Input, trỏ ZIP hoặc thư mục `artifacts`/thư mục cha chứa nó:

```python
!python -u kaggle/online_remote.py --config config/online_kaggle.yaml --artifact "/kaggle/input/DUONG_DAN_THUC_TE/artifacts"
```

Kiểm `/ready` với API key như cách đang dùng. Cần thấy build mới và hai trường tính năng ở mục 3. Cập nhật `VITE_BACKEND_TARGET` nếu URL ngrok đổi, rồi khởi động lại Vite. Không đặt khóa Gemini/Ollama hoặc API key backend vào mã gửi xuống trình duyệt.

### Đo routing không tải model

```powershell
.venv\Scripts\python.exe scripts/audit_online_coverage.py --questions artifacts/online_benchmarks/labor_285_v4_20261009T124602Z.questions.json --out artifacts/reports/online_coverage_review_20261015.json
```

Chỉ số này dùng để tìm khoảng trống phân loại/task; không thay thế chạy backend, kiểm căn cứ hay chấm pháp lý.

### Thử Top-K trên máy có đủ RAM/GPU

```bash
python scripts/benchmark_retrieval.py --config config/online_kaggle.yaml --gold PATH_TO_REVIEWED_GOLD.jsonl --pool-sweep --out artifacts/online_evaluation/pool_sweep.json
```

So sánh `30/30/20/fusion30` và `12/12/8/fusion12`, tách lần nạp đầu khỏi P50/P95 khi đã nạp. Đo recall của ID căn cứ bắt buộc, có dùng reranker nếu cấu hình bật. Đây là benchmark truy xuất, không phải độ đúng của toàn bộ câu trả lời. Với Gold draft hoặc sai build, báo cáo là provisional; script không tự đổi cấu hình triển khai. Không dùng một câu hoặc hai nhóm có tập mẫu khác nhau để kết luận giảm Top-K an toàn.

## 5. Phạm vi còn phải kiểm chứng

Chưa đo latency/accuracy đầu cuối của backend Kaggle đang chạy; chưa A/B Gemini; chưa có Gold do chuyên gia duyệt để xác nhận các chủ đề rộng đủ và đúng. Không tuyên bố “đã bao phủ toàn bộ luật lao động” từ alias hoặc số lượng test. Các mục trên không cần chạy lại OFFLINE; việc duyệt 174 trang, nguồn, temporal và Gold vẫn là công việc riêng.

Kết quả kiểm thử và số liệu routing thực tế được lưu ở `artifacts/reports/online_review_followup_20261015.json`, `release15_tests.log` và `online_coverage_review_20261015.json` sau vòng xác minh cuối.

## 6. Kết quả xác minh bản sửa

| Kiểm tra | Kết quả |
|---|---|
| Python, toàn repository | 526/526 PASS; 0 failure, 0 error |
| Frontend | 8/8 PASS; lint PASS; production build PASS |
| `compileall`, `git diff --check` | PASS; chỉ có cảnh báo chuyển LF/CRLF hiện hữu |
| `run.bat online-check` mặc định trên ZIP thật | PASS; build `9a615f19…`; effective adjudication `http` |
| Technical-check riêng trên ZIP thật | PASS; các pin khớp; legal status vẫn PROVISIONAL |
| Audit analyzer 285 câu | 231 có nhãn chủ đề rộng; 96 có subissue; 123 có yêu cầu căn cứ theo ngày; 59 có nhiều task |

Định nghĩa `profile_covers_issues` nay chặt hơn: nếu còn task deterministic chưa có profile, fast path không được xem là bao phủ đầy đủ. Vì vậy số 59/285 theo định nghĩa mới không được đem so trực tiếp với 78/285 theo định nghĩa cũ để kết luận accuracy tăng hoặc giảm. Registry 50 nhóm là bước routing; không chứng nhận 50 nhóm đã có nội dung pháp lý hoàn chỉnh.

Các test mới dùng fixtures/mô hình giả cho truy xuất; không nạp BGE/Qwen/Gemini thật trên máy local. Chưa chạy lại 285 câu qua backend Kaggle. Không có số liệu P50/P95 mới để hứa hệ thống đã nhanh hơn.
