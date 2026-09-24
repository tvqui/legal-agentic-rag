# Prompt Copilot P2.1 — sửa attachment resolution trước khi chạy batch

Bạn hãy tiếp tục hoàn thiện **Automatic Legal Source Resolver** từ trạng thái P2 hiện tại. Đây là một vòng sửa correctness và provider discovery có kiểm soát. **Không chạy batch 76 record, không merge catalog, không thay corpus và không chạy lại pipeline OFFLINE** trong vòng này.

Trước khi sửa, hãy đọc và đối chiếu trực tiếp:

1. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
2. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`
3. toàn bộ package `src/vn_labor_offline/source_resolver/` (hoặc vị trí package thực tế trong repository)
4. `config/source_provider_registry.yaml`
5. `test_source_resolver.py`
6. DB `artifacts/00_manifest/source_resolution_p2.sqlite`
7. export `artifacts/00_manifest/source_resolution_p2_export/`
8. cache `.cache/source_resolver_p2/`

Không chỉ dựa vào báo cáo Markdown. Hãy kiểm tra database, evidence events, candidate states, file cache và JSONL export thực tế.

## 1. Hiện trạng đã xác minh

P2 đã có nền tảng đúng: required/optional candidates, seed/resolver fields riêng, HTML attachment extraction, retry/state/batch CLI và smoke test giới hạn. Test hiện báo cáo `14/14` resolver và `115/115` toàn repository.

Tuy nhiên chưa được mở batch vì còn các lỗi correctness sau:

1. Hai fallback Công báo cho `06/2020/TT-BLĐTBXH` và `24/2022/TT-BLĐTBXH` là **trang HTML identity**, nhưng có đường đi khiến URL HTML bị xử lý như binary. Export có thể ghi `final_binary_url` là trang `.htm`, cùng `UNKNOWN_MAGIC`, `SHA_MISMATCH` và `resolved_sha_match=NO`.
2. Resolver đang giữ biến kết quả binary/identity theo kiểu candidate xử lý cuối ghi đè candidate trước. Một candidate lỗi chạy sau có thể làm mất evidence exact tốt hơn đã có.
3. Identity HTTP 200 nhưng identifier không khớp có thể còn candidate state `FETCHED`, dù record state là `NEEDS_REVIEW`.
4. `resolved_sha_match=NO` đang được dùng cả khi chưa tải được binary. Trạng thái này phải là `NOT_DOWNLOADED` hoặc `UNKNOWN`, không phải mismatch.
5. Export còn các field seed cũ không prefix nằm cạnh field resolver mới, tạo hai cách hiểu mâu thuẫn.
6. Generic link parser có thể dùng nhãn “Tải về/Xem nhanh” để nâng một URL HTML hoặc JavaScript control thành `BINARY` mà chưa chứng minh endpoint trả binary.
7. Provider registry áp route quá rộng theo provider; `/van-ban/*.htm` của Công báo có thể được chấp nhận ở role `BINARY`.
8. Playwright hiện mới là boundary/stub, chưa thực hiện browser download thật.
9. Báo cáo implementation có phần cũ không còn đúng, gồm schema version và kết quả direct8/P2.

## 2. Sửa mô hình tổng hợp evidence

### 2.1 Candidate độc lập và chọn evidence tốt nhất

Mỗi candidate phải tạo một kết quả độc lập, bất biến. Sau khi xử lý hết candidates, hãy chọn:

- `best_identity_evidence`
- `best_binary_evidence`
- `best_status_evidence` nếu có

Không dùng biến “kết quả cuối cùng đã xử lý”. Xếp hạng binary tối thiểu theo thứ tự:

1. official/allowed binary, magic và MIME hợp lệ, SHA trùng corpus, identifier từ binary khớp;
2. official/allowed binary, magic và MIME hợp lệ, SHA trùng corpus nhưng identity chưa đủ;
3. binary hợp lệ, identifier khớp nhưng SHA khác;
4. binary hợp lệ nhưng identity chưa xác minh;
5. tải lỗi, HTML giả binary, magic/MIME lỗi hoặc candidate bị chặn.

Evidence mức thấp hơn chạy sau không được ghi đè evidence tốt hơn. Candidate optional lỗi chỉ tạo warning/evidence event; không hạ state nếu required capabilities đã đạt.

Viết hàm xếp hạng thuần/deterministic và unit test trực tiếp. Nếu hai evidence cùng hạng, tie-break bằng quy tắc ổn định như provider priority, URL canonical và event timestamp/ID; ghi rõ quy tắc trong code.

### 2.2 State và reason codes phải nhất quán

- Identity HTTP 200 nhưng canonical identifier không khớp hoặc không tìm thấy: candidate state `NEEDS_REVIEW`, không phải `FETCHED`.
- Binary tải thành công nhưng SHA khác corpus: `NEEDS_REVIEW`.
- HTTP/redirect/domain/size/magic/MIME lỗi: state đúng theo taxonomy hiện có; không hạ thành `FETCH_PENDING`.
- Tách `blocking_reasons` và `warnings`. Summary có thể gộp để hiển thị, nhưng logic quyết định chỉ dùng nhóm tương ứng.
- `AUTO_EXACT_SHA` chỉ khi binary official/allowed thực sự được tải, magic/MIME hợp lệ, SHA trùng corpus và identity đã được xác minh theo rule hiện hành.
- Không tạo `AUTO_CONTENT_MATCH` chỉ từ confidence score hoặc metadata gần giống.

### 2.3 Semantics của export

Chuẩn hóa:

- `resolved_sha_match=YES`: đã tải valid binary và SHA trùng corpus.
- `resolved_sha_match=NO`: đã tải valid binary và SHA thực sự khác corpus.
- `resolved_sha_match=NOT_DOWNLOADED`: chưa có valid binary bytes để so SHA.
- Không dùng `NO` cho HTML, HTTP error, magic lỗi hoặc chưa tìm thấy attachment.
- `final_binary_url` chỉ được ghi khi URL cuối đã trả về valid binary bytes. Không bao giờ ghi trang HTML identity vào trường này.
- `final_identity_url` chỉ trỏ đến trang/binary evidence dùng để xác minh identity, với `identity_source` tương ứng.
- Giữ seed provenance bằng các field `seed_*`. Loại bỏ khỏi auto export các alias mơ hồ `collection_result`, `sha_match`, `downloaded_sha256`, hoặc đánh dấu deprecated và bảo đảm mọi consumer/merge chỉ đọc field có prefix. Không được để hai bộ field cùng mang nghĩa “kết quả hiện tại”.
- Review queue, summary và merge diff phải dùng resolver fields.

Thêm schema/export version nếu thay đổi contract. Nếu cần migration DB, migration phải idempotent và giữ evidence cũ.

## 3. Provider registry theo role

Đổi registry để domain/route có thể giới hạn theo role/capability, thay vì một allowlist rộng cho mọi role.

Quy tắc tối thiểu:

- `congbao.chinhphu.vn/van-ban/*.htm`: `IDENTITY`, không phải `BINARY`.
- Endpoint tải Công báo có tham số/route tải rõ ràng và CDN chính thức: `BINARY`.
- Bổ sung host CDN chính thức được quan sát từ trang Công báo, tối thiểu `g7.cdnchinhphu.vn`; kiểm tra thêm host thực tế trước khi thêm, không allow wildcard toàn `*.chinhphu.vn`.
- `vbpl.vn/.../Pages/*.aspx`: `IDENTITY` hoặc `STATUS_HISTORY` theo route.
- `vbpl.vn/FileData/...`: `BINARY`.
- Route identity không được pass validation với role binary chỉ vì cùng provider.

Mỗi redirect phải được kiểm allowlist và role trước request kế tiếp và tại URL cuối. Không mở rộng allowlist chỉ để smoke test pass.

## 4. Sửa deterministic attachment extraction

### 4.1 Generic parser

- Sửa quản lý anchor text theo đúng start/end tag; không để label của anchor trước dồn sang anchor sau.
- Resolve URL tương đối bằng `urljoin`, giữ encoding hợp lệ và deduplicate bằng canonical URL.
- Chỉ tạo direct `BINARY` khi một trong các điều kiện deterministic đúng:
  - path có extension binary được hỗ trợ; hoặc
  - endpoint/provider rule xác định rõ response tải binary; hoặc
  - probe HTTP đã xác nhận response là valid binary rồi mới nâng role trong evidence.
- Nếu label là “Tải về”, “Xem nhanh”, “PDF”, “DOC” nhưng href là `javascript:`, `#`, HTML route, postback hoặc control, tạo candidate/action loại `DOWNLOAD_CONTROL`; không gán `BINARY`.
- Không coi `Content-Type` đơn lẻ là đủ; vẫn xác minh magic bytes và size.

### 4.2 Adapter Công báo

Tạo adapter/provider rule riêng để parse attachment thật từ trang chi tiết. Dùng fixture tối giản lấy từ cấu trúc trang chính thức, không lưu toàn bộ nội dung có bản quyền.

Kiểm chứng tối thiểu với:

- `06/2020/TT-BLĐTBXH`: trang identity `https://congbao.chinhphu.vn/van-ban/thong-tu-so-06-2020-tt-bldtbxh-32743.htm`
- `24/2022/TT-BLĐTBXH`: trang identity `https://congbao.chinhphu.vn/van-ban/thong-tu-so-24-2022-tt-bldtbxh-38574.htm`

Hai trang này có link tải DOC/PDF trên CDN chính thức. Parser phải phát hiện link CDN thật và tuyệt đối không biến URL `.htm` thành binary. Không cần Playwright cho trang nếu link thật đã có trong HTML response.

### 4.3 Adapter VBPL

Với `ItemID`, probe có kiểm soát các route chính thức đã đăng ký, gồm thuộc tính/toàn văn/lịch sử/văn bản gốc. Phát hiện homepage shell/error dù HTTP 200.

- Trích `FileData`, href trực tiếp, `data-*`, `onclick`, postback/download control có cấu trúc đã biết.
- Với URL FileData cũ 404, giữ evidence rồi tiếp tục thử attachment được khám phá từ identity/history page.
- Không đoán tên attachment bằng cách thay chuỗi hoặc tự ghép filename.
- `10/2020/TT-BLĐTBXH`, `ItemID=146696`, phải có fixture provider-specific. Nếu HTML chỉ chứa control cần JS, tạo `DOWNLOAD_CONTROL` để Playwright xử lý.

## 5. Triển khai Playwright thật nhưng chỉ dùng khi cần

Boundary Playwright hiện tại phải trở thành implementation opt-in, deterministic:

- Chỉ chạy khi CLI bật network/browser rõ ràng và candidate là `DOWNLOAD_CONTROL` hoặc provider adapter xác định cần JS.
- Kiểm package và browser executable; thiếu dependency phải trả reason code rõ ràng, không silent fallback.
- Mở đúng official identity URL, chờ selector/provider rule cụ thể, thao tác click có giới hạn và bắt `download` event.
- Lưu download vào temp file, sau đó chạy lại size, magic, MIME, SHA, identity và allowlist/final URL checks trước atomic rename.
- Ghi `action_log`: URL, selector/action, thời điểm, navigation/redirect, suggested filename, download URL nếu Playwright cung cấp, hash kết quả và lỗi.
- Giới hạn timeout, số action, số download và cleanup partial file.
- Không dùng LLM/vision để tự click tùy ý. Không click ngoài provider adapter/selector allowlist.

Nếu Kaggle chưa có browser binary, code phải báo hướng dẫn cài/enable rõ ràng; test bằng mock/fixture vẫn phải chạy offline.

## 6. Regression tests bắt buộc

Bổ sung test đủ để bắt lại các lỗi trên. Tối thiểu:

1. exact binary evidence không bị candidate mismatch/lỗi chạy sau ghi đè;
2. optional identity 403 không hạ record khi exact binary + binary identity đã đủ;
3. identity HTTP 200 thiếu/sai identifier có candidate state `NEEDS_REVIEW`;
4. chưa tải valid binary xuất `NOT_DOWNLOADED`, không phải `NO`;
5. valid binary SHA khác mới xuất `NO`;
6. `final_binary_url` không bao giờ là HTML page;
7. role-specific registry từ chối Công báo `.htm` ở role binary;
8. fixture Công báo 06 và 24 khám phá direct CDN DOC/PDF đúng, deduplicate đúng;
9. generic parser không phân loại HTML/JavaScript “Tải về” thành binary;
10. anchor label không bị nối qua nhiều thẻ;
11. fixture VBPL 10 tìm direct link hoặc tạo `DOWNLOAD_CONTROL` đúng;
12. mocked Playwright download lưu action log và đi qua full binary verification;
13. redirect sang host/route/role không được phép bị chặn trước khi tải;
14. export không còn field mang nghĩa hiện tại mâu thuẫn;
15. resume/idempotency không nhân đôi evidence hoặc đổi best evidence không có lý do.

Chạy `compileall`, resolver tests và toàn bộ repository tests. Báo số test thực tế; không ghi PASS nếu có skipped quan trọng mà chưa giải thích.

Đổi `import fitz` sang API hiện hành `import pymupdf` nếu dependency đang cung cấp tên đó, và thêm test import để tránh deprecation warning; không nâng dependency tùy tiện.

## 7. Network verification có kiểm soát

Sau khi toàn bộ test offline pass, dùng **DB/cache/export mới hoàn toàn** cho P2.1; không ghi đè P2/direct8:

1. chạy lại bốn record smoke P2 hiện tại;
2. xác minh NATLEX vẫn `AUTO_EXACT_SHA`, identity 403 chỉ là warning;
3. chạy Công báo 06 và 24 bằng HTTP parser trước, kiểm `final_binary_url` là CDN binary thật;
4. chạy VBPL 10 bằng HTTP adapter; chỉ bật Playwright nếu nhận `DOWNLOAD_CONTROL`;
5. kiểm tay database/export/evidence của từng record;
6. nếu đúng, chạy tối đa một record mỗi provider còn lại;
7. sau đó mới chạy tối đa 5 record/provider.

Không chạy 76-record batch trong vòng P2.1. Dừng mở rộng nếu gặp CAPTCHA, login, robots/policy block, redirect ngoài allowlist, repeated 403/429 hoặc cấu trúc provider chưa có fixture.

Network result phải báo riêng:

- attempted/succeeded/blocked/review;
- số valid binary downloads;
- exact SHA/mismatch/not downloaded;
- identity source;
- final identity/binary domain;
- warning và blocking reason;
- Playwright có thực sự được dùng hay không.

## 8. Phạm vi cấm

- Không sửa `config/source_catalog.yaml`.
- Không sửa review draft catalog.
- Không thay file trong `data/`.
- Không merge tự động.
- Không ghi reviewer, `APPROVED`, `metadata_verified=true` hoặc giả lập human/legal review.
- Không chạy pipeline, Dense, BM25, Neo4j/Aura.
- Không xóa DB/cache/evidence của P1.3/P2.
- Không nới quality gate hoặc allowlist để ép trạng thái PASS.
- Không hardcode kết quả state/SHA cho riêng ba record smoke.

## 9. Deliverables

Hoàn thành và báo cáo:

1. code P2.1;
2. registry có role-specific rules;
3. fixtures/provider adapters cần thiết;
4. regression tests;
5. DB/cache/export P2.1 mới nếu network được chạy;
6. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md` được viết lại phần current status, tách lịch sử cũ khỏi kết quả hiện hành;
7. bảng per-record của smoke P2.1, gồm URL role, final URL, HTTP/MIME/magic, SHA comparison, identity source, state và reasons;
8. kết luận rõ một trong hai:
   - `READY_FOR_LIMITED_PROVIDER_BATCH`; hoặc
   - `NOT_READY`, kèm blocker cụ thể.

Khi kết thúc, liệt kê chính xác file đã sửa/tạo, lệnh test/network đã chạy và xác nhận production catalog, corpus, pipeline artifacts và Aura không bị thay đổi.
