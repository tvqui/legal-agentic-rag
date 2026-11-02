> Cập nhật sau khi nhận Excel: dùng package revision **20261027-source-links-v3** và làm theo [hướng dẫn link nguồn mới](source-links-applied-20261027.md). Hiện 84/95 tài liệu có link; 11 bản án còn thiếu nguồn.

# Hoàn thiện dữ liệu và chạy Kaggle — 27/10/2026

## Đã làm và giới hạn còn lại

Đã sửa code OFFLINE trong dự án chính; gói code mang revision `20261027-source-accounting-v2`. Bản `result_14-10` gốc được giữ nguyên, SHA-256 `895db689d0cb60f6a76042a70452cedadfb80151bc1d9818b1cb54c182d19071`. Chưa có lần chạy GPU/Kaggle mới trong lượt sửa này; không thể cam kết dịch vụ bên ngoài không bao giờ lỗi.

| Phần | Kết quả thực hiện | Chưa được phép kết luận |
| --- | --- | --- |
| AI | Thêm theo dõi từng đoạn nguồn, xử lý tiếp theo trạng thái MORE, giới hạn số trang/lượt; kiểm thử preflight schema thật trước job dài; sửa stop_reason khi không còn đủ thời gian cho một request | Chưa có số liệu AI_COMPLETE/chất lượng sau lần chạy GPU mới |
| OCR | Đối chiếu máy toàn bộ 174 trang với PDF đúng SHA, dựng đủ ảnh/diff; kiểm tra ảnh trực tiếp trang chỉ có số 5 và trang 13 NĐ 140/2018; bổ sung bản chép trang 13 để khôi phục tiêu đề Điều 3 bị mất | Không coi tất cả trang đã được người duyệt; bản chép AI vẫn REVIEW_REQUIRED |
| Cách ly | Kiểm đếm 896 bản ghi thực, 553 nhóm vị trí từ 33 cảnh báo mơ hồ và 9 cảnh báo ngắn; xuất đầy đủ nội dung | Không tự đưa chúng lại vào graph khi chưa giải quyết xung đột |
| Nguồn/hiệu lực | Lập 95 hồ sơ nguồn khớp SHA, 25 hồ sơ thay đổi kèm nguyên văn; lấy thêm URL ứng viên từ catalog/seed đúng SHA; kiểm tra truy cập trang chính thức | Không tự tạo 95 approval hay áp 25 thay đổi chưa được duyệt |
| Cập nhật | Tìm và tải PDF chính thức ứng viên 27/2026/TT-BNV; phân biệt ngày ban hành 20/10/2026 và ngày hiệu lực 01/01/2027 | Chưa nhập vào corpus, không áp dụng như luật đã hiệu lực năm 2026 và không đổi ngày chốt lên hôm nay |
| Gold | Xuất 100 câu kèm đáp án, nhóm căn cứ, nguyên văn, URL và cảnh báo; không có nhóm ID đã gán nào mất khỏi build | Khớp ID chưa chứng minh đủ/đúng pháp lý. Tất cả ngày hỏi sau 15/09/2026; 9 câu có lưu ý annotation từ trước. Gold vẫn DRAFT |

### Cơ chế AI mới khác gì?

Nhánh cũ coi trả đủ 4 mục là bão hòa rồi chia lại nguồn, tạo nhiều cây request và lỗi capacity dù model đã trả hết. Nhánh mới chia nguồn thành các excerpt không bỏ đuôi, mặc định tối đa 4 excerpt/cửa sổ và 4 trang trả kết quả/cửa sổ. Model phải đối soát từng excerpt bằng EXTRACTED, NO_ITEM hoặc MORE. EXTRACTED phải có mục hiện tại/trước đó; NO_ITEM không được đồng thời chứa mục; mọi mục phải thuộc đúng excerpt.

Code mở quote ID thành nguyên văn, kiểm schema, đối soát chỉ mục và giữ nguồn/offset. MORE mới tạo lượt tiếp theo; lặp không tiến triển hoặc chạm giới hạn vẫn ghi lỗi rõ ràng. Cache từng trang được dùng lại khi tiếp tục; ledger sai bị vô hiệu để có thể sửa ở phiên sau. Dữ liệu/cache legacy giữ nguyên, nhưng không dùng chúng để tự chứng nhận đã đối soát v2.

`SOURCE_ACCOUNTING_NOT_LEGAL_APPROVAL` chỉ có nghĩa các đoạn nguồn được xử lý theo giao thức; model vẫn có thể bỏ ý hoặc hiểu sai. Các gate provenance, grounding và duyệt pháp lý tiếp tục tồn tại. Không tăng giới hạn lên 2.000 provision ngay.

## 1. Chọn đúng notebook

Các file trong `build/kaggle/`:

