# Prompt Copilot P2.3 — deterministic readiness gate và self-correction loop

Bạn hãy tiếp tục Automatic Legal Source Resolver từ P2.2. Mục tiêu của vòng này là tạo một **readiness gate tự kiểm tra được**, sửa hết correctness blockers còn lại và chỉ kết luận sẵn sàng khi mọi acceptance invariant đều pass.

**Không chạy batch 76 record, không merge catalog, không thay corpus và không chạy downstream pipeline.**

Đọc trực tiếp:

1. `SOURCE_RESOLVER_P2_2_AUDIT.md`
2. `SOURCE_RESOLVER_P2_1_AUDIT.md`
3. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
4. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`
5. toàn bộ `src/vn_labor_offline/source_resolver/`
6. `config/source_provider_registry.yaml`
7. `config/source_candidate_overrides.yaml`
8. `tests/test_source_resolver.py`
9. DB/export/cache P2.2b.

Không được coi test hiện có là đủ. Query SQLite, đọc export và kiểm cache/evidence thực tế.

## 1. Vòng lặp bắt buộc

Thực hiện vòng sau cho đến khi **tất cả deterministic gates đều PASS**:

1. Chạy targeted resolver tests.
2. Chạy readiness audit ở chế độ strict.
3. Đọc từng gate fail và artifact minh chứng.
4. Sửa nguyên nhân trong code/config/test; không sửa expected output để che lỗi.
5. Chạy lại targeted tests và strict audit từ đầu.
6. Khi targeted gates xanh, chạy toàn bộ repository tests.
7. Nếu full suite fail, sửa rồi quay lại bước 1.
8. Chỉ khi offline gates xanh mới chạy network smoke mới.
9. Audit DB/export network smoke; nếu invariant fail, sửa rồi quay lại bước 1.

Không dừng ở lần test xanh đầu tiên nếu audit còn fail. Không dùng retry vô hạn cho network: mỗi URL chỉ thử trong giới hạn HTTP retry hiện có; 403/404/429/502/CAPTCHA/shell phải trở thành evidence và external blocker, không phải lý do lặp request.

Nếu deterministic code gates không thể pass, kết luận `NOT_READY_CODE` và chỉ rõ gate. Nếu mọi code gate pass nhưng provider bên ngoài không truy cập được, kết luận `READY_FOR_LIMITED_BATCH_EXCLUDING_BLOCKED_PROVIDERS` hoặc `NOT_READY_EXTERNAL` theo matrix ở phần 9. Không ép network record thành PASS.

## 2. Xây readiness audit có exit code

Bổ sung CLI, ví dụ:

```text
vn-labor-offline source-resolver audit --db <db> --export-dir <dir> --strict --out <json>
```

Audit phải đọc SQLite và export, tạo JSON machine-readable và:

- exit code `0` chỉ khi tất cả invariant áp dụng đều pass;
- exit code khác `0` nếu có invariant fail;
- mỗi gate có `name`, `passed`, `observed`, `expected`, `record_ids/candidate_ids`, `details`;
- output deterministic, sort keys/lists;
- không sửa DB/export.

Tạo test cho exit code và từng gate fail/pass bằng fixture DB nhỏ.

## 3. Sửa capability/alternative aggregation

### 3.1 Outcome có provenance đầy đủ

Mỗi outcome phải mang:

- `candidate_id`
- `role`
- `required`
- `alternative_group`
- `source_class`
- `authority_verified`
- `state`
- `reason_codes`
- `selected_as_best_identity/binary/status`

Không tổng hợp chỉ từ role.

### 3.2 Capability rules

- `binary` capability đạt khi có ít nhất một trusted valid binary, dù SHA match hay mismatch.
- `identity` capability đạt khi có verified official identity page hoặc verified identity từ trusted binary theo policy.
- PDF/DOC/mirror/direct/browser candidates trong cùng alternative group là `any-of`.
- Alternative lỗi chỉ là warning nếu capability tương ứng đã đạt bằng candidate khác.
- `PLAYWRIGHT_DISABLED` chỉ là blocking khi một proven browser control là con đường bắt buộc duy nhất còn lại.
- Old VBPL 404 chỉ là warning khi Công báo/official binary khác đã thỏa binary capability.

Xuất ba nhóm không mâu thuẫn:

- `decision_reason_codes`: lý do tạo final state, ví dụ `SHA_MISMATCH`, `IDENTITY_FAILED`, `BINARY_NOT_FETCHED`;
- `blocking_reason_codes`: lỗi khiến required capability chưa đạt;
- `warning_reason_codes`: lỗi của alternatives không được chọn hoặc evidence phụ.

`reason_codes` có thể là union tương thích, nhưng decision chỉ dùng hai nhóm đầu theo rule rõ ràng.

### 3.3 Một selected evidence object duy nhất

Dựng aggregate fields từ `best_binary_evidence`:

- `binary_state`
- `final_binary_url`
- `resolved_downloaded_sha256`
- `resolved_sha_match`
- `binary_provider`
- `binary_candidate_id`
- `binary_authority_verified`

Không loop outcomes để lấy giá trị cuối. Tương tự cho identity/status.

## 4. Sửa evidence ranking

Identity rank phải deterministic và tối thiểu theo thứ tự:

1. identity match từ trusted exact official binary;
2. identity match từ trusted official binary SHA mismatch;
3. verified official identity page;
4. verified official status page;
5. mismatch/shell/error.

Authority fail luôn đứng dưới authority pass. Tie-break bằng configured provider priority rồi canonical URL/candidate ID, không dùng URL lexicographic như proxy cho chất lượng.

Binary rank:

1. trusted exact + binary identity match;
2. trusted exact + identity page match;
3. trusted valid mismatch + binary identity match;
4. trusted valid mismatch + identity page match;
5. trusted valid binary chưa đủ identity;
6. untrusted/invalid/fetch failure.

Best evidence chạy live và resume phải giống nhau. Viết test đảo thứ tự candidates và khẳng định aggregate không đổi.

## 5. Sửa VBPL và status processing

### 5.1 STATUS_HISTORY phải được verify

Không lưu `STATUS_HISTORY=FETCHED` chỉ vì HTTP 200. Kiểm:

- authority;
- HTML/shell/not-found;
- canonical identifier;
- expected ItemID nếu có;
- status/history-specific content marker.

Homepage/loading shell phải `NEEDS_REVIEW` hoặc `BLOCKED` với `VBPL_HOME_SHELL`, không `FETCHED`.

### 5.2 Adaptive route probing

Đừng fetch toàn bộ route vô điều kiện. Dùng state machine:

1. thử seed identity + direct binary;
2. nếu direct binary 404/blocked và identity route là shell/mismatch, thử route kế tiếp trong bounded route list;
3. dừng khi required capabilities đạt;
4. ghi `probe_index`, `probe_reason`, `discovered_from`.

Tình huống thật bắt buộc test: record có direct VBPL binary cũ 404 vẫn phải thử các identity/status alternatives tiếp theo. Test hiện tại chỉ kiểm record không có direct binary là chưa đủ.

### 5.3 Không discover từ page chưa xác minh

Không fetch attachment/control được phát hiện từ identity/status page nếu page đó shell, authority fail hoặc identifier mismatch. Có thể lưu candidate ở `NEEDS_REVIEW_UNTRUSTED_DISCOVERY` hoặc tương đương, nhưng không network fetch và không dùng cho trust decision.

### 5.4 Official mirror

Có thể thêm `vbpl.moj.gov.vn` làm official alternate provider chỉ sau khi:

- domain/ownership được xác minh;
- role routes được giới hạn;
- page chứa đúng identifier/ItemID;
- network availability được ghi evidence.

Nếu 403/502, giữ external blocker. Không dùng search cache làm live fetch evidence và không đoán attachment URL.

## 6. Sửa browser path và test thật sự có giá trị

### 6.1 Selector

- Mock browser fixture phải từ chối selector rỗng giống Playwright thật.
- Full path test phải dùng fixture HTML có selector provider-specific thực sự được parser sinh ra, và assert selector khác rỗng trước browser call.
- Generic control không có selector được chứng minh phải dừng với `PLAYWRIGHT_SELECTOR_NOT_PROVEN`; không gọi browser.

### 6.2 Page authority

Sau navigation và trước click:

- kiểm `page_final_url` vẫn thuộc allowed identity/control route;
- xác minh page vẫn chứa expected identifier hoặc provider adapter marker đã được kiểm trước đó;
- redirect sang login/home/external domain phải dừng.

Actual `download_url` tiếp tục phải qua binary role registry và common verification.

### 6.3 Cleanup và evidence

- `action_log` là per-call, không tích lũy calls trước.
- Persist action/error log cả khi navigation/click/download thất bại.
- Đóng page/context/browser trong `finally`.
- Cleanup cả destination lẫn temp trên mọi exception.
- Dùng temp + `os.replace` atomic trong cùng directory.
- Derived binary candidate/evidence idempotent khi resume.

## 7. Strict override và provider registry validation

### 7.1 Override

Unknown provider, unknown role, non-HTTPS, disallowed route, duplicate key, thiếu canonical identifier/provenance, sai kiểu `required`, empty alternative group phải `raise ValueError` kèm entry index. Không được bỏ qua im lặng.

Giữ toàn bộ structured fields của override khi tạo Candidate; không rút còn `(role, url)`.

### 7.2 Registry

- Query-aware rules phải kiểm query riêng; không đặt `?docid=*` trong path glob rồi tưởng đã match.
- Mọi provider có role routes rõ; `moha_labor` không được dùng một route cho tất cả roles.
- Định nghĩa rõ `allowed_redirect_domains`: nếu cho cross-domain, final domain vẫn phải có explicit role route/rule; nếu không hỗ trợ, từ chối config đó.
- Thêm static registry audit cho HTML-as-binary, binary-as-identity ngoài rule, overlapping ambiguous providers và wildcard quá rộng.

## 8. Regression tests bắt buộc

Bổ sung test cho tất cả mục sau; không chỉ ghi trong report:

1. required/alternative group quyết định warning vs blocking;
2. Công báo trusted binary làm old VBPL 404 và disabled optional control thành warning;
3. best binary fields cùng trỏ một candidate;
4. outcome cuối kém hơn không đổi `binary_state`/URL/SHA;
5. identity ranking đúng source/authority, không theo URL;
6. đảo candidate order cho kết quả giống nhau;
7. `STATUS_HISTORY` home shell không `FETCHED`;
8. status identifier mismatch không `FETCHED`;
9. direct binary 404 kích hoạt bounded adaptive VBPL probes;
10. shell/mismatch không tạo trusted/fetched attachment;
11. browser fixture từ chối empty selector;
12. proven selector đi qua full mocked browser path;
13. browser page redirect ngoài allowlist bị chặn trước click;
14. download URL ngoài allowlist bị chặn dù SHA exact;
15. exact bytes + authority fail không auto exact;
16. browser error action log được persist;
17. browser temp/destination cleanup;
18. derived candidate resume không duplicate;
19. invalid override từng loại bị reject;
20. override structured fields được giữ;
21. query-aware provider rule;
22. registry audit từng provider/role;
23. strict readiness audit exit `0` khi pass;
24. strict readiness audit nonzero và liệt kê record/candidate khi fail.

Không dùng live network trong unit tests.

## 9. Expected output — acceptance contract

### 9.1 Offline commands

Chạy đúng các lệnh và ghi nguyên văn vào report:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m unittest tests.test_source_resolver -v
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m vn_labor_offline.source_resolver.cli audit --db artifacts/00_manifest/source_resolution_p2_3.sqlite --export-dir artifacts/00_manifest/source_resolution_p2_3_export --strict --out artifacts/reports/source_resolution_p2_3_readiness.json
```

