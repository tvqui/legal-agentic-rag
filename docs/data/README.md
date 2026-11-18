# Tổ chức dữ liệu để nghiên cứu và bảo trì

Bản vận hành và bản nghiên cứu dùng chung dữ liệu gốc nhưng có mục đích khác nhau. Backend tiếp tục nạp artifact đã ghim; công cụ `scripts/organize_research_data.py` tạo một thư mục mới để đọc, đối chiếu và nghiên cứu theo từng lớp. Không di chuyển thư mục cũ, không đổi ID, không thay chỉ mục và không đổi cấu hình ONLINE.

## Đọc dữ liệu từ đâu?

| Thư mục trong bản nghiên cứu | Câu hỏi mà thư mục giúp trả lời | Nội dung |
|---|---|---|
| `00_catalog/` | Đây là dữ liệu phiên bản nào? Có bao nhiêu bản ghi? | Manifest, hash đầu vào/đầu ra và kiểm kê tệp artifact |
| `01_sources/` | Quy định xuất phát từ nguồn nào? | Bản sao danh mục nguồn nếu có và vị trí các tệp gốc trong artifact; không sao chép PDF |
| `02_graph/rule/` | Văn bản, Điều, Khoản, Điểm và phiên bản nằm ở đâu? | Node quy định và cạnh nội tầng, nguyên bản |
| `02_graph/ontology/` | Hệ thống có những khái niệm/chủ đề nào? | LegalIssue, LegalConcept và cạnh nội tầng |
| `02_graph/fact/` | Có những hồ sơ và đặc trưng vụ án nào? | Bản án, án lệ, đặc trưng, cộng đồng vụ án; không tự xác nhận đặc trưng là sự thật của tòa |
| `02_graph/derived/` | Thông tin nào được tạo thêm phục vụ xử lý? | DiagnosticItem và các loại node chưa có phân nhóm; giữ nguyên để không mất dữ liệu |
| `02_graph/cross_layer/` | Các tầng nối với nhau thế nào? | Toàn bộ cạnh có hai đầu ở hai nhóm khác nhau |
| `03_retrieval/` | BM25/Dense tìm trên những đơn vị nào? | Bản sao retrieval_units nguyên vẹn; index BM25/FAISS được tham chiếu qua kiểm kê, không dựng lại |
| `04_peer_ontology/` | Bộ của thành viên khác bổ sung gì? | Định nghĩa có đối chiếu nguyên văn, ánh xạ ID, quan hệ phân loại từ nguồn và báo cáo các mục không đạt |

Đây là **các góc nhìn tách từ đồ thị hiện tại**, không thay đổi kiến trúc LegalGraphRAG ba tầng. `derived` và `cross_layer` là nơi lưu giúp phân biệt nguồn gốc và tránh lặp cạnh, không phải agent hay tầng suy luận mới. Muốn dựng lại graph, hợp các node của bốn nhóm và hợp cạnh nội nhóm với `cross_layer/edges.jsonl`. Không đổi chiều `PART_OF`. Không tự chuyển `CONTAINS` của nguồn khác thành cạnh tương đương nếu chưa xác định đầu mút và cấp phân loại.

## Phần tái sử dụng từ LegalGarph

- Tiếp thu cách chia rõ Rule/Ontology/Fact, kèm manifest, thông tin nguồn và báo cáo.
- Ánh xạ Provision về `source_record_id` hiện có, tránh nhân đôi quy định đã có.
- Nhập định nghĩa ở chế độ **bổ sung nghiên cứu, mặc định không bật ONLINE**. Kiểm tra node nguồn, quan hệ `REGULATED_BY`, span, SHA-256 đoạn trích, định nghĩa bằng đoạn trích và đoạn trích xuất hiện nguyên văn trong `source_text` của unit hiện tại. Lưu thêm span và hash của `source_text` hiện tại.
- Không biến tuyên bố `APPROVED` hoặc tên một AI reviewer trong nguồn thành xác nhận của con người. Các trường này chỉ nằm dưới `source_claims`; trạng thái của bộ nhập là `LITERAL_MATCH_ONLY_NOT_LEGAL_APPROVAL`.
- `taxonomy_source_observations.jsonl` giữ quan hệ `IS_A` như quan sát từ nguồn; chưa khẳng định quan hệ đã được bộ nhập xác minh ngữ nghĩa.
- Không nhập Fact Graph chỉ có 24 node không cạnh để thay kênh vụ án hiện tại. Không lấy bản Rule rút gọn thay tập truy xuất rộng hơn.

## Chạy trên Windows

Tại thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/organize_research_data.py `
  --artifact 'D:\data_thô\result\result_28-10\vn_labor_results.zip' `
  --peer 'D:\data_thô\data_test\LegalGarph' `
  --output 'build/research_data/labor_organized_20261118'
```

Thay `--artifact` bằng ZIP hoặc thư mục artifact của lần OFFLINE sau. Mỗi lần dùng tên `--output` mới; công cụ từ chối ghi đè. Có thể bỏ `--peer` nếu chỉ muốn tổ chức artifact của mình. Bản đã xuất vẫn đọc được khi không còn thư mục peer; đường dẫn nguồn được giữ để truy vết, không phải phụ thuộc chạy ONLINE.

Dữ liệu sinh trong `build/` không commit. Chỉ mã công cụ, test và hướng dẫn được quản lý phiên bản. Không đưa bản nghiên cứu vào `artifact_source`, không sửa fingerprint của bản vận hành để ép chấp nhận bản nghiên cứu.

## Kết quả kiểm tra ngày 18/11/2026

Trên artifact `result_28-10/vn_labor_results.zip`: giữ 53.227 node, 80.559 cạnh, 19.144 đơn vị tìm kiếm. Có 3.934 ánh xạ Provision và 10 định nghĩa khớp nguyên văn từ LegalGarph. Đây là kết quả kiểm tra dữ liệu, **chưa có phép đo chứng minh tăng độ đúng, đầy đủ hay tốc độ**.

Bản clone LegalGarph thiếu một số tệp mà tài liệu nguồn nhắc tới. Công cụ chỉ dùng và ghim hash bốn tệp thực có, không kết luận đã tái hiện đầy đủ quá trình xây graph của thành viên đó.

## Bước tiếp theo nếu muốn dùng Ontology khi trả lời

Cần adapter chủ động đọc các gợi ý, giới hạn mở rộng truy vấn và đưa căn cứ đi qua Auditor/hậu kiểm hiện tại; sau đó so bật/tắt trên cùng dữ liệu và cấu hình. Bộ tổ chức này chưa bật chức năng đó, không thay đổi benchmark đang đo và không bảo đảm chất lượng trả lời tăng chỉ vì đã tách thư mục.

Kiểm thử cục bộ:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_research_organization.py -v
```

## Gói chạy thực tế

Công cụ trên vẫn là bản nghiên cứu. Luồng đóng gói OFFLINE mới đã có gói runtime riêng; xem [artifact-layout.md](../offline/artifact-layout.md). Bộ đọc runtime hỗ trợ cấu trúc mới và cũ; không cần biến bản nghiên cứu thành artifact vận hành.
