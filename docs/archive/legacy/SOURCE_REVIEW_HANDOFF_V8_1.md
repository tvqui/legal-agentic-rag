# Bàn giao công việc Bước 1 — kiểm nguồn cho 95 tài liệu V8.1

## 1. Mục tiêu và giới hạn công việc

Mục tiêu là tạo hồ sơ nguồn có thể kiểm tra lại cho **đúng 95 file** đang dùng trong build V8.1: tìm trang nguồn và tệp tải chính thức, so sánh với file trong corpus, ghi URL/cơ quan/ngày thu thập/SHA và mô tả bằng chứng. Công việc này xác minh **nguồn gốc file**, không tự kết luận toàn bộ nội dung pháp luật đang có hiệu lực hoặc phê duyệt dữ liệu cho hệ thống.

Người thực hiện có thể làm vai trò **người thu thập nguồn**. Nếu không phải người có chuyên môn pháp lý được giao duyệt, không điền `APPROVED`, không tự nhận là `reviewer`, không đổi `metadata_verified` thành true và không sửa `config/source_catalog.yaml`. Kết quả được gửi lại dưới dạng bảng thu thập; người phụ trách dự án và reviewer sẽ kiểm lần hai trước khi tích hợp.

## 2. Gói cần gửi cho người thực hiện

Gửi **một file duy nhất**:

`review_packages/source_review_handoff_v8_1_full.zip`

Gói này có:

- `README_SOURCE_REVIEW.md`: bản hướng dẫn này.
- `source_review_tracking.csv`: bảng 95 dòng cần điền; đây là file kết quả chính.
- `corpus_manifest.jsonl`: đường dẫn, SHA-256, nhóm nguồn và thông tin file của build V8.1; chỉ để đối chiếu.
- `source_catalog_current_reference.yaml`: metadata/URL hiện có; đây là candidate, không phải kết luận đã duyệt.
- `source_catalog_review_draft_reference.yaml`: bản nháp 95 nguồn hiện tại; chỉ để tham khảo.
- `corpus/`: đúng 95 file nguồn theo cấu trúc thư mục của dự án.
- `PACKAGE_REPORT.json`: số file corpus và thông tin tạo gói. SHA-256 của ZIP nằm trong file `.sha256` gửi cạnh ZIP.

Không cần gửi toàn bộ repository, ZIP kết quả Aura, model BGE-M3, Dense/BM25 indexes, `.env`, Kaggle Secrets hay mật khẩu Neo4j. Nếu không gửi được ZIP lớn, có thể gửi năm mục đầu cùng thư mục `data/judicial_corpus`, `data/legal_corpus` và `data/supplementary_corpus`, nhưng phải giữ nguyên cấu trúc đường dẫn và đủ đúng 95 file trong manifest.

Corpus có thể chứa tài liệu không phù hợp để công khai. Chỉ chia sẻ riêng với người được giao việc và không đưa gói lên Git/public drive.

## 3. File được phép sửa và quy tắc an toàn

Chỉ sửa `source_review_tracking.csv`. Có thể dùng Excel, LibreOffice Calc hoặc VS Code. Khi lưu bằng Excel/Calc, chọn **CSV UTF-8**, giữ nguyên hàng tiêu đề và không đổi tên/cấu trúc cột.

Không sửa, đổi tên, chuyển đổi, nén lại hoặc ghi đè file trong `corpus/`. Tệp tải từ website phải lưu trong một thư mục riêng do người thực hiện tạo, ví dụ `official_downloads/`. Không chép tệp tải mới đè lên corpus, kể cả khi cho rằng tệp mới “đúng hơn”.

Không xóa hàng, thêm hàng, sắp xếp làm mất liên kết, sửa `relative_path`, `source_group` hoặc `corpus_sha256`. Bảng trả lại phải có đúng 95 hàng và mỗi `relative_path` xuất hiện một lần.

## 4. Nguồn được ưu tiên

Tìm bằng số/ký hiệu văn bản, tên văn bản và cơ quan ban hành. Thứ tự ưu tiên:

1. Trang/tệp của cơ quan ban hành hoặc cơ quan có thẩm quyền công bố.
2. Cơ sở dữ liệu quốc gia về văn bản pháp luật: `https://vbpl.vn/`.
3. Công báo điện tử: `https://congbao.chinhphu.vn/`.
4. Hệ thống văn bản Chính phủ: `https://vanban.chinhphu.vn/`.
5. Với bản án/quyết định/án lệ: cổng công bố của Tòa án nhân dân hoặc nguồn chính thức của cơ quan tư pháp tương ứng.
6. Với tài liệu ILO: trang chính thức thuộc `ilo.org`.

