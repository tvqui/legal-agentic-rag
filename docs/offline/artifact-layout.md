# Đầu ra OFFLINE: gói chạy ONLINE và hồ sơ kiểm tra

## Cấu trúc bàn giao

```text
releases/<lần chạy>/
├── vn_labor_online.zip          # Chỉ gói này cần đưa vào Backend
│   └── artifacts/
│       ├── shared/             # source_catalog_resolved.jsonl dùng chung
│       ├── graph/              # nodes.jsonl và edges.jsonl
│       ├── retrieval/
│       │   ├── retrieval_units.jsonl
│       │   ├── bm25/           # Chỉ mục từ khóa và corpus của BM25S
│       │   └── dense/          # Chỉ mục FAISS và ánh xạ unit_id
│       ├── checks/             # Ba báo cáo tương thích tối thiểu
│       ├── runtime_manifest.json
│       └── README.md
├── vn_labor_offline_review.zip  # Báo cáo chi tiết và dữ liệu trung gian
├── release.json                # SHA-256 của hai ZIP và build ID
└── README.md
```

Gói kiểm tra chứa những tệp còn lại của artifact làm việc: bản trích xuất, registry, cấu trúc, tri thức trung gian, báo cáo/log, vector phục vụ OFFLINE và cache được lưu trong artifact. Không lặp lại node/cạnh, retrieval units hay các tệp index đã có trong gói ONLINE. Corpus PDF gốc nằm ngoài artifact vẫn cần được giữ để dựng lại từ đầu; hai ZIP không thay thế bộ nguồn đầu vào.

Không chia vật lý Rule/Ontology/Fact thành nhiều bản node trùng nhau: `label`/`type` đã phân loại, `source`/`target` giữ liên kết giữa các lớp. Checklist được giữ cùng graph vì ONLINE đang dùng. Muốn nghiên cứu tách lớp có thể dùng công cụ trong [docs/data/README.md](../data/README.md), nhưng không dùng bản nghiên cứu thay gói runtime.

BM25S cần corpus và tệp số liệu của riêng thư viện; FAISS cần metadata ánh xạ. Đây là thành phần chỉ mục hiện có, không phải bản sao graph bổ sung. BGE-M3 là mô hình tạo embedding; trọng số BGE-M3/reranker không được nhét vào runtime ZIP, ONLINE tải/nạp theo cấu hình hiện tại. `vectors.npy` dùng cho OFFLINE được chuyển sang gói kiểm tra, FAISS phục vụ tìm kiếm vẫn đi cùng ONLINE.

## Chạy OFFLINE từ đầu

Giữ quy trình dựng dữ liệu và kiểm tra hiện có:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m vn_labor_offline.cli all --config config/pipeline.yaml
# Nếu quy trình yêu cầu kiểm chứng Neo4j: cấu hình dịch vụ rồi chạy bước có sẵn.
.\.venv\Scripts\python.exe -B -X utf8 -m vn_labor_offline.cli load-neo4j --config config/pipeline.yaml
.\.venv\Scripts\python.exe -B -X utf8 scripts/validate_outputs.py --config config/pipeline.yaml
```

Khi audit đạt đủ bốn kiểm tra kỹ thuật, lệnh cuối tự tạo hai gói trong `releases/<UTC timestamp>/` cạnh thư mục artifact làm việc. Nếu chưa đạt, báo cáo lỗi được giữ; không tạo báo cáo PASS giả để ép đóng gói. Tạo dữ liệu và kiểm tra kỹ thuật không tự cấp phê duyệt pháp lý.

Để đóng gói lại một artifact làm việc đã đủ điều kiện mà không OCR hoặc chạy model lại:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m vn_labor_offline.cli package `
  --artifact artifacts `
  --output build/releases/my_release_v2
```

Đầu vào của lệnh `package` là thư mục artifact OFFLINE đầy đủ, không phải thư mục bản nghiên cứu hoặc runtime v2. Với ZIP cũ, giải nén vào một thư mục riêng rồi trỏ `--artifact` vào thư mục đó. Mỗi lần chọn thư mục `--output` mới, không ghi đè release cũ.

Trên Kaggle, bước `kaggle/remote.py export` của lần chạy cuối thành công tự xuất thêm `vn_labor_online.zip`, `vn_labor_offline_review.zip` và `release.json` vào `/kaggle/working/`. Notebook OFFLINE được sinh từ `kaggle/final_notebook.py` liệt kê các tệp này để tải. `vn_labor_results.zip` và các checkpoint cũ vẫn được giữ để tương thích các notebook khôi phục OFFLINE; chúng là bản sao đầy đủ phục vụ tiếp tục công việc, không cần tải lên Backend nếu đã có gói runtime mới.

## Dùng cho ONLINE và bộ đo

1. Dùng code mới có hỗ trợ `phapdien-runtime-2` và notebook Backend cập nhật tại `kaggle/ONLINE_Backend.ipynb`.
2. Đưa **vn_labor_online.zip** lên Kaggle. Nếu Kaggle tự giải nén, chọn thư mục `artifacts` tương ứng.
3. Notebook có thể tự nhận diện cấu trúc cũ và mới; nếu gắn nhiều bản cùng lúc, phải điền `ARTIFACT` rõ ràng.
4. Giữ bước pin/kiểm fingerprint. Đổi cấu trúc ZIP làm **archive SHA-256 thay đổi**, trong khi graph build, fingerprint nội dung và dense fingerprint giữ nguyên khi chỉ đóng gói lại. Cập nhật archive SHA trong cấu hình bằng giá trị thật; không bỏ kiểm tra.
5. Không đưa `vn_labor_offline_review.zip` hoặc `research_data` vào `artifact_source`.

`ArtifactStore.path()` cung cấp tên logic cũ cho code sử dụng dữ liệu, rồi ánh xạ sang các đường dẫn mới. Bộ đo chính, bộ đo Graph QA và bước nhận diện Kaggle đã được cập nhật. Công cụ kiểm tra OFFLINE cũ đọc trực tiếp staging vẫn dùng artifact làm việc hoặc checkpoint đầy đủ.

## Phạm vi kiểm thử

- Kiểm thử tích hợp dùng BM25S và FAISS thật trên dữ liệu giả: nạp ZIP/thư mục, đối chiếu kết quả cũ/mới, kiểm fingerprint, từ chối dữ liệu bị sửa, layout trộn, manifest thiếu và đường dẫn không hợp lệ.
- Kiểm thử dữ liệu thật ngày 28/10: so toàn bộ units/node/cạnh; truy vấn BM25; tìm FAISS bằng vector đã lưu. Không chạy lại BGE-M3 để tạo vector mới.
- Kiểm thử này không chứng minh chất lượng pháp lý tăng. Không đổi thuật toán, không bật thêm Ontology và không tự tăng trạng thái phê duyệt dữ liệu.
- Chưa chạy lại toàn bộ OCR, AI enrichment, Neo4j từ xa hay notebook trong phiên Kaggle thực tế. Những phần đó vẫn phụ thuộc bộ nguồn, cấu hình, dịch vụ và phần cứng.