Không hardcode tổng số test mong đợi; yêu cầu **tất cả discovered tests pass, 0 failure, 0 error**, và không có skipped test quan trọng. Số test resolver phải tăng tương ứng với test thật đã thêm.

### 9.2 Readiness JSON bắt buộc

`artifacts/reports/source_resolution_p2_3_readiness.json` tối thiểu phải có:

```json
{
  "schema_version": 1,
  "passed": true,
  "database_user_version": 3,
  "gates": {
    "candidate_column_metadata_mismatches": 0,
    "identity_or_status_mismatch_saved_as_fetched": 0,
    "home_shell_saved_as_fetched": 0,
    "html_final_binary_urls": 0,
    "auto_exact_without_authority": 0,
    "auto_exact_without_identity": 0,
    "best_binary_field_mismatches": 0,
    "conflicting_sha_semantics": 0,
    "blocking_reasons_from_satisfied_alternatives": 0,
    "browser_derived_orphans": 0,
    "duplicate_candidates": 0,
    "duplicate_evidence_events": 0,
    "invalid_override_entries": 0,
    "provider_role_route_violations": 0,
    "unclassified_reason_codes": 0
  }
}
```

Có thể thêm gates nhưng không được bỏ hoặc đổi nghĩa các gate trên. Nếu DB chưa có browser derived candidate thì `browser_derived_orphans=0` vẫn phải được test bằng fixture DB riêng.

