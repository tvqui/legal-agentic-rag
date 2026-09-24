# OFFLINE 100% Completion Contract

Tài liệu này định nghĩa điều kiện kết thúc cho toàn bộ **OFFLINE — Data & Knowledge Construction**. Một lệnh chạy thành công hoặc `OFFLINE v1: PASS` chưa đủ để kết luận `OFFLINE 100%`.

## 1. Các trạng thái hợp lệ

Hệ thống chỉ được công bố một trong các trạng thái sau:

| Trạng thái | Ý nghĩa |
|---|---|
| `COMPLETE` | Tất cả gate kỹ thuật, dữ liệu, kiểm duyệt pháp lý, Gold evaluation, Kaggle và Aura đều đạt trên cùng build. |
| `WAITING_FOR_HUMAN_REVIEW` | Phần tự động đã hoàn thành nhưng còn quyết định cần người đủ chuyên môn xác nhận. |
| `WAITING_FOR_REMOTE_EXECUTION` | Code và gói chạy đã sẵn sàng nhưng cần chạy Kaggle/Aura rồi đưa artifact về kiểm tra. |
| `BLOCKED_EXTERNAL` | Nguồn chính thức, dịch vụ hoặc quyền truy cập bên ngoài đang chặn tiến độ; phải ghi rõ record và bằng chứng. |
| `FAILED_CODE` | Còn lỗi code, test, invariant hoặc machine audit mà agent có thể tiếp tục sửa. |

Không dùng `COMPLETE` nếu còn bất kỳ gate bắt buộc nào ở trạng thái `FAIL`, `UNKNOWN`, `NOT_RUN`, `DRAFT`, `UNVERIFIED` hoặc `PENDING_REVIEW`.

## 2. Điều kiện bắt buộc để đạt COMPLETE

### 2.1 Tính toàn vẹn build

- Có một `build_id` duy nhất cho registry, structured provisions, graph, retrieval units, Dense, BM25 và Neo4j.
- Gold/evaluation ghi rõ `gold_build_id` và corpus/build được đánh giá.
- Không dùng artifact cũ để chứng minh code mới.
- Manifest ghi hash của input, config, model, output và công cụ tạo artifact.

### 2.2 Bốn đầu ra kỹ thuật

- Document Registry: `PASS`.
- Structured Provisions: `PASS`.
- Versioned HierarGraph: `PASS`.
- Dense + BM25 indexes: `PASS`.
- Không còn validation issue mức `ERROR` hoặc lỗi cấu trúc nghiêm trọng.
- Số retrieval unit trong metadata, Dense và BM25 phải khớp nhau.
- Neo4j được nạp từ đúng graph build và live audit đạt.

### 2.3 Source Catalog

- Source Resolver chỉ được coi là hoàn thành phần tự động khi mọi record đã được attempt, không còn record/candidate bắt buộc ở `FETCH_PENDING`, không còn lỗi code/retryable và mỗi record có terminal state cùng evidence phù hợp. `resolution_attempted_at` tự nó không chứng minh resolution hoàn tất.
- Mọi record corpus đều có quyết định review; baseline hiện tại là 95 record.
- Mọi tài liệu cần nguồn có provider, URL vai trò đúng, ngày thu thập, SHA-256, evidence và quyết định rõ ràng.
- Không còn authoritative source ở trạng thái `UNVERIFIED`.
- Không còn SHA mismatch chưa được giải quyết hoặc giải thích bằng quyết định review.
- Resolver có thể đề xuất và chứng minh dữ liệu, nhưng không tự ghi reviewer hay tự biến quyết định pháp lý thành `APPROVED`.

### 2.4 Cấu trúc và provenance

- Article/Clause/Point có identity ổn định và source span hợp lệ.
- Page/line/character/segment provenance nhất quán với loại tài liệu.
- Quarantine ambiguity và short provision có quyết định review cho từng record; không được xóa warning chỉ để qua gate.
- Mọi exclusion đều có reason, reviewer, thời gian và evidence.

### 2.5 Temporal và legal relations

