# Thiết kế Automatic Legal Source Resolver

## Kết luận thiết kế

Ý tưởng tự động hóa bước tìm nguồn là đúng, nhưng không nên dùng chuỗi `SearXNG -> Crawl4AI -> Browser-use` làm đường đi mặc định cho mọi tài liệu. Dự án hiện có metadata và nhiều `ItemID`/URL cũ; cách chính xác, nhẹ và dễ kiểm toán hơn là dùng **adapter xác định theo từng cổng thông tin trước**, sau đó mới tìm kiếm web và cuối cùng mới dùng tác nhân AI.

Mục tiêu của resolver là tự động thu thập và chứng minh nguồn kỹ thuật. Nó không được tự tuyên bố một văn bản đã được duyệt pháp lý. Kết quả phải phân biệt:

- nguồn chính thức đã tải lại và khớp đúng SHA-256;
- nguồn có metadata khớp nhưng tệp khác byte/nội dung;
- URL chỉ là ứng viên;
- quyết định pháp lý đã được người đủ chuyên môn duyệt.

Ví dụ URL cũ `https://vbpl.vn/bolaodong/Pages/ivbpq-thuoctinh.aspx?ItemID=162453` có thể bị chuyển về trang chủ. Resolver phải lấy `ItemID=162453`, thử tuyến chuẩn toàn quốc như `https://vbpl.vn/TW/Pages/vbpq-van-ban-goc.aspx?ItemID=162453`, xác nhận số `21/2021/TT-BLĐTBXH`, rồi lấy trang/tệp Công báo tương ứng nếu cần. Không nên coi redirect về trang chủ là tài liệu hợp lệ.

## Dữ liệu seed đã có từ lượt thu thập V8.1

Không tìm lại từ đầu. Import `review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv` làm seed, sau khi đọc [báo cáo kiểm tra](source_review_return_audit.md). Bảng có đủ 95 dòng và SHA corpus không đổi; đã thu được 84 candidate official, 81 trang nguồn và 8 direct download URL. Có 10 `SOURCE_NOT_FOUND` và 1 `MULTIPLE_CANDIDATES` thuộc nhóm judicial.

Toàn bộ 95 dòng vẫn là `NOT_DOWNLOADED`, nên không dòng nào được nhập thành `AUTO_EXACT_SHA`. Khi import, ánh xạ `ACCESS_BLOCKED` có URL thành `DISCOVERED/FETCH_PENDING`; không coi đó là website chắc chắn chặn. 38 candidate official có identity chưa hoàn toàn chắc chắn phải qua metadata verifier. Dùng `instrument_number` cho legal/consolidated và `document_number` cho judicial, chuẩn hóa thành `canonical_identifier` thay vì giả định một cột áp dụng cho mọi nhóm.

## Kiến trúc đề xuất

```text
Manifest + Source Catalog + SHA corpus
                 |
                 v
        Metadata normalizer
                 |
                 v
     Provider-specific adapters
  VBPL / Công báo / Chính phủ / Tòa án
                 |
       +---------+----------+
       |                    |
  URL/tệp có sẵn       Chưa tìm thấy
       |                    |
       |          Official-site search
       |                    |
       |            SearXNG discovery
       |                    |
       +---------+----------+
                 |
       HTTP fetch + HTML parser
                 |
      Playwright deterministic fallback
                 |
      Candidate and binary verifier
                 |
       Evidence store + decision rules
                 |
       +---------+----------+
       |         |          |
 AUTO_EXACT  CONTENT_MATCH  NEEDS_REVIEW
       |         |          |
       +---------+----------+
                 |
      Source Catalog candidate export
```

### 1. Chuẩn hóa đầu vào

Resolver lấy `document_number`, loại văn bản, cơ quan ban hành, ngày ban hành, tiêu đề, đường dẫn corpus, SHA-256 và URL/ItemID cũ. Số văn bản phải được chuẩn hóa khoảng trắng, dấu gạch, chữ hoa/thường nhưng vẫn giữ nguyên giá trị gốc để làm bằng chứng.

### 2. Adapter theo nhà cung cấp là đường mặc định

Tạo adapter riêng cho:

- VBPL: nhận diện `ItemID`, thử các tuyến `TW`, `vbpq-van-ban-goc`, `vbpq-thuoctinh`, `vbpq-lichsu`; phát hiện redirect sai về trang chủ.
- Công báo: tìm trang chi tiết và các tệp PDF/DOC chính thức; lưu cả trang metadata lẫn URL tệp.
- Văn bản Chính phủ: tìm theo số/ký hiệu và trích trang chi tiết/tệp đính kèm.
- Tòa án/án lệ: dùng adapter và quy tắc metadata riêng; không dùng cùng tiêu chí với văn bản quy phạm pháp luật.
- Nguồn cơ quan ban hành khác: chỉ hoạt động nếu domain và mẫu URL nằm trong registry đã duyệt.

Thứ tự này tận dụng cấu trúc ổn định của từng website và cho kết quả lặp lại được. Không cần hỏi công cụ tìm kiếm nếu URL hoặc ItemID hiện có đã định vị được tài liệu.

### 3. Fetcher theo tầng

1. `httpx`/HTTP và BeautifulSoup cho trang tĩnh, redirect và tệp tải trực tiếp.
2. Playwright với selector cố định cho trang cần JavaScript, nút “Xem”, form tìm kiếm hoặc sự kiện download.
3. Crawl4AI chỉ là bộ trích xuất tổng quát tùy chọn khi adapter chưa hiểu bố cục trang.
4. Browser-use chỉ tạo ứng viên trong chế độ thí nghiệm, tắt mặc định. Kết quả của agent luôn là `NEEDS_REVIEW` cho tới khi bộ xác minh độc lập kiểm tra xong.

Playwright phù hợp hơn AI agent cho thao tác click đã biết vì hành vi có thể kiểm thử, ghi lại selector và chạy lại. Browser-use có thể bị nội dung trang tác động, khó lặp lại và có chi phí LLM, nên không được phép tự phê duyệt nguồn hay dùng trình duyệt đã đăng nhập.

### 4. Tìm kiếm chỉ là fallback

SearXNG dùng khi adapter và chức năng tìm kiếm nội bộ của website không trả kết quả. Nó là metasearch, không phải kho dữ liệu pháp luật và không tự bảo đảm kết quả chính xác. Public instance có thể tắt JSON, giới hạn truy cập hoặc trả kết quả khác nhau; `site:` cũng không được mọi search engine xử lý giống nhau. Khi dùng SearXNG phải lưu query, engine, thời điểm và toàn bộ candidate đã trả về.

Không cần dựng SearXNG thường trực ngay ở phiên bản đầu. Với 95 tài liệu, adapter trực tiếp cộng Playwright có khả năng giải quyết phần lớn hồ sơ với ít RAM và ít điểm lỗi hơn. Self-host SearXNG chỉ nên thêm khi số tài liệu tăng hoặc official-site search không đủ.

### 5. Không dùng một bảng xếp hạng domain chung

Không hard-code `VBPL > Chính phủ > Công báo` cho mọi trường hợp. Một văn bản có thể cần ba loại nguồn:

- `identity_url`: trang chứng minh số, tên, cơ quan và ngày;
- `binary_url`: tệp PDF/DOC cụ thể đã tải;
- `status_url`: trang lịch sử, sửa đổi, bãi bỏ và hiệu lực.

Công báo có thể là nguồn tệp tốt nhất, còn VBPL là nguồn lịch sử tốt hơn. Adapter khai báo vai trò và thẩm quyền của từng domain/route trong `config/source_provider_registry.yaml`. Nguồn thứ cấp chỉ hỗ trợ discovery, không tự trở thành nguồn chính thức.

Nếu nút “Xem” dùng POST, JavaScript hoặc URL tải tạm thời nên không thể copy một link bền vững, catalog vẫn lưu `identity_url` ổn định của trang chi tiết. Evidence store lưu thao tác/selector hoặc request tải, thời điểm, response headers và SHA của bytes nhận được; `binary_url` được đánh dấu `EPHEMERAL` hoặc để trống thay vì bịa một URL. Adapter phải chứng minh có thể tải lại qua trang chi tiết.

### 6. Bộ xác minh xác định

Mỗi candidate phải qua các kiểm tra độc lập:

