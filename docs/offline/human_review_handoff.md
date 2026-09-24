# Bàn giao cho người duyệt chuyên môn — OFFLINE V8.1

## Mục tiêu

Xác minh nguồn, quan hệ sửa đổi/bãi bỏ, các provision bị quarantine,
khoảng hiệu lực và bộ Gold retrieval. Công việc này là duyệt pháp lý;
không phải chỉ kiểm tra file có mở được hay không.

## File cần gửi

1. `source_review_handoff_v8_1_full.zip`: 95 file corpus gốc, manifest và CSV theo dõi.
2. `source_review_handoff_v8_1_full.zip.sha256`.
3. `offline_human_review_7b33c8206124e32d423ddfc02adbf58ad26cce68e8ac0154329d51b5dd667d38.zip`:
   case review, resolver evidence, provision/retrieval/graph reference, manifest và hướng dẫn.
4. File `.zip.sha256` tương ứng của gói thứ hai.
5. File hướng dẫn này.

Hai ZIP là dữ liệu nội bộ. Không upload công khai. Sau khi nhận, tính SHA-256
và so sánh với sidecar trước khi duyệt.

## Nguyên tắc bắt buộc

- Kiểm nội dung file gốc, URL/nhà cung cấp và evidence; không duyệt chỉ theo tên file.
- `AUTO_EXACT_SHA` là bằng chứng exact bytes, không thay thế quyết định của reviewer.
- `candidate_unit_ids` trong Gold chỉ là gợi ý. Reviewer phải tự chọn `gold_unit_ids`.
- Không dùng tên reviewer giả, ngày ước lượng, evidence chung chung hoặc approve hàng loạt.
- Giữ nguyên ID, SHA, build ID và số dòng. Chỉ sửa các trường review/decision
  và các kết luận pháp lý được chỉ định.
- Nếu chưa đủ bằng chứng, giữ `DRAFT` hoặc ghi `NEEDS_MORE_EVIDENCE`;
  không ép `APPROVED` để qua gate.

## Năm nhóm công việc

### 1. Source review — 95 record

Làm trên `source_review_tracking_seed.csv` và đối chiếu `source_review_cases.jsonl`,
resolver evidence, cùng file trong thư mục `corpus/` của gói full.

Với mỗi dòng, xác minh:

- Đúng văn bản/số/ký hiệu/phiên bản.
- Nguồn có thẩm quyền và URL đúng identity/binary.
- SHA file tải được có khớp corpus hay không.

Khi kết luận, điền `source_provider`, `downloaded_sha256`, `sha_match`,
`legal_decision`, `legal_reviewer`, `legal_reviewed_at`, `legal_review_notes`.
`legal_decision` chỉ là `APPROVED`, `REJECTED`, hoặc `NEEDS_MORE_EVIDENCE`.
Nếu `sha_match=NO`, phải giải thích khác biệt; trường hợp này chưa được xem là đóng.

### 2. Legal changes — 25 case

Làm trên `legal_change_review_cases.jsonl`. Kiểm evidence span trong văn bản gốc,
operation, văn bản/điều/khoản/điểm đích và ngày có hiệu lực.

Case `APPROVED` phải có `target_provision_identity_id`, `effective_from`, `reviewer`,
`reviewed_at`, `review_evidence`. Nếu loại, dùng `EXCLUDED` và ghi `exclusion_reason`.

### 3. Quarantine — 36 case/837 member

Làm trên `quarantine_review_cases.jsonl`; xem toàn bộ dòng tương ứng trong
`quarantine_review_members.jsonl`. Quyết định cấu trúc/canonical path đúng,
hoặc loại đoạn không phải provision.

Mỗi case cuối phải có `review_status`, `decision`, `reviewer`, `reviewed_at`,
`review_evidence`; `EXCLUDED` phải có `exclusion_reason`.

### 4. Temporal — 61 case/18.449 provision version

Làm trên `temporal_review_cases.jsonl`; tra thành viên trong `temporal_review_members.jsonl`
và nội dung trong `provisions_reference.jsonl`/`retrieval_units_reference.jsonl`.
Xác minh `valid_from`, `valid_to`, thay đổi từ legal-change nào, khoảng thời gian
có chồng lấn/thiếu hay không, và mốc `temporal_coverage_as_of`.

Case cuối phải có reviewer/date/evidence và quyết định. Nếu chỉ một số member
sai, liệt kê chính xác `provision_version_id` và giá trị cần sửa trong `review_note`.

### 5. Gold retrieval — 17 candidate/9 query type

Làm trên `gold_query_candidates.jsonl`, tra toàn bộ unit trong
`retrieval_units_reference.jsonl` và quan hệ trong `graph_edges_reference.jsonl`.

- Sửa câu hỏi nếu câu sinh tự động mơ hồ.
- Chọn tất cả qrel đúng vào `gold_unit_ids`.
- Temporal/amendment query phải có `query_date`.
- `INSUFFICIENT_FACTS` phải có `expected_no_answer=true`.
- Khi approve, điền `reviewer`, `reviewed_at`, `gold_source`, giữ đúng `build_id`.
- Duyệt `quality_thresholds_draft.json`; chỉ đổi thành `APPROVED` sau khi
  reviewer chấp nhận k, recall threshold, coverage và số query tối thiểu.

## Kết quả phải trả lại

Tạo một ZIP giữ UTF-8 và nguyên tên sau:

- `source_review_tracking_completed.csv`
- `legal_change_review_cases.jsonl`
- `quarantine_review_cases.jsonl`
- `temporal_review_cases.jsonl`
- `gold_queries.jsonl`
- `quality_thresholds.json`
- `REVIEWER_REPORT.md`

`REVIEWER_REPORT.md` ghi họ tên/vai trò reviewer, ngày duyệt, phạm vi, các record
còn `DRAFT`/`NEEDS_MORE_EVIDENCE`, các thay đổi đề xuất cho corpus/parser và tuyên bố
rằng reviewer đã đối chiếu evidence.

Tính SHA-256 của ZIP trả lại và gửi kèm file `.sha256`.

## Tiêu chí đầu ra đạt

- Đủ 95 source decisions; không cò SHA mismatch chưa giải quyết.
- Đủ 25 legal-change decisions.
- Đủ 36 quarantine decisions, phủ đủ 837 member.
- Đủ 61 temporal decisions, phủ đủ 18.449 provision version.
- Gold bao phủ đủ 9 query type, qrels tồn tại trong build hiện tại, thresholds được duyệt.
- Mọi record cuối cùng có reviewer thật, ngày ISO `YYYY-MM-DD` và evidence cụ thể.
- Không đổi ID/SHA/build ID; không xóa record để làm giảm số lỗi.

Việc reviewer hoàn thành các file trên chưa tự động có nghĩa OFFLINE `COMPLETE`.
Sau khi nhận kết quả, nhóm kỹ thuật phải validate, merge dry-run, rebuild pipeline,
nạp lại Aura và chạy Gold/completion audit trên cùng build mới.
