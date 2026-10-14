# Chạy tiếp AI từ kết quả OFFLINE ngày 13/10

## Những gì đã sửa

- Giữ cache hợp lệ cũ và trích dẫn đã khớp nguồn. Kết quả giữ lại được kiểm lại SHA/offset; nguồn đã thay đổi không được dùng tiếp.
- Yêu cầu mới dùng mã đoạn nguồn S1, S2…; chương trình lấy nguyên văn tương ứng. AI không phải tự gõ lại chữ, số hoặc ngày trong trích dẫn.
- Mỗi phản hồi mới tối đa 4 mục, nội dung mô tả/câu hỏi tối đa 200 ký tự. Nếu chạm mức tối đa, chương trình chia nguồn nhỏ hơn, tối đa 3 cấp; nếu vẫn chạm mức tối đa thì ghi `AI_FRAGMENT_CAPACITY_REACHED`, giữ phần đã có và không công bố hoàn tất.
- Giữ mục đã khớp; thử trích xuất lại mục không khớp theo nhóm tối đa 4. Kết quả rỗng, thiếu hoặc sai nguồn vẫn là `AI_GROUNDING_REPAIR_INCOMPLETE`.
- Lỗi độ dài/JSON được xử lý ở từng tác vụ, không dùng nó để kết luận toàn bộ dịch vụ đã hỏng. Lỗi mạng, xác thực và provider vẫn có circuit breaker. Ngân sách mỗi stage vẫn 3 giờ; notebook giới hạn tổng 10 giờ.
- Thêm `--resume-ai`: kiểm corpus/SHA, provenance và các chỉ mục trước AI. Không dựng lại OCR, registry hoặc Dense/BM25; dựng lại knowledge/graph sau enrichment, sau đó tải Aura và audit. Case features và checklist AI hợp lệ không bị xóa như khi dựng heuristic lại.
- Checkpoint trước AI ghi rõ `RESTORED_BASELINE` hoặc `HEURISTIC_BASELINE`. Báo cáo case phân biệt `complete_cases`, `partial_cases`, `retained_ai_features` và số yêu cầu mạng; không coi “có một feature” là một bản án đã hoàn tất.

## Hai Input cần dùng

1. Cập nhật Dataset code Private bằng `build/kaggle/vn_labor_kaggle_v8.zip` mới. Manifest phải có `bundle_revision=20261013-anchored-ai-resume-v1`.
2. Dataset kết quả Private phải chứa **ZIP cuối** `D:/data_thô/result/result_13-10/vn_labor_results.zip`, SHA-256 `ee128bcbc47d14212f07188a29d27d736f18bac6752951c0989c0b6ce891e3c0`. Nếu Kaggle giải nén thành `artifacts/` thì vẫn dùng được.

Không dùng technical checkpoint thay ZIP cuối cho lần chạy này: ZIP cuối có cache AI mới nhất. Chỉ gắn một Dataset code và một Dataset kết quả để AUTO không nhầm phiên bản.

## Thao tác trên Kaggle

