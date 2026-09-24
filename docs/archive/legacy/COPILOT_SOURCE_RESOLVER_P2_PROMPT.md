# Prompt Copilot P2 — provider attachment resolution và batch 84 candidate

Bạn hãy tiếp tục triển khai Automatic Legal Source Resolver. Đọc:

1. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
2. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`
3. `SOURCE_RESOLVER_P0_P1_REVIEW.md`
4. toàn bộ `src/vn_labor_offline/source_resolver/`
5. `config/source_provider_registry.yaml`
6. `review_inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv`
7. direct8 DB/export hiện có trong `artifacts/00_manifest/`.

P1.3 đã tải 8 direct candidates: 4 record `AUTO_EXACT_SHA`, 4 record `BLOCKED`. Không sửa rule để ép PASS. P2 phải sửa consistency và triển khai provider-specific attachment resolution cho 76 record chưa có direct URL.

## 1. Sửa correctness trước khi mở rộng batch

### 1.1 Required/optional evidence

Một record có thể xác minh identity bằng một trong hai đường đáng tin cậy:

- official identity page chứa đúng canonical identifier; hoặc
- official binary có SHA exact và nội dung binary chứa đúng canonical identifier.

Nếu binary official exact SHA và `BINARY_CONTENT` đã xác minh identity, lỗi của một identity page phụ không được tự động chặn record. Giữ lỗi trang phụ như warning/evidence, nhưng record có thể `AUTO_EXACT_SHA` khi tất cả điều kiện bắt buộc đã đạt. Trường hợp NATLEX hiện tại phải được test theo quy tắc này: binary candidate đã exact và binary identity đã có, còn identity page trả 403.

`BLOCKED` chỉ dùng khi không còn đường evidence bắt buộc nào thành công. Mỗi candidate phải có `required`/`optional` hoặc vai trò tương đương rõ ràng; tổng hợp state theo capability đạt được, không theo “có bất kỳ candidate nào lỗi”.

### 1.2 Candidate state phải phản ánh verification

- Identity tải HTTP thành công nhưng không chứa identifier: `NEEDS_REVIEW`, không phải `FETCHED`.
- Binary HTTP thành công nhưng SHA khác: `NEEDS_REVIEW`.
- Candidate optional lỗi có warning riêng, không làm mất evidence thành công khác.
- Record state, candidate state, reason codes và summary phải nhất quán.

### 1.3 Export không được mâu thuẫn

Export hiện có record `AUTO_EXACT_SHA` nhưng vẫn giữ seed fields `sha_match=NOT_DOWNLOADED`, `downloaded_sha256=""`, `collection_result=ACCESS_BLOCKED`. Hãy tách rõ:

- trường seed bất biến: `seed_collection_result`, `seed_sha_match`, `seed_downloaded_sha256`;
- trường resolver: `resolution_state`, `resolved_downloaded_sha256`, `resolved_sha_match`, `resolved_at`, `identity_match`, `identity_source`, `final_identity_url`, `final_binary_url`.

Hoặc cập nhật schema tương đương nhưng không để một record vừa “exact” vừa “not downloaded” mà không phân biệt provenance. JSONL/summary/review queue và merge diff phải dùng trường resolver.

### 1.4 Sửa báo cáo direct8

Báo cáo hiện có câu nói bốn exact results “include ... ILO record”, nhưng DB thực tế là:

- exact records: ba Tòa án + một `datafiles.chinhphu.vn`;
- ILO record: record `BLOCKED`, binary candidate exact, identity page 403;
- ba VBPL: binary 404 và identity không khớp.

Sửa báo cáo theo DB, không theo suy đoán.

## 2. Provider-specific attachment resolution

Hiện 76 record chỉ có page URL nên resolver fetch identity xong nhưng chưa tìm/tải attachment. Triển khai adapters thật.

Mỗi adapter phải trả candidate có cấu trúc:

```text
url
role = IDENTITY | BINARY | STATUS_HISTORY
provider_id
source_class
discovered_from
attachment_label
expected_identifier
required/optional
reason_codes
```

Candidate URL phải được canonicalize, deduplicate và kiểm provider registry trước khi fetch.

### 2.1 VBPL

- Với `ItemID`, probe có kiểm soát cả `vbpq-van-ban-goc`, `vbpq-thuoctinh`, `vbpq-toanvan`, `vbpq-lichsu` và legacy ministry route nếu cần; không chỉ dùng route đầu tiên.
- Phát hiện homepage/shell/error dù HTTP 200.
- Trích link `FileData`, DOC/DOCX/PDF và link “Tải về/Xem nhanh”.
- Nếu FileData cũ 404, giữ evidence rồi thử attachment được phát hiện từ route còn hoạt động.
- Không giả link bằng cách chỉ đổi tên file.

Ba direct VBPL đang block phải là regression fixtures:

- `ItemID=143667` — `06/2020/TT-BLĐTBXH`;
- `ItemID=146696` — `10/2020/TT-BLĐTBXH`;
- `ItemID=159196` — `24/2022/TT-BLĐTBXH`.

Nguồn chính thức thay thế đã được xác định cho discovery/fallback:

- `06/2020/TT-BLĐTBXH`: `https://congbao.chinhphu.vn/van-ban/thong-tu-so-06-2020-tt-bldtbxh-32743.htm` và trang Chính phủ `https://vanban.chinhphu.vn/default.aspx?docid=201337&pageid=27160`;
- `24/2022/TT-BLĐTBXH`: `https://congbao.chinhphu.vn/van-ban/thong-tu-so-24-2022-tt-bldtbxh-38574.htm`;
- `10/2020/TT-BLĐTBXH`: VBPL history/attachment vẫn được index tại `ItemID=146696`; nếu direct HTTP không lấy được thì dùng deterministic browser/official-site discovery, không chuyển sang nguồn thương mại.