### 9.3 Seed/dry-run invariants

Audit offline trên seed phải xác nhận:

- records: `95`;
- source groups: `57/24/10/4`;
- direct-only records: `8`;
- duplicate relative paths: `0`;
- duplicate record IDs: `0`;
- production catalog và corpus không bị ghi.

### 9.4 Fresh smoke matrix

Tạo mới, không ghi đè:

- `artifacts/00_manifest/source_resolution_p2_3.sqlite`
- `artifacts/00_manifest/source_resolution_p2_3_export/`
- `.cache/source_resolver_p2_3/`

Smoke đúng bốn records:

| record | expected state/SHA | invariant bắt buộc |
|---|---|---|
| `f7b2a95453d4d6b6` | `AUTO_EXACT_SHA / YES` nếu official PDF vẫn tải được | authority + identity true; identity 403 chỉ warning |
| `cbd1f72df7f0d08f` | `NEEDS_REVIEW / NO` nếu Công báo bytes không đổi | decision `SHA_MISMATCH`; old VBPL/control failures không ở blocking khi trusted binary đã có |
| `ebd563a10f4e9b84` | `NEEDS_REVIEW / NO` nếu Công báo bytes không đổi | cùng semantics record 06; phải có lại trong smoke P2.3 |
| `114cafe0807308bb` | `AUTO_EXACT_SHA/YES`, `NEEDS_REVIEW/NO`, hoặc `BLOCKED/NOT_DOWNLOADED` tùy live evidence | state phải đúng semantics; shell không FETCHED; final binary rỗng nếu chưa có valid binary |

