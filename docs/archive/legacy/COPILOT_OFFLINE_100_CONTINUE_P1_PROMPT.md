# Prompt Copilot — tiếp tục vòng OFFLINE 100% sau P2.3 import

Tiếp tục thực hiện [COPILOT_OFFLINE_100_LOOP_PROMPT.md](COPILOT_OFFLINE_100_LOOP_PROMPT.md) và tuân thủ [OFFLINE_100_COMPLETION_CONTRACT.md](OFFLINE_100_COMPLETION_CONTRACT.md). Đọc trước [OFFLINE_COMPLETION_AUDIT_P1.md](OFFLINE_COMPLETION_AUDIT_P1.md).

Kết quả vừa tạo **chưa phải một human-only checkpoint**. Không dừng ở báo cáo hiện tại. Hãy tự sửa, kiểm tra và lặp đến khi mọi việc tự động thực sự hoàn thành hoặc đạt `COMPLETE`.

## 1. Sự thật phải tái hiện trước khi sửa

Query fresh P2.3 SQLite và xác nhận:

```text
records = 95
candidates = 0
evidence = 0
states = FETCH_PENDING 84, NEEDS_DISCOVERY 10, NEEDS_REVIEW 1
```

Phân biệt hai khái niệm:

- `resolver_consistency_pass=true`: 15 invariant trên dữ liệu hiện có đạt;
- `resolver_resolution_complete=false`: chưa chạy resolution thật.

Một DB chỉ import seed, không có candidate/evidence, không được dùng để kết luận automation work remaining bằng 0.

## 2. Sửa unified completion audit trước

Refactor `scripts/audit_offline_completion.py` thành evidence-backed gate. Không hard-code kết quả. Tách loader, validator và gate result có:

```json
{
  "name": "...",
  "passed": false,
  "status": "PASS|FAIL|WAITING|NOT_RUN",
  "observed": {},
  "expected": {},
  "evidence_paths": [],
  "reason_codes": []
}
```

### 2.1 State machine bắt buộc

Triển khai đúng thứ tự:

1. `FAILED_CODE`: còn gate code/invariant/machine-derived work fail hoặc artifact bắt buộc chưa chạy.
2. `BLOCKED_EXTERNAL`: automation đã thử hợp lệ nhưng external source/service/access chặn và có evidence.
3. `WAITING_FOR_REMOTE_EXECUTION`: chỉ thiếu fresh Kaggle/Aura run/returned artifact.
4. `WAITING_FOR_HUMAN_REVIEW`: tất cả automation prerequisite PASS, package review tồn tại và hợp lệ, chỉ còn quyết định reviewer.
5. `COMPLETE`: mọi gate trong contract PASS, không còn action bắt buộc, `offline_ready_for_online=true`.

Audit phải có positive code path tạo `COMPLETE`; strict exit `0` chỉ ở trạng thái đó. Các trạng thái khác trả nonzero.

### 2.2 Không được suy diễn hoặc hard-code

Đọc và xác minh thật:

- resolver record/candidate/evidence/state coverage từ SQLite/export;
- source review đủ allowed decision + reviewer + reviewed_at + review evidence + SHA/record match;
- authority policy theo source group, không tính mọi record giống nhau;
- unresolved SHA mismatch từ resolver/review decision;
- registry/structure/graph checks từ validation artifact;
- Dense và BM25 riêng: artifact tồn tại, load được, retrieval-unit IDs/count khớp, model/config/fingerprint khớp;
- graph build ID từ graph metadata;
- Neo4j build ID từ live audit và so bằng đúng graph build ID;
- source spans, invalid intervals, overlaps và derived evidence từ report/check thật;
- legal-change/provision temporal/quarantine queue qua schema + decision validator;
- Gold bằng evaluator thật: approved record validity, reviewer, qrel IDs, required query groups, thresholds và build ID.

Không dùng mặc định `0` khi artifact thiếu. Artifact thiếu phải là `NOT_RUN` hoặc `FAIL`.

### 2.3 Iteration log