Không dùng blog, diễn đàn, website tổng hợp thương mại hoặc trang tải lại làm `exact_source_url` nếu có thể tìm bản chính thức. Có thể ghi một trang thứ cấp trong `evidence_notes` để hỗ trợ tìm kiếm, nhưng `official_source` phải là `NO` và `collection_result` chưa được coi là hoàn tất nếu nguồn chính thức còn thiếu.

## 5. Quy trình bắt buộc cho từng dòng

### 5.1 Xác định file và văn bản

Mở file tại `corpus/<relative_path>`. Đối chiếu tên/số ký hiệu, loại văn bản, cơ quan, ngày ban hành, tiêu đề và số trang với các cột gợi ý trong bảng. `current_candidate_url` chỉ là manh mối ban đầu; phải mở và kiểm tra, không sao chép URL vào kết quả mà chưa xem.

### 5.2 Tìm hai loại URL

- `exact_source_url`: trang chi tiết chính thức mô tả đúng văn bản/tài liệu.
- `direct_download_url`: link tải trực tiếp đúng PDF/DOC/DOCX/HTML nếu trang cung cấp. Nếu website không có link tải riêng, để trống và giải thích trong `evidence_notes`.

Cả hai URL phải dùng HTTPS. Không dùng URL trang kết quả tìm kiếm khi đã có trang chi tiết. Nếu trang có nhiều phần Công báo/tệp đính kèm, ghi đầy đủ các link cần thiết trong `evidence_notes` và nêu corpus tương ứng với phần nào.

### 5.3 Tải candidate vào thư mục riêng và tính SHA-256

