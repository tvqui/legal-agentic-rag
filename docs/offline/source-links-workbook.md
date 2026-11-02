# Excel cập nhật link nguồn dùng lại cho OFFLINE

File đã tạo: `review/link_updates/PhapDienAI_Cap_nhat_link_nguon_20261027.xlsx`.

Đủ **95 tài liệu**, gồm văn bản luật/hợp nhất, bản án và tài liệu bổ sung; **4 hồ sơ tải PDF đính kèm**. File liên kết với artifact `result_14-10`, SHA `895db689d0cb60f6a76042a70452cedadfb80151bc1d9818b1cb54c182d19071`. Không tự áp dụng URL gợi ý và không thay cấu hình hiện tại khi chỉ tạo Excel.

## Bạn chỉ cần điền gì?

1. Mở sheet **DIEN_LINK_MOI**.
2. Tìm tài liệu theo số/ký hiệu, tên và file gốc. Điền URL mới vào **cột F màu vàng**.
3. Mở URL, đối chiếu đúng văn bản/phiên bản rồi chọn **DA_DOI_CHIEU ở cột G**. Chưa chắc thì giữ CHUA_DOI_CHIEU và ghi chú ở H.
4. Lưu thành bản riêng, ví dụ `PhapDienAI_Link_nguon_da_dien.xlsx`, rồi gửi lại để áp dụng trước khi đóng gói/chạy OFFLINE.

**Để trống link mới = giữ nguyên link cũ.** Không cần điền lại 95 link nếu chỉ đổi vài mục. Không xóa/thêm dòng, sửa số văn bản, mã hồ sơ, file hoặc SHA; các ô này được khóa để tránh nhầm. Bộ lọc vẫn dùng được. Ô vàng chuyển xanh khi có link và xác nhận.

## Các sheet

| Sheet | Chứa gì? | Cần điền? |
| --- | --- | --- |
| HUONG_DAN | Cách điền, số lượng, artifact gốc và SHA | Không |
| DIEN_LINK_MOI | Tên/số văn bản, nhóm, link cấu hình, URL gợi ý chưa duyệt, file nguồn | F, G và ghi chú H nếu cần |
| LINK_TAI_FILE | 4 nguồn PDF dùng để trích xuất, kể cả tài liệu tải nhiều phần | Chỉ khi đổi URL tải file: E, F, ghi chú G; mỗi URL một dòng |
| THONG_TIN_DATA | File, SHA, ngày ban hành/hiệu lực theo metadata, cơ quan, số đơn vị điều khoản, link artifact và PDF đính kèm | Không; dùng đối chiếu |

Link ở **DIEN_LINK_MOI** là trang mô tả/thuộc tính/toàn văn chính xác để dẫn nguồn. Link ở **LINK_TAI_FILE** là đường dẫn tải file; hai loại không nhất thiết giống nhau. Cột gợi ý không phải kết quả đã xác minh. Trang chủ, trang danh sách hoặc kết quả tìm kiếm không thay thế được URL một văn bản cụ thể.

Ngày/hiệu lực hiện trong sheet là metadata đang lưu, chưa phải kết luận pháp lý đã được duyệt. `DA_DOI_CHIEU` chỉ xác nhận link bạn đã xem; không tự tạo human legal approval.

## Dùng lại công cụ về sau

Chạy tại thư mục dự án, dùng venv của dự án. Thư viện Excel được khai báo bằng extra `review`:

```powershell
python -m pip install -e ".[review]"
```

Xuất biểu mẫu mới cho đúng build hiện có, không ghi đè file đã điền:

```powershell
python scripts/source_links_workbook.py export `
  --artifact "D:/data_thô/result/result_14-10/vn_labor_results.zip" `
  --seed review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv `
  --output review/link_updates/Bieu_mau_link_MOI.xlsx
```

`--seed` chỉ cung cấp URL gợi ý từ hồ sơ cũ có cùng SHA, có thể bỏ nếu không có file này. Công cụ xuất theo manifest thực, không cố định phải là 95 tài liệu.

Xem thử thay đổi từ file đã điền; **chưa sửa cấu hình**:

```powershell
python scripts/source_links_workbook.py import `
  --artifact "D:/data_thô/result/result_14-10/vn_labor_results.zip" `
  --workbook review/link_updates/PhapDienAI_Link_nguon_da_dien.xlsx `
  --output review/link_updates/preview_LAN_1
```

Đọc `import_report.json`, `changes.diff` và các YAML dự kiến. Khi áp dụng, dùng **thư mục output khác** để giữ lịch sử:

```powershell
python scripts/source_links_workbook.py import `
  --artifact "D:/data_thô/result/result_14-10/vn_labor_results.zip" `
  --workbook review/link_updates/PhapDienAI_Link_nguon_da_dien.xlsx `
  --output review/link_updates/applied_LAN_1 `
  --apply
```

Công cụ chỉ cập nhật link đã điền và có DA_DOI_CHIEU. Nó:

- Đối chiếu artifact, đường dẫn, SHA file và cột nhận diện; không tự chấp nhận Excel của build khác.
- Cập nhật `source_catalog.yaml`; đồng bộ URL trang văn bản trong `source_attachments.yaml` nếu tài liệu có PDF đính kèm. URL tải file chỉ đổi khi bạn điền sheet tương ứng.
- Giữ bản YAML trước/sau và diff, phục hồi cấu hình đã ghi nếu có lỗi ghi giữa chừng. Các thư mục output cũ không bị ghi đè.
- Không sửa file PDF, SHA, nội dung luật, ngày hiệu lực, `metadata_overrides.yaml` hay artifact ZIP. Không tải URL hoặc tự kiểm tra xem URL còn hoạt động.
- Không mang approval nguồn cũ sang URL mới: thông tin duyệt nguồn cũ được bỏ khỏi mục đã đổi link, `official_source=false` cho tới khi nguồn mới được kiểm chứng theo quy trình. Các trường ngày/hiệu lực hiện có được giữ nguyên.

Nếu file tải ở URL mới khác nội dung/nhị phân cũ, phải kiểm tra và chuẩn bị lại PDF cùng SHA; không sửa SHA cho qua chỉ vì URL mở được.

## Trước khi chốt OFFLINE

Excel là công cụ điền/nhập cấu hình, **không phải Kaggle Input hay artifact ONLINE**. Sau khi nhập link, đóng gói code mới bằng `python scripts/package_kaggle.py`, dùng package đó cho lần dựng OFFLINE tiếp theo. Chỉ nhập Excel mà vẫn dùng package/artifact cũ thì chatbot vẫn trả link cũ.

Chỉ đổi URL không bắt buộc OCR lại, nhưng cần dựng metadata/graph/index liên quan cho đồng bộ và giữ cache AI đúng nguồn. Không dùng AI-resume trên ZIP cũ để kỳ vọng nó đọc URL mới từ YAML. Nếu đồng thời áp dụng sửa OCR thì dùng quy trình Quality Refresh đã hướng dẫn.

Sau khi chốt artifact mới, xuất biểu mẫu mới cho build đó. Đừng sửa baseline/SHA ẩn để tái sử dụng một biểu mẫu đã lỗi thời.