- **`VN_Labor_Quality_Refresh.ipynb`**: dùng khi muốn áp dụng sửa OCR mới, rồi dựng lại structure/knowledge/graph/indexes và chạy AI. Đây là bản nên chạy để tạo dữ liệu mới từ những sửa đổi lần này.
- **`VN_Labor_Kaggle_V8.ipynb`** (alias `ai-v9-1.ipynb`): chỉ tiếp tục AI trên checkpoint đang có. Nhanh hơn vì không OCR/dựng Dense lại, nhưng **không áp dụng sửa OCR trang 13** vào text/index của checkpoint cũ.
- **`vn_labor_kaggle_v8.zip`**: package code/corpus mới dùng cho cả hai notebook. Phải thay package cũ trên Kaggle bằng bản mới, không chỉ import notebook mới.
- Các file `.sha256`: dùng đối chiếu tải lên/tải xuống, không phải Input bắt buộc riêng.

Không chạy đồng thời hai notebook để tránh trùng phiên/Aura/GPU quota.

## 2. Kaggle: chuẩn bị một lần cho mỗi phiên

1. Tạo hoặc mở notebook riêng cho OFFLINE, import `VN_Labor_Quality_Refresh.ipynb`.
2. Chọn **GPU T4 x2**, bật **Internet**.
3. Add Input: Dataset package chứa **ZIP code mới**; Dataset kết quả chứa **`result_14-10/vn_labor_results.zip`**. Chỉ gắn một bản package và một bản kết quả. Kaggle có thể tự giải nén chúng thành thư mục; notebook hỗ trợ cả hai.
4. Trong Add-ons → Secrets, cấp quyền cho `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Aura phải hoạt động; preflight sẽ kiểm trước bước dài.
5. Giữ `OFFLINE_AI_MAX_PROVISIONS = 250`, `OFFLINE_AI_TIMEOUT_SECONDS = 240`, `LOAD_AURA = True`. Notebook refresh đã đặt `RESUME_AI_ONLY = False`, `REFRESH_EXTRACTION_QUALITY = True` sẵn.
6. Chọn **Save Version → Save & Run All**. Đầu notebook đã cài `apt-get update -y` và `apt-get install -y zstd`.

Notebook kiểm revision, hash package, checkpoint và môi trường; Python 3.12/3.13 được bootstrap hỗ trợ. Runtime Linux/GPU và tải model vẫn cần chạy thật trên Kaggle; kiểm thử local không thay thế bước đó. Gói có sẵn code nên **không cần git push để job OFFLINE dùng được bản sửa này**.

## 3. Hiểu log và tải đúng đầu ra

- `AI_PREFLIGHT`: kiểm sao chép quote và giao thức source-accounting-v2. Nếu probe mới thất bại, sửa lỗi được báo trước khi để chạy nhiều giờ; không xóa probe để chạy cho qua.
- `AI_REQUEST ... source_accounting`: số excerpt đã đối soát, số mục nhận, đoạn còn chờ; không phải phần trăm chính xác pháp lý.
- `AI_CONTINUATION_NO_PROGRESS` / `AI_CONTINUATION_PAGE_LIMIT`: vẫn còn thiếu hoặc model lặp. Không tự coi complete.
- `AI_STAGE_BUDGET_EXHAUSTED`: ngân sách không đủ cho request tiếp; cache và mục đã khớp nguồn được giữ. Không có nghĩa OCR hay mạng đã hỏng.
- `AI_COMPLETE` nếu có: trạng thái xử lý theo gate kỹ thuật, không phải chuyên gia đã duyệt toàn bộ nội dung.

Đầu ra cần tải: `vn_labor_results.zip` + SHA và toàn bộ báo cáo. Nếu job thất bại, tải `vn_labor_results_recovery.zip` + SHA; dùng recovery làm checkpoint phiên tiếp theo với notebook **AI-resume** nếu đã qua rebuild kỹ thuật. `vn_labor_results_technical_checkpoint.zip` là mốc trước AI, không phải kết quả AI cuối.

Không ghép graph/index từ build cũ vào text đã sửa. Dùng công cụ pin artifact để chọn ZIP mới cho ONLINE và kiểm compatibility; Gold phải ánh xạ/duyệt lại nếu ID hoặc nội dung thay đổi.

## 4. Hồ sơ đã chuẩn bị để duyệt

Gói `build/review/final_data_20261027/final_data_review_20261027.zip` chứa:

- `pages/index.html`: đủ 174 ảnh, native/OCR/cleaned và diff; `page_review_tracking.csv` để ghi quyết định.
- `reconciled/source_review.jsonl`: 95 hồ sơ; ứng viên URL nêu rõ lấy từ catalog/seed nào và chỉ dùng khi SHA nguồn khớp.
- `reconciled/temporal_changes_review.jsonl`: 25 thay đổi, có nguyên văn đầy đủ; không chỉ trích đoạn đầu.
- `reconciled/quarantine_review.jsonl`: 896 hàng cách ly, nhóm theo vị trí để đối chiếu.
- `reconciled/gold100_review.html` và JSONL: 100 câu cùng đáp án/căn cứ đã gán.
- `official_final/results.jsonl`: kết quả đọc URL chính thức, final URL và SHA response; có phân biệt trang truy cập được nhưng chưa xác nhận đúng văn bản.
- `update_candidates/`: PDF và metadata ứng viên mới, tách khỏi corpus đang dùng.
- `page13_correction_verification.json`: thử bản chép với PDF thật; trạng thái trang vẫn chờ duyệt.

Lượt kiểm URL này: 12 hồ sơ có số văn bản xuất hiện trên trang, 64 chưa xác nhận được danh tính, 6 lỗi truy cập, 13 thiếu URL chính thức phù hợp. Đây là **ứng viên đối chiếu**, không phải 12 nguồn đã được duyệt. Các URL VBPL cũ có thể trả HTTP 200 nhưng chuyển về trang chủ; giữ nguyên bằng chứng chuyển hướng để tìm lại nguồn, không ghi VERIFIED cho qua.

Người duyệt cần ghi danh tính/ngày duyệt thật, quyết định và căn cứ. Không tự đổi 0/95 thành 95/95, không duyệt nguyên gói 18.871 khoảng hiệu lực theo ngày của văn bản nếu chưa kiểm được điều khoản sửa đổi/chuyển tiếp.

## 5. Chạy lại công cụ sau mỗi lần đổi dữ liệu

Từ thư mục dự án (đường dẫn output phải là thư mục mới):

```powershell
.\.venv\Scripts\python.exe scripts/audit_final_dataset.py `
  --artifact "D:/data_thô/result/result_14-10/vn_labor_results.zip" `
  --snapshot-as-of 2026-09-15 `
  --gold-archive gold_dataset/result/evaluation_20261023T121029Z.zip `
  --annotations benchmarks/evaluation_suite/gold100_annotation_notes.json `
  --catalog config/source_catalog.yaml `
  --source-seed review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv `
  --output artifacts/reviews/final_dataset_NEW

.\.venv\Scripts\python.exe scripts/check_official_sources.py `
  --input artifacts/reviews/final_dataset_NEW/source_review.jsonl `
  --output artifacts/reviews/final_dataset_NEW/official_sources
```

