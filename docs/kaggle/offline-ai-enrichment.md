# Chạy OFFLINE hoàn chỉnh trên Kaggle trong khi tiếp tục kiểm thử ONLINE

Quy trình này dành cho repository hiện tại. Nó dùng extraction cache trong checkpoint V8.1 để tránh OCR lại,
nhưng dựng lại toàn bộ phần phụ thuộc bằng code mới:

`Document Registry → Structured Provisions → Knowledge/Version Graph → Dense + BM25 → Aura`

ONLINE trên máy local vẫn có thể tiếp tục dùng `vn_labor_results_v8.1(aura).zip` trong lúc Kaggle chạy.
Chỉ thay artifact ONLINE sau khi ZIP mới đã hoàn tất và vượt kiểm tra.

## Thiết kế chống mất một phiên chạy dài

Notebook mới chạy theo các mốc sau:

1. Xác minh SHA của package và đối chiếu file ID giữa corpus với extraction checkpoint.
2. Chấp nhận môi trường Kaggle Python 3.12 hoặc 3.13 và ghim Torch theo container hiện tại.
3. Dựng lại toàn bộ artifact từ extracted text bằng parser/code hiện tại, gồm Dense và BM25.
4. Audit toàn bộ đầu ra local.
5. Xuất `vn_labor_results_technical_checkpoint.zip` **trước khi chạy AI**.
6. Chạy Qwen3-8B ở chế độ `hybrid_ai`, mặc định tối đa 250 provision; mỗi kết quả hợp lệ được ghi cache nguyên tử.
7. Nạp graph cuối vào Aura, kiểm build ID và audit bốn đầu ra.
8. Xuất `vn_labor_results.zip`.

Nếu AI hoặc phiên Kaggle lỗi sau bước 4, bản technical checkpoint vẫn còn. Notebook cũng cố tạo
`vn_labor_results_recovery.zip`, chứa cache AI đã hoàn thành để phiên sau tiếp tục.

Không chương trình nào có thể bảo đảm 100% trước lỗi hạ tầng Kaggle, mất Internet hoặc Aura tạm ngừng.
Quy trình trên bảo đảm fail-closed, không báo PASS giả, và giảm phần công việc bị mất khi có lỗi ngoài code.

## Hai file cần upload

1. `build/kaggle/vn_labor_kaggle_v8.zip` — package mới vừa tạo từ repository hiện tại.
2. `vn_labor_results_v8.1(aura).zip` — checkpoint cũ đã PASS kỹ thuật.

Tạo hoặc cập nhật hai **Private Dataset** riêng trên Kaggle. Không upload `.env`, mật khẩu Aura,
virtual environment, model cache hoặc token.

Sau khi cập nhật Dataset code, vào trang Dataset và kiểm tra timestamp/version mới. Xóa Input code cũ khỏi
Notebook rồi Add Input lại nếu Kaggle vẫn ghim phiên bản Dataset cũ.

## Bốn Kaggle Secrets bắt buộc

Trong Notebook, mở **Add-ons → Secrets** và cấp quyền cho:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

`NEO4J_USER` thường là `neo4j`. `NEO4J_DATABASE` phải là database ID thật trong credentials Aura,
không tự điền chữ `neo4j` nếu instance của bạn dùng ID khác.

## Tạo và chạy Notebook

1. Import `build/kaggle/VN_Labor_Kaggle_V8.ipynb` vào Kaggle.
2. Add Input đúng hai Private Dataset nói trên.
3. Mở **Settings**:
   - Accelerator: **GPU T4 x2**.
   - Internet: **On**.
   - Notebook: **Private**.
4. Không gắn thêm checkpoint OFFLINE thứ hai; chế độ `AUTO` yêu cầu đúng một checkpoint.
5. Chọn **Save Version → Save & Run All**.

Không cần chạy từng cell. Không bấm Stop Session trong khi version đang chạy.

## Cấu hình mặc định đã chọn

```python
RESTORE_ARCHIVE = "AUTO"
RUN_AI_ENRICHMENT = True
OFFLINE_AI_MODEL = "qwen3:8b"
OFFLINE_AI_MAX_PROVISIONS = 250
LOAD_AURA = True
TOTAL_SECONDS = 10 * 60 * 60
```

250 là giới hạn số provision được AI tinh chỉnh trong phiên đầu, không phải giới hạn dữ liệu pháp luật.
Toàn bộ provision vẫn được parse, đưa vào graph, Dense/BM25 và có checklist heuristic khi phù hợp.
Giới hạn này tránh lặp lại lần chạy 2.000 provision đã vượt 8 giờ.

