# Sửa AI enrichment và chất lượng trang — 12/10/2026

> Đã bổ sung bản sửa provenance v2 cho 38 điều khoản có chú thích giữa nội dung. Xem `offline-provenance-fix-20261012.md`; cần cập nhật cả ZIP code và notebook.

Code đã sửa trực tiếp trong `legal-agentic-rag`. ZIP kết quả ngày 12/10 và corpus gốc được giữ nguyên. Cần chạy lại OFFLINE trên Kaggle để xuất một build có các sửa chữa này; cấu hình ONLINE đang dùng chưa được đổi.

## Những gì đã sửa

### AI

- Chia đầy đủ văn bản bản án và điều khoản thành các fragment giới hạn 3.500 byte UTF-8, có overlap. Không cắt bỏ phần cuối văn bản.
- Giữ ancestor context cho checklist. Đầu vào không đủ chỗ cho đầy đủ context bị ghi rõ `AI_ANCESTOR_CONTEXT_TOO_LARGE`, không âm thầm cắt mất ngoại lệ.
- Qwen3 vẫn `think=false`, context giảm từ 32.768 xuống 16.384, output từ 4.096 xuống 2.048 token. JSON schema và prompt giới hạn 12 mục/fragment; không bỏ qua lỗi output bị cắt.
- Thời hạn request Kaggle từ 120 lên 240 giây. Timeout hoặc lỗi output-token có thể chia fragment nhỏ hơn một lần; không retry vô hạn.
- Lưu quyết định chia nhỏ để phiên sau đọc cache của fragment con thay vì lại gửi fragment cha đã timeout. Cache chỉ có hiệu lực khi model/prompt/schema/payload khớp; cache cũ vẫn giữ, nhưng thay đổi prompt hoặc payload có thể cần tạo kết quả mới.
- Circuit breaker và ngân sách tối đa 3 giờ cho mỗi stage AI vẫn được giữ; notebook có giới hạn tổng riêng 10 giờ. Cache tốt vẫn đọc được khi circuit đang mở; đọc cache không tự cho rằng provider đã phục hồi.
- `reports/offline_ai_requests.jsonl` ghi thời gian, loại lỗi gốc, HTTP status, số byte đầu vào, ID/cache key và cache-hit. Không ghi API key, URL chứa credential hoặc thông điệp exception tùy ý.
- Báo cáo phân biệt request mạng, cache-hit, fragment hoàn tất, record xử lý một phần và phần chưa thực hiện. Grounding không đạt sẽ giữ trạng thái chưa hoàn thành.
- Nếu gián đoạn khi xử lý bản án/checklist, checkpoint vẫn giữ đủ danh sách bản án và baseline checklist heuristic, không thay bằng một prefix đã xử lý.
- Thêm preflight structured inference với đầu vào ngắn và một fragment bản án thật trước khi chạy enrichment dài. Preflight không chứng nhận độ đúng pháp lý.

### Trang PDF và chú thích

- Đã tạo evidence audit đủ 174/174 trang đáng ngờ trong ZIP ngày 12/10: ảnh PDF, native text, raw selected/OCR text, cleaned text, diff và khác biệt chữ số. Tất cả 174 trang có nguồn đúng SHA và raw selected text để đối chiếu.
- Tìm được 106 chú thích có marker pháp lý, nằm ở phần dưới trang, cỡ chữ nhỏ hơn thân bài và khớp nguyên văn bản đã trích xuất.
- Document text giữ nguyên chú thích và offsets. Parser dùng bản mask riêng để chú thích không nhập vào nội dung điều/khoản/điểm; segments/evidence vẫn dựa trên nguồn gốc.
- Chú thích được ghi `01_extracted/footnotes.jsonl`, có SHA nguồn, SHA đoạn văn, page, bbox, font và document offsets. Không biến chú thích thành approval hoặc tự áp dụng ngày sửa đổi.
- Lỗi đã xác nhận qua ảnh: một số biểu mẫu PDF chữ xoay/dòng chấm đọc được bằng native text bị OCR biến thành chữ/số rời rạc. Code mới giữ native text cho biểu mẫu có đủ bằng chứng layout, có nhiều chữ thật và ít raster. Không dùng ngoại lệ này cho scan, native chỉ có chữ ký điện tử hoặc text layer hỏng.
- Caches OCR từng trang vẫn giữ cùng schema/key để tái sử dụng. Document caches cũ được dựng lại để áp dụng cách chọn native và chú thích mới. Điều này cần đọc lại PDF bằng CPU, nhưng không bắt buộc OCR lại các trang đã có cache hợp lệ.
- Luồng Kaggle mới tạo bộ review toàn bộ trang đáng ngờ sau checkpoint kỹ thuật. Không còn giới hạn ảnh review ở 12 trang/document trong bộ review riêng.

## Những gì chưa thể chứng nhận tự động

174 trang được đối chiếu không có nghĩa 174 trang đã được duyệt. Native chỉ chứa chữ ký điện tử không thể làm bản chuẩn cho nội dung scan. Lỗi chữ số như `152` đọc thành `452`, ngày `30` đọc thành `80`, hoặc từ bị nhầm ký tự phải đối chiếu ảnh nguồn; code không đoán và sửa số pháp lý dựa vào tên file.

