# Prompt giao Copilot — Implement Automatic Legal Source Resolver

Bạn hãy đóng vai **Senior Python Engineer + Data Provenance Engineer + Legal NLP/GraphRAG Engineer** và trực tiếp triển khai Automatic Legal Source Resolver trong repository hiện tại. Đây là công việc sửa code thật, không chỉ viết đề xuất.

## 1. Đọc bắt buộc trước khi sửa code

Đọc kỹ và coi đây là nguồn yêu cầu theo thứ tự:

1. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
2. `SOURCE_REVIEW_RETURN_V8_1_AUDIT.md`
3. `review_inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv`
4. `review_inputs/v8_1/source_review_return_v8_1/OPEN_QUESTIONS.md`
5. `OFFLINE_TO_100_NEXT_STEPS.md`
6. `config/source_catalog.yaml`
7. `review_inputs/v8_1/source_catalog_review_draft.yaml`
8. `pyproject.toml`, cấu trúc `src/vn_labor_offline/`, các CLI và test hiện có.

Nếu một file trong `review_inputs/` không tồn tại, dừng phần phụ thuộc vào file đó và báo chính xác file thiếu. Không tự tạo 95 record giả và không suy đoán nội dung của ZIP.

## 2. Bối cảnh dữ liệu đã được kiểm tra

Seed V8.1 có đúng 95 record và không làm thay đổi `relative_path`, `source_group`, `corpus_sha256`:

- 57 `LEGAL_DOCUMENT`;
- 24 `JUDICIAL`;
- 10 `SUPPLEMENTARY`;
- 4 `CONSOLIDATED`;
- 84 record có candidate được đánh dấu official;
- 81 `exact_source_url`;
- 8 `direct_download_url`;
- 84 `ACCESS_BLOCKED` do môi trường thu thập chưa đưa được raw binary vào filesystem;
- 10 `SOURCE_NOT_FOUND` và 1 `MULTIPLE_CANDIDATES`, đều thuộc nhóm judicial;
- 95/95 `sha_match=NOT_DOWNLOADED`;
- 0 `downloaded_sha256` và 0 content match đã xác minh;
- 38 candidate official vẫn có identity chưa chắc chắn;
- `official_downloads/` đang rỗng.

Các con số trên phải được importer kiểm lại từ CSV. Nếu kết quả thực tế khác, không hard-code để ép test pass; báo diff và dùng dữ liệu thực làm căn cứ.

## 3. Mục tiêu phải đạt

Triển khai resolver có khả năng:

1. Import seed an toàn và kiểm tra 95 path/SHA với manifest/catalog hiện có.
2. Chuẩn hóa identifier, metadata và URL cũ.
3. Resolve theo adapter xác định cho VBPL, Công báo, Văn bản Chính phủ, Tòa án và ILO.
4. Tải trang/tệp bằng HTTP; dùng Playwright có selector/hành vi cố định khi trang cần JavaScript hoặc nút “Xem”.
5. Xác minh final domain/route, identity, MIME/magic bytes, kích thước, SHA-256 và nội dung cần thiết.
6. Lưu evidence đầy đủ, lặp lại được và không làm thay đổi corpus.
7. Xuất queue cho những trường hợp cần discovery/review.
8. Có dry-run/diff trước mọi thao tác merge.
9. Chạy được trên Windows local và Kaggle Linux; phần browser phải là optional dependency/fallback rõ ràng.

Không đặt mục tiêu “làm cho báo cáo PASS bằng mọi giá”. Mục tiêu là kết quả đúng, có bằng chứng và không tạo false positive.

## 4. Giới hạn tin cậy bắt buộc

- Không tự điền `legal_reviewer`, `legal_reviewed_at`, `legal_decision` hoặc giả tên người duyệt.
- Không đổi `metadata_verified: true` chỉ vì tìm được URL.
- Không coi `official_source=YES` trong CSV là bằng chứng đủ; phải kiểm provider registry và final URL sau redirect.
- Không nâng record lên `AUTO_EXACT_SHA` nếu chưa tải bytes và chưa so SHA với corpus.
- Không ghi `APPROVED`; trạng thái này chỉ dành cho người có thẩm quyền.
- Không tự thay, xóa, chuyển đổi hoặc ghi đè file trong `data/`, corpus, checkpoint hoặc ZIP V8.1.
- Không merge tự động vào `config/source_catalog.yaml` trong lần triển khai này. Chỉ tạo lệnh `merge --dry-run` và diff đề xuất.
- Không chạy lại toàn pipeline, Dense, BM25 hoặc Aura chỉ vì resolver được thêm. Resolver phải được kiểm riêng trước.
- Không vượt CAPTCHA, không né rate limit, không dùng cookies/tài khoản cá nhân và không ghi secret vào log.
- Nguồn thứ cấp chỉ dùng cho discovery/evidence; không tự đánh dấu official.

