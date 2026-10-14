# Hoàn thiện AI/resume và bộ kiểm trang — 13/10/2026

Đã sửa trực tiếp code trong `D:/data_thô/legal-agentic-rag`, tạo gói Kaggle mới và cấu hình ONLINE riêng. Chưa chạy mô hình trên Kaggle/Aura trong lần làm việc này; không công bố dữ liệu đã qua kiểm duyệt pháp lý.

## Kết quả kiểm chứng

- Toàn bộ repository: **485 tests PASS**, 0 failure/error; compileall PASS.
- Notebook: mọi code cell compile; chưa có output/secret; hai notebook giống byte và SHA đúng.
- ZIP: CRC PASS, SHA từng file trong manifest PASS; 277 file, revision `20261013-anchored-ai-resume-v1`.
- Replay cache thật trong thư mục tạm: **95 tài liệu, 18.871 provision, 24 case, 2.036 feature AI và 132 checklist AI được giữ nguyên**, 0 gọi mạng/mô hình.
- Chuẩn bị provenance và temporal bằng code/config hiện tại: tất cả **19.160 retrieval units** vẫn trùng Dense metadata. Không cần dựng lại embeddings cho AI-only resume.
- Bộ đối chiếu: **174/174 trang**, đủ ảnh và raw selected text, 106 chú thích có evidence hình học; **68 trang khác biệt số liệu** ưu tiên HIGH. Không tự phê duyệt trang nào.
- ONLINE pin cho ZIP cuối ngày 13/10: compatible; vẫn provisional vì source review, temporal review và Gold chưa được duyệt.

## Phạm vi sửa

`anchored_ai.py`: AI chọn mã đoạn nguồn; chương trình mở rộng thành đúng chuỗi gốc. Có giới hạn đầu ra và repair có cache cho các mục chưa khớp.

`ai_requests.py`, `ai_enrichment.py`, `cases.py`, `checklists.py`: chia nhỏ nhiều cấp có giới hạn, kiểm string length, giữ cache cũ, xác minh lại span/SHA của kết quả được giữ, không coi lỗi độ dài là outage dịch vụ, không công bố complete cho output chạm trần hoặc repair còn thiếu.

`pipeline.py`: dừng sớm khi code/config làm retrieval metadata thay đổi, trước mọi yêu cầu AI. Trường hợp này phải dựng technical indexes trước; không chờ nhiều giờ rồi mới phát hiện.

`offline_final_remote.py`, `final_notebook.py`, `package_kaggle.py`: chế độ tiếp tục từ technical baseline, giữ cache/features, kiểm corpus, checkpoint trước AI, heartbeat, ngân sách, recovery, Aura/final audit. Dựng heuristic lại lưu thống kê AI cũ riêng để tránh hiểu nó là lần chạy mới.

`page_review.py`: CSV giao việc có source SHA, ảnh, priority, finding, trạng thái, reviewer/evidence và bản sửa; không tự nhập approval vào corpus.

`config/online_release_20261013.yaml`: cấu hình riêng khóa đúng ZIP/build/retrieval/Dense của ngày 13/10. Không đổi cấu hình ONLINE mặc định hoặc `.env`.

## File bàn giao

- `build/kaggle/VN_Labor_Kaggle_V8.ipynb` và `.sha256`.
- `build/kaggle/ai-v9-1.ipynb` là alias của notebook trên.
- `build/kaggle/vn_labor_kaggle_v8.zip` và `.sha256`.
- SHA package: `e798624f24e20b6ba35ecc642ae16db5fc9fbbfb5db60768daa22a6a15847466`.
- SHA notebook: `65c7d6a731a8a8fb8ecef530421b5b77dbf52bb76a8caae1939c76462d7149b0`.
- Input phục hồi: **ZIP cuối** `D:/data_thô/result/result_13-10/vn_labor_results.zip`.
- Hướng dẫn thao tác: [offline-ai-resume-20261013.md](offline-ai-resume-20261013.md).
- Bộ kiểm trang local: `artifacts/reviews/page_quality_20261013/index.html` và `page_review_tracking.csv`.
- Bằng chứng kiểm thử: `artifacts/reports/offline_ai_upgrade_validation_20261013.json`, `offline_ai_resume_replay_20261013.json`, `offline_ai_resume_preflight_20261013.json` và log test.

## Phần cần chạy/duyệt tiếp

Upload Dataset code mới, dùng Input kết quả ngày 13/10 và notebook mới, GPU T4 x2 + Internet + Aura Secrets; chạy Save & Run All. Không cần git push cho notebook OFFLINE dùng bundle ZIP.

Đầu ra vẫn phải đọc riêng technical PASS và AI quality; có thể cần tiếp tục từ ZIP cache ở phiên sau nếu hết ngân sách. Phạm vi 250 checklist là chọn lọc, không phải AI enrichment toàn corpus. Chưa có phép đo accuracy/benchmark ONLINE trên đầu ra AI mới, vì đầu ra đó chưa được tạo trên Kaggle.

Các quyết định source/temporal/quarantine/Gold và sửa OCR trên 174 trang cần người duyệt thật. Dữ liệu hiện tại dùng cho ONLINE provisional; không dùng kết quả local test thay chứng nhận tính đúng pháp lý.
