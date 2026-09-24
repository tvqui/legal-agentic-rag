# Prompt Copilot — sửa terminal-state, audit và final human-review handoff

Tiếp tục vòng lặp trong [COPILOT_OFFLINE_100_LOOP_PROMPT.md](COPILOT_OFFLINE_100_LOOP_PROMPT.md). Đọc [OFFLINE_100_COMPLETION_CONTRACT.md](OFFLINE_100_COMPLETION_CONTRACT.md), [OFFLINE_COMPLETION_AUDIT_P1.md](OFFLINE_COMPLETION_AUDIT_P1.md) và [OFFLINE_COMPLETION_AUDIT_P2.md](OFFLINE_COMPLETION_AUDIT_P2.md).

Kết quả hiện tại **chưa đạt `WAITING_FOR_HUMAN_REVIEW`**. Không gửi review ZIP hiện tại và không dừng ở report vừa tạo. Hãy tiếp tục vòng inspect → fix → test → rerun → audit cho đến khi không còn công việc tự động.

## 1. Sửa định nghĩa resolution completion

`resolution_attempted_at` chỉ chứng minh đã bắt đầu/thử một vòng. Nó không phải terminal evidence.

Định nghĩa terminal states rõ ràng:

- terminal success: `AUTO_EXACT_SHA` và các success state khác được policy thực sự cho phép;
- terminal human decision: `NEEDS_REVIEW` với evidence/reason/action đầy đủ;
- terminal external: `BLOCKED` với classified external/provider reason, retry exhaustion và evidence;
- nonterminal: `FETCH_PENDING`, `DISCOVERED`, queued/retryable, code exception chưa sửa.

`resolver_resolution_complete=true` chỉ khi:

- 95/95 record đã attempt;
- không còn record `FETCH_PENDING`;
- không còn required candidate `FETCH_PENDING`/`DISCOVERED`;
- không còn code/config error có thể sửa;
- không còn retryable attempt;
- mọi record có terminal state và terminal reason/evidence nhất quán;
- record aggregate được tái tạo deterministically từ persisted candidate/evidence.

Nếu optional candidate được phép deferred, phải có explicit `OPTIONAL_DEFERRED` policy, reason và không được che required capability.

## 2. Sửa aggregate/resume ordering

Tạo một hàm thuần deterministic để recompute record resolution từ toàn bộ persisted candidates/evidence. Cùng một database phải cho cùng kết quả bất kể:

- candidate order;
- live so với resume;
- evidence insertion order;
- identity trước hay binary trước;
- optional candidate lỗi sau evidence tốt.

Hàm phải chọn identity/binary evidence tốt nhất bằng rank rõ ràng, rồi tính state/reasons/URLs/SHA từ chính selected evidence.

Regression cases bắt buộc từ database hiện tại:

- 12 record có `AUTO_EXACT_SHA` + `FETCHED` không được còn `FETCH_PENDING` nếu authority/identity requirements đạt;
- 13 record chỉ `NEEDS_REVIEW` phải kết thúc `NEEDS_REVIEW` nếu không còn required fetch;
- 8 record chỉ `BLOCKED` phải kết thúc `BLOCKED` hoặc explicit retryable state;
- mixed alternatives không được hạ evidence tốt;
- required pending capability phải giữ record nonterminal;
- optional pending alternative không được giữ record pending khi capability đã được thỏa.

Sau khi sửa, chạy recompute/migration an toàn trên copy của DB, rồi fresh rerun để chứng minh live và recompute giống nhau.

## 3. Xử lý 39 candidate còn FETCH_PENDING

Phân loại từng candidate:

1. chưa được vòng resolver process do queue/dynamic discovery bug;
2. retryable network failure;
3. browser selector cần fixture;
4. provider registry/role route thiếu;
5. optional alternative có thể đóng;
6. external block thật.

Process lại nhóm 1–4 sau khi sửa. Không để candidate required ở pending chỉ vì record đã có `resolution_attempted_at`.

Với dynamic candidates được append trong khi resolve, dùng queue/while hoặc pass kế tiếp có visited set; bảo đảm candidate mới được process đúng một lần và idempotent.

## 4. Sửa lỗi code/network classification

### 4.1 Unicode URL

Sửa `UnicodeEncodeError`/ASCII codec error cho URL có tên file Unicode. Percent-encode path/query đúng chuẩn, giữ nguyên escape hợp lệ và không đổi semantic URL. Thêm fixture cho URL Tòa án có ký tự tổ hợp/ngoặc/khoảng trắng.

Expected: không còn reason code chứa raw Python exception string; dùng stable enum như `URL_ENCODING_FAILED` nếu vẫn lỗi.

### 4.2 Provider/route

Với `PROVIDER_NOT_ALLOWED`:

- nếu URL là route chính thức hợp lệ, cập nhật registry tối thiểu và test role/source group/redirect;
- nếu ngoài policy, giữ `BLOCKED` với stable reason và action;
- không để provider ID rỗng mà coverage không giải thích.

### 4.3 Browser/runtime

- `RuntimeError` phải được map sang reason code có nghĩa;
- `PLAYWRIGHT_SELECTOR_NOT_PROVEN` chỉ terminal external/human khi đã có fixture chứng minh không thể chạy generic discovery;
- không dùng exception class/message làm API reason code;
- retry/backoff có giới hạn và lưu attempt count/last attempt/next action.

## 5. Sửa coverage audit

`source_resolution_*_coverage.json` phải có tối thiểu:

