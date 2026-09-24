# Audit vòng hoàn thiện OFFLINE P2

## Kết luận

Batch bounded đã tạo evidence thật cho 95 record và review ZIP có hash/manifest hợp lệ. Tuy nhiên trạng thái tổng vẫn phải là **`FAILED_CODE`/`AUTOMATION_IN_PROGRESS`**, chưa phải `WAITING_FOR_HUMAN_REVIEW`, vì 76 record còn `FETCH_PENDING`, aggregate state còn mâu thuẫn với candidate evidence, completion audit vẫn dùng điều kiện quá yếu và review package chưa giảm/validate khối lượng review.

## Bằng chứng Source Resolver

Fresh batch có:

- records: 95;
- candidates: 235;
- evidence: 217;
- record states: 5 `AUTO_EXACT_SHA`, 3 `BLOCKED`, 76 `FETCH_PENDING`, 11 `NEEDS_REVIEW`;
- candidate states: 17 `AUTO_EXACT_SHA`, 18 `BLOCKED`, 20 `FETCHED`, 39 `FETCH_PENDING`, 141 `NEEDS_REVIEW`.

Trong 76 record `FETCH_PENDING`:

| Candidate-state composition | Records |
|---|---:|
| `FETCH_PENDING` + `NEEDS_REVIEW` | 38 |
| chỉ `NEEDS_REVIEW` | 13 |
| `AUTO_EXACT_SHA` + `FETCHED` | 12 |
| chỉ `BLOCKED` | 8 |
| `BLOCKED` + `FETCHED` + `NEEDS_REVIEW` | 3 |
| `BLOCKED` + `FETCHED` | 1 |
| `FETCHED` + `NEEDS_REVIEW` | 1 |

Các mâu thuẫn quan trọng:

- 12 record có exact binary candidate nhưng aggregate record vẫn `FETCH_PENDING`.
- 13 record chỉ có review evidence nhưng aggregate không chuyển `NEEDS_REVIEW`.
- 8 record chỉ có blocked evidence nhưng aggregate không chuyển trạng thái kết thúc phù hợp.
- 39 candidate vẫn `FETCH_PENDING`, nghĩa là vẫn có công việc fetch/process chưa hoàn tất.
- Có `UnicodeEncodeError`/ASCII codec error; đây là lỗi code có thể sửa.
- Có `RuntimeError`, `PROVIDER_NOT_ALLOWED` và `PLAYWRIGHT_SELECTOR_NOT_PROVEN` cần phân loại thành code/config/retry/external bằng evidence, không được xem như đã hoàn tất chỉ vì có attempt timestamp.

`source_resolution_p2_3_coverage.json` hiện đặt `resolution_complete=true` chỉ vì `attempted=95`. Điều kiện này chưa đúng.

## Bằng chứng completion audit

Completion audit hiện coi resolver đạt nếu:

- attempted bằng records;
- database có ít nhất một candidate và một evidence;
- export count bằng record count.

Điều kiện trên có thể PASS ngay cả khi phần lớn record chưa có terminal state. Audit vẫn còn các điểm chưa sửa từ vòng trước:

- `same_build_verified` chỉ kiểm Neo4j có build ID, chưa so sánh các build ID;
- Dense/BM25 mới kiểm file tồn tại, chưa load/count/ID/fingerprint;
- `unresolved_sha_mismatches`, interval errors và derived-evidence errors còn hard-code 0;
- queue mới đếm status, chưa validate quyết định;
- chỉ có 2 completion-audit tests, chưa có positive `COMPLETE` fixture và các negative tests đã yêu cầu.

## Bằng chứng review package

ZIP có SHA-256 đúng `918db1999aaf383c7e6d427aff1160ae4a7c63cae81abafeac5c53437e8b1750`, gồm 9 entry và `ZipFile.testzip()` không báo lỗi. Tuy nhiên package chưa sẵn sàng giao reviewer:

- instruction chỉ là một đoạn rất ngắn, không hướng dẫn từng queue/allowed decision;
- không chứa validator/command validate;
- quarantine vẫn là 837 raw rows, chưa gom decision case;
- chưa có temporal instrument-level review cases;
- chưa có Gold candidate/query/qrel review package;
- không có grouped review manifest thể hiện số decision units thực tế.

ZIP hiện tại nên được giữ làm evidence của vòng P2, không dùng làm final human handoff.