Nếu ưu tiên chắc chắn hoàn tất technical build hơn AI, đổi duy nhất:

```python
RUN_AI_ENRICHMENT = False
```

Bản này vẫn là OFFLINE technical build đầy đủ; nó chỉ không có lớp tinh chỉnh checklist/case ontology bằng Qwen.

## Thời gian dự kiến

Thời gian phụ thuộc Kaggle và tốc độ model:

- Chuẩn bị môi trường + BGE-M3: khoảng 10–40 phút.
- Rebuild structure/graph/Dense/BM25 từ extraction cache: khoảng 30 phút–3 giờ.
- Qwen3-8B cho 250 provision và case ontology: thường khoảng 1–6 giờ.
- Aura + audit + nén ZIP: khoảng 10–60 phút.

Mục tiêu là hoàn tất trong 10 giờ. Đây là ước lượng, không phải cam kết thời gian của Kaggle.

## Kiểm tra khi chạy nền

Trong trang Version đang chạy, mở **Logs**. Heartbeat khoảng mỗi phút có dạng:

```text
HEARTBEAT elapsed=... stage=... progress=.../... ai=.../... cache=... idle=... gpu=[...]
```

Các stage hợp lệ:

- `technical_rebuild`
- `technical_checkpoint`
- `ai_enrichment`, `case_ontology`, `checklists`
- `ai_complete`
- `aura_load`
- `complete`

Log pip có dòng `dependency resolver ... conflicts` về package có sẵn của Kaggle không tự động là lỗi.
Chỉ kết luận lỗi khi cell/runner có traceback hoặc exit code khác 0.

Notebook tự dừng AI nếu không tăng tiến độ 20 phút, và tự dừng toàn quy trình sau 10 giờ để tránh giữ GPU vô hạn.

## File cần tải sau khi chạy

Trong tab **Output**:

- `vn_labor_results.zip`: kết quả cuối, chỉ xuất sau quy trình hoàn tất.
- `vn_labor_results_technical_checkpoint.zip`: bản kỹ thuật được lưu trước AI.
- `vn_labor_results_recovery.zip`: chỉ xuất khi có lỗi hoặc timeout; dùng để tiếp tục.
- `offline_final_build.log`: log đầy đủ nếu cần chẩn đoán.

Ưu tiên tải `vn_labor_results.zip`. Đổi tên local thành một tên version rõ ràng, ví dụ
`vn_labor_results_v9_final_aura.zip`, nhưng không sửa nội dung ZIP.

## Dấu hiệu thành công

Mở `artifacts/reports/offline_final_run.json` trong ZIP. Kết quả cuối phải có:

```json
{
  "status": "PASS",
  "stage": "complete"
}
```

Đồng thời:

- `final_outputs_validation.json.ready_for_offline_v1 = true`
- registry, structure, graph, indexes đều PASS
- `neo4j_validation.json.passed = true`
- build ID local và Aura giống nhau
- `kaggle_run.json.pipeline_exit_code = 0`

`offline_ready_for_online` có thể vẫn là `false` vì human legal review/Gold chưa xong. Đây không phải lỗi kỹ thuật.
ONLINE vẫn dùng provisional mode và phải giữ cảnh báo cho người dùng.

## Nếu phiên chạy lỗi hoặc hết giờ

1. Tải `vn_labor_results_recovery.zip` nếu có.
2. Nếu recovery không có, tải `vn_labor_results_technical_checkpoint.zip`.
3. Tạo Private Dataset checkpoint mới từ ZIP đó.
4. Ở Notebook phiên sau, thay Input checkpoint V8.1 bằng checkpoint mới; vẫn chỉ gắn một checkpoint.
5. Save Version → Save & Run All lại.

Cache AI nằm trong `artifacts/04_knowledge/ai_cache`. Những prompt/model/source đã hoàn thành sẽ được dùng lại.
Sau khi phiên 250 hoàn tất, có thể tăng `OFFLINE_AI_MAX_PROVISIONS` lên 500; 250 mục đầu sẽ đọc cache và
AI chỉ cần xử lý phần mới. Chỉ tăng theo từng nấc khi còn quota.

## Trong lúc Kaggle chạy

Giữ backend/frontend local dùng artifact V8.1 hiện tại và tiếp tục:

1. chạy bộ test ONLINE;
2. kiểm tra các câu hỏi Gold/edge case;
3. sửa query analysis, applicability, evidence coverage, generation và citation;
4. không đổi schema artifact OFFLINE nếu không thật sự cần.

Khi ZIP mới PASS, pin artifact mới vào ONLINE, chạy lại regression/evaluation rồi mới thay build đang dùng.
