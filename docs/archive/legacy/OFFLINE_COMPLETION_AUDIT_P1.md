# Audit vòng hoàn thiện OFFLINE P1

## Kết luận

Kết quả P2.3 xác nhận seed 95 record được import và 15 invariant nội bộ của Source Resolver đạt. Tuy nhiên trạng thái đúng hiện tại vẫn là **`FAILED_CODE`/automation incomplete**, chưa phải `WAITING_FOR_HUMAN_REVIEW`, vì các bước tự động bắt buộc chưa chạy và unified completion audit chưa đủ khả năng chứng minh `COMPLETE`.

## Bằng chứng đã kiểm tra

### Source Resolver

Fresh database `artifacts/00_manifest/source_resolution_p2_3.sqlite` có:

- records: 95;
- candidates: 0;
- evidence events: 0;
- `FETCH_PENDING`: 84;
- `NEEDS_DISCOVERY`: 10;
- `NEEDS_REVIEW`: 1.

Do đó strict resolver audit hiện chỉ chứng minh database nhất quán sau import. Nó chưa chứng minh network resolution, attachment discovery, browser path, SHA verification hoặc provider coverage cho fresh P2.3.

### Unified completion audit

`scripts/audit_offline_completion.py` còn các lỗi thiết kế sau:

1. Không có đường code tạo `status=COMPLETE`; khi hết pending action nó trả `FAILED_CODE`.
2. `offline_ready_for_online` luôn bị hard-code `False`.
3. Source record được tính là reviewed nếu **bất kỳ** `legal_decision`, `review_status` hoặc `reviewer` có nội dung; không kiểm bộ trường, allowed decision, evidence, timestamp hoặc SHA.
4. `authoritative_unverified` lấy tổng 95 trừ reviewed, không phân biệt source group/authority policy.
5. `unresolved_sha_mismatches`, `invalid_or_overlapping_intervals`, `derived_records_missing_evidence` bị hard-code bằng 0.
6. `missing_required_spans` suy ra từ technical PASS thay vì đọc check/artifact thật.
7. Dense và BM25 cùng suy ra từ một boolean `indexes`; không kiểm file, ID/count/model/fingerprint riêng.
8. `same_build_verified` chỉ kiểm Neo4j có `passed` và có `build_id`; không so sánh registry/graph/index/Aura build IDs.
9. Gold chỉ kiểm `approved_queries > 0`, boolean `required_query_types` và `passed`; chưa xác minh threshold, nhóm query, qrel, reviewer và build compatibility trong completion audit.
10. Queue chỉ được đếm status; không validate schema, uniqueness, decision completeness hoặc reviewer.
11. Iteration luôn ghi `iteration=1`, fingerprint chỉ hash chuỗi đường dẫn và tạo nhiều dòng trùng nhau.
12. Báo cáo hard-code `automation work remaining: 0` dù resolver chưa tạo candidate/evidence.
13. Test mới chỉ có hai tình huống, chưa có positive COMPLETE path và các negative cases trong completion contract.

### Quarantine queue

`quarantine_review_queue.jsonl` có 837 dòng nhưng không tương ứng 837 quyết định độc lập:

- 492 `provision_id` duy nhất;
- 492 `canonical_path` duy nhất;
- 33 documents;
- 345 dòng lặp theo `provision_id`;
- một canonical path có từ 1 đến 8 dòng;
- levels: 474 POINT, 360 CLAUSE, 3 ARTICLE.

Queue cần được phân nhóm theo collision/canonical identity và nguyên nhân, rồi tạo quyết định nhóm có khả năng áp dụng deterministic xuống record. Không giao thẳng 837 dòng rời rạc cho reviewer.

## Trạng thái đúng

Technical V8.1 vẫn là bằng chứng PASS hợp lệ cho build cũ. Trạng thái completion hiện tại phải phản ánh đồng thời:

- technical baseline: PASS;
- Source Resolver fresh resolution: NOT RUN beyond import;
- unified completion audit correctness: FAIL;
- human review: chưa thực hiện.

Vì còn công việc code/network deterministic, trạng thái tổng phải là `FAILED_CODE` hoặc `AUTOMATION_IN_PROGRESS`. Chỉ chuyển sang `WAITING_FOR_HUMAN_REVIEW` khi mọi công việc tự động đã hoàn thành, các review package đã được validate và chỉ còn quyết định con người.
