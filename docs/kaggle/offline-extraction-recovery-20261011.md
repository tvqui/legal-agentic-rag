# Sửa lỗi extraction từ recovery Kaggle — 11/10/2026

Sửa trực tiếp source trong `D:/data_thô/legal-agentic-rag`. Không sửa corpus hoặc ZIP recovery gốc.

## Nguyên nhân đã xác nhận

Recovery có đủ 95 documents và 3.116 pages; worker không timeout/OCR fail.
`extraction_integrity.json` thất bại vì đúng một trang có `EMPTY_AFTER_CLEANING`:
trang 5 của `judicial_corpus/cassation_decisions/02-2021-LĐ-GĐT.pdf`.
Native và OCR đều nhận đúng ký tự `5`; số này bị bỏ khi cleaning.
Đã đối chiếu SHA file gốc và xem cả ảnh nguồn/ảnh preview: trang chỉ có số trang ở lề trên.
Không có ảnh, vector hoặc nội dung bản án bị bỏ.

## Thay đổi

- `extract.py`: lưu bằng chứng số trang, hộp text, chiều cao trang, số ảnh/vector.
- `page_quality.py`: chỉ miễn lỗi mất nội dung nếu đúng số trang vật lý, native/OCR khớp,
  tất cả text nằm ở lề và không có ảnh/vector. Ghi `PAGE_NUMBER_ONLY_REMOVED`, giữ REVIEW_REQUIRED.
- `quality.py`: cùng kiểm chứng hình học và SHA text ở audit downstream; không tin chỉ một nhãn.
- `integrity.py`: log ngắn có path/page/reason_codes khi thất bại.
- `test_pagination_quality.py`: số ở giữa trang, scan/vector, số sai, mất body và OCR fail vẫn bị chặn;
  SHA evidence bị đổi không vượt audit downstream.

Không thay extraction schema/settings/cache keys vì OCR/cleaning semantics không đổi.
Không thêm reviewer, không bỏ gate mất nội dung và không hạ lỗi OCR thành PASS.

## Kiểm chứng

- Toàn repository: 454 tests PASS; compileall PASS; diff whitespace check PASS.
- Replay extraction trong thư mục tạm từ ZIP recovery thật, không gọi OCR/model/GPU/network:
  dùng lại 94 document caches, xử lý lại một document từ page cache, 95 documents/3.116 pages.
- Text của cả 95 documents bằng nguyên văn recovery; 0 ERROR pages;
  174 REVIEW_REQUIRED, 2.927 PASS, 15 REVIEWED có sẵn.
- Không có INCOMPLETE_PAGE_EXTRACTION/PAGE_EXTRACTION_QUALITY_FAILED ở audit downstream.
- Chưa chạy Dense/BM25/AI/Aura hoặc toàn OFFLINE trên Kaggle với bản này.

Báo cáo: `artifacts/reports/offline_recovery_replay_20261011.json`,
`offline_pagination_tests_20261011.log`, `offline_pagination_validation_20261011.json`.

## Chạy tiếp

1. Cập nhật Private Dataset code bằng `build/kaggle/vn_labor_kaggle_v8.zip` mới.
2. Tạo Private Dataset checkpoint từ `D:/data_thô/vn_labor_results_recovery.zip`.
3. Import `build/kaggle/VN_Labor_Kaggle_V8.ipynb` mới.
4. Chỉ gắn code mới và recovery, gỡ checkpoint V8.1 cũ để AUTO không chọn nhầm/nhiều checkpoint.
5. Giữ REFRESH_EXTRACTION_QUALITY=True và settings OCR/cleaning mặc định.
6. Đợi Aura Running nếu LOAD_AURA=True. Bật Internet, GPU T4 x2 và cấp Secrets.
7. Save & Run All với session mới; không restore đè thư mục artifacts sẵn có.

Khả năng dùng lại cache đã được xác minh trên CPU, không bảo đảm môi trường Kaggle không gặp
lỗi Internet/GPU/Dense/AI khác. Recovery chưa phải build mới đã vượt đầy đủ audit để chuyển ONLINE.