- Tăng iteration theo phase/fingerprint thật.
- Fingerprint nội dung input/artifact, không chỉ hash path string.
- Không append dòng trùng nếu cùng invocation/fingerprint/result.
- Ghi đúng command thực sự chạy và file thực sự thay đổi.
- Không hard-code `automation work remaining: 0`; tính từ failed/not-run automation gates.

### 2.4 Tests bắt buộc

Bổ sung test ít nhất cho:

- clean fixture đạt `COMPLETE` và strict exit 0;
- seed-only resolver phải là `FAILED_CODE`, không phải waiting human;
- một cột reviewer/decision rời rạc không được tính reviewed;
- fabricated/missing reviewer fields;
- invalid decision/timestamp/evidence/SHA;
- stale/mismatched graph–index–Aura build;
- missing Dense hoặc BM25;
- Dense/BM25 unit ID/count mismatch;
- hard missing artifact không được thành zero/PASS;
- unresolved SHA mismatch;
- invalid/overlapping temporal interval;
- incomplete legal-change/provision/quarantine decision;
- Gold zero, stale build, missing query group, failed metric;
- duplicate iteration suppression;
- đúng classification cho năm trạng thái.

## 3. Hoàn tất phần tự động của Source Resolver

Sau khi audit phân loại seed-only đúng là chưa hoàn thành, thực hiện Phase A3/A4 trong master prompt.

### 3.1 Fresh four-record smoke

Chạy network smoke bằng opt-in, DB/cache riêng. Phải tạo candidate và evidence thật. Kiểm exact binary, Công báo mismatch, VBPL shell/download control và một discovery case. Nếu browser được dùng, derived binary phải qua common verification path.

Expected:

- consistency audit PASS;
- resolution coverage audit ghi attempted/succeeded/review/blocked;
- candidates > 0 và evidence > 0;
- không HTML-as-binary;
- SHA semantics đúng;
- lỗi network/provider được phân loại, không biến thành `FETCH_PENDING`.

### 3.2 Controlled provider batches

Nếu four-record smoke đạt:

1. chạy một record/provider;
2. tối đa năm record/provider;
3. kiểm redirect, rate limit, retry, cache, resume và distributions;
4. mới mở rộng đủ 95 bằng batch nhỏ/resume.

Không gọi việc này là human-only nếu còn record chưa từng được automation attempt. Với `NEEDS_DISCOVERY`, triển khai discovery trong allowlist/provider policy hoặc ghi `BLOCKED_EXTERNAL` sau khi đã thử và lưu evidence.

### 3.3 Resolution completion report

Sinh machine-readable report có:

- total/imported/attempted/unattempted;
- candidate/evidence counts;
- state/provider/reason distributions;
- exact SHA/content match/mismatch/not-downloaded;
- authority/identity coverage;
- retry-exhausted/external-blocked;
- review-required records;
- automation action remaining.

Chỉ khi `unattempted=0` và không còn deterministic action mới được chuyển source phase sang human review.

## 4. Giảm khối lượng human review bằng grouping có provenance

Không tự duyệt pháp lý. Mục tiêu là loại thao tác lặp và đưa reviewer đúng decision unit.

### 4.1 Source review

Prefill từ resolver evidence, nhóm theo document/official identity. Mỗi record vẫn có quyết định cuối riêng nhưng reviewer không phải nhập lại URL/SHA/provider/evidence đã xác minh. Package phải có validator và diff preview.

### 4.2 Quarantine

Hiện queue có 837 dòng nhưng chỉ 492 provision IDs/canonical paths trên 33 documents, với 345 dòng lặp provision ID. Xác định nguyên nhân phát sinh từ `provision_quarantine.jsonl` và validation issues.

Tạo:

- `quarantine_case_id` ổn định cho mỗi collision/issue group;
- group summary: document, canonical path, members, spans, text diff, parser pattern, proposed deterministic fix;
- distinct member IDs; không dùng colliding `provision_id` làm khóa duy nhất;
- quyết định nhóm khi một rule áp dụng được cho toàn group;
- record-level exception chỉ khi thật sự khác;
- mapping quyết định group → affected rows có hash/provenance;
- validator ngăn missing/duplicate/partial application.

