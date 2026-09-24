# Audit Automatic Legal Source Resolver P2.1

Ngày kiểm tra: 2026-09-16

## Kết luận

P2.1 đã sửa đúng phần HTTP attachment resolution cho Công báo và kết quả smoke P2.1d phù hợp với export. Tuy nhiên trạng thái hiện tại vẫn là **NOT_READY**. Hai blocker Copilot đã nêu là đúng nhưng chưa đầy đủ; trước limited provider batch còn phải sửa consistency trong candidate store, trust decision của browser download và route probing VBPL.

Đã chạy lại:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_source_resolver -v
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Kết quả:

- Resolver: **21/21 PASS**.
- Toàn repository: **122/122 PASS**.
- `git diff --check`: không có whitespace error; chỉ có cảnh báo chuyển LF/CRLF của các file cũ.

## Phần đã đúng

- Công báo `.htm` không còn được xuất thành `final_binary_url`.
- Link `g7.cdnchinhphu.vn/api/download/stream` được tải và kiểm magic/MIME/SHA.
- `resolved_sha_match` của bốn smoke records đúng ba trạng thái `YES`, `NO`, `NOT_DOWNLOADED`.
- NATLEX exact SHA vẫn được giữ dù identity page trả 403.
- Hai binary Công báo có SHA khác corpus được giữ ở `NEEDS_REVIEW`.
- Production catalog, review draft và corpus không bị sửa.

## Lỗi phải sửa trước batch

### 1. Candidate identity sai vẫn được lưu `FETCHED`

Trong DB `source_resolution_p2_1d.sqlite`, hai candidate của record `114cafe0807308bb` có `IDENTITY_NOT_FOUND` nhưng column `candidates.state` vẫn là `FETCHED`:

- `https://vbpl.vn/TW/Pages/vbpq-van-ban-goc.aspx?ItemID=146696`
- `https://vbpl.vn/TW/Pages/vbpq-lichsu.aspx?ItemID=146696`

Nguyên nhân: `resolver.py` tính đúng outcome `NEEDS_REVIEW`, nhưng nhánh lưu candidate dùng `FETCHED` cho mọi non-binary candidate khi authority hợp lệ mà không xét `identity_ok`.

### 2. Live identity evidence vẫn có thể bị ghi đè

Nhánh resume dùng `_select_identity`, nhưng nhánh HTTP identity live gán trực tiếp `identity_evidence = ...`. Một identity page lỗi chạy sau vẫn có thể ghi đè identity page tốt chạy trước.

### 3. Browser download chưa nằm trong trust boundary đúng

`PlaywrightFetcher.fetch()` trả:

- `final_url = page.url` — URL trang HTML;
- `download_url = download.url` — URL binary thực tế.

Sau đó resolver đổi trực tiếp `candidate.role` và `candidate.requested_url`, rồi gọi authority verification giữa binary URL và HTML page URL. Candidate ID/database row vẫn được tạo từ role/URL cũ, còn metadata có thể mang role/URL mới.

Nghiêm trọng hơn, final decision hiện có thể dùng một `binary_result` hợp lệ mà không bắt buộc `authority_ok=true`. Vì vậy một browser download có bytes exact nhưng authority verification thất bại vẫn có nguy cơ lên `AUTO_EXACT_SHA`.

### 4. Chưa có end-to-end Playwright regression test

Hai test Playwright hiện chỉ kiểm `plan_download()` và lỗi thiếu dependency. Chưa có test đi qua:

`DOWNLOAD_CONTROL → browser download → authority → magic/MIME/size/SHA → binary identity → evidence → aggregate state`.

### 5. VBPL route probing chưa được dùng đầy đủ

`vbpl_routes()` trả bốn route, nhưng `candidates_for()` chỉ lấy phần tử `[0]`. `VBPLAdapter.candidate_urls()` chưa được gọi trong resolution flow.

Response P2.1d của hai legacy URL VBPL là homepage/loading shell của site mới, không chứa record 146696. `VBPLAdapter.is_homepage()` đã tồn tại nhưng chưa được gọi. Vì vậy đây chưa thể kết luận đơn thuần là “cần click download control”; trước hết resolver phải phát hiện shell và thử route/mirror chính thức phù hợp.

### 6. Required/optional chưa tham gia đầy đủ vào aggregate decision

Attachments khám phá được đều đang có `required=True`. `has_block` không đọc `candidate.required`; nó xét mọi outcome role `BINARY`. Cần mô hình “any valid candidate satisfies required binary capability”, thay vì coi từng định dạng PDF/DOC hoặc mỗi fallback là bắt buộc.

### 7. Warning và blocking reason chưa tách

Aggregate hiện chỉ có `reason_codes`. `PLAYWRIGHT_DISABLED`, 404 từ candidate cũ và lỗi optional xuất chung với lý do quyết định. Điều này khó phân biệt cảnh báo lịch sử với blocker hiện hành.

### 8. Một số provider vẫn chưa có role routes chặt

Role routes mới tốt cho VBPL và Công báo, nhưng các provider như `vanban_chinhphu`, `social_insurance`, `isos`, `toaan` và `ilo` vẫn cho nhiều role dùng chung route rộng. Trước provider batch phải audit từng provider để HTML route không được dùng như binary.

### 9. Fallback records đang hardcode trong resolver

Ba canonical identifier và URL fallback nằm trực tiếp trong `resolver.py`. Chúng nên chuyển sang candidate override/config có schema, provenance và validation; resolver engine không nên chứa dữ liệu riêng của từng văn bản.

### 10. Báo cáo còn dòng cũ

Phần current status nói schema hiện tại là version 2, nhưng phần mô tả cũ vẫn ghi “SQLite schema version 1”. Cần sửa để báo cáo không tự mâu thuẫn.

## Quan sát riêng cho VBPL 10/2020

- Official indexed VBPL page xác nhận đúng identifier và có PDF/DOC attachment.
- P2.1d HTTP response lại là homepage/loading shell của site mới; dùng Playwright trên chính shell này chưa chắc tạo ra document detail.
- Official Ministry of Justice mirror `vbpl.moj.gov.vn` vẫn có indexed detail pages cho ItemID 146696, nhưng network availability phải được kiểm fail-closed trước khi thêm registry.
- Resolver nên thử official HTTP alternatives có evidence trước, rồi mới dùng Playwright trên một page đã xác minh chứa đúng identifier và download control.

## Quyết định

Không chạy limited provider batch. Thực hiện P2.2 correctness/browser/VBPL route fix, tạo DB/cache/export mới, rồi audit lại.
