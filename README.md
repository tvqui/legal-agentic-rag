# VN Labor Legal GraphRAG

Hệ thống xây dựng và truy vấn tri thức pháp luật lao động Việt Nam theo một repository thống nhất:

- **OFFLINE** xử lý tài liệu, metadata, cấu trúc Điều/Khoản/Điểm, quan hệ pháp lý, graph, Dense và BM25.
- **ONLINE** phân tích câu hỏi, truy hồi lai, kiểm tra hiệu lực/applicability và tạo câu trả lời có dẫn nguồn.
- **Frontend** cung cấp giao diện React/Vite cho API ONLINE.

## Cấu trúc

```text
frontend/          Giao diện React/Vite
src/               Mã nguồn Python OFFLINE và ONLINE
config/            Cấu hình pipeline, nguồn, review và runtime
scripts/           Công cụ vận hành, audit, benchmark và đóng gói
tests/             Test OFFLINE và ONLINE
docs/              Kiến trúc, runbook, review và tài liệu lịch sử
review/            Template và hồ sơ human review cục bộ
kaggle/            Bootstrap/runner chạy pipeline trên Kaggle
data/              Corpus nguồn cục bộ (không commit)
artifacts/         Đầu ra pipeline và indexes (không commit)
build/             Gói Kaggle/review sinh tự động (không commit)
```

## Bắt đầu nhanh trên Windows

```bat
run.bat setup-full
run.bat test
run.bat online-check
run.bat online
```

Đặt ZIP OFFLINE ngày 14/10/2026 tại `build/releases/vn_labor_results_20261014.zip` trước khi chạy. Các cấu hình ONLINE chính đã ghim SHA-256, graph build và fingerprints của bản này; không đổi đường dẫn sang một ZIP khác mà giữ các mã kiểm tra cũ. Gói này đạt kiểm tra kỹ thuật, vẫn cần duyệt pháp lý.

Lệnh `online` và `online-check` chọn cấu hình theo thứ tự: `-Config` → `VN_LABOR_ONLINE_CONFIG` trong môi trường/`.env` → `config/online.yaml`. `online-check` in cấu hình, artifact và chế độ provider thực tế. Biến môi trường có thể ghi đè các trường trong YAML.

Mở terminal thứ hai:

```bat
run.bat frontend
```

Giao diện thường chạy tại `http://127.0.0.1:5173`, API tại `http://127.0.0.1:8000` và Swagger tại `http://127.0.0.1:8000/docs`.

Xem toàn bộ lệnh:

```bat
run.bat help
```

## Các luồng chính

```bat
run.bat offline
run.bat dense
run.bat neo4j
run.bat load-neo4j
run.bat validate
run.bat kaggle
```

YAML ONLINE local mặc định dùng adjudication deterministic; `.env` có thể chọn HTTP/Ollama thay thế. Sau khi cài Ollama và tải `qwen3:8b`, có thể thử cấu hình LLM có kiểm soát:

```bat
run.bat online-ollama
```

Applicability vẫn chạy deterministic và mọi câu trả lời vẫn phải qua Reference Audit.

## Tài liệu

- [Mục lục](docs/README.md)
- [Kiến trúc tổng thể](docs/architecture.md)
- [OFFLINE](docs/offline.md)
- [ONLINE](docs/online.md)
- [Đối chiếu đánh giá và nâng cấp ONLINE 15/10](docs/online/review-followup-20261015.md)
- [Vận hành](docs/operations.md)
- [Human review](docs/human-review.md)
- [Kaggle](docs/kaggle.md)
- [Kế hoạch hoàn thiện và phát hành](docs/project-completion.md)

## Đánh giá chất lượng ONLINE

```bat
python scripts/evaluate_gold_set.py --config config/online.yaml --gold path\to\gold_queries.jsonl
```

Chỉ kết quả có `status=OFFICIAL` mới được dùng để báo cáo chất lượng. Trạng thái này yêu cầu Gold đã được người có chuyên môn duyệt và khớp chính xác build ID.

## Trạng thái dữ liệu

Build kỹ thuật hiện tại đã đồng bộ registry, structure, graph, Dense, BM25 và Neo4j. ONLINE vẫn phải giữ chế độ provisional cho đến khi source catalog, temporal metadata cấp provision và Gold set được người có chuyên môn duyệt hoàn tất.
