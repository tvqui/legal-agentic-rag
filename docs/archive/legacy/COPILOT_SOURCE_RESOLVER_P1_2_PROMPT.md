# Prompt Copilot vòng tiếp theo — hoàn thiện P1 trước network smoke test

Hãy tiếp tục vai trò Senior Python/Data Provenance Engineer. Đọc:

1. `SOURCE_RESOLVER_P0_P1_REVIEW.md`
2. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
3. `COPILOT_AUTOMATIC_SOURCE_RESOLVER_PROMPT.md`
4. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`
5. toàn bộ `src/vn_labor_offline/source_resolver/`, `config/source_provider_registry.yaml` và `tests/test_source_resolver.py`.

Mục tiêu vòng này là biến P1 skeleton thành resolver deterministic có thể chạy **network smoke test an toàn**. Sửa code và test thật; không chỉ cập nhật báo cáo.

## Việc bắt buộc

1. Nối flow thực tế: candidate -> fetch -> validate final URL -> extract -> identity -> binary -> decision -> evidence -> update candidate/record state.
2. Sửa `verify_binary`: SHA khác không bao giờ tự thành `AUTO_CONTENT_MATCH`. Chỉ comparator nội dung thực, có evidence, mới được tạo trạng thái đó; nếu chưa có comparator đủ mạnh thì trả `NEEDS_REVIEW` với `SHA_MISMATCH`.
3. Sửa HTTP fetcher:
   - redirect handler có giới hạn thực;
   - kiểm scheme/provider/final host trước khi commit file;
   - temp file + atomic rename + cleanup khi lỗi/quá size;
   - timeout, retry/backoff và rate limit;
   - streaming SHA;
   - ghi redirect chain/status/headers cần thiết;
   - không để partial file.
4. Sửa `SourceResolver.candidates_for()` để giữ riêng `identity_url`, `binary_url`, `status_url`; không làm mất direct attachment khi chuẩn hóa VBPL và không gán HTML page làm binary.
5. Hoàn thiện registry bằng route/role cụ thể và các official binary host thật trong seed. Mô hình hóa redirect/cross-host theo provider; không mở allowlist chung `/*` nếu có thể thu hẹp.
6. Hoàn thiện SQLite store: add evidence, update state, foreign keys, schema version/migration check, idempotency, resume và deterministic export.
7. Làm `merge --dry-run` tạo diff thật nhưng tuyệt đối không ghi `config/source_catalog.yaml`.
8. Integrity import phải xác nhận đủ 95 record với catalog/manifest và hash file corpus thực khi file có mặt; entry thiếu/mismatch phải fail rõ.
9. Playwright vẫn optional nhưng phải có interface/action log và fixture test. Nếu chưa thể implement browser thật, HTTP flow phải hoàn chỉnh và record cần browser phải chuyển `BLOCKED/NEEDS_REVIEW` đúng lý do.
10. Network phải opt-in bằng `--network`; mặc định `resolve` không truy cập mạng. Thêm `--record`, `--provider`, `--limit`, `--resume`, concurrency/rate-limit an toàn.

## Test bắt buộc trước network

Dùng local fixture HTTP server/mocked transport, không dùng Internet trong test mặc định. Bổ sung test cho:

- import DB hai lần không duplicate;
- catalog/manifest/path/SHA mismatch và thiếu record bị từ chối;
- redirect hợp lệ, redirect ngoài allowlist, redirect loop/max limit;
- VBPL redirect homepage;
- HTML giả PDF, MIME/magic mismatch, size limit và partial cleanup;
- exact SHA -> `AUTO_EXACT_SHA`;
- SHA mismatch -> `NEEDS_REVIEW`, không phải `AUTO_CONTENT_MATCH`;
- secondary source không thành official;
- direct VBPL attachment không bị mất;
- hai binary Nghị quyết 326 dùng cùng metadata page được xử lý riêng;
- evidence/state transition và resume;
- export deterministic;
- merge dry-run sinh diff và catalog không đổi;
- Windows/POSIX path.

Không xóa test cũ để làm PASS. Sửa test nếu test cũ đang chứng nhận hành vi sai và ghi rõ lý do.

## Network smoke test sau khi Gate A PASS

Chỉ khi toàn bộ test offline PASS, chạy opt-in trên **một direct URL trước**, không chạy 84 record. Ghi cache/evidence ngoài corpus. Báo requested/final URL, provider, status, MIME/magic, size, downloaded SHA, corpus SHA, state và reason codes. Nếu sandbox/network chặn, không giả kết quả; cung cấp đúng lệnh để chạy trên Kaggle.

Sau record đầu thành công mới chạy tối đa 8 direct URL với concurrency 1 và rate limit. Không merge catalog, không sửa corpus, không chạy pipeline/Aura.

## Báo cáo

Cập nhật `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md` theo thực tế và thêm:

- các lỗi review đã sửa/chưa sửa;
- test count và lệnh;
- network có thực sự chạy hay không;
- bảng kết quả tối đa 8 direct URL;
- đường dẫn cache/evidence;
- xác nhận corpus/catalog không đổi;
- lệnh Kaggle cho smoke test nếu local bị chặn.

Không gọi P1 hoàn tất khi `resolve` vẫn chỉ queue candidate hoặc evidence còn rỗng.
