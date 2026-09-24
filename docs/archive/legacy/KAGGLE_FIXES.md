# Bản sửa sau kết quả Kaggle v4 — 14/09/2026

> **Trạng thái cuối:** bản sửa đã được chạy thành công trong `vn_labor_results_V5.zip`. Cả bốn đầu ra và Aura đều PASS; xem [KAGGLE_RESULTS_REVIEW.md](KAGGLE_RESULTS_REVIEW.md). Các bước chạy lại bên dưới chỉ cần dùng khi code hoặc corpus thay đổi.

Gói `vn_labor_results_v4.zip` đã chạy hết pipeline và nạp Aura thành công, nhưng chưa đạt OFFLINE v1 vì validation còn lỗi metadata, một tài liệu scan bị timeout và các lỗi cấu trúc phát sinh từ phần trích xuất đó. Những vấn đề này đã được sửa và xác nhận bằng kết quả V5.

## Kết quả kiểm tra v4

- ZIP hợp lệ, SHA-256: `77e1310ce2e9b1b9ebdcd7f200a9886ed31cf069eea04578a72c469b52cc5bb7`.
- 95 documents, 8.536 provisions, 24 cases, 7.410 diagnostic items.
- Graph v4 có 16.611 node và 30.677 cạnh; ID và đầu mút cạnh hợp lệ.
- Dense v4 có 8.768 vector × 1.024 chiều; thứ tự metadata khớp retrieval units, vector hữu hạn và đã chuẩn hóa.
- BM25 v4 nạp và truy vấn được; corpus khớp retrieval units.
- Aura v4 đã nạp và audit thành công.
- Tài liệu `145-2020-ND-CP_Huong-dan-BLLD.pdf` bị timeout sau 600 giây, khiến `NO_MACHINE_TEXT`, `MISSING_PAGE_PROVENANCE` và nhiều lỗi cấu trúc dây chuyền.

## Những phần đã sửa

1. Bổ sung metadata đã đối chiếu nguồn chính thức cho toàn bộ văn bản pháp luật còn thiếu trong v4. Review cô lập hiện không còn `UNKNOWN_LEGAL_STATUS`, `MISSING_EFFECTIVE_FROM`, `UNVERIFIED_METADATA`, `UNVERIFIED_TEMPORAL_METADATA`, thiếu issuer, ngày ban hành, số hiệu hoặc URL nguồn.
2. Thay phần trích xuất của Nghị định 145/2020/NĐ-CP bằng bản Công báo chính thức gồm hai phần, ghép thành một PDF 142 trang có chữ máy. Liên kết được khóa bằng SHA-256; file gốc trong corpus và định danh tài liệu vẫn giữ nguyên.
3. Trang 95 của PDF Công báo được xác nhận không có nội dung; trang 111–112 là biểu mẫu xoay ngang và được xoay 90 độ trước OCR. Kết quả kiểm tra riêng có 246.486 ký tự, đủ provenance 142 trang và không có lỗi trích xuất.
4. Parser chấp nhận thêm một số lỗi OCR ở tiêu đề “Điều”, xử lý trích dẫn sửa đổi có ngoặc kép lồng nhau, và cách ly riêng các nhánh bị trùng canonical path. Các nhánh hợp lệ vẫn được giữ trong Structured Provisions.
5. Cache checkpoint được kiểm tra theo từng tài liệu và SHA. Với chính ZIP v4, **94/95 tài liệu được tái sử dụng**; chỉ Nghị định 145/2020/NĐ-CP phải trích xuất lại. Không cần OCR lại toàn bộ corpus.
6. Pipeline thử lại worker tối đa ba lần nếu một tài liệu chạm timeout; page cache giúp tiếp tục các trang còn lại.

## Review cô lập sau sửa

Review dùng dữ liệu v4, metadata mới và kết quả trích xuất đã xác minh của Nghị định 145, chưa dựng lại index và chưa kết nối Aura:

| Chỉ tiêu | v4 | Sau sửa, review cô lập |
|---|---:|---:|
| Documents | 95 | 95 |
| Provisions được chấp nhận | 8.536 | 18.445 |
| Diagnostic items | 7.410 | 15.314 |
| Graph nodes | 16.611 | 34.425 |
| Graph edges | 30.677 | 61.994 |
| Lỗi metadata/extraction nghiêm trọng | Có | 0 |

