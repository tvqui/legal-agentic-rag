# Prompt cho Copilot Agent — hoàn thiện toàn bộ OFFLINE bằng vòng lặp kiểm chứng

Bạn là **Senior Software Engineer + Legal NLP / GraphRAG Engineer + Data Quality Engineer**. Hãy trực tiếp làm việc trong repository hiện tại để đưa toàn bộ **OFFLINE — Data & Knowledge Construction** đến trạng thái hoàn tất theo [OFFLINE_100_PERCENT_PLAN.md](OFFLINE_100_PERCENT_PLAN.md) và [OFFLINE_100_COMPLETION_CONTRACT.md](OFFLINE_100_COMPLETION_CONTRACT.md).

Đây là nhiệm vụ triển khai, sửa lỗi, kiểm thử và tạo artifact. Không chỉ viết kế hoạch hoặc báo cáo. Hãy tự lặp **inspect → implement → test → audit → compare → repair** cho đến khi:

1. đạt `COMPLETE`; hoặc
2. chỉ còn đầu vào thật sự phải do con người/Kaggle/Aura cung cấp và trạng thái được ghi đúng là `WAITING_FOR_HUMAN_REVIEW`, `WAITING_FOR_REMOTE_EXECUTION` hoặc `BLOCKED_EXTERNAL`.

Không dừng vì một lỗi code có thể sửa. Không hỏi người dùng sau mỗi vòng nội bộ. Không tuyên bố thành công từ exit code pipeline hoặc số test pass riêng lẻ.

---

## 0. Sửa ngay kết luận blocker hiện tại

Kết luận “không tồn tại `review_inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv`” là sai đối với workspace chính. File này nằm trong thư mục bị `.gitignore`, nên không được dùng Git index hoặc `rg --files` mặc định để kết luận nó vắng mặt.

Chạy đúng các kiểm tra filesystem sau từ repository root:

```powershell
$seed = 'review_inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv'
Get-Location
Test-Path -LiteralPath $seed
Get-Item -LiteralPath $seed | Select-Object FullName,Length,LastWriteTime
$rows = Import-Csv -LiteralPath $seed
$rows.Count
$rows | Group-Object source_group | Select-Object Name,Count
rg --files -uu review_inputs/v8_1
```

Kết quả mong đợi trong workspace này:

- `Test-Path=True`;
- 95 data record, ngoài header;
- phân bố seed phải được kiểm lại theo schema thực tế, baseline đã biết là `57/24/10/4`;
- không được báo thiếu file chỉ vì file bị ignore.

Nếu vẫn không thấy file, trước tiên xác minh `Get-Location`, worktree và absolute path. Chỉ sau khi filesystem thực sự không có file mới được kiểm tra package `review_packages/source_review_handoff_v8_1_full.zip` theo SHA/report để phục hồi an toàn. Không ghi đè dữ liệu hiện có.

Sau khi xác nhận seed, tiếp tục fresh P2.3 run. Không dùng strict audit trên artifact P2.2 cũ làm bằng chứng cho code P2.3.

---

## 1. Sự thật nền phải giữ

- V8.1 đã chứng minh **technical OFFLINE v1 PASS** trên Kaggle + Aura với 95 documents, 18,449 provisions, 50,118 graph nodes, 76,844 graph edges và bốn đầu ra kỹ thuật PASS.
- Baseline đó chưa phải `OFFLINE 100%`: source review, temporal review, quarantine decisions và Gold review còn thiếu.
- Người dùng hiện **chưa có người duyệt pháp lý**. Không được tự điền reviewer, `APPROVED`, `VERIFIED`, qrel hoặc quyết định pháp lý thay con người.
- P2.3 hiện có 24 resolver tests và full suite 125 tests. Số test pass không chứng minh fresh network path, full corpus hoặc toàn bộ OFFLINE đã đạt.
- Artifact readiness P2.3 hiện tại đang audit DB P2.2 cũ và fail một gate; nó chỉ là bằng chứng regression, không phải output fresh P2.3.
- Production catalog, review draft, corpus và Aura không được âm thầm sửa. Mọi mutation phải qua staging, diff, validation và quyết định phù hợp.

