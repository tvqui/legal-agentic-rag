# Review triển khai Automatic Source Resolver P0/P1

Ngày review: 2026-09-16

## Kết luận

P0 (import/model/registry/store boundary/CLI dry-run) đã hình thành và các kiểm tra hiện có chạy được. P1 mới là **skeleton**, chưa phải resolver có thể chạy network: `resolve` hiện chỉ tạo candidate trong SQLite, chưa fetch, extract, verify, ghi evidence hoặc cập nhật state. Không bật network trên 84 record trước khi sửa các mục chặn dưới đây.

Đã chạy lại bằng `.venv`:

- `compileall`: PASS;
- `unittest tests.test_source_resolver`: 5/5 PASS;
- root CLI `import-seed --dry-run`: 95 record, phân bố 84/10/1 đúng;
- root CLI `resolve --all --dry-run`: 95 record, 84 record có candidate.

## Lỗi chặn network smoke test

1. **`resolve` không resolve:** `SourceResolver.queue_record()` chỉ ghi candidate. `HttpFetcher`, adapter, authority/identity/binary verifier và decision không được nối thành flow.
2. **False positive content match:** `verify_binary()` trả `AUTO_CONTENT_MATCH` cho mọi binary hợp lệ có SHA khác, dù chưa so nội dung. SHA khác phải là `NEEDS_REVIEW`/`FETCHED`; chỉ content comparator thật mới được nâng lên `AUTO_CONTENT_MATCH`.
3. **HTTP boundary chưa an toàn:** `max_redirects` không được áp dụng; URL có thể redirect ra ngoài allowlist rồi được ghi xuống đĩa trước khi authority check; file quá giới hạn có thể còn file dở; chưa có temp + atomic rename, retry/backoff/rate limit và cleanup.
4. **Adapter gần như stub:** Công báo/Chính phủ/Tòa án/ILO chỉ trả URL đầu vào; chưa extract attachment/metadata. Playwright chỉ kiểm import package, chưa có hành vi click/download/action log.
5. **Registry quá rộng và thiếu host:** route đều `/*`; thiếu các host binary/official đang có trong seed như `datafiles.chinhphu.vn`, `baohiemxahoi.gov.vn`, `hopdonglaodong.moha.gov.vn`, `isos.gov.vn`. Cần khai báo vai trò/route cụ thể và redirect giữa các host cùng provider.
6. **Lỗi candidate VBPL:** khi bất kỳ URL nào chứa `vbpl.vn`, `candidates_for()` thay toàn bộ URL bằng bốn route HTML, làm mất `direct_download_url` thật và có thể gán trang HTML làm `BINARY`.
7. **Evidence store chưa hoàn chỉnh:** chưa có method ghi evidence, update candidate/record state, lưu redirect/header/hash/action log; chưa bật foreign key hoặc kiểm migration/schema version.
8. **`merge --dry-run` chưa tạo diff:** hiện chỉ in câu “catalog was not modified”. Chưa thể review đề xuất merge.
9. **Integrity check chưa đủ:** importer so với catalog nếu entry tồn tại nhưng chấp nhận entry thiếu; chưa hash file corpus thật hoặc đối chiếu manifest đầy đủ.
10. **Test coverage chưa đạt yêu cầu prompt:** mới có 5 test; chưa kiểm idempotent DB, allowlist redirects, HTML giả PDF, VBPL homepage, secondary source, SHA mismatch, evidence/export, Windows/POSIX và hai binary cùng metadata URL.

## Trình tự tiếp theo

### Gate A — Hoàn thiện offline P1

- Nối flow fetch -> authority -> extract -> identity -> binary -> decision -> evidence/state.
- Sửa false positive SHA/content.
- Hoàn thiện registry, HTTP safety, store và dry-run diff.
- Bổ sung fixture/test deterministic; test mặc định không dùng Internet.

Chỉ qua Gate A khi mọi test mới PASS và một local fixture server chứng minh redirect, HTML/PDF, size limit, SHA match/mismatch và cleanup hoạt động.

### Gate B — Network smoke có kiểm soát

- Thêm flag rõ như `--network` và mặc định vẫn offline.
- Chạy từng record, trước tiên trên 8 direct URL; không chạy `--all` ngay.
- Cache vào `.cache/source_resolver/`, không vào `data/`.
- Sau mỗi record kiểm final URL, provider, MIME/magic, bytes, SHA, evidence và state.
- Kỳ vọng ban đầu có thể là `AUTO_EXACT_SHA=0`; không sửa rule để tăng số PASS.

### Gate C — Batch 84 candidate

- Chạy theo provider với concurrency thấp, rate limit và resume.
- VBPL canonicalize/probe route trước; Playwright chỉ cho record HTTP không xử lý được.
- Xuất summary/review queue và kiểm mẫu trước khi tiếp tục.

### Gate D — Discovery 11 judicial

- Official-site search trước, SearXNG sau.
- Secondary source chỉ tạo candidate/evidence.
- Multiple/not-found vẫn ở review queue nếu không có exact official source.

### Gate E — Merge và pipeline

- Chỉ tạo diff cho `AUTO_EXACT_SHA` có evidence đầy đủ.
- Review diff; không tự đặt legal approval.
- Chỉ sau quyết định merge mới xác định stage pipeline nào cần chạy lại. Thay URL/provenance không đổi corpus thường chỉ cần gate/report; thay binary/corpus mới cần extraction -> graph -> indexes.