Review còn 32 cảnh báo `AMBIGUOUS_CANONICAL_PATH_QUARANTINED` và 4 cảnh báo `SHORT_PROVISION_QUARANTINED`. Đây là các nhánh nguồn mơ hồ/ngắn đã bị cách ly, không phải lỗi cấu trúc nghiêm trọng trong graph được xuất. Ba ERROR `MISSING_DENSE_INDEX`, `MISSING_BM25_INDEX`, `NEO4J_BUILD_NOT_VERIFIED` chỉ xuất hiện vì review cô lập chủ ý không dựng index và không gọi Aura; lần chạy Kaggle mới sẽ kiểm tra ba phần này.

Toàn bộ **77/77 kiểm thử PASS**. Kết quả review máy đọc được nằm tại `artifacts/review_kaggle_v4/reports/comparison.json`.

## Bạn làm tiếp trên Kaggle

### A. Tạo hai Dataset Private

1. Mở Dataset nguồn cũ **VN Labor Offline Private** và tạo version mới bằng file `kaggle_upload/vn_labor_kaggle.zip` của bản sửa này.
2. Tạo một Dataset Private thứ hai, ví dụ **VN Labor Checkpoint V4**.
3. Upload `C:\Users\Acer\Downloads\vn_labor_results_v4.zip` vào Dataset checkpoint đó. Không giải nén và không đổi nội dung ZIP trước khi upload.

### B. Tạo Notebook mới

1. Import `kaggle_upload/VN_Labor_Kaggle.ipynb`.
2. Trong **Add Input**, thêm đúng hai Dataset: Dataset nguồn phiên bản mới và Dataset checkpoint v4.
3. Bật **GPU T4 x2** và **Internet**.
4. Bảo đảm bốn Secrets cũ đã được cấp quyền cho Notebook: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
5. Trong cell tham số đặt:

   ```python
   RUN_PIPELINE = True
   LOAD_AURA = True
   RESTORE_ARCHIVE = "AUTO"
   ```

   `AUTO` sẽ tìm đúng một Dataset checkpoint. Nếu cell báo tìm thấy 0 hoặc nhiều hơn 1, hãy gỡ Dataset checkpoint thừa rồi chạy lại.

### C. Chạy và lấy kết quả

1. Chọn **Save Version → Save & Run All** một lần.
2. Không bấm Stop Session khi tiến trình đang chạy. Bạn có thể đóng tab trình duyệt; phiên chạy nền vẫn tiếp tục.
3. Chờ đủ các dòng: `run_all_offline.log exit code: 0`, `kaggle_audit.log exit code: 0`, `neo4j_load.log exit code: 0` và `Aura: đã nạp và chạy audit`.
4. Mở version đã hoàn tất → **Output** → tải `vn_labor_results.zip`.
5. Gửi ZIP mới để kiểm tra độc lập bốn đầu ra cuối.

Kết luận OFFLINE v1 chỉ được đưa ra khi báo cáo mới ghi cả bốn phần `registry`, `structure`, `graph`, `indexes` đều PASS. Mã thoát pipeline 0 riêng lẻ chưa đủ.

## Nguồn chính thức tiêu biểu

- [Thông tư 08/2026/TT-BNV — Công báo](https://congbao.chinhphu.vn/van-ban/thong-tu-so-08-2026-tt-bnv-469695.htm)
- [Thông tư 09/2026/TT-BNV — Công báo](https://congbao.chinhphu.vn/van-ban/thong-tu-so-09-2026-tt-bnv-469696.htm)
- [Nghị định 10/2024/NĐ-CP — Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?classid=0&docid=209657&pageid=27160)
- [Nghị định 145/2020/NĐ-CP — Cơ sở dữ liệu quốc gia về văn bản pháp luật](https://vbpl.vn/Toaannhandantoicao/Pages/vbpq-toanvan.aspx?ItemID=152668)
- [Trang tải Công báo Nghị định 145/2020/NĐ-CP](https://congbao.chinhphu.vn/van-ban-dang-cong-bao/nghi-dinh-l1/trang-123.htm)
