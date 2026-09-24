# Kiểm tra `source_review_return_v8_1.zip`

Ngày kiểm tra: 2026-09-16

## Kết luận

Gói trả về **dùng được ngay làm dữ liệu đầu vào/seed cho Automatic Legal Source Resolver**. Không được merge trực tiếp vào `config/source_catalog.yaml`, không được đặt `metadata_verified: true` và không được coi các dòng `official_source=YES` là đã duyệt.

Lý do: gói đã tìm được nhiều trang nguồn chính thức nhưng không tải được raw binary trong môi trường thu thập. Vì vậy 95/95 dòng vẫn có `sha_match=NOT_DOWNLOADED`, `downloaded_sha256` trống và `content_match=UNCERTAIN`.

## Kiểm tra cấu trúc và tính toàn vẹn

- ZIP có 3 entry: `source_review_tracking.csv`, `OPEN_QUESTIONS.md` và thư mục rỗng `official_downloads/`.
- Bảng có đúng 95 dòng, đúng bốn nhóm: 57 legal, 24 judicial, 10 supplementary, 4 consolidated.
- Có 95 `relative_path` duy nhất; không thiếu, không thừa, không trùng.
- So với bảng gốc trong `source_review_handoff_v8_1_full.zip`: 0 sai khác ở `relative_path`, `source_group`, `corpus_sha256`, `filename` và `current_candidate_url`.
- Người thu thập đã bổ sung `document_number` cho 31 dòng và `title` cho 34 dòng. Đây là metadata candidate hữu ích nhưng vẫn cần resolver/corpus verifier kiểm lại.
- Trường reviewer và legal decision để trống toàn bộ, đúng phạm vi công việc.

## Mức hoàn thành thực tế

| Chỉ tiêu | Kết quả |
|---|---:|
| Trang nguồn chính xác (`exact_source_url`) | 81/95 |
| Link tải trực tiếp (`direct_download_url`) | 8/95 |
| Có provider | 84/95 |
| Đánh dấu nguồn chính thức | 84/95 |
| `ACCESS_BLOCKED` | 84/95 |
| `SOURCE_NOT_FOUND` | 10/95 |
| `MULTIPLE_CANDIDATES` | 1/95 |
| Đã tải/tính SHA | 0/95 |
| `content_match=YES` | 0/95 |
| Legal review | 0/95 |

Các host được tìm thấy đều thuộc nhóm có thể dùng làm candidate chính thức: VBPL, Cổng Văn bản/Công báo Chính phủ, Cổng công bố bản án/Tòa án, các domain cơ quan nhà nước và ILO. Tuy nhiên authority phải được resolver xác nhận bằng provider registry và final URL sau redirect.

## Các vấn đề quan trọng

### 1. `ACCESS_BLOCKED` chưa có nghĩa website thật sự chặn

Trong gói này, trạng thái đó chủ yếu có nghĩa môi trường của người thu thập không đưa được raw binary vào filesystem. Khi import vào resolver nên ánh xạ các dòng có URL và `official_source=YES` thành `DISCOVERED` hoặc `FETCH_PENDING`, không giữ nó như kết luận website bị chặn. Chỉ chuyển sang `BLOCKED` sau khi HTTP fetcher và Playwright đều thất bại với lỗi đã ghi.

### 2. Chưa có dòng nào đủ điều kiện `AUTO_EXACT_SHA`

`official_source=YES` chỉ xác nhận candidate nằm trên domain được cho là chính thức. Chưa có downloaded SHA, content match hoặc bằng chứng tệp corpus là đúng binary. Resolver phải tải lại, kiểm magic/MIME, SHA và nội dung trước khi nâng trạng thái.

### 3. Có 38 dòng official nhưng identity vẫn chưa chắc chắn

Trong 84 dòng `official_source=YES`, có 38 dòng mà `document_number_match` hoặc `title_match` chưa phải `YES`: 35 legal và 3 supplementary. Các dòng này phải qua metadata normalizer/verifier; không được tự động xác minh chỉ dựa trên domain.

