# Audit Automatic Legal Source Resolver P2.2

Ngày kiểm tra: 2026-09-16

## Kết luận

P2.2 đã sửa được các lỗi lớn của P2.1: candidate identity mismatch không còn lưu `FETCHED`, best binary cần `authority_verified`, browser control không bị mutate, schema v3 giữ parent provenance và smoke artifacts không sửa catalog/corpus. Tuy nhiên kết luận **NOT_READY** vẫn đúng. Implementation chưa đáp ứng toàn bộ acceptance requirements của prompt P2.2 và chưa được mở limited provider batch.

Đã chạy lại:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_source_resolver -v
.\.venv\Scripts\python.exe -m unittest discover -s tests
git diff --check
```

Kết quả:

- Resolver: **24/24 PASS**.
- Toàn repository: **125/125 PASS**.
- SQLite P2.2b: schema version **3**, 3 records, 11 candidates, 7 evidence events.
- Không có whitespace error; chỉ có cảnh báo LF/CRLF của working tree hiện có.

## Những phần đã đúng

- Candidate columns và metadata của DB P2.2b thống nhất về role/URL/state/reasons.
- Hai VBPL identity candidates lưu `NEEDS_REVIEW`, không còn `FETCHED`.
- NATLEX vẫn `AUTO_EXACT_SHA`, SHA `YES`, binary content identity hợp lệ.
- Công báo 06 có binary CDN hợp lệ và SHA mismatch nên `NEEDS_REVIEW/NO`.
- VBPL 10 không có binary hợp lệ nên `BLOCKED/NOT_DOWNLOADED` và `final_binary_url` rỗng.
- Browser derived candidate có parent fields và actual download URL trong mocked path.
- Ba record ở smoke P2.2b là đúng phạm vi prompt P2.2: NATLEX, một Công báo và VBPL. Record 24 chưa được re-smoke ở vòng này và phải được đưa lại vào P2.3 matrix.

## Các lỗi còn lại

### 1. `required` và `alternative_group` chưa điều khiển quyết định

Candidate model có hai field này nhưng aggregate logic gần như không đọc chúng. Mọi binary outcome lỗi vẫn có thể trở thành blocking reason. Export Công báo 06 cho thấy:

- đã có trusted Công báo binary, state đúng là `NEEDS_REVIEW` do `SHA_MISMATCH`;
- nhưng `blocking_reason_codes` vẫn chứa old VBPL 404 và `PLAYWRIGHT_DISABLED`.

Hai lỗi alternative này phải là warning vì binary capability đã được candidate Công báo thỏa mãn. Cần tổng hợp theo capability/alternative group, không theo role chung.

### 2. `binary_state` vẫn lấy outcome cuối

`resolver.py` loop qua toàn bộ outcomes rồi gán `aggregate["binary_state"]` nhiều lần. Field cuối có thể không thuộc `best_binary_evidence`. Tất cả final binary fields phải được dựng từ một selected evidence object duy nhất.

### 3. Identity selector chưa theo rank đã yêu cầu

`_select_identity()` chỉ xếp theo boolean match và URL. Nó chưa ưu tiên verified identity từ exact official binary hơn identity page, và chưa dùng authority/source type/provider priority.

### 4. `STATUS_HISTORY` chưa được xác minh

P2.2b lưu VBPL history URL là `FETCHED` dù response thực tế là homepage/loading shell. Shell detection chỉ chạy cho role `IDENTITY`. `STATUS_HISTORY` cũng phải kiểm shell, identifier và loại nội dung trước khi `FETCHED`.

### 5. Route probing dừng sớm sai trường hợp

Nếu seed có `direct_download_url`, `candidates_for()` cắt `identity_urls` còn route đầu tiên. Với VBPL 10, direct URL cũ trả 404 nhưng resolver không thích ứng bằng cách thử thuộc tính/toàn văn/legacy/mirror tiếp theo. Test hiện chỉ kiểm route probing khi **không có** direct binary nên bỏ lọt tình huống thật.

### 6. Mocked browser test đang xanh giả

Fixture HTML dùng `javascript:download()` nhưng không có `id` hoặc `data-atc`; parser tạo selector rỗng. `BrowserFixture` trong test vẫn tải file mà không từ chối selector rỗng, trong khi Playwright thật sẽ ném `PLAYWRIGHT_SELECTOR_NOT_PROVEN`. Vì vậy test chưa chứng minh end-to-end path có selector hợp lệ.

### 7. Browser page authority và failure evidence chưa hoàn chỉnh

- `page_final_url` sau navigation chưa được authority-check lại trước click.
- `PlaywrightFetcher.action_log` là state dùng chung giữa calls và có thể tích lũy action cũ.
- Khi browser lỗi, error action log không được persist vào evidence.
- Temp file riêng của Playwright chưa được cleanup trong mọi exception.
- `shutil.move` chưa bảo đảm atomic replace như HTTP fetch path.

### 8. Attachment discovery vẫn chạy trên identity mismatch/shell

Adapter discovery được gọi sau khi parse mọi identity HTML, kể cả `identity_ok=false` hoặc `is_shell=true`. Browser control/direct attachment chỉ nên được tin từ page đã qua identity + shell + authority gates, hoặc được giữ ở trạng thái untrusted review mà không fetch.

### 9. Override validation đang fail-open

Loader gặp unknown provider thì `continue`, làm nhánh `raise ValueError("unknown override provider")` phía sau không thể chạy. Disallowed routes cũng bị bỏ qua im lặng. Prompt P2.2 yêu cầu invalid override bị từ chối rõ ràng.

Ngoài ra override đang bị chuyển thành tuple `(role, url)`, làm mất `required`, `alternative_group` và provenance khi tạo Candidate.

### 10. Redirect semantics chưa đúng cho cross-domain provider

`allowed_redirect_domains` được kiểm rồi lại gọi `self.allows()`, vốn buộc host phải thuộc `domains`. Vì vậy domain chỉ có trong `allowed_redirect_domains` nhưng không có trong `domains` vẫn không thể được redirect tới. Cần định nghĩa rõ cross-provider/cross-domain rule, hoặc bỏ khả năng này và dùng derived candidate sau redirect discovery.

### 11. Provider role coverage chưa hoàn tất

`moha_labor` vẫn chưa có `role_routes`. Một số route patterns dùng query trong path pattern (`/?docid=*`) nhưng `Provider.allows()` chỉ so `parsed.path`, nên pattern query không có tác dụng.

### 12. Báo cáo còn tự mâu thuẫn

Phần current status nói schema v3 nhưng phần lịch sử phía dưới vẫn nói schema v2 như hiện hành. Báo cáo giữ nguyên nhiều current-status sections P2.1/P2.2 thay vì tách rõ historical results. Prompt trước yêu cầu sửa mọi dòng stale nhưng chưa hoàn thành.

### 13. Phần lớn regression requirements P2.2 chưa có test

Test count chỉ tăng từ 21 lên 24. Chưa thấy test trực tiếp cho:

- exact bytes + authority fail;
- best `binary_state`/URL đồng nguồn;
- warning vs blocking theo alternative group;
- secondary candidate không hạ official exact;
- browser outside allowlist;
- page redirect outside allowlist;
- browser failure cleanup/action evidence;
- shell không tạo attachment/control;
- strict override validation;
- resume idempotency cho derived candidates;
- role route audit từng provider.

## Quyết định

Không chạy limited provider batch. Thực hiện P2.3 như một readiness gate có machine-readable audit và vòng tự sửa bắt buộc.