Không ép exact states nếu provider đã thay đổi. Nếu live response khác baseline, ghi actual HTTP/magic/SHA/evidence và đánh giá bằng invariant.

### 9.5 Expected reason classification

- NATLEX: `blocking_reason_codes=[]`; identity 403 ở warnings.
- Công báo 06/24 khi trusted mismatch binary tồn tại:
  - `decision_reason_codes` chứa `SHA_MISMATCH`;
  - `blocking_reason_codes=[]`;
  - old VBPL 404/shell và optional Playwright disabled ở warnings hoặc control không được tạo nếu thừa.
- VBPL 10 khi chưa có valid binary:
  - `resolved_sha_match=NOT_DOWNLOADED`;
  - `final_binary_url=""`;
  - access failure của con đường required còn lại ở blocking;
  - shell/mismatch không được ghi `FETCHED`.

### 9.6 Ready decision

Chỉ kết luận:

- `READY_FOR_LIMITED_PROVIDER_BATCH` khi strict audit pass và mỗi provider dự kiến đưa vào batch có ít nhất một successful live smoke theo trust semantics;
- `READY_FOR_LIMITED_BATCH_EXCLUDING_BLOCKED_PROVIDERS` khi strict code audit pass nhưng một provider như VBPL còn external access blocker; liệt kê provider được phép và bị loại;
- `NOT_READY_CODE` nếu bất kỳ deterministic gate/test fail;
- `NOT_READY_EXTERNAL` nếu code pass nhưng không có provider nào đủ live smoke để chạy limited batch.

Không dùng nhãn `READY` chung chung.

## 10. Báo cáo cuối và self-check

Cập nhật `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md` để chỉ có **một Current status** ở đầu. Các P1/P2 cũ phải nằm dưới heading `Historical results` và không được phát biểu schema/state cũ như hiện hành.

Cuối báo cáo phải có bảng:

| Gate | Expected | Actual | PASS/FAIL | Evidence path |
|---|---|---|---|---|

Trước khi kết thúc, Copilot phải tự đọc lại:

- readiness JSON;
- SQLite candidates/evidence;
- export JSONL;
- git diff;
- test output.

Nếu bảng có bất kỳ `FAIL`, quay lại vòng lặp phần 1. Chỉ dừng với FAIL khi có external blocker không thể sửa bằng code; ghi URL, HTTP/error, số attempt và vì sao không retry thêm.

Xác nhận production catalog, review draft catalog, corpus, pipeline artifacts và Aura không bị thay đổi. Liệt kê chính xác file sửa/tạo và lệnh đã chạy.