- Tất cả `LegalChange` thuộc phạm vi bắt buộc có quyết định review.
- Không còn effective interval thiếu, đảo ngày hoặc chồng lấn trái quy tắc.
- Mỗi provision version cần kiểm duyệt có status, reviewer, `reviewed_at` và evidence.
- `AMENDS`, `REPEALS`, `REPLACES`, `IMPLEMENTS` ở mức document/provision phải có target và scope xác định; quan hệ không chắc chắn phải ở review queue.

### 2.6 Derived knowledge

- Diagnostic items và derived relations truy ngược được về provision/source span.
- Record suy diễn không được gắn nhãn như fact đã xác minh.
- Không còn derived record bắt buộc nhưng thiếu exact evidence.

### 2.7 Gold và evaluation

- Gold set có các nhóm truy vấn mà kiến trúc yêu cầu, gồm temporal và multi-hop nếu được bật trong config.
- Mỗi Gold record dùng để tính gate phải ở trạng thái `APPROVED`, có reviewer, ngày duyệt và nguồn Gold.
- Gold build khớp corpus/build được đánh giá.
- Tất cả metric/threshold bắt buộc đạt; báo cáo phải công bố mẫu số, số query hợp lệ và failure cases.
- Không được tự tạo nhãn Gold hoặc reviewer để làm gate pass.

### 2.8 Kaggle và Aura

- Fresh Kaggle run hoàn tất, không dựa vào output cũ.
- Artifact tải về vượt qua local strict audit.
- Aura load hoàn tất và live audit chứng minh cùng graph build.
- `offline_ready_for_online=true` chỉ được ghi khi mọi điều kiện trên đạt.

## 3. Machine-readable completion artifact

Phải sinh `artifacts/reports/offline_completion_contract.json` với tối thiểu cấu trúc sau:

```json
{
  "schema_version": 1,
  "status": "COMPLETE",
  "offline_ready_for_online": true,
  "build_id": "...",
  "gold_build_id": "...",
  "same_build_verified": true,
  "technical": {
    "registry": "PASS",
    "structure": "PASS",
    "graph": "PASS",
    "dense": "PASS",
    "bm25": "PASS",
    "neo4j": "PASS",
    "error_count": 0
  },
  "source_catalog": {
    "corpus_records": 95,
    "review_decisions": 95,
    "authoritative_unverified": 0,
    "unresolved_sha_mismatches": 0
  },
  "temporal": {
    "pending_legal_changes": 0,
    "unreviewed_provision_versions": 0,
    "invalid_or_overlapping_intervals": 0
  },
  "provenance": {
    "missing_required_spans": 0,
    "pending_quarantine_decisions": 0,
    "derived_records_missing_evidence": 0
  },
  "gold": {
    "approved_records": 0,
    "required_query_groups_present": true,
    "all_required_metrics_pass": true
  },
  "artifacts": {},
  "remaining_actions": []
}
```

`approved_records` phải là số đo thực tế và phải đạt threshold trong config; số `0` ở ví dụ không phải giá trị PASS.

## 4. Strict final audit

Phải có lệnh tương đương:

```powershell
python scripts/audit_offline_completion.py --strict
```

Lệnh chỉ trả exit code `0` khi `status=COMPLETE`, `offline_ready_for_online=true` và tất cả gate bắt buộc đạt. Mọi trạng thái chờ hoặc lỗi phải trả nonzero và ghi machine-readable reason.

## 5. Ranh giới kiểm duyệt

Automation được phép thu thập, chuẩn hóa, so khớp SHA/nội dung, phát hiện mâu thuẫn, xếp hàng review và tạo diff. Automation không được giả mạo:

- tên reviewer;
- quyết định thẩm quyền/đúng nguồn;
- scope sửa đổi hoặc khoảng hiệu lực còn mơ hồ;
- Gold label/qrel;
- quyết định loại bỏ nội dung pháp lý.

Khi thiếu các quyết định này, trạng thái đúng là `WAITING_FOR_HUMAN_REVIEW`. Sau khi nhận file review hợp lệ, vòng lặp phải tiếp tục từ checkpoint tương ứng đến khi đạt `COMPLETE`.

`WAITING_FOR_HUMAN_REVIEW` chỉ hợp lệ khi mọi gate tự động bắt buộc đã đạt, review package đã qua schema/hash validator và không còn lỗi code, retryable request hoặc candidate bắt buộc ở trạng thái chờ.