## 5. Kiến trúc cần triển khai

Đặt code trong package hiện có:

```text
src/vn_labor_offline/source_resolver/
  __init__.py
  models.py
  resolver.py
  normalizer.py
  provider_registry.py
  import_seed.py
  evidence.py
  store.py
  cli.py
  providers/
    __init__.py
    vbpl.py
    congbao.py
    vanban_chinhphu.py
    toaan.py
    ilo.py
    generic_official.py
  discovery/
    __init__.py
    official_search.py
    searxng.py
  fetchers/
    __init__.py
    http.py
    playwright.py
  extractors/
    __init__.py
    html.py
    binary.py
  verification/
    __init__.py
    authority.py
    identity.py
    binary.py
    content.py
    decision.py
```

Có thể điều chỉnh tên file nếu kiến trúc repository hiện tại yêu cầu, nhưng phải giữ ranh giới rõ giữa import, discovery, fetch, extract, verify, evidence và decision. Tái sử dụng utility sẵn có thay vì sao chép logic hash/path/config.

Thêm `config/source_provider_registry.yaml` để khai báo:

- provider ID và tên;
- allowed host/domain;
- allowed route patterns;
- vai trò `IDENTITY`, `BINARY`, `STATUS_HISTORY`;
- nhóm tài liệu được phép;
- redirect policy;
- rate limit/retry;
- official/secondary classification.

Không dùng một thứ tự chung `VBPL > Chính phủ > Công báo` cho mọi mục đích. Một record có thể có `identity_url`, `binary_url` và `status_url` từ các provider chính thức khác nhau.

## 6. Quy tắc import seed

Importer phải:

- yêu cầu đúng header CSV;
- từ chối path traversal, path tuyệt đối hoặc path không nằm trong corpus;
- kiểm 95 `relative_path` duy nhất;
- so `source_group` và `corpus_sha256` với manifest/catalog hiện có;
- không tin metadata mới nếu mâu thuẫn với file/catalog;
- lưu metadata mới như candidate kèm provenance;
- tạo `canonical_identifier`:
  - legal/consolidated ưu tiên `instrument_number`;
  - judicial ưu tiên `document_number`;
  - supplementary dùng identifier phù hợp và giữ nguyên trường gốc;
- ánh xạ trạng thái:
  - `ACCESS_BLOCKED` + URL official -> `DISCOVERED` hoặc `FETCH_PENDING`;
  - `SOURCE_NOT_FOUND` -> `NEEDS_DISCOVERY`;
  - `MULTIPLE_CANDIDATES` -> `NEEDS_REVIEW`;
- không ánh xạ bất kỳ dòng hiện tại nào thành `AUTO_EXACT_SHA`.

Import phải idempotent: import cùng một seed hai lần không tạo duplicate event/candidate.

## 7. Trạng thái resolver

Dùng enum/model chặt chẽ, tối thiểu gồm:

- `DISCOVERED`
- `FETCH_PENDING`
- `FETCHED`
- `AUTO_EXACT_SHA`
- `AUTO_CONTENT_MATCH`
- `NEEDS_DISCOVERY`
- `NEEDS_REVIEW`
- `BLOCKED`
- `APPROVED` chỉ để biểu diễn dữ liệu bên ngoài đã được người duyệt; resolver không tự tạo trạng thái này.

Decision phải dựa trên rule/reason code, không dựa vào một confidence score duy nhất. Có thể có score để xếp hàng review nhưng score không được tự override điều kiện bắt buộc.

## 8. Adapter và fetcher

### VBPL

- Trích `ItemID` từ các URL legacy, kể cả route theo bộ/ngành.
- Thử route toàn quốc có kiểm soát: `vbpq-van-ban-goc.aspx`, `vbpq-thuoctinh.aspx`, `vbpq-toanvan.aspx`, `vbpq-lichsu.aspx` và URL giao diện mới nếu phát hiện được.
- Nếu final page là homepage, trang lỗi, login hoặc không chứa identity mong đợi thì đánh dấu fetch/candidate thất bại.
- Fixture bắt buộc: `ItemID=162453`.

### Công báo, Chính phủ, Tòa án, ILO