---

## 2. Quy tắc vòng lặp bắt buộc

Thực hiện từng phase bên dưới. Với mỗi phase:

1. **Preflight:** kiểm input, schema, SHA, build ID và precondition.
2. **Implement:** sửa tối thiểu nhưng đầy đủ, không làm pass giả.
3. **Targeted tests:** thêm test có ý nghĩa cho failure vừa sửa rồi chạy chúng.
4. **Repository tests:** chạy toàn bộ test phù hợp.
5. **Fresh artifact:** dùng database/output/cache mới có tên phase/build; không sửa artifact bảo vệ.
6. **Strict audit:** chạy machine audit trên fresh artifact.
7. **Compare:** so actual output với acceptance criteria của phase.
8. Nếu fail do code/data transformation deterministic, sửa và quay lại bước 2.
9. Nếu fail vì network tạm thời, retry có giới hạn/backoff/resume rồi phân loại chính xác.
10. Nếu chỉ còn quyết định con người hoặc remote execution, tạo gói handoff đầy đủ và dừng ở trạng thái chờ tương ứng. Khi đầu vào được trả lại, validate rồi tiếp tục từ checkpoint; không chạy lại vô ích từ đầu.

Mỗi vòng phải ghi vào `artifacts/reports/offline_completion_iterations.jsonl`:

- timestamp;
- phase và iteration;
- input fingerprint/build ID;
- commands;
- exit codes;
- failed gates;
- files changed;
- decision `RETRY`, `ADVANCE`, `WAITING_*` hoặc `COMPLETE`.

Đặt giới hạn cho retry đồng nhất. Nếu cùng một external blocker lặp lại mà không có input mới, không spin vô hạn; chuyển thành trạng thái chờ có action cụ thể.

---

## 3. Phase A — hoàn tất Source Resolver P2.3 bằng fresh evidence

### A1. Correctness trước network

Audit implementation hiện tại thay vì tin báo cáo. Đặc biệt kiểm:

- readiness audit không hard-code gate bằng `0`;
- `unclassified_reason_codes` được tính từ enum/allowlist thật;
- selected binary evidence và mọi trường aggregate (`final_binary_url`, SHA, MIME, authority, identity, candidate ID) đến từ cùng một evidence event/candidate;
- override validation fail-closed và có index/path/provenance;
- identity/status page chưa xác minh không sinh attachment candidate đáng tin;
- capability đã được evidence tốt thỏa mãn không bị alternative optional làm thành blocking;
- resume chọn evidence mới nhất hợp lệ và không thay đổi kết luận do thứ tự candidate;
- browser-derived binary luôn đi qua common magic/MIME/size/SHA/authority/evidence path;
- SQLite migration idempotent, giữ evidence cũ và schema/version nhất quán.

Thêm regression tests cho từng invariant còn thiếu. Không chỉ giữ tổng 24 tests nếu phạm vi P2.3 đã mở rộng mà chưa có test tương ứng.

### A2. Fresh seed/import

Tạo DB/cache/export mới, không dùng artifact P2.2:

```text
artifacts/00_manifest/source_resolution_p2_3.sqlite
artifacts/00_manifest/source_resolution_p2_3_export/
.cache/source_resolver_p2_3/
artifacts/reports/source_resolution_p2_3_readiness.json
```

Import đủ 95 record từ tracking CSV và review draft catalog. Kiểm:

- 95 record duy nhất;
- source group đúng;
- path và SHA khớp catalog/corpus;
- import lần hai idempotent;
- dry-run không tải binary và không sửa catalog.

### A3. Four-record smoke

Chạy fresh four-record network smoke gồm các tình huống đã biết: exact official binary, identity warning nhưng binary đủ mạnh, Công báo CDN SHA mismatch, và VBPL shell/download control. Network/browser phải opt-in và rate-limited.

Expected smoke output:

