# Completion and release runbook

## Kiểm tra nhanh

```bat
run.bat test
run.bat online-check
```

```bat
cd frontend
npm run lint
npm run build
```

## Gold evaluation

Chỉ chạy với file Gold trả về từ reviewer và khớp build:

```bat
python scripts/evaluate_gold_set.py --config config/online.yaml --gold path\to\gold_queries.jsonl
```

Kết quả nằm ở `artifacts/online_evaluation/gold_evaluation.json` và `.md`. Trạng thái `PROVISIONAL_DRAFT_GOLD` không được dùng làm số liệu chính thức.

## OFFLINE rebuild bắt buộc

Sau thay đổi parser hoặc source resolver, chạy lại OFFLINE, Dense, BM25, validation và Aura. Sau đó pin ZIP/build ID mới vào cấu hình ONLINE. Không trộn provisions của build mới với graph/index của V8.1.

## Smoke ONLINE bắt buộc

- Tra cứu trực tiếp một Điều cụ thể.
- Nghỉ phép 12/14/16 ngày.
- Nghỉ việc không xác định thời hạn: nhánh công việc thường, công việc đặc thù và chưa rõ công việc.
- Câu hỏi thiếu dữ kiện phải trả `NEED_MORE_FACTS`.
- Câu hỏi hình sự/đất đai rõ ràng phải trả `ABSTAIN`.
- Citation giả hoặc URL ngoài evidence phải làm Reference Audit fail closed.