Sửa parser tự động cho pattern tổng quát khi có thể, thêm fixture/test rồi regenerate queue. Chỉ đưa các case mơ hồ thật sự cho người duyệt. Audit phải báo cả `raw_rows`, `unique_members`, `review_cases`, `auto_fixed`, `human_pending` thay vì gọi 837 là 837 quyết định.

### 4.3 Temporal/provision versions

Không yêu cầu reviewer duyệt tay 18.449 version nếu cùng một quyết định instrument-level có thể áp dụng an toàn. Dùng `temporal_coverage_reviews.yaml` và legal-change scope để tạo decision units theo instrument/coverage interval, kèm affected provision IDs và hash. Chỉ apply sau quyết định người duyệt hợp lệ. Giữ provision-level exceptions riêng.

Report phải tách:

- raw provision versions;
- instrument-level review cases;
- legal-change cases;
- exception cases;
- automated validations;
- human decisions pending.

### 4.4 Gold

Tự động tạo candidate query package từ retrieval units theo required query groups, kèm candidate qrels, evidence text, source spans, dates và build IDs. Không đặt `APPROVED`. Validator phải bảo đảm qrel tồn tại và query date tương thích trước khi giao reviewer.

## 5. Tiếp tục các phase tự động khác

Sau Source Resolver, không nhảy thẳng đến waiting state. Tiếp tục audit/implement các Phase C–I trong master prompt:

- parser/provenance fixes có thể suy ra deterministic;
- legal relation candidate resolution;
- temporal validation;
- derived evidence audit;
- dependency-aware rebuild plan;
- Gold candidate generation/evaluator tooling;
- Kaggle package/fresh-run instructions;
- Aura same-build verification.

Nếu một phase cần human decision để apply, vẫn hoàn thành code, candidate generation, grouping, schema, validators, tests và package trước khi đánh dấu waiting.

## 6. Expected outputs của vòng này

Tạo/cập nhật:

```text
artifacts/reports/offline_completion_contract.json
artifacts/reports/offline_completion_iterations.jsonl
artifacts/reports/source_resolution_p2_3_coverage.json
artifacts/reports/automation_remaining.json
review_packages/offline_human_review_<build_id>.zip
review_packages/offline_human_review_<build_id>.zip.sha256
review_packages/offline_human_review_<build_id>_manifest.json
OFFLINE_100_IMPLEMENTATION_REPORT.md
```

Review ZIP phải chỉ chứa dữ liệu cần duyệt, hướng dẫn, schemas, manifests/hashes và validator; không chứa secrets, cache thừa hoặc model.

Expected completion contract ở cuối vòng tự động:

```json
{
  "status": "WAITING_FOR_HUMAN_REVIEW",
  "offline_ready_for_online": false,
  "automation": {
    "remaining": 0,
    "all_prerequisite_gates_passed": true
  },
  "source_resolution": {
    "records": 95,
    "unattempted": 0
  },
  "human_review": {
    "packages_valid": true,
    "source_cases": "<actual>",
    "quarantine_cases": "<actual grouped count>",
    "temporal_cases": "<actual grouped count>",
    "gold_cases": "<actual>"
  }
}
```

Nếu automation vẫn còn việc, trạng thái phải là `FAILED_CODE`/`AUTOMATION_IN_PROGRESS`, report liệt kê đúng gate và tiếp tục vòng sửa. Không được ghi `WAITING_FOR_HUMAN_REVIEW` chỉ vì review fields đang trống.

## 7. Điều kiện tự kiểm cuối vòng

Trước khi dừng:

1. chạy compileall;
2. chạy toàn repository tests;
3. chạy fresh resolver consistency + coverage audits;
4. chạy completion audit trên negative current state;
5. chạy completion audit trên synthetic clean fixture để chứng minh nhánh COMPLETE;
6. validate review package/manifest/hash;
7. chạy `git diff --check`;
8. đọc lại actual JSON, SQLite counts và ZIP manifest thay vì chỉ báo command PASS.

Tiếp tục tự sửa và kiểm tra nếu bất kỳ expected invariant nào fail. Chỉ dừng ở human checkpoint sau khi `automation.remaining=0` được tính từ evidence thật.
