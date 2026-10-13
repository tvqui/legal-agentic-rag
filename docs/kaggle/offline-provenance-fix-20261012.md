# Sửa lỗi 38 INVALID_PROVISION_PROVENANCE — 12/10/2026

Revision code/notebook: `20261012-footnote-provenance-v2`.

## Nguyên nhân và bản sửa

Đã tái hiện đúng 38 lỗi bằng extracted documents của build ngày 12/10. Chú thích cuối trang nằm giữa hai phần của cùng điều khoản. Parser loại chú thích khỏi body nhưng validator cũ yêu cầu body khớp một đoạn raw source liền mạch, nên phát hiện mismatch.

Bản sửa trước thiếu kiểm tra assertion cho toàn bộ semantic issues trong CPU replay: suite và ví dụ Điều 62 PASS, nhưng summary vẫn chứa 38 lỗi. Bản sửa này kiểm toàn bộ provision và không coi chạy xong replay là PASS nếu còn lỗi provenance.

- Mỗi provision bị ảnh hưởng giữ bounding span gốc và `excluded_annotation_spans`, gồm segment/document offsets, SHA nguồn, SHA đoạn chú thích, page.
- Validator tính lại các annotations hợp lệ từ document; yêu cầu declaration khớp chính xác, vị trí document khớp, và toàn bộ body sau mask khớp từng dòng. Sửa SHA, tọa độ, tự loại chữ trong body hoặc thiếu declaration đều bị từ chối.
- Nguồn/segments/chú thích giữ nguyên. Không bỏ qua INVALID_PROVISION_PROVENANCE, không xóa 38 provisions để chạy qua gate.
- Dùng cùng validator trước AI/Dense/BM25 và trong final semantic audit. Có report `reports/provision_provenance_integrity.json`.
- Metadata retrieval giữ liên kết tới annotations bị loại.

## Kiểm chứng

473 repository tests PASS, bao gồm 5 regression tests mới: chú thích giữa khoản qua hai trang, SHA bị sửa, declaration giả/thiếu, mất chữ body và chặn AI/Dense khi provenance sai.

Replay toàn bộ 95 tài liệu, 18.871 provisions, 19.160 retrieval units. Cần đọc kết quả mới trong `artifacts/reports/offline_provenance_fix_20261012.json` và `offline_quality_upgrade_validation_20261012.json`: 38 lỗi được tái hiện, 0 lỗi provenance sau sửa, giữ đủ provision IDs. Replay không chạy Dense/AI/OCR model/Aura; thiếu indexes trong replay CPU là điều được báo cáo riêng, không chứng nhận full ONLINE-ready.

## Chạy lại Kaggle

1. Tải `vn_labor_results_recovery.zip` từ Output của run vừa lỗi. Cache extraction còn hữu ích; đây là checkpoint, không phải code.
2. Cập nhật Dataset code bằng `build/kaggle/vn_labor_kaggle_v8.zip` mới và SHA sidecar. Import notebook `build/kaggle/VN_Labor_Kaggle_V8.ipynb` mới; alias `ai-v9-1.ipynb` cùng nội dung.
3. Gắn đúng một checkpoint: recovery vừa tải hoặc `result_12-10/vn_labor_results.zip`. Tháo checkpoint khác để AUTO không chọn nhầm. Không đổi Dataset code thành ZIP recovery.
4. Bắt đầu session mới, bật Internet/GPU T4 x2; Aura RUNNING nếu LOAD_AURA=True. Giữ REFRESH_EXTRACTION_QUALITY=True, AI tối đa 250 provision và timeout 240 giây.
5. Save & Run All. Không cần git push vì code chạy từ Dataset ZIP.

Log cần có:

```text
Bundle revision: 20261012-footnote-provenance-v2
PROVENANCE_INTEGRITY {"passed": true, "provisions": 18871}
```

Sau đó mới đến Dense/BM25 và AI. Nếu thấy Dataset code cũ thì chưa cập nhật đúng Input; không tiếp tục bằng cách bỏ guard. Số provision có thể thay đổi nếu corpus/decisions đổi; 18.871 là corpus hiện tại.

Neo4j chưa xác minh ở checkpoint trước load là dự kiến. Source/temporal/Gold review vẫn đang chờ, AI completion rate cần đo trên Kaggle. Bản sửa xử lý lỗi provenance đã tái hiện, không đảm bảo mạng/quota/model luôn thành công.