Các URL trên là candidates, vẫn phải qua identity/binary/SHA verifier.

### 2.2 Công báo Chính phủ

- Trích link PDF/DOC từ trang `/van-ban/...` và endpoint `/tai-ve-van-ban-...?format=pdf|doc`.
- Hỗ trợ official CDN host nếu final redirect hợp lệ và đã khai báo registry.
- Một Công báo có thể ghép nhiều văn bản/trang; SHA khác corpus không được tự coi content match.

### 2.3 Văn bản Chính phủ

- Trích `Tài liệu đính kèm` và URL `datafiles.chinhphu.vn`.
- Lưu identity page riêng với binary attachment.

### 2.4 Tòa án và ILO

- Direct official binary có thể tự cung cấp identity.
- Detail/article chỉ là identity/status evidence; bài giới thiệu không thay file bản án/án lệ.
- NATLEX 403 ở identity page phải có browser/header fallback có kiểm soát, nhưng nếu exact binary + binary identity đã đủ thì identity page là optional warning.

### 2.5 Playwright fallback

- Chỉ gọi khi HTTP adapter xác định trang cần JS/click.
- Selector/action deterministic, domain allowlist, timeout và action log.
- Không dùng browser-use/LLM để approve.
- Download qua Playwright vẫn phải qua cùng binary verifier và evidence store.

## 3. Cross-provider official fallback

Nếu provider A có page/binary lỗi, resolver có thể thử provider chính thức B dựa trên canonical identifier. Không áp dụng một bảng xếp hạng domain chung; đánh dấu vai trò và provenance từng candidate.

Thứ tự discovery:

1. URL/ItemID seed;
2. attachment từ official page;
3. official-site search của cùng provider;
4. official provider khác đã đăng đúng văn bản;
5. SearXNG chỉ tạo candidate nếu các bước trên thất bại.

Nguồn thứ cấp không được auto exact ngay cả khi tải được file.

## 4. State, queue và resume

- Một record có nhiều candidates; lưu tất cả attempt/evidence bất biến.
- Dừng sớm khi có exact official binary + identity đủ, nhưng không xóa attempt trước.
- Retry `BLOCKED` chỉ khi lỗi được phân loại retryable hoặc có candidate mới.
- 404 URL cũ là permanent cho URL đó nhưng không block toàn record nếu có official fallback.
- 403 có thể chuyển Playwright/header fallback; giới hạn số lần.
- CLI thêm/làm rõ `--state`, `--retry-blocked`, `--batch-size`, `--provider`, `--resume` nếu cần.
- Không tải lại exact candidate khi resume.

## 5. Test bắt buộc

Test mặc định dùng saved/local HTML fixtures, không truy cập Internet:

1. NATLEX exact binary identity + optional page 403 -> record exact với warning;
2. identity page HTTP 200 nhưng thiếu identifier -> candidate review;
3. export exact record có resolved SHA fields nhất quán và seed fields tách riêng;
4. ba VBPL ItemID probe đủ route, homepage bị loại;
5. HTML VBPL fixture trích đúng attachment;
6. Công báo fixture trích PDF/DOC endpoint;
7. Văn bản Chính phủ fixture trích datafiles attachment;
8. relative URL và URL encoded được resolve đúng;
9. attachment ngoài allowlist bị loại;
10. duplicate attachment không tạo duplicate candidate/evidence;
11. fallback official provider A -> B;
12. 404 candidate cũ không block record nếu fallback exact;
13. resume không tải lại exact candidate;
14. Playwright fallback action log và download đi qua verifier;
15. summary/queue/merge sử dụng resolved fields đúng.

Chạy `compileall`, resolver tests và toàn bộ repository tests. Ghi số test thực tế.

## 6. Trình tự network P2

Không chạy cả 76 record ngay.

1. Dùng DB/cache mới; giữ direct8 DB làm bằng chứng.
2. Rerun bốn blocked records sau correction/fallback.
3. Chạy một record mẫu cho mỗi provider: VBPL, Công báo, Văn bản Chính phủ, Tòa án, ILO/BHXH nếu có.
4. Kiểm evidence/state/export thủ công.
5. Chạy batch tối đa 5 record/provider, concurrency 1, rate limit tối thiểu 1 giây.
6. Nếu không có false positive hoặc lỗi hệ thống mới chạy 76 candidate còn lại theo provider với resume.
7. Chưa chạy discovery 11 judicial trong vòng attachment batch; chúng là phase tiếp theo.

Không merge catalog thật, không sửa corpus và không chạy pipeline/Dense/BM25/Aura.

## 7. Báo cáo P2

Cập nhật `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md` và tạo bảng:

- tổng record attempted/resolved/exact/review/blocked/pending theo provider;
- requested/final identity và binary URLs;
- downloaded/corpus SHA;
- identity source;
- fallback/discovery path;
- warning/reason code;
- retry/resume statistics;
- danh sách record làm thay đổi candidate URL so với seed.

Xuất DB/artifact riêng cho P2. Xác nhận corpus, production catalog và review draft không thay đổi. Không tuyên bố hoàn tất 84 records nếu còn URL chưa tải hoặc binary chưa xác minh.
