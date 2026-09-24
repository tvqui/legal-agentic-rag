# Prompt Copilot P2.2 — browser trust path và VBPL resolution

Bạn hãy tiếp tục Automatic Legal Source Resolver từ P2.1. Đây vẫn là vòng correctness giới hạn. **Không chạy batch 76 record, không merge catalog, không thay corpus và không chạy downstream pipeline.**

Đọc trước khi sửa:

1. `SOURCE_RESOLVER_P2_1_AUDIT.md`
2. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
3. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`
4. toàn bộ `src/vn_labor_offline/source_resolver/`
5. `config/source_provider_registry.yaml`
6. `tests/test_source_resolver.py`
7. `artifacts/00_manifest/source_resolution_p2_1d.sqlite`
8. `artifacts/00_manifest/source_resolution_p2_1d_export/`
9. `.cache/source_resolver_p2_1d/`

Không chỉ đọc report. Query trực tiếp SQLite candidates/evidence và kiểm cache pages.

## 1. Sửa các lỗi consistency còn lại

### 1.1 Candidate state

- Identity HTTP 200 nhưng identifier không khớp/không tìm thấy phải lưu `candidates.state=NEEDS_REVIEW`.
- Shell/homepage/404 page HTTP 200 phải có state/reason riêng như `BLOCKED + IDENTITY_SHELL` hoặc taxonomy tương đương, không lưu `FETCHED`.
- Candidate column và `metadata_json` phải có cùng `role`, `requested_url`, `final_url`, `state` và reason codes.
- Thêm migration nếu schema thay đổi; migration idempotent và giữ toàn bộ evidence cũ.

Regression bắt buộc: query SQLite sau resolve và khẳng định identity mismatch không thể có state `FETCHED`.

### 1.2 Identity evidence selection

Mọi nhánh live, resume, HTTP và browser phải dùng cùng một deterministic selector. Không gán trực tiếp biến global làm evidence tốt bị candidate sau ghi đè.

Xếp hạng tối thiểu:

1. verified identity từ official exact binary;
2. verified identity page;
3. official page tải được nhưng mismatch;
4. shell/error/unavailable.

Tie-break phải ổn định và được test.

### 1.3 Best binary và final aggregate

- `binary_state`, `final_binary_url`, `resolved_downloaded_sha256` và `resolved_sha_match` phải đến từ **cùng best binary evidence**, không lấy state của outcome cuối trong loop.
- Một binary chỉ được dùng cho `AUTO_EXACT_SHA` khi đồng thời đạt:
  - official/allowed provider và role;
  - requested/download URL và final URL vượt authority checks;
  - magic, MIME/known-content semantics, size hợp lệ;
  - SHA trùng corpus;
  - identity requirement đạt.
- Gắn rõ `authority_verified` vào evidence/binary result. `_valid_binary()` chỉ nói bytes hợp lệ; final trust decision phải dùng hàm mạnh hơn, ví dụ `_trusted_binary()`.
- Binary bytes exact nhưng authority fail phải `BLOCKED` hoặc `NEEDS_REVIEW` theo taxonomy; tuyệt đối không `AUTO_EXACT_SHA`.

### 1.4 Required capability và alternative candidates

Không đánh dấu mọi PDF/DOC/fallback là required độc lập. Mô hình hóa required capability:

- `identity`: cần ít nhất một evidence hợp lệ, trừ khi exact official binary content đã xác minh identity theo rule;
- `binary`: cần ít nhất một candidate hợp lệ;
- nhiều PDF/DOC/mirror là `any-of` alternatives.

Candidate optional/alternative lỗi chỉ tạo warning nếu capability đã được candidate khác thỏa mãn. Aggregate phải xuất riêng:

- `blocking_reason_codes`
- `warning_reason_codes`
- có thể giữ `reason_codes` làm union để tương thích, nhưng decision không được dùng union này.

### 1.5 Secondary candidates

Không dùng quy tắc “có bất kỳ candidate SECONDARY nào thì cả record NEEDS_REVIEW”. Chỉ source/evidence được chọn làm best evidence mới quyết định trust; candidate phụ bị loại không được hạ evidence official tốt hơn.

## 2. Làm lại browser download boundary

### 2.1 Candidate bất biến

Không mutate `candidate.role` hoặc `candidate.requested_url` sau khi đã tạo candidate ID/store row.

Khi `DOWNLOAD_CONTROL` tạo download:

1. giữ nguyên control candidate và evidence action;
2. tạo derived `BINARY` candidate/evidence riêng từ actual `download.url`;
3. liên kết bằng `discovered_from_candidate_id`/`parent_candidate_id`;
4. binary candidate ID phải được tính từ role `BINARY` và actual download URL.

### 2.2 URL semantics

Playwright result phải tách:

- `page_requested_url`
- `page_final_url`
- `download_url`
- `suggested_filename`
- `download_content_type` nếu quan sát được
- `action_log`

`final_binary_url` phải là actual allowed `download_url`/binary response URL, không phải `page.url`.

Authority kiểm hai bước:

1. page URL được phép ở role `IDENTITY`/`DOWNLOAD_CONTROL`;
2. actual download URL được phép ở role `BINARY`.

Không thay một check bằng check còn lại. Nếu browser trả `blob:` hoặc URL không quan sát được, giữ bytes/evidence nhưng không auto exact cho đến khi có rule được audit rõ ràng.

### 2.3 Common binary verification path

HTTP download và Playwright download phải gọi cùng một hàm xử lý:

`authority → size → magic → MIME/response metadata → SHA → identity extraction → evidence persistence → best-evidence ranking`.

Không sao chép logic giữa hai nhánh.

Playwright phải:

- giới hạn page timeout, selector timeout, action count và download count;
- bắt download event trước click;
- dùng temp file trong cùng filesystem và atomic replace;
- cleanup destination/temp trên mọi exception;
- đóng page/context/browser trong `finally`;
- ghi action/error log kể cả thất bại;
- không dùng generic default selector nếu provider adapter chưa tạo selector được chứng minh bởi fixture.

## 3. VBPL: phát hiện shell trước, Playwright sau

P2.1d cache của ItemID `146696` cho thấy legacy URLs trả homepage/loading shell của site mới, title/canonical trỏ trang chủ và không có identifier. Do đó không được mặc định rằng trang này có download control để click.

### 3.1 Shell/error detection

Tích hợp `VBPLAdapter.is_homepage()` thật vào flow và mở rộng deterministic signals:

- final URL/canonical URL là root;
- title là Trang chủ;
- loading shell/portal placeholder;
- requested `ItemID` không xuất hiện trong page data;
- explicit not-found markers.

Xuất reason code rõ ràng: `VBPL_HOME_SHELL`, `IDENTITY_NOT_FOUND`, `DOCUMENT_NOT_FOUND` hoặc taxonomy tương đương.

### 3.2 Probe route đầy đủ

`vbpl_routes()` đang trả nhiều route nhưng `candidates_for()` chỉ lấy `[0]`. Sửa để adapter sinh controlled candidates cho:

- `vbpq-van-ban-goc`
- `ivbpq-van-ban-goc` khi có evidence route này tồn tại
- `vbpq-thuoctinh`/`ivbpq-thuoctinh`
- `vbpq-toanvan`
- `vbpq-lichsu` với role `STATUS_HISTORY`
- ministry route/dvid chỉ khi lấy được từ seed/page evidence, không đoán tùy ý.

Deduplicate canonical URL và giới hạn số route. Không fetch tất cả route sau khi capabilities cần thiết đã đạt, trừ chế độ audit rõ ràng.

`VBPLAdapter.candidate_urls()` phải được dùng hoặc loại bỏ; không để dead abstraction.

### 3.3 Official legacy/mirror fallback

Các trang indexed chính thức cho `10/2020/TT-BLĐTBXH` cho thấy:

- `https://vbpl.vn/tw/Pages/ivbpq-thuoctinh.aspx?ItemID=146696`
- `https://vbpl.vn/TW/Pages/vbpq-lichsu.aspx?ItemID=146696`
- mirror Bộ Tư pháp `https://vbpl.moj.gov.vn/bolaodong/Pages/vbpq-van-ban-goc.aspx?ItemID=146696&dvid=318`