Mọi trang và chú thích chưa có reviewer vẫn `REVIEW_REQUIRED`. Các chú thích kéo sang trang sau hoặc không đủ bằng chứng hình học vẫn phải giữ lại để review, không xóa tự động. Độ đúng pháp lý của thuộc tính/checklist AI vẫn cần Gold và reviewer.

## Kiểm tra đã thực hiện tại máy

- Regression tests cho chia UTF-8 không mất tail, timeout chia nhỏ, resume không gọi lại fragment cha, circuit/cache, giới hạn stage, lỗi schema, không log secret, tọa độ evidence, tách chú thích và native form.
- Toàn repository: 473 tests PASS ở lần kiểm tra cuối. Kết quả cuối và các CPU replay được lưu trong `artifacts/reports/offline_quality_upgrade_validation_20261012.json`.
- Replay riêng 95 tài liệu với chú thích: Điều 62 khoản 2 điểm đ không còn chứa chú thích 33; chú thích vẫn nằm nguyên trong document và có offsets hợp lệ. Không gọi AI/OCR/GPU/Aura trong replay này.
- Replay extraction 95 tài liệu dùng page caches từ ZIP gốc đã giữ được native text cho 75 trang biểu mẫu, với 0 lần gọi OCR model và integrity PASS. Báo cáo: `artifacts/reports/offline_native_refresh_replay_20261012.json`.

## Bạn cần làm trên Kaggle

1. Upload phiên bản mới của Dataset code bằng:
   - `build/kaggle/vn_labor_kaggle_v8.zip`
   - file `.sha256` cùng tên để đối chiếu.
2. Dùng `D:/data_thô/result_12-10/vn_labor_results.zip` làm checkpoint Input. Đây là ZIP kết quả, **không thay cho ZIP code**. Chỉ gắn một checkpoint để `AUTO` không chọn nhầm; tháo checkpoint V8.1/recovery cũ nếu đang gắn song song.
3. Import notebook mới `build/kaggle/VN_Labor_Kaggle_V8.ipynb` (alias `ai-v9-1.ipynb` có cùng nội dung), bật Internet và GPU T4 x2.
4. Giữ mặc định:

```python
RESTORE_ARCHIVE = "AUTO"
REFRESH_EXTRACTION_QUALITY = True
RUN_AI_ENRICHMENT = True
OFFLINE_AI_MAX_PROVISIONS = 250
OFFLINE_AI_TIMEOUT_SECONDS = 240
LOAD_AURA = True
```

Chưa tăng số provision trước khi xem tỷ lệ hoàn thành của run mới. Nếu cần nạp Aura, instance phải RUNNING và bốn Secrets phải đúng. Notebook vẫn cài `apt-get update -y` và `apt-get install -y zstd` ở đầu.

5. Bấm Save Version → Save & Run All. Không cần git push để notebook dùng code trong Dataset ZIP mới. Cần cả notebook mới và Dataset code mới; chỉ thay một trong hai có thể chạy logic cũ.
6. Sau khi chạy, xem:
   - `reports/ai_provider_preflight.json`: preflight PASS;
   - `reports/case_ai_quality.json`: đầy đủ số case và fragment; không chỉ nhìn số case có vài features;
   - `reports/checklist_ai_quality.json`: planned/succeeded/partial/skipped và complete;
   - `reports/offline_ai_requests.jsonl`: request duration và lỗi;
   - `reviews/page_quality/index.html`, `page_review_evidence.jsonl`, `summary.json`;
   - `01_extracted/footnotes.jsonl`;
   - `reports/final_outputs_validation.json`: kiểm kỹ thuật và readiness pháp lý tách biệt.

Nếu hết thời gian hoặc provider lỗi, tải recovery/checkpoint chứa cache làm Input cho phiên sau. Không sửa report để ép `COMPLETE`. Cơ chế resume được kiểm thử bằng fixture; tốc độ và tỷ lệ thành công thật của Qwen/T4 cần xác minh trong lần Kaggle tiếp theo. Không thể bảo đảm nhà cung cấp, quota hoặc mạng không lỗi.

## Mở bộ review ngay tại máy

`artifacts/reviews/page_quality_20261012/index.html` là bộ 174 trang gốc đã tạo, mở bằng trình duyệt. Cùng folder có evidence JSONL và `documents_with_annotations.jsonl`; file sau chỉ là dữ liệu replay riêng, không thay extraction đang chạy.

CLI để tạo lại một bộ đối chiếu riêng:

```powershell
.\.venv\Scripts\python.exe -m vn_labor_offline.page_review `
  --archive "D:/data_thô/result_12-10/vn_labor_results.zip" `
  --root . --output artifacts/reviews/page_quality_20261012_new
```

Chỉ sau khi có ZIP build mới đạt validation, tạo pin ONLINE mới và benchmark. Không trộn index/graph V8.1, build ngày 12/10 cũ và build được dựng bằng code mới.