- không có exception chưa phân loại;
- exact official binary hợp lệ đạt `AUTO_EXACT_SHA` khi authority + identity requirements được thỏa;
- HTML không bao giờ được ghi làm binary;
- SHA mismatch là `NEEDS_REVIEW`;
- chưa tải được binary là `NOT_DOWNLOADED`, không phải `NO`;
- homepage/loading shell không sinh trusted attachment;
- strict resolver audit exit `0` cho consistency gates. Record có legitimate `NEEDS_REVIEW/BLOCKED` vẫn được phép nếu gate audit đánh giá trạng thái/evidence nhất quán.

### A4. Mở rộng có kiểm soát

Chỉ khi A1–A3 đạt:

1. một record/provider;
2. tối đa 5 record/provider;
3. review rate, redirect, reason distributions, cache/resume;
4. mới chạy toàn bộ 95 record bằng batch nhỏ và resume.

Không khởi chạy batch lớn nếu provider-specific fixture hoặc browser selector chưa được chứng minh. Không dùng confidence score để tự phê duyệt.

### A5. Output của Phase A

- Fresh SQLite/export/cache và readiness JSON.
- Summary tổng 95 record theo state/provider/reason.
- Review queue có evidence và action cụ thể.
- Proposed catalog diff; không tự merge quyết định cần người duyệt.
- Strict source-resolver audit deterministic và exit code đúng.

---

## 4. Phase B — Source Catalog review completion

Từ resolver output, tạo một gói review tối thiểu, chống nhầm record, bao gồm:

- record ID/path/source group/canonical identifier;
- corpus SHA và downloaded SHA;
- identity/status/binary URL tách riêng;
- redirect chain, provider/authority result;
- identity evidence và excerpt/hash phù hợp;
- resolver recommendation và reason codes;
- các lựa chọn quyết định hữu hạn;
- ô reviewer, reviewed_at, review_evidence và note.

Tự động áp dụng chỉ các trường kỹ thuật đã được chứng minh và được policy cho phép. Không tự duyệt tính pháp lý. Validate file review trả về theo schema, record set, SHA, allowed decisions, timestamps và reviewer presence trước merge.

Acceptance criteria Phase B:

- 95/95 record có quyết định review hợp lệ;
- authoritative source cần thiết không còn `UNVERIFIED`;
- mọi mismatch có quyết định và evidence;
- production `config/source_catalog.yaml` được merge qua diff đã duyệt;
- source-catalog quality gate PASS.

Nếu chưa có reviewer, hoàn thành toàn bộ resolver, prefill và package có thể tự động rồi ghi `WAITING_FOR_HUMAN_REVIEW`. Đây không phải `FAILED_CODE` và không được đổi thành PASS giả.

---

## 5. Phase C — cấu trúc, provenance và quarantine

Audit toàn bộ structured provisions:

- Article/Clause/Point identity ổn định;
- `char_start/end`, `line_start/end`, `segment_id`, page provenance hợp lệ theo loại tài liệu;
- hierarchy Chapter/Section/Article/Clause/Point nhất quán;
- canonical path không collision ngoài các trường hợp được review/exclude;
- short provision không phải lỗi parser/OCR bị che giấu.

Tạo queue cho 32 `AMBIGUOUS_CANONICAL_PATH_QUARANTINED` và 4 `SHORT_PROVISION_QUARANTINED` của baseline, nhưng số thực tế phải được đọc từ fresh build. Mỗi quyết định include/fix/exclude cần evidence. Sửa parser nếu pattern có thể tổng quát hóa; thêm fixture/test trước khi rebuild.

Acceptance criteria:

- không còn lỗi source span/identity/hierarchy;
- mọi quarantine item có quyết định hợp lệ;
- exclusion không làm mất nội dung âm thầm;
- structure/provenance gates PASS.

---

## 6. Phase D — legal relations và temporal/version processing

Audit và hoàn thiện:

- document/provision target cho `AMENDS`, `REPEALS`, `REPLACES`, `IMPLEMENTS`;
- exact scope đến Article/Clause/Point nếu nguồn cho phép;
- `valid_from/valid_to` đồng bộ đúng với effective interval;
- interval không đảo/chồng lấn trái quy tắc;
- supersession chain và version identity ổn định;
- mọi quan hệ/scope không chắc chắn vào review queue.

