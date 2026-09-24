# Chạy OFFLINE V8 trên Kaggle từ checkpoint 7.3

> **Đã nạp Aura V8.1 và kiểm live:** cả bốn đầu ra OFFLINE v1 PASS; xem [OFFLINE_V8_1_AURA_RESULT_REVIEW.md](OFFLINE_V8_1_AURA_RESULT_REVIEW.md). Không cần chạy lại các bước build/nạp bên dưới để xác nhận mốc kỹ thuật. ONLINE-ready vẫn chờ review nguồn, hiệu lực và Gold.
> **Công việc tiếp theo để hướng tới 100%:** làm theo [OFFLINE_TO_100_NEXT_STEPS.md](OFFLINE_TO_100_NEXT_STEPS.md), bắt đầu bằng bản nháp nguồn trong `review_inputs/v8_1`. Chưa cần khởi động lại Kaggle khi mới thu thập bằng chứng.

> **Lịch sử candidate V8 trước Aura:** xem [OFFLINE_V8_RESULT_REVIEW.md](OFFLINE_V8_RESULT_REVIEW.md). Các bước bên dưới dành cho lần build lại sau khi có review hoặc khi cần tái lập môi trường Kaggle.

V8 dùng kết quả 7.3 để tiết kiệm bước trích xuất, nhưng dựng lại structure, graph, BM25 và Dense vì metadata và schema đã đổi. Hai file gốc trên máy vẫn được giữ. Hiện chưa có người duyệt pháp lý, vì vậy `offline_ready_for_online=false` là kết quả đúng dù pipeline chạy thành công.

## 1. Hai file cần đưa lên Kaggle

1. Trong thư mục `kaggle_upload`, dùng `vn_labor_kaggle_v8.zip` làm **Dataset Private** mới. Đây là code, config và 96 file corpus; không dùng package V7 cũ.
2. Dùng `C:\Users\Acer\Downloads\vn_labor_results_7.3.zip` làm **Dataset Private** thứ hai. Đây là checkpoint; không cần gửi các ZIP V6/V7/V7.2 cùng lúc.
3. `VN_Labor_Kaggle_V8.ipynb` là Notebook để import, không phải file Dataset. Đặt Notebook ở chế độ **Private**.

Kaggle có thể giải nén Dataset tự động. Trong Dataset thứ nhất cần thấy `vn_labor_bundle/bundle_manifest.json`; Dataset thứ hai cần thấy file ZIP hoặc thư mục `artifacts`. Notebook tự tìm đúng một checkpoint. Nếu báo tìm thấy nhiều checkpoint, bỏ các Dataset cũ khỏi **Input**.

## 2. Tạo Notebook và chạy build mới

1. Vào Kaggle bằng tài khoản `qutrnvinh3`, mở **Code → New Notebook** rồi chọn **File → Import Notebook** và đưa `kaggle_upload/VN_Labor_Kaggle_V8.ipynb` vào.
2. Trong **Input → Add Input**, gắn đúng hai Dataset Private ở mục 1. Kiểm tra Notebook cũng là Private.
3. Trong **Settings**, chọn GPU T4 x2 và bật Internet. V8 dùng GPU 0; CPU/RAM cho parsing và BM25 cũng là của server Kaggle.
4. Giữ cell cấu hình đầu tiên như sau:

```python
RUN_PIPELINE = True
LOAD_AURA = False
RESTORE_ARCHIVE = "AUTO"
```

5. Chọn **Save Version → Save & Run All** một lần. Chờ phiên kết thúc, mở phiên Version đó → **Output** → tải `vn_labor_results.zip`. Lần chạy này dựng lại cả Dense và BM25 trên retrieval units mới. Aura cũ 7.3 được giữ nguyên trong lúc kiểm tra candidate V8.

Trong ZIP mới mở `artifacts/reports/summary.json`, `final_outputs_validation.json`, `dense_validation.json`, `kaggle_audit.log` và `validation_issues.jsonl`. `kaggle_audit.log exit code: 1` trước khi nạp Aura có thể xảy ra vì Graph DB chưa được kiểm live; xem riêng các stage registry, structure, graph và Dense/BM25. Gửi ZIP kết quả mới để kiểm tra các lỗi phát sinh trước khi nạp graph mới.
Sau build kỹ thuật, `final_outputs_validation.json` có `gold_build_id` để người duyệt gắn Gold/qrels và ngưỡng với đúng graph + Dense + BM25 của V8.

## 3. Nạp Aura khi candidate V8 đạt kỹ thuật

Sau khi graph/index candidate được kiểm tra, gắn chính ZIP kết quả V8 vào Dataset Private checkpoint mới. Trong Notebook V8, bỏ checkpoint 7.3 khỏi Input và dùng checkpoint V8. Đổi cấu hình thành:

```python
RUN_PIPELINE = False
LOAD_AURA = True
RESTORE_ARCHIVE = "AUTO"
```

Trong **Add-ons → Secrets**, cấp quyền Notebook cho `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` của instance hiện có. `NEO4J_DATABASE` lấy tên database trong credentials, không dùng tên hiển thị instance. Chọn **Save Version → Save & Run All**. Lần này Notebook khôi phục artifacts, nạp graph và chạy audit live; không chạy lại OCR/Dense/BM25. Loader sẽ thay dataset dự án trong instance hiện có, nên chỉ làm sau khi kiểm tra candidate V8. Tải ZIP xuất sau nạp và xem `neo4j_validation.json` với build ID mới.

## 4. Phần review cần làm sau build

`review_inputs/v7_3` trên máy đã có danh sách 95 nguồn, 25 candidate legal change và 837 dòng quarantine từ ZIP 7.3; đây là bản nháp, không có record nào được phê duyệt. V8 còn tạo các review queue riêng cho bằng chứng relation/checklist/issue. Người có chuyên môn cần duyệt nguồn và SHA, ngày/phạm vi sửa đổi, khoảng hiệu lực, các dòng quarantine quan trọng, cùng Gold questions/qrels và ngưỡng chất lượng. Sau khi các review record được ghi vào `config/source_catalog.yaml`, `config/legal_change_reviews.yaml`, `config/provision_version_reviews.yaml` hoặc `config/temporal_coverage_reviews.yaml`, và Gold của đúng build, đóng package rồi chạy lại các stage phụ thuộc. Không tự đổi `UNVERIFIED` thành `VERIFIED` để làm đẹp báo cáo.
