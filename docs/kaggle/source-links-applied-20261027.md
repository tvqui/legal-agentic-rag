# Chạy OFFLINE sau khi nhập Excel link nguồn — 27/10/2026

## Đã cập nhật

Đã nhập workbook `PhapDienAI_Cap_nhat_link_nguon_DA_DOI_CHIEU_20261027.xlsx`: **72 link trang nguồn thay đổi**, trong đó 23 tài liệu được bổ sung link trước đây trống. Hiện **84/95 tài liệu có link cấu hình; 11 bản án còn chờ xác định nguồn**. Không thay PDF, SHA, ngày hiệu lực, link tải PDF hay tự tạo phê duyệt pháp lý. Workbook xác nhận link chưa chứng nhận nội dung PDF/hiệu lực pháp luật đã được chuyên gia duyệt.

Code đã sửa lỗi nhập các trường provenance vào registry, hỗ trợ đường dẫn VBPL `/van-ban/chi-tiet/…--ID`, đồng thời kiểm tra link xuyên suốt registry → source catalog resolved → graph Document → retrieval units. Khi cấu hình và checkpoint không khớp, validation báo lỗi thay vì cho phép dùng trộn link mới với dữ liệu cũ. Link còn thiếu được ghi riêng, không tự điền bằng trang chủ.

## Chỉ dùng hai Input trên Kaggle

1. **Thay package code** trong Dataset `vn-labor-kaggle-v8-ai` bằng `build/kaggle/vn_labor_kaggle_v8.zip` mới, revision **20261027-source-links-v3**. Tạo phiên bản Dataset mới rồi chọn phiên bản mới trong Input của notebook. Gỡ bản package cũ khỏi Input để tránh nhận nhầm. Giữ ZIP nguyên hoặc để Kaggle giải nén; notebook hỗ trợ cả hai.
2. **Giữ Dataset kết quả `result_14-10`** (`vn_labor_results.zip` hoặc thư mục `artifacts` đã giải nén) làm checkpoint. Không thay nó bằng ZIP code; không thêm cùng lúc recovery/technical checkpoint khác.
3. Import **`build/kaggle/VN_Labor_Quality_Refresh.ipynb`** mới vào notebook OFFLINE. Không dùng bản AI-resume/VN_Labor_Kaggle_V8 để cập nhật metadata từ checkpoint cũ. Bản Quality Refresh đã đặt `RESUME_AI_ONLY=False`, `REFRESH_EXTRACTION_QUALITY=True`.
4. Bật **GPU T4 x2**, **Internet**; cấp bốn Secrets `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Chờ Aura RUNNING trước khi chạy. Không chạy job khác cùng lúc trên cùng Aura.
5. Chọn **Save Version → Save & Run All**. Không cần upload Excel lên Kaggle, không cần git push cho job này: link đã nằm trong config bên trong ZIP code. Notebook có bước `apt-get update -y` và cài `zstd` đầu tiên.

Quality Refresh khôi phục checkpoint, rà lại extraction/page corrections và dựng lại registry, structure, knowledge, graph, BM25/Dense theo cấu hình mới; sau đó xử lý AI còn thiếu, nạp Aura, kiểm tra và export. Đây vẫn là một job dài. Ngân sách thời gian/quota, mạng, GPU và dịch vụ bên ngoài có thể giới hạn số phần AI hoàn tất; không đổi nhãn partial thành complete.

## Khi chạy xong

- Tải **`vn_labor_results.zip` + `.sha256`** và lưu báo cáo. `reports/final_outputs_validation.json` phải PASS bốn đầu ra kỹ thuật. Kiểm tra `reports/source_links_validation.json`: `passed=true`, `configured_documents=84`, `matched_configured_documents=84`, `missing_source_count=11`. Đây là kiểm tra link khớp cấu hình, không phải chứng nhận 84 trang web luôn truy cập được hay đã đúng nội dung luật.
- Xem `00_manifest/source_links_snapshot.json` để biết chính xác các link được đóng trong build. Xem `checklist_ai_quality.json` và `case_ai_quality.json` để biết phần AI còn thiếu; Technical PASS có thể đi cùng AI_DEGRADED.
- Nếu thất bại, tải recovery ZIP và log trước khi đóng phiên. Chỉ tiếp tục AI-resume từ checkpoint đã qua rebuild với cấu hình nguồn mới; không dùng AI-resume để bỏ qua lỗi mismatch.
- Dùng **nguyên ZIP kết quả mới** thay `result_14-10` trong Input của backend ONLINE, chạy lại cell pin artifact và backend. Không ghép indexes/graph cũ vào build mới. Với local, pin ZIP mới và dùng file config pin được tạo. Giữ bản cũ để có thể quay lại.
- Khi code ONLINE thay đổi, có thể tiếp tục dùng ZIP này nếu kiểm tra compatibility đạt. Khi sửa link, nội dung, phiên bản hiệu lực hoặc bổ sung luật, cần build lại phần liên quan. Bộ dữ liệu là snapshot đã chốt, không tự cập nhật pháp luật tương lai. Gold phải kiểm tra/migrate lại theo build mới, vẫn DRAFT cho đến khi duyệt.

## Kiểm thử đã thực hiện

875/875 unit tests đạt. Đã dựng thử metadata, structure, graph và retrieval units từ 95 tài liệu của artifact thật, không gọi OCR/LLM/GPU/Aura: các link của 84 tài liệu cấu hình khớp qua các lớp; 11 tài liệu thiếu nguồn được giữ riêng. Kiểm tra này không thay thế chạy GPU/Linux/Aura thực tế trên Kaggle. Sau đóng gói có CRC ZIP, SHA từng file, SHA gói và kiểm tra cú pháp mọi cell.

## Những việc chưa tự động phê duyệt

11 nguồn bản án còn trống, các trang OCR đáng ngờ, nguồn/hiệu lực cấp điều khoản, khoảng thời gian bao phủ và Gold cần tiếp tục đối chiếu. Ngày chạy mới không tự kéo dài mốc dữ liệu 15/09/2026. Danh sách 11 nguồn thiếu và lịch sử nhập Excel được lưu tại `review/link_updates/applied_20261027/`. Không xóa cảnh báo hoặc nâng thành legal-ready để làm báo cáo đẹp hơn.