- final URL sau redirect thuộc domain và route được phép;
- trang không phải homepage/error/login/CAPTCHA;
- số văn bản khớp chính xác sau chuẩn hóa;
- loại, cơ quan, ngày và tiêu đề không mâu thuẫn;
- tệp tải có magic bytes, MIME, phần mở rộng và kích thước hợp lệ;
- SHA-256 tệp tải được so với SHA của corpus;
- nếu SHA khác: so nội dung đã chuẩn hóa, số trang, phụ lục và dấu hiệu phiên bản; tuyệt đối không tự thay corpus;
- dữ liệu hiệu lực/lịch sử cần nguồn có đúng vai trò, và nên được đối chứng từ hai trang chính thức khi có thể.

Không quyết định bằng một điểm `confidence=0.98` duy nhất. Hệ thống dùng bảng luật với reason code; điểm chỉ phục vụ sắp hàng review.

## Trạng thái và quyền quyết định

| Trạng thái | Điều kiện | Tác động |
|---|---|---|
| `DISCOVERED` | Có URL ứng viên | Chưa đủ dùng |
| `FETCHED` | Đã lưu trang/tệp và bằng chứng | Chưa xác minh |
| `AUTO_EXACT_SHA` | Domain/route chính thức, identity khớp, tệp tải khớp SHA corpus | Có thể qua gate provenance kỹ thuật |
| `AUTO_CONTENT_MATCH` | Metadata và nội dung khớp nhưng SHA khác | Phải review sự khác biệt phiên bản/tệp |
| `NEEDS_REVIEW` | Nhiều ứng viên, thiếu trường, mâu thuẫn hoặc nguồn thứ cấp | Con người xử lý ngoại lệ |
| `BLOCKED` | CAPTCHA, lỗi nguồn, không tìm thấy, cấm truy cập | Giữ lỗi và hướng xử lý |
| `APPROVED` | Người có thẩm quyền đã duyệt bằng chứng | Duyệt pháp lý |

Gate hiện tại cần được tách thành:

1. **Source acquisition/provenance gate**: chấp nhận `AUTO_EXACT_SHA` với evidence đầy đủ.
2. **Legal/temporal review gate**: vẫn yêu cầu reviewer cho hiệu lực, phạm vi sửa đổi, bản hợp nhất và Gold.

Việc này cho phép máy xử lý khâu lặp lại mà không giả mạo `reviewer`. Một người có thể duyệt một lần registry domain/route và bộ fixture của adapter, sau đó chỉ kiểm mẫu và ngoại lệ thay vì bấm 95 hồ sơ.

## Bằng chứng phải lưu bất biến

Mỗi lần resolve cần lưu:

- URL yêu cầu, final URL, chuỗi redirect, HTTP status và headers cần thiết;
- query/search engine nếu có tìm kiếm;
- thời điểm UTC, phiên bản resolver/adapter và cấu hình provider;
- snapshot HTML hoặc WARC, URL tải và hash của bytes tải về;
- SHA corpus, MIME/magic, kích thước, số trang nếu có;
- metadata trích xuất, từng phép so khớp, reason code và quyết định;
- lỗi, retry, CAPTCHA/rate limit và thao tác Playwright;
- nếu có AI agent: model, prompt, danh sách action và candidate; agent không được ghi `APPROVED`.

Dùng SQLite làm hàng đợi/trạng thái vì dữ liệu chỉ có 95 tài liệu và cần transaction/idempotency. Xuất JSONL/CSV để review và tích hợp Git; chưa cần PostgreSQL.

Các đầu ra đề xuất:

```text
artifacts/00_manifest/source_resolution.sqlite
artifacts/00_manifest/source_catalog_auto.jsonl
artifacts/00_manifest/source_resolution_evidence.jsonl
artifacts/reports/source_resolution_summary.json
artifacts/reports/source_resolution_review_queue.csv
.cache/source_resolver/pages/
.cache/source_resolver/downloads/
```

Snapshot và download có thể lớn, chứa corpus và phải để trong Dataset/ZIP Private, không push Git công khai.

## An toàn và vận hành