```json
{
  "records": 95,
  "attempted": 95,
  "terminal_records": 95,
  "nonterminal_records": 0,
  "required_candidates_pending": 0,
  "retryable_failures": 0,
  "code_errors": 0,
  "external_blocked": 0,
  "needs_review": 0,
  "auto_verified": 0,
  "resolution_complete": true,
  "automation_action_remaining": []
}
```

Các số 0 cuối là schema minh họa và phải thay bằng actual counts; chỉ các trường nonterminal/retryable/code error/required pending bắt buộc bằng 0 để completion true.

Coverage phải liệt kê record IDs/candidate IDs cho mọi non-pass bucket. Stable reason-code allowlist phải reject raw exception messages.

## 6. Hoàn thiện completion audit thật sự

Thực hiện các yêu cầu còn bỏ sót:

- resolver gate dùng terminal/pending/retryable/code-error semantics ở trên;
- same-build so sánh graph build ID, Dense/BM25/retrieval build/fingerprint và Aura live build;
- Dense/BM25 được load/validate IDs/counts, không chỉ kiểm file tồn tại;
- unresolved SHA mismatch đọc từ evidence/review decisions;
- span/interval/overlap/derived evidence đọc report thật; thiếu artifact là `NOT_RUN`;
- queue schema và approved decision validation;
- Gold groups/threshold/qrels/reviewer/build validation;
- portable artifact references, không phụ thuộc tuyệt đối vào `C:\\Users\\...` trong final contract;
- iteration dedup/increment/content fingerprint đúng.

Thêm các test đã yêu cầu ở P1. Hiện completion audit chỉ có 2 tests; tổng test vẫn là 127, chứng tỏ danh sách negative/positive tests chưa được triển khai. Số lượng test không phải mục tiêu, nhưng mọi invariant phải có fixture có ý nghĩa.

Phải có synthetic clean fixture đạt `COMPLETE`/exit 0 và fixtures fail cho stale build, pending resolver, missing indexes, invalid review, temporal conflict, zero/stale Gold.

## 7. Tạo final human-review package đúng decision units

Chỉ package sau khi resolver và automation audits đạt.

### 7.1 Quarantine grouping

Thay 837 raw rows bằng case view:

- stable `quarantine_case_id`;
- 492 unique canonical identities hiện quan sát phải được nhóm tiếp theo collision/root cause;
- member key không dựa vào colliding `provision_id` duy nhất;
- text/span/order diff;
- proposed deterministic repair;
- affected-member mapping + hash;
- group decision và exception decision;
- validator apply completeness.

Report cả `raw_rows`, `unique_members`, `review_cases`, `auto_fixed`, `human_pending`.

### 7.2 Temporal grouping

Tạo instrument-level coverage/legal-change cases và mapping đến 18.449 provisions. Reviewer duyệt decision unit có evidence; code áp dụng xuống provision deterministic. Giữ exception cases riêng. Không đưa 18.449 dòng rời rạc nếu có thể chứng minh coverage theo instrument.

### 7.3 Gold candidates

Tạo draft queries/qrel candidates cho mọi required query group, kèm retrieval unit IDs, excerpts, provenance, query dates và build ID. Không tự đặt `APPROVED`.

### 7.4 Package contents

Final package phải có:

- hướng dẫn chi tiết theo từng queue và allowed decisions;
- source review cases đã prefill evidence;
- grouped quarantine cases + raw mapping;
- grouped temporal/legal-change cases + provision mapping;
- Gold candidates;
- JSON Schema hoặc validator logic;
- `validate_review_return` script/command;
- manifest/hash cho mọi file;
- empty return directory/template;
- không có secrets/cache/model.

Instruction 276 byte hiện tại là không đủ. Giữ ZIP SHA `918d...` làm historical evidence, tạo ZIP final tên/version mới.

## 8. Expected output trước khi được dừng

Source Resolver:

```text
records=95
attempted=95
terminal_records=95
record FETCH_PENDING=0
required candidate FETCH_PENDING=0
retryable_failures=0
code_errors=0
resolution_complete=true
```

Không ép số `AUTO_EXACT_SHA`; báo actual. Mọi record còn cần con người phải là `NEEDS_REVIEW` với evidence/action. Mọi external block phải là `BLOCKED` với classified reason/retry history.

Completion contract chỉ được ghi:

```text
status=WAITING_FOR_HUMAN_REVIEW
automation.remaining=0
all_prerequisite_gates_passed=true
```

khi các điều kiện trên, audit kỹ thuật đầy đủ và final review package validator đều PASS. Nếu còn external blocker không thể chuyển thành review action hợp lệ, dùng `BLOCKED_EXTERNAL`. Nếu còn pending/code/retry, giữ `FAILED_CODE`/`AUTOMATION_IN_PROGRESS` và tự tiếp tục vòng sửa.

## 9. Validation cuối vòng

Chạy và đọc lại:

1. targeted resolver state/recompute/URL tests;
2. targeted completion audit tests gồm positive COMPLETE path;
3. toàn repository tests;
4. compileall với cache riêng nếu Windows lock;
5. fresh bounded resolver/recompute audit;
6. resolver consistency + coverage strict audits;
7. completion audit;
8. human-review package validator;
9. ZIP SHA/manifest/testzip;
10. `git diff --check`.

Tiếp tục sửa và chạy lại nếu actual output chưa khớp expected output. Không dừng chỉ vì `attempted=95` hoặc test suite cũ vẫn PASS.