`--snapshot-as-of` là mốc bao phủ pháp luật đã xác định, không phải ngày bấm Run All hay ngày tải ZIP. Lệnh đầu không gọi model/mạng, không sửa corpus/Gold. Lệnh sau đọc trang công khai với giới hạn timeout/bytes và lưu response; không tự tạo approval.

## 6. Kiểm chứng và việc còn cần hoàn tất

261 tests OFFLINE đạt, gồm 24 tests mới cho tiếp tục AI, preflight, audit dữ liệu, URL và bản chép nguồn. Đã thử bản chép trang 13 trên PDF thật mà không chạy OCR/GPU hoặc thay artifact sản xuất. Hash bản chép dùng UTF-8/LF để không lỗi vì Git đổi CRLF trên Windows. Các test có model giả lập nhằm kiểm giao thức/lỗi/khôi phục, không chứng minh Qwen sẽ đối soát đúng mọi đoạn.

Việc còn lại sau khi chạy Kaggle: đọc report AI/coverage mới; xử lý các đoạn vẫn partial; duyệt các trang/căn cứ chưa rõ; kiểm hiệu lực và Gold rồi đo lại ONLINE. Bản nâng cấp này giúp phát hiện/khắc phục lỗi có bằng chứng và tiếp tục công việc an toàn, **chưa biến toàn bộ bộ dữ liệu thành bản hoàn thiện đã kiểm chứng pháp lý**.

## Nguồn cập nhật đã kiểm tra

- [Cổng Chính phủ: 27/2026/TT-BNV](https://vanban.chinhphu.vn/?classid=0&docid=220049&pageid=27160), [PDF chính thức](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/10/27-bnv.signed.pdf): ngày ban hành và hiệu lực phải phân biệt; ứng viên chưa nhập corpus.
- [Công báo: VBHN 18/VBHN-VPQH](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm): hồ sơ nền để đối chiếu Bộ luật Lao động hợp nhất.
- [Bộ Nội vụ ngày 21/10/2026](https://moha.gov.vn/tin-tuc/chinh-phu-trinh-quoc-hoi-xem-xet-cho-y-kien-04-du-an-luat-ve-lao-dong-bao-hiem-xa-hoi-va-dan-chu-o-co-so---id19766): thông tin trình dự án luật, không tự biến nội dung dự thảo thành quy định đã hiệu lực.