### 4. Schema số văn bản đang dùng hai cột không đồng nhất

57 legal documents dùng `instrument_number`, trong khi 24 judicial records dùng `document_number`. Vì bảng chỉ có `document_number_match`, kết quả có thể không nhất quán giữa hai nhóm. Resolver cần tạo `canonical_identifier` từ trường phù hợp với `source_group`, đồng thời giữ hai trường gốc để audit.

### 5. URL VBPL legacy cần chuẩn hóa

Nhiều candidate giữ `ItemID` và route cũ. Đây là dấu vết tốt để adapter thử `/TW/Pages/vbpq-van-ban-goc.aspx`, `vbpq-thuoctinh.aspx`, `vbpq-toanvan.aspx`, `vbpq-lichsu.aspx` hoặc giao diện mới. Redirect về homepage phải bị coi là fetch thất bại, không phải source match.

### 6. Một URL được dùng cho hai biểu diễn cùng văn bản

Hai file Nghị quyết 326/2016/UBTVQH14 (`.doc` text copy và `.pdf`) cùng trỏ `ItemID=119086`. Đây không phải lỗi trùng record, nhưng cùng trang metadata không chứng minh cả hai binary. Resolver phải xác minh riêng từng file; một trang có thể dẫn tới PDF chính thức nhưng không khớp bản DOC đã sao chép.

### 7. 11 hồ sơ tư pháp cần discovery/review tiếp

Có 10 `SOURCE_NOT_FOUND` và 1 `MULTIPLE_CANDIDATES`, đều thuộc judicial. `OPEN_QUESTIONS.md` ghi rõ từng hồ sơ và nguồn thứ cấp hỗ trợ. Các URL thứ cấp chỉ được dùng để tìm kiếm; không nâng thành nguồn chính thức.

## Cách sử dụng ngay

Các file đã được staging ở:

```text
review/inputs/v8_1/source_review_return_v8_1/
  source_review_tracking.csv
  OPEN_QUESTIONS.md
  official_downloads/
```

Importer của resolver nên dùng bảng này theo ánh xạ:

| Dữ liệu trả về | Trạng thái resolver ban đầu |
|---|---|
| `ACCESS_BLOCKED` + URL official | `DISCOVERED` / `FETCH_PENDING` |
| `SOURCE_NOT_FOUND` | `NEEDS_DISCOVERY` |
| `MULTIPLE_CANDIDATES` | `NEEDS_REVIEW` |
| Có direct URL | ưu tiên download queue |
| Có `ItemID` VBPL | ưu tiên VBPL adapter/canonicalizer |
| Metadata được bổ sung | candidate metadata, cần verifier kiểm |

Thứ tự xử lý:

1. Thử tải 8 direct URL và xác minh SHA trước để kiểm đường ống end-to-end.
2. Chạy adapter/fetcher cho 76 candidate official còn lại.
3. Chuẩn hóa 41 record VBPL/ItemID và phát hiện homepage redirect.
4. Đưa 38 identity-uncertain qua metadata verifier.
5. Dùng discovery adapter cho 11 judicial unresolved.
6. Chỉ xuất `AUTO_EXACT_SHA` khi binary chính thức khớp SHA corpus; mọi khác biệt chuyển review queue.

## Quyết định tích hợp

- **Có thể dùng:** URL candidate, provider, metadata bổ sung, evidence notes, danh sách 11 ngoại lệ và toàn bộ SHA corpus làm resolver seed.
- **Chưa thể dùng như dữ liệu verified:** `official_source=YES` đứng một mình, `ACCESS_BLOCKED`, các nhận định identity còn uncertain và bất kỳ nội dung nào chưa tải/so SHA.
- **Chưa chạy lại pipeline:** staging/import seed không thay graph/index. Chỉ rebuild sau khi resolver tạo kết quả đã xác minh và có quyết định merge vào source catalog/corpus.
