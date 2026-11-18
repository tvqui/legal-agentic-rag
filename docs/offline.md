# OFFLINE: từ nguồn đến artifact

Đầu vào là corpus cục bộ `data/`, danh mục trong `config/` và các bản sửa nguồn cần thiết trong `review/corrections/`. OFFLINE trích xuất và chuẩn hóa, dựng registry/Điều–Khoản–Điểm, provenance, phiên bản, tri thức/graph, rồi xây BM25 và Dense BGE-M3/FAISS.

```bat
run.bat offline
run.bat load-neo4j
run.bat validate
```

Cần chuẩn bị dependency, model và cấu hình dịch vụ tương ứng trước khi chạy. Neo4j và kiểm tra kỹ thuật phải đạt yêu cầu của quy trình; không tự bỏ bước để đổi trạng thái sang PASS.

Artifact làm việc ở `artifacts/`; sau audit/export thành công, gói chạy ONLINE và hồ sơ kiểm tra được tách riêng. Xem [cấu trúc và lệnh đóng gói](offline/artifact-layout.md). Checkpoint đầy đủ phục vụ chạy tiếp OFFLINE, khác gói runtime gọn cho Backend.

Hướng dẫn liên quan: [dữ liệu nguồn](../data/README.md), [nguồn và phê duyệt](human-review.md), [đổi link nguồn](offline/source-links-workbook.md), [Kaggle](kaggle.md).