Đối với 25 LegalChange pending và 18,449 provision version unreviewed trong baseline, đọc số fresh thay vì hard-code. Tạo review package theo từng thay đổi, nhóm những provision dùng cùng một căn cứ để giảm thao tác nhưng vẫn lưu quyết định record-level.

Acceptance criteria:

- pending required LegalChange = 0;
- unreviewed required provision version = 0;
- invalid/overlapping interval = 0;
- relation không có exact evidence bắt buộc = 0;
- temporal/semantic gates PASS.

Nếu scope/ngày hiệu lực cần phán đoán pháp lý, dừng tại `WAITING_FOR_HUMAN_REVIEW` sau khi đã tạo package đầy đủ; không đoán.

---

## 7. Phase E — derived knowledge và diagnostic checklist

Kiểm tra mọi diagnostic item/derived edge:

- truy ngược được về document/provision/version/source span;
- phân biệt extracted fact, deterministic derivation và model suggestion;
- không biến model suggestion thành verified legal fact;
- deduplicate ổn định;
- validity interval và build provenance được giữ trong retrieval metadata.

Nếu chạy Ollama enrichment, coi đó là optional proposal layer; output phải qua schema/evidence validation và không được tự nâng trạng thái review.

Acceptance criteria:

- required derived record thiếu exact evidence = 0;
- dangling source reference = 0;
- derived quality gate PASS.

---

## 8. Phase F — rebuild graph và retrieval indexes

Sau bất kỳ thay đổi corpus/catalog/structure/temporal/relations nào, tính fingerprint để quyết định rebuild tối thiểu đúng dependency. Khi cần rebuild:

- tạo Document Registry;
- Structured Provisions;
- Versioned HierarGraph;
- retrieval units;
- Dense BGE-M3 index;
- BM25 index;
- manifest/report mới.

Kiểm:

- registry/structure/graph/indexes đều PASS;
- retrieval-unit count/IDs khớp Dense và BM25;
- embedding dimension/model/hash đúng config;
- BM25 có thể load và retrieve fixture;
- Dense có thể load và retrieve fixture;
- temporal/provenance metadata tồn tại trong retrieval units;
- không reuse index khi upstream fingerprint thay đổi.

Không dùng exit code `0` của pipeline làm tiêu chuẩn duy nhất.

---

## 9. Phase G — Gold set và evaluation

Tạo tooling, schema, candidate queries, sampling và review package cho Gold. Bao phủ các query group mà config/kiến trúc yêu cầu, gồm temporal, citation, hierarchy và multi-hop khi có.

Ranh giới bắt buộc:

- Copilot được tạo candidate và kiểm consistency.
- Copilot không tự phê duyệt Gold label/qrel hoặc tự ghi reviewer.
- Chỉ record `APPROVED` có reviewer/evidence hợp lệ mới đi vào gate chính thức.

Sau khi có Gold đã duyệt:

- khóa `gold_build_id`;
- chạy retrieval/evaluation;
- công bố sample count, metric, threshold, failure cases;
- sửa code/data issue deterministic rồi chạy lại;
- nếu metric thấp do dữ liệu/Gold conflict, tạo queue phân tích, không chỉnh nhãn để tăng điểm.

Acceptance criteria:

- đủ approved Gold theo threshold cấu hình;
- đủ required query groups;
- build compatibility PASS;
- mọi required metric đạt;
- Gold evaluation gate PASS.

Khi chưa có reviewer pháp lý, expected status là `WAITING_FOR_HUMAN_REVIEW` sau khi tooling và package đã hoàn tất.

---

## 10. Phase H — unified completion audit

Triển khai `scripts/audit_offline_completion.py` và test cho nó. Audit phải đọc artifact thật, không hard-code kết quả. Nó phải tổng hợp ít nhất:

- technical four-output validation;
- source-catalog quality;
- structure/provenance/quarantine decisions;
- temporal/relation review;
- derived evidence;
- Dense/BM25 integrity;
- Gold/evaluation;
- build/fingerprint consistency;
- Neo4j live build verification.

Sinh:

