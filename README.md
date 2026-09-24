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

ONLINE mặc định dùng adjudication deterministic. Sau khi cài Ollama và tải `qwen3:8b`, có thể thử cấu hình LLM có kiểm soát:

```bat
run.bat online-ollama
```

Applicability vẫn chạy deterministic và mọi câu trả lời vẫn phải qua Reference Audit.

## Tài liệu

- [Mục lục](docs/README.md)
- [Kiến trúc tổng thể](docs/architecture.md)
- [OFFLINE](docs/offline.md)
- [ONLINE](docs/online.md)
- [Vận hành](docs/operations.md)
- [Human review](docs/human-review.md)
- [Kaggle](docs/kaggle.md)

## Trạng thái dữ liệu

Build kỹ thuật hiện tại đã đồng bộ registry, structure, graph, Dense, BM25 và Neo4j. ONLINE vẫn phải giữ chế độ provisional cho đến khi source catalog, temporal metadata cấp provision và Gold set được người có chuyên môn duyệt hoàn tất.