Không hardcode URL này trong resolver engine. Đưa official alternate endpoints/candidate overrides vào config có schema, classification, provenance note và validation.

Chỉ thêm `vbpl.moj.gov.vn` vào registry sau khi xác minh đây là official Ministry of Justice endpoint và network smoke cho thấy route hoạt động. Nếu hiện trả 502/403, lưu evidence và tiếp tục fail-closed.

### 3.4 Parse legacy attachment controls

Tạo fixture tối giản cho cấu trúc legacy page đã biết:

- direct `FileData/...` attachment;
- WOPI `sourcedoc=/TW/Lists/vbpq/Attachments/...` preview link;
- image-only attachment/download controls;
- PDF và DOC alternatives.

Decode `sourcedoc` để tạo candidate chỉ khi path, ItemID và provider route hợp lệ. Không đoán filename và không đổi domain/path nếu không có evidence trong page/config.

Playwright chỉ được chạy khi page sau navigation đã chứa đúng canonical identifier và selector do VBPL adapter tạo. Nếu page là home shell, dừng; không click selector chung.

## 4. Provider registry audit

Role routes phải chặt cho **mọi provider trước limited batch**, không chỉ VBPL/Công báo:

- identity HTML routes;
- binary extension/download endpoints;
- status/history routes;
- allowed redirect domains.