```text
artifacts/reports/offline_completion_contract.json
artifacts/reports/offline_completion_report.md
artifacts/reports/offline_completion_iterations.jsonl
```

Strict CLI phải có semantics:

- exit `0` chỉ khi `COMPLETE` và `offline_ready_for_online=true`;
- nonzero cho mọi trạng thái còn lại;
- JSON vẫn được ghi đầy đủ khi fail;
- không biến warning được policy cho phép thành lỗi, nhưng phải liệt kê;
- không cho artifact thiếu/chưa chạy được coi là PASS.

Thêm negative tests cho stale build, stale Neo4j, missing artifact, zero Gold, unverified source, pending temporal review, mismatched index IDs và fabricated reviewer fields.

---

## 11. Phase I — Kaggle và Aura final build

Khi local/code gates sẵn sàng:

1. tạo package Kaggle mới và manifest/hash;
2. kiểm package chứa đúng code/config/review input cần thiết, không chứa secrets;
3. viết chính xác cell/flags cho fresh run;
4. chạy full pipeline trên Kaggle hoặc tạo trạng thái `WAITING_FOR_REMOTE_EXECUTION` với đúng một handoff rõ ràng;
5. tải ZIP output về và kiểm SHA/schema/build ID;
6. chạy local strict completion audit;
7. nạp Neo4j Aura từ cùng graph build;
8. chạy live audit và cập nhật completion artifact;
9. chạy strict audit lần cuối.

Không yêu cầu xóa Aura cũ nếu loader hỗ trợ replace theo build an toàn; nhưng audit phải chứng minh không còn stale/mixed build.

---

## 12. Kết quả đầu ra cuối cùng mong muốn

Chỉ được kết luận hoàn tất khi tất cả điều sau xuất hiện trong fresh final report:

```text
OFFLINE v1: PASS
ONLINE-ready: PASS
offline_ready_for_online: true
completion status: COMPLETE
registry: PASS
structure: PASS
graph: PASS
dense: PASS
bm25: PASS
neo4j: PASS
source catalog: PASS
temporal/version review: PASS
provenance/quarantine review: PASS
derived evidence: PASS
gold evaluation: PASS
same build verified: true
validation ERROR count: 0
remaining required actions: 0
```

Các count phải lấy từ build cuối, không sao chép baseline. Warnings được phép chỉ khi policy định nghĩa rõ là non-blocking và report ghi lý do.

Lệnh cuối phải tương đương:

```powershell
python scripts/audit_offline_completion.py --strict
```

và trả exit code `0`.

Nếu chưa thể đạt kết quả trên vì chưa có reviewer, output mong muốn của vòng hiện tại là:

```text
completion status: WAITING_FOR_HUMAN_REVIEW
automation work remaining: 0
human review queues: <danh sách file + số record>
first resume command: <một lệnh cụ thể>
offline_ready_for_online: false
```

Nếu cần Kaggle/Aura:

```text
completion status: WAITING_FOR_REMOTE_EXECUTION
package: <path>
package sha256: <sha>
exact run instructions: <path>
required returned artifact: <tên ZIP/log>
offline_ready_for_online: false
```

---

## 13. Báo cáo mỗi lần dừng

Khi dừng, cập nhật `OFFLINE_100_IMPLEMENTATION_REPORT.md` theo dữ liệu thực tế:

1. trạng thái completion hiện tại;
2. phase cuối đã đạt;
3. changes theo file;
4. commands và kết quả test/audit;
5. fresh artifact paths/build IDs;
6. bảng gate PASS/FAIL/WAITING;
7. blocker được phân loại code/human/remote/external;
8. đúng một danh sách hành động tiếp theo có thể thực hiện;
9. không tuyên bố `COMPLETE` nếu strict final audit chưa exit `0`.

Bắt đầu ngay bằng việc xác minh file seed bị ignore, sửa false blocker, audit correctness của P2.3 và tạo fresh P2.3 artifacts. Sau đó tiếp tục tuần tự qua các phase, tự lặp sửa và kiểm tra cho đến trạng thái hợp lệ theo completion contract.
