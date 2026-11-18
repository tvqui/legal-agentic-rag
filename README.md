# Pháp Điển AI — LegalGraphRAG cho pháp luật lao động Việt Nam

Dự án gồm pipeline xây dựng dữ liệu **OFFLINE**, Backend hỏi đáp có căn cứ **ONLINE**, giao diện web và bộ đánh giá. Hệ thống kết hợp BM25, Dense BGE-M3/FAISS, đồ thị pháp lý và các vai trò Researcher, Auditor, Adjudicator; câu trả lời được kiểm tra nội dung và trích dẫn theo cấu hình.

## Đọc và chạy từ đâu?

| Nhu cầu | Điểm bắt đầu |
|---|---|
| Hiểu kiến trúc và giới hạn | [Kiến trúc](docs/architecture.md) |
| Chạy Backend và giao diện | [ONLINE](docs/online.md), [Frontend](frontend/README.md) |
| Xây dữ liệu từ đầu | [OFFLINE](docs/offline.md) |
| Hiểu gói artifact và báo cáo | [Cấu trúc đầu ra OFFLINE](docs/offline/artifact-layout.md) |
| Chạy trên Kaggle | [Kaggle](docs/kaggle.md), [Notebook Backend](kaggle/ONLINE_Backend.ipynb) |
| Đo và so sánh hệ thống | [Bộ đo](đo/README.md), [Ablation](đo/ABLATION_GUIDE.md), [Graph QA](benchmarks/graph_qa/README.md) |
| Xem số liệu đã lưu | [Bảng kết quả và phạm vi so sánh](đo/results_summary/README.md) |
| Kiểm tra trước khi nộp | [Kiểm chứng bản bàn giao](docs/project-completion.md) |

## Tổ chức repository

```text
src/          Mã OFFLINE và ONLINE
frontend/     Giao diện React/Vite
config/       Cấu hình và danh mục nguồn
scripts/      Lệnh vận hành, kiểm tra, đóng gói
kaggle/       Notebook và mã chạy từ xa
đo/           Bộ đo thống nhất, notebook và bảng kết quả nhỏ
benchmarks/   Các module đo chuyên biệt được bộ đo tái sử dụng
gold_dataset/ Bộ Gold và hồ sơ nhãn (không mặc định đã duyệt)
tests/        Kiểm thử hồi quy
docs/        Tài liệu kiến trúc, chạy và đánh giá
review/       Template và bản sửa nguồn cần để dựng lại dữ liệu
tools/        Coding Team tùy chọn; không thuộc luồng hỏi đáp
```

`đo/` là điểm vào khi thực nghiệm; `benchmarks/` giữ các module đang được mã đo, notebook và test tham chiếu. Không di chuyển hai thư mục này chỉ để đổi hình thức trình bày.

## Chạy nhanh trên Windows

Cần Python 3.12 hoặc 3.13, Node.js tương thích với frontend, một artifact đã xây dựng và các dịch vụ/model được cấu hình cho chế độ muốn chạy.

```bat
run.bat setup-full
```

Git **không chứa** corpus PDF, trọng số model, môi trường cài sẵn hoặc các ZIP artifact lớn. Xem [dữ liệu đầu vào](data/README.md) và [cách nạp artifact](docs/online.md). Khi dùng một artifact khác với bản ghim trong YAML, tạo cấu hình ghim mới; không bỏ kiểm fingerprint.

Sau khi cấu hình artifact và dịch vụ:

```bat
run.bat online-check
run.bat online
```

Trong terminal khác:

```bat
run.bat frontend
```

Frontend thường ở `http://localhost:5173`, API ở `http://127.0.0.1:8000`, tài liệu API ở `/docs`. `.env` có thể ghi đè cấu hình YAML; chỉ dùng `.env.example` làm mẫu, không đưa khóa vào Git.

## Xây dựng và kiểm thử

```bat
run.bat offline
run.bat load-neo4j
run.bat validate
run.bat test
```

OFFLINE tạo `vn_labor_online.zip` để chạy Backend và `vn_labor_offline_review.zip` để xem báo cáo, dữ liệu trung gian. Quy trình đầy đủ và điều kiện đóng gói được mô tả trong [artifact-layout.md](docs/offline/artifact-layout.md).

Frontend:

```powershell
cd frontend
npm ci
npm test
npm run lint
npm run build
```

Xem `run.bat help` để biết toàn bộ lệnh. Kiểm thử local dùng fixture/mock ở những bước cần dịch vụ ngoài; test PASS không có nghĩa toàn bộ câu trả lời đã được kiểm duyệt pháp lý.

## Phạm vi khoa học và giới hạn

- Khả năng trả lời phụ thuộc phạm vi, chất lượng nguồn, phiên bản và ngày chốt của artifact được nạp.
- Ngày hỏi, điều kiện áp dụng và ngoại lệ phải được kiểm tra; thiếu dữ kiện thì hỏi bổ sung, thiếu căn cứ thì giới hạn hoặc từ chối kết luận.
- Gold và điểm AI phải được công bố đúng trạng thái. Không gộp retrieval, QA và dự đoán bản án thành một độ chính xác chung.
- Chỉ đối chiếu các lần đo tương đương về dữ liệu, code, model và điều kiện. Các kết quả lưu hiện tại gồm những lần khác phiên bản; không tự suy ra đóng góp nhân quả từ chúng.
- Thông tin nguồn/hiệu lực chưa được duyệt vẫn phải được công bố; hệ thống không cam kết bao phủ mọi câu hỏi pháp luật.

## Dữ liệu và công cụ phát triển cục bộ

`data/`, `artifacts/`, `build/`, `.cache/`, `.venv/`, `node_modules/`, `.env` và các lần chạy được Git-ignore. Chúng có thể tồn tại trên máy để tiếp tục làm việc nhưng không thuộc bản mã nguồn nộp Git.

Tài liệu lịch sử, ZIP kết quả và bundle cũ được bảo quản ngoài repository. Bản Git giữ tài liệu hiện hành, mã đo và bảng tổng hợp nhỏ có truy vết. [Coding Team](tools/coding_team/README.md) là tiện ích tùy chọn; [AGENTS.md](AGENTS.md) chỉ hướng dẫn công cụ phát triển, không phải phần của mô hình pháp lý.