Tải tệp chính thức vào `official_downloads/`, không dùng chức năng “Print to PDF” để tạo bản thay thế. Trên Windows PowerShell, tính SHA bằng:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "C:\duong-dan\tep-vua-tai.pdf"
```

Chép chuỗi 64 ký tự vào `downloaded_sha256`. SHA của corpus đã có trong `corpus_sha256`; không sửa cột đó.

### 5.4 So sánh file và chọn đúng kết quả

Đối chiếu bằng cả SHA và nội dung hiển thị:

| `collection_result` | Khi dùng |
| --- | --- |
| `MATCH_EXACT_SHA` | Tệp tải chính thức có SHA giống hoàn toàn `corpus_sha256`, đúng văn bản và đúng bản đính kèm. |
| `MATCH_CONTENT_DIFFERENT_BINARY` | SHA khác nhưng số văn bản, toàn bộ nội dung, số trang/phần đính kèm tương ứng; khác do đóng gói, metadata PDF, OCR hoặc định dạng. Phải mô tả khác biệt. |
| `DIFFERENT_FILE` | URL/file chính thức là văn bản khác, thiếu phần, khác phiên bản, khác số trang hoặc nội dung có sai khác đáng kể. |
| `MULTIPLE_CANDIDATES` | Có nhiều bản chính thức và chưa xác định corpus khớp bản nào. Ghi tất cả candidate trong notes. |
| `SOURCE_NOT_FOUND` | Đã tìm bằng số/tên/cơ quan nhưng chưa tìm được nguồn đủ tin cậy. Ghi nơi và từ khóa đã tìm. |
| `ACCESS_BLOCKED` | Trang/link có vẻ đúng nhưng không truy cập/tải được. Ghi lỗi và thời điểm. |
| `NOT_STARTED` | Chưa xử lý. |

`sha_match` chỉ nhận `YES`, `NO` hoặc `NOT_DOWNLOADED`. Không ghi `YES` nếu chưa tự tính SHA. `document_number_match`, `title_match`, `content_match` chỉ nhận `YES`, `NO` hoặc `UNCERTAIN`; không suy diễn từ tên file.

### 5.5 Ghi ngày và bằng chứng

- `collected_at`: ngày thực sự mở/tải và kiểm nguồn, dạng `YYYY-MM-DD`; không dùng ngày ước đoán hoặc ngày ban hành văn bản.
- `source_provider`: tên đầy đủ của cơ quan/site cung cấp, ví dụ `Cơ sở dữ liệu quốc gia về văn bản pháp luật`, `Công báo điện tử nước CHXHCN Việt Nam`, `Tòa án nhân dân tối cao`.
- `official_source`: `YES`, `NO` hoặc `UNCERTAIN`. Chỉ ghi `YES` khi tên miền/cơ quan thực sự là nguồn chính thức phù hợp loại tài liệu.
- `evidence_notes`: ghi ngắn nhưng đủ tái kiểm, theo mẫu: `Số/tên khớp; tệp tải ... trang; SHA ...; corpus ... trang; khác biệt ...; link đính kèm ...`.
- `collector_name`: tên/người thực hiện thu thập. Đây không phải trường reviewer pháp lý.
- `collector_checked_at`: ngày hoàn tất dòng, dạng `YYYY-MM-DD`.
- `legal_reviewer`, `legal_reviewed_at`, `legal_decision`, `legal_review_notes`: để trống nếu người thực hiện chỉ thu thập nguồn. Chỉ người được giao review pháp lý điền; quyết định chỉ nhận `APPROVED`, `REJECTED`, `NEEDS_MORE_EVIDENCE`.

### 5.6 Ví dụ một dòng hoàn tất tốt

```text
collection_result=MATCH_EXACT_SHA
exact_source_url=https://.../trang-chi-tiet-van-ban
direct_download_url=https://.../tep.pdf
source_provider=Công báo điện tử nước CHXHCN Việt Nam
collected_at=2026-09-16
downloaded_sha256=<64 ký tự, giống corpus_sha256>
sha_match=YES
document_number_match=YES
title_match=YES
content_match=YES
official_source=YES
evidence_notes=Số, tên và 42 trang khớp; tải PDF từ mục Tải về; SHA trùng corpus.
collector_name=<tên người thu thập>
collector_checked_at=2026-09-16
```

## 6. Lưu ý theo từng nhóm tài liệu

- `LEGAL_DOCUMENT`: cần nguồn của đúng luật/nghị định/thông tư/nghị quyết và đúng bản đính kèm. Trang thuộc tính nhưng link tải là file khác chưa đủ để kết luận exact match.
- `CONSOLIDATED`: phải đúng số văn bản hợp nhất, ngày hợp nhất và đủ các phần Công báo/tệp kèm. Không nhầm với luật gốc được hợp nhất.
- `JUDICIAL`: phân biệt án lệ, bản án, quyết định giám đốc thẩm và bản tóm tắt. Một bài giới thiệu vụ án không thay cho file quyết định/bản án.
- `SUPPLEMENTARY`: xác minh đúng cơ quan ban hành tài liệu hướng dẫn. Nguồn tư vấn/tóm tắt không được đánh dấu official. Với ILO, ưu tiên đúng trang/tệp trên tên miền ILO.
- File DOC/HTML/text trong corpus: vẫn tìm bản nguồn chính thức. SHA có thể khác bản tải hiện hành; nếu vậy dùng `MATCH_CONTENT_DIFFERENT_BINARY` hoặc `DIFFERENT_FILE`, không tự đổi corpus.

## 7. Kiểm tra trước khi gửi lại

1. Bảng còn đúng 95 dòng, không trùng/mất `relative_path`.
2. Mọi dòng không còn `NOT_STARTED`, hoặc đã ghi rõ `SOURCE_NOT_FOUND`/`ACCESS_BLOCKED`/`MULTIPLE_CANDIDATES` cùng bằng chứng tìm kiếm.
3. Dòng `MATCH_EXACT_SHA` có URL HTTPS, provider, ngày, downloaded SHA, `sha_match=YES` và ba trường đối chiếu đều `YES`.
4. Dòng SHA khác có `sha_match=NO`, mô tả khác biệt và giữ tệp tải mới trong `official_downloads/`.
5. Không có ngày tương lai, ngày ước đoán hoặc ngày ban hành bị dùng thay ngày thu thập.
6. Không sửa file corpus và không tự điền approval/reviewer pháp lý.

## 8. Những gì phải gửi lại

Bắt buộc:

- `source_review_tracking.csv` đã điền đủ.

Gửi kèm:

- thư mục `official_downloads/` cho tất cả dòng `MATCH_CONTENT_DIFFERENT_BINARY`, `DIFFERENT_FILE` hoặc `MULTIPLE_CANDIDATES`;
- một file `OPEN_QUESTIONS.md` liệt kê các dòng cần quyết định hoặc nguồn bị chặn, nếu có.

Không cần gửi lại 95 file trong `corpus/` vì chủ dự án đã có bản gốc. Không gửi mật khẩu, token, cookies trình duyệt hoặc ảnh chứa thông tin tài khoản.

Khi nhận lại, chủ dự án sẽ kiểm cấu trúc bảng, URL, SHA và sự đầy đủ. Sau đó người có chuyên môn pháp lý mới duyệt authority/metadata và các record đạt mới được chuyển vào `config/source_catalog.yaml`. Việc thu thập đủ bảng không tự làm `offline_ready_for_online=true`.