- Phân biệt trang chi tiết với direct binary.
- Hỗ trợ nhiều attachment và ghi record corpus đang đối chiếu với attachment nào.
- Với Tòa án, phân biệt án lệ, bản án, quyết định và bài giới thiệu; bài giới thiệu không thay binary chính thức.
- Với ILO, giữ rõ bản gốc, bản dịch và trạng thái unofficial translation.

### HTTP và Playwright

- HTTP là đường mặc định; cấu hình timeout, redirect limit, retry có backoff và rate limit theo provider.
- Kiểm lại allowlist sau mọi redirect.
- Playwright chỉ dùng khi adapter khai báo cần JS/click/download; dùng selector cố định và lưu action log.
- Nếu direct URL là tạm thời, lưu stable `identity_url`, download recipe/action và đánh dấu binary URL `EPHEMERAL` thay vì bịa URL cố định.
- Browser-use, Crawl4AI và SearXNG không phải dependency bắt buộc của P0/P1. SearXNG chỉ là discovery fallback có interface rõ; Browser-use không được thêm vào đường tự phê duyệt.

## 9. Xác minh binary và bảo mật

Trước khi lưu candidate binary:

- chỉ chấp nhận HTTPS và final host được phép;
- giới hạn kích thước, timeout, redirect và số retry;
- kiểm `Content-Type`, phần mở rộng và magic bytes;
- tạo tên file an toàn, chống path traversal;
- không thực thi macro/script hoặc mở tệp bằng chương trình có thể chạy code;
- tính SHA-256 streaming;
- lưu kích thước và số trang nếu xác định an toàn;
- tải vào cache/quarantine riêng, không ghi vào corpus;
- nếu SHA khác, không tự thay corpus và không kết luận content match nếu chưa có bộ so sánh phù hợp.

`AUTO_EXACT_SHA` chỉ được tạo khi đồng thời:

1. final provider/domain/route hợp lệ;
2. identity không mâu thuẫn;
3. binary hợp lệ;
4. downloaded SHA bằng chính xác `corpus_sha256`;
5. evidence đầy đủ.

## 10. Evidence store và đầu ra

Dùng SQLite cho state/evidence, có schema version và transaction. Lưu tối thiểu:

- record/candidate ID;
- requested URL, final URL và redirect chain;
- query/discovery method nếu có;
- HTTP status và headers cần thiết;
- fetched time UTC;
- provider/adapter/resolver version;
- snapshot path/hash;
- binary cache path, MIME, size, page count, SHA;
- corpus SHA;
- metadata extracted và từng phép so khớp;
- decision, reason codes, lỗi và retry;
- Playwright action log nếu có.

Xuất các artifact sau, nhưng không commit cache/binary lớn:

```text
artifacts/00_manifest/source_resolution.sqlite
artifacts/00_manifest/source_catalog_auto.jsonl
artifacts/00_manifest/source_resolution_evidence.jsonl
artifacts/reports/source_resolution_summary.json
artifacts/reports/source_resolution_review_queue.csv
.cache/source_resolver/pages/
.cache/source_resolver/downloads/
```

Cập nhật `.gitignore` nếu cần cho database tạm, cache, snapshot và binary; không ignore code, config schema, fixture nhỏ hoặc report thiết kế cần review.

## 11. CLI yêu cầu

Cung cấp CLI hoặc subcommand phù hợp với CLI hiện có, hỗ trợ tối thiểu:

```text
import-seed --csv ... --dry-run
resolve --record ...
resolve --all --dry-run
export
merge --dry-run
```

Yêu cầu:

- `import-seed --dry-run` không ghi state/config;
- `resolve --all` có resume/checkpoint, giới hạn concurrency và không tải lại binary đã có evidence hợp lệ;
- có lựa chọn offline/test mode không truy cập mạng;
- `merge --dry-run` chỉ sinh diff đề xuất, không sửa catalog;
- exit code khác 0 khi integrity/schema/security check thất bại;
- log gọn, không in toàn bộ HTML/binary hoặc secret.

## 12. Kiểm thử bắt buộc

Không viết test chỉ lặp lại implementation. Dùng fixture nhỏ, deterministic và không phụ thuộc Internet cho test mặc định.

Phải có test cho:

1. import đủ 95 seed record và kiểm đúng phân bố 57/24/10/4;
2. 84/10/1 được ánh xạ đúng từ seed thực tế;
3. protected field/path/SHA mismatch bị từ chối;
4. path traversal bị từ chối;
5. import hai lần không duplicate;
6. `instrument_number` và `document_number` tạo đúng `canonical_identifier` theo nhóm;
7. record chưa tải không thể trở thành `AUTO_EXACT_SHA`;
8. downloaded SHA trùng corpus tạo `AUTO_EXACT_SHA` khi mọi điều kiện khác đạt;
9. SHA khác chuyển `AUTO_CONTENT_MATCH` hoặc `NEEDS_REVIEW`, không sửa corpus;
10. redirect VBPL về homepage bị phát hiện;
11. chuẩn hóa `ItemID=162453`;
12. direct PDF hợp lệ và HTML giả PDF bị phân biệt bằng magic/MIME;
13. final redirect ra ngoài allowlist bị chặn;
14. hai file Nghị quyết 326 dùng cùng metadata URL vẫn được xác minh binary riêng;
15. secondary URL không thể tự thành official;
16. resolver không bao giờ ghi reviewer/APPROVED;
17. export JSONL/CSV ổn định và deterministic;
18. Windows path và POSIX/Kaggle path đều hoạt động.

Network smoke test phải opt-in bằng marker/env, không chạy trong test mặc định. Nếu dùng Playwright, test mặc định dùng local fixture server hoặc mocked transport; không yêu cầu download browser chỉ để chạy unit test.

## 13. Kaggle và dependency

- Kiểm `kaggle/bootstrap.py`, `kaggle/constraints.txt`, bundle/package script và các dependency groups hiện có.
- Thêm dependency tối thiểu; ưu tiên thư viện đang có trong project.
- Playwright phải optional và có thông báo rõ nếu browser binary chưa được cài.
- Không làm hỏng môi trường Python/Kaggle hiện tại hoặc bắt buộc dựng SearXNG service chỉ để chạy P0/P1.
- Nếu package/bundle Kaggle cần cập nhật để chứa code/config/fixture mới, cập nhật script nguồn tạo bundle; không sửa tay duy nhất một bản ZIP sinh ra.

## 14. Trình tự thực hiện

1. Audit code/config/test hiện có và nêu ngắn gọn điểm tích hợp.
2. Thực hiện P0: models, provider registry, importer, SQLite/evidence, fixture và test.
3. Thực hiện P1: HTTP fetcher, verifier, VBPL/Công báo/Chính phủ adapters, CLI và test.
4. Chạy thử end-to-end trên 8 direct URL khi môi trường cho phép. Nếu mạng bị chặn, giữ smoke test opt-in và báo chính xác; không giả kết quả SHA.
5. Chạy dry-run trên toàn bộ seed; tuyệt đối không merge catalog.
6. Chỉ sau khi P0/P1 ổn định mới thêm adapter Tòa án/ILO và discovery interface. Không thêm AI browser trước khi deterministic path đã hoàn chỉnh.
7. Chạy test phù hợp, lint/type check nếu repository có cấu hình và kiểm packaging/Kaggle manifest.

## 15. Tiêu chí hoàn tất

Chỉ báo hoàn thành khi:

- code, config, migration/schema và test đều tồn tại trong repository;
- seed 95 record import được và integrity check pass;
- dry-run tạo đúng queue/artifact mà không sửa corpus/catalog;
- state/evidence idempotent;
- không có record chưa tải bị nâng sai thành exact match;
- test mặc định không cần Internet và pass;
- Kaggle/bootstrap/package không bị phá;
- có tài liệu chạy ngắn cho local Windows và Kaggle;
- có báo cáo implementation nêu file thay đổi, test đã chạy, kết quả dry-run, phần chưa thể xác minh vì mạng và bước tiếp theo.

## 16. Định dạng báo cáo cuối

Tạo `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md` gồm:

1. kiến trúc thực tế đã triển khai;
2. file thêm/sửa;
3. dependency thay đổi;
4. test và lệnh đã chạy;
5. kết quả import/dry-run theo từng trạng thái;
6. số URL đã fetch, số binary đã tải, số exact SHA, số content mismatch, số review/block;
7. các giới hạn còn lại;
8. hướng dẫn local Windows;
9. hướng dẫn Kaggle;
10. khẳng định rõ corpus/catalog có bị thay đổi hay không.

Không báo “hoàn thành 100%” nếu chưa tải và xác minh nguồn. Không dùng exit code 0 làm bằng chứng dữ liệu đúng. Nếu phát hiện yêu cầu trong tài liệu xung đột với code hoặc dữ liệu thực, ưu tiên tính toàn vẹn, ghi rõ xung đột trong báo cáo và chọn phương án không làm sai provenance.
