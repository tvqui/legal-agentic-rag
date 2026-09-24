# Chạy pipeline trên Kaggle

Kaggle dùng để chạy OFFLINE bằng GPU/CPU/RAM từ xa. Notebook và Dataset phải để **Private**.
Build kỹ thuật V8.1 hiện đã PASS; chỉ chạy lại khi code, config, corpus hoặc quyết định review
được thay đổi.

## Chuẩn bị trên máy local

Tạo lại bundle từ code hiện tại:

```powershell
.\.venv\Scripts\python.exe scripts\package_kaggle.py
```

Sau khi lệnh chạy xong, chỉ dùng ba đầu ra hiện hành trong `build/kaggle/`:

- `vn_labor_kaggle_v8.zip`: Dataset Private chứa code/config/corpus;
- `VN_Labor_Kaggle_V8.ipynb`: Notebook để import;
- `package_report.json`: SHA-256 và kết quả kiểm ZIP.

Nếu chạy nối tiếp, tạo Dataset Private thứ hai từ ZIP checkpoint mới nhất có thư mục
`artifacts/`. Không gắn đồng thời nhiều checkpoint vì Notebook sẽ từ chối khi tìm thấy nhiều
nguồn khôi phục.

## Chạy build OFFLINE

1. Vào Kaggle bằng tài khoản của bạn, chọn **Code → New Notebook**.
2. Chọn **File → Import Notebook** và tải `VN_Labor_Kaggle_V8.ipynb`.
3. Trong **Input → Add Input**, gắn Dataset code/corpus và đúng một Dataset checkpoint.
4. Trong **Settings**, bật Internet và chọn GPU T4 x2.
5. Giữ cấu hình:

```python
RUN_PIPELINE = True
LOAD_AURA = False
RESTORE_ARCHIVE = "AUTO"
```

6. Chọn **Save Version → Save & Run All** và chờ hoàn tất.
7. Tải `vn_labor_results.zip` từ Output. Kiểm tra `final_outputs_validation.json`,
   `dense_validation.json`, `validation_issues.jsonl` và `tong_hop_sau_chay.md`.

## Nạp Neo4j Aura mà không build lại

Gắn ZIP kết quả vừa kiểm tra làm checkpoint duy nhất, sau đó đặt:

```python
RUN_PIPELINE = False
LOAD_AURA = True
RESTORE_ARCHIVE = "AUTO"
```

Trong **Add-ons → Secrets**, cấp cho Notebook bốn secret:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

Chạy **Save Version → Save & Run All**. Cách này chỉ khôi phục artifacts, nạp Aura và audit;
không chạy lại OCR, Dense hay BM25. Kết quả hợp lệ phải có `neo4j_validation.json` cùng
build ID với graph/indexes.

## Quy tắc an toàn dữ liệu

- Không đưa secret vào cell hoặc ZIP.
- Không tự đổi `UNVERIFIED` thành `VERIFIED`.
- Không trộn code bundle, checkpoint và Gold của các build khác nhau.
- Nếu chỉ làm human review, không cần chạy lại Kaggle.
- Sau khi merge review, rebuild các stage phụ thuộc rồi cập nhật fingerprint ONLINE.

Các bước review tiếp theo nằm tại [review_next_steps.md](../offline/review_next_steps.md).