1. Dừng phiên cũ, mở phiên mới; upload/import `build/kaggle/VN_Labor_Kaggle_V8.ipynb` mới. `build/kaggle/ai-v9-1.ipynb` là bản giống hệt.
2. Chọn GPU T4 x2, bật Internet, gắn hai Input ở trên.
3. Cấp quyền Secrets `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Aura phải Running. Dùng cùng database sẽ thay build đồ thị hiện có; nên dừng backend ONLINE phụ thuộc Aura trong khi nạp.
4. Giữ các mặc định dưới đây, chọn Save Version → Run All. Cell đầu cài `apt-get update -y` và `apt-get install -y zstd`.

```python
RESTORE_ARCHIVE = "AUTO"
RESUME_AI_ONLY = True
REFRESH_EXTRACTION_QUALITY = False
RUN_AI_ENRICHMENT = True
OFFLINE_AI_MAX_PROVISIONS = 250
OFFLINE_AI_TIMEOUT_SECONDS = 240
LOAD_AURA = True
```

Nếu cần OCR/structure mới thay vì tiếp tục AI, đặt `RESUME_AI_ONLY=False`, `REFRESH_EXTRACTION_QUALITY=True`. Nếu Aura chưa sẵn sàng có thể tắt `LOAD_AURA`; kết quả sẽ chưa có xác minh Aura cho build mới.

Không cần thêm API AI cho thay đổi này. Notebook vẫn dùng Qwen3:8b qua Ollama. Số 250 là phạm vi checklist AI chọn lọc, không phải toàn bộ 18.871 điều/khoản/điểm. Tất cả provision vẫn có pipeline và chỉ mục; không báo AI hoàn tất toàn corpus khi chỉ xử lý nhóm chọn lọc.

## Đọc kết quả đúng cách

- `offline_final_run.json`: kết thúc kỹ thuật, build ID, phạm vi AI và trạng thái chất lượng.
- `case_ai_quality.json`: cần xem `complete_cases`, coverage và errors của từng case.
- `checklist_ai_quality.json`: xem planned/succeeded/partial/skipped, record errors và stop_reason.
- `offline_ai_requests.jsonl`: request/cache theo run_id, thời gian và loại lỗi. Cache hit không tính là gọi mạng.
- `final_outputs_validation.json`, `neo4j_validation.json`: chỉ mục/đồ thị/Aura phải cùng build.
- `artifacts/reviews/page_quality/page_review_tracking.csv`, `index.html`, `page_review_evidence.jsonl`: ảnh/trích xuất/diff để người duyệt kiểm tra.

Nếu ngân sách hết mà vẫn `AI_DEGRADED`, tải ZIP cuối/recovery rồi dùng nó làm Input cho phiên tiếp theo. Cache repair cũng được giữ; không cần lặp lại phần đã thành công. Không xóa cache hoặc tăng 250 ngay khi còn nhiều lỗi chưa giải quyết.

## 174 trang cần đối chiếu

Đã xuất riêng bộ ngày 13/10 tại `artifacts/reviews/page_quality_20261013/`. Mở `index.html` để xem ảnh PDF, native text, selected text, cleaned text và khác biệt. CSV ưu tiên các trang `NUMERIC_DIFFERENCE_COMPARE_WITH_IMAGE`; các trang text layer bất thường hoặc chữ ký vẫn phải xem ảnh trước khi kết luận.

Người duyệt ghi reviewer thật, ngày duyệt, quyết định, evidence và đường dẫn bản sửa nếu cần trong CSV. Trang chưa đủ bằng chứng giữ `REVIEW_REQUIRED`. CSV hiện là hàng đợi giao việc, không tự sửa corpus hoặc phê duyệt. Sửa text sau duyệt sẽ cần dựng lại structure/knowledge/graph/indexes và kiểm provenance.

## Dùng build ngày 13/10 cho ONLINE ngay

Đã tạo cấu hình riêng `config/online_release_20261013.yaml`, khóa SHA ZIP, build, retrieval và dense fingerprint. Cấu hình đang dùng `config/online.yaml` được giữ nguyên. Kiểm tra/chạy cấu hình mới trên máy local:

```powershell
cd D:\data_thô\legal-agentic-rag
.\run.bat online-check -Config config/online_release_20261013.yaml
.\run.bat online -Config config/online_release_20261013.yaml
```

Chỉ chạy một backend trên cổng 8000. Nếu `.env` có `VN_LABOR_ARTIFACT_SOURCE` trỏ ZIP cũ thì sửa biến đó hoặc bỏ override trước; SHA pin của cấu hình mới sẽ từ chối dữ liệu cũ. Nếu chạy backend Kaggle, thay Dataset kết quả bằng ZIP cuối ngày 13/10 và truyền `--artifact` đúng đường dẫn Input cho `kaggle/online_remote.py`. Script sẽ pin theo Input mới; không chép đường dẫn Windows của cấu hình local sang Kaggle. Khi dùng ZIP tên `vn_labor_results.zip`, truyền đường dẫn explicit; AUTO cũ chỉ nhận tên ZIP V8.1 hoặc một thư mục artifacts đã giải nén.

Build này **compatible** cho ONLINE provisional. Chưa có source/temporal/Gold review đầy đủ nên không phải dữ liệu đã được chứng nhận pháp lý. Cần đo benchmark trên backend mới để biết chất lượng câu trả lời thay đổi thế nào.

## Giới hạn kiểm chứng

Kiểm thử local dùng fixture và cache thật trong thư mục tạm; không chạy OCR corpus, Ollama/GPU, nạp Aura hoặc đổi dữ liệu canonical. Giảm sao chép trích dẫn và xử lý lỗi độ dài là cải thiện có thể kiểm chứng bằng code; mức tăng chất lượng suy luận phải đo trên lần chạy Kaggle và Gold đã duyệt. Không thể bảo đảm một dịch vụ bên ngoài không bao giờ mất kết nối hoặc hết quota.