- chỉ cho phép HTTPS và domain allowlist; kiểm lại domain sau mọi redirect;
- giới hạn kích thước, thời gian, số redirect/retry và tốc độ theo domain;
- kiểm magic bytes, chống path traversal, không chạy macro/script trong tệp tải;
- cách ly tệp lạ; không vượt CAPTCHA hoặc cơ chế chống bot;
- tôn trọng robots, điều khoản sử dụng và cache để không tải lặp;
- Browser-use không được dùng cookie/tài khoản cá nhân hoặc đọc secret;
- online runtime chỉ được tạo candidate/cache DRAFT, không tạo citation “đã xác minh” ngay trong câu trả lời;
- citation online dùng URL đã được resolver lưu từ offline build để giữ tính lặp lại.

## Cấu trúc code

```text
src/vn_labor_offline/source_resolver/
  models.py
  resolver.py
  normalizer.py
  provider_registry.py
  providers/
    vbpl.py
    congbao.py
    vanban_chinhphu.py
    toaan.py
    generic_official.py
  discovery/
    official_search.py
    searxng.py
  fetchers/
    http.py
    playwright.py
    browser_agent.py
  extractors/
    html.py
    binary.py
  verification/
    identity.py
    authority.py
    binary.py
    content.py
    decision.py
  evidence.py
  store.py
  cli.py
```

## Lộ trình triển khai

### P0 — Đóng băng quy tắc và fixture

- Lập registry domain/route và vai trò nguồn.
- Chọn 10 fixture gồm URL VBPL redirect, trang cần bấm “Xem”, PDF/DOC, hai tệp cùng số văn bản, án lệ và trường hợp không tìm thấy.
- Bắt buộc có fixture `ItemID=162453`.
- Viết importer cho bảng trả về V8.1; xác nhận 95 path/SHA với manifest trước khi tạo queue.

### P1 — Resolver không AI

- Viết normalizer, SQLite/evidence store, HTTP fetcher và ba adapter VBPL/Công báo/Chính phủ.
- Trước tiên tải và kiểm 8 direct URL trong seed để chứng minh đường ống fetch/hash/decision chạy end-to-end.
- Sau đó chạy trên 84 candidate official; adapter tự chuẩn hóa URL/ItemID và không tin cờ `official_source` từ CSV nếu final URL/metadata không đạt rule.
- Chỉ xuất `AUTO_EXACT_SHA`, `AUTO_CONTENT_MATCH`, `NEEDS_REVIEW`, `BLOCKED`; chưa sửa config gốc.

### P2 — Discovery và nhóm tư pháp

- Thêm official-site search, rồi SearXNG fallback.
- Thêm adapter Tòa án/án lệ và quy tắc riêng cho judicial/supplementary.

### P3 — Trang động

- Thêm Playwright deterministic cho nút “Xem”, form tìm và download.
- Chỉ thử Browser-use trên queue còn lại và không cho agent phê duyệt.

### P4 — Tích hợp gate

- Review kết quả và bộ fixture; phê duyệt provider registry.
- Tách gate provenance kỹ thuật khỏi gate pháp lý.
- Merge `AUTO_EXACT_SHA` vào catalog bằng lệnh riêng có dry-run, diff và rollback.

### P5 — Nghiệm thu

- 95/95 record có trạng thái và evidence, không bị bỏ im lặng.
- Chạy hai lần cho kết quả idempotent nếu nguồn không đổi.
- 100% `AUTO_EXACT_SHA` thực sự tải từ allowlist và khớp SHA.
- 0 candidate từ nguồn thứ cấp được đánh dấu official tự động.
- Mọi SHA khác, redirect homepage, nhiều candidate hoặc metadata mâu thuẫn đều vào review queue.
- Người kiểm tra lấy mẫu toàn bộ nhóm adapter; nếu có một false positive thì hạ rule đó về `NEEDS_REVIEW` và sửa fixture.

Không cam kết trước resolver sẽ tự giải quyết 80/95 tài liệu. Tỷ lệ tự động hóa phải đo sau P1/P2; độ chính xác của `AUTO_EXACT_SHA` quan trọng hơn số lượng. Với mô hình này, con người không phải tự tìm và copy 95 URL: họ duyệt chính sách nguồn một lần, kiểm mẫu kết quả khớp tuyệt đối và xử lý các ngoại lệ thực sự.