Đặc biệt rà `vanban_chinhphu`, `social_insurance`, `isos`, `toaan`, `ilo`. Không để wildcard `/*` dùng cho role `BINARY` nếu route có thể trả HTML.

`allowed_redirect_domains` và `redirect_policy` hiện được load nhưng chưa áp dụng đầy đủ. Hoặc triển khai semantics và test, hoặc bỏ field; không để config tạo cảm giác kiểm soát giả.

## 5. Chuyển record-specific fallback ra config

Di chuyển map hardcode ba văn bản khỏi `resolver.py` sang file như `config/source_candidate_overrides.yaml` hoặc cấu trúc phù hợp. Mỗi entry cần:

- canonical identifier/record ID;
- URL;
- role;
- provider;
- reason/provenance;
- `required` hoặc alternative group;
- validation bằng registry.

Config chỉ cung cấp candidate; không được hardcode expected state/SHA/result.

## 6. Tests bắt buộc

Bổ sung ít nhất các regression sau:

1. identity mismatch được lưu `NEEDS_REVIEW` trong SQLite column và metadata;
2. live identity match không bị later mismatch ghi đè;
3. `binary_state` và final URL đến từ best binary, không outcome cuối;
4. bytes exact + authority fail không thể `AUTO_EXACT_SHA`;
5. secondary/optional candidate lỗi không hạ official exact evidence;
6. alternative PDF lỗi nhưng DOC thành công thỏa binary capability;
7. warning/blocking codes được tách đúng;
8. full mocked browser path đi qua common verification và đạt exact khi mọi authority/identity/SHA điều kiện đúng;
9. browser download outside allowlist bị chặn dù SHA exact;
10. browser `page_final_url` không bao giờ được xuất làm `final_binary_url`;
11. control candidate không bị mutate; derived BINARY candidate có ID/role/URL nhất quán trong SQLite;
12. browser failure cleanup temp/destination và vẫn có failure action log;
13. VBPL home shell được phát hiện và không tạo/click download control;
14. `candidates_for()` thực sự dùng controlled VBPL routes và gán history role đúng;
15. legacy fixture parse FileData/WOPI/control đúng, không đoán URL;
16. registry từ chối HTML ở role binary cho từng provider;
17. fallback config validation từ chối unknown provider, disallowed route, duplicate và path không HTTPS;
18. resume/idempotency không nhân đôi derived browser candidate/evidence.

Không phụ thuộc live network trong unit tests. Fixture chỉ giữ HTML tối thiểu cần để chứng minh cấu trúc.

## 7. Verification sequence

Chạy và ghi nguyên văn lệnh thật trong report:

```powershell
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe -m unittest tests.test_source_resolver -v
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Sau offline tests, tạo **DB/cache/export P2.2 mới**, không ghi đè P2.1d.

Network smoke tối đa:

1. NATLEX record để kiểm exact + optional identity warning;
2. Công báo 06 hoặc 24 để kiểm HTTP binary mismatch path;
3. VBPL 10 qua controlled routes/mirror;
4. browser chỉ bật nếu page đã xác minh identifier và có adapter selector.

Không chạy limited provider batch trong P2.2. Nếu không có browser/dependency hoặc VBPL vẫn chỉ trả shell/403/502, báo `BLOCKED_BY_PROVIDER_ACCESS`; không ép PASS.

## 8. Báo cáo và phạm vi cấm

Cập nhật `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`:

- sửa mọi dòng schema version cũ;
- ghi lệnh thật, số test thật, skipped tests;
- bảng per-candidate và per-record của P2.2;
- tách warning/blocking reasons;
- ghi Playwright có thực sự chạy hay chỉ mocked;
- kết luận `READY_FOR_LIMITED_PROVIDER_BATCH` hoặc `NOT_READY` với blocker cụ thể.

Không:

- sửa production/review catalog;
- thay corpus;
- ghi reviewer/approval/verified metadata;
- merge catalog;
- chạy pipeline, Dense, BM25, Neo4j/Aura;
- xóa DB/cache cũ;
- nới allowlist/quality rule để ép state;
- dùng search-engine cache làm bằng chứng tải file hiện hành;
- hardcode state/SHA/output cho smoke records.

Khi hoàn tất, liệt kê chính xác file sửa/tạo và xác nhận catalog, corpus, pipeline artifacts, Aura không bị thay đổi.
