# Rà soát OFFLINE trước khi chạy Kaggle — 10/10/2026

Các sửa đổi đã áp dụng trực tiếp trong `D:/data_thô/legal-agentic-rag`.
Notebook/ZIP trong `build/kaggle/` chứa code mới, không phải chỉ là bản trong thư mục review.

## Lỗi đã sửa

- Chỉ mục từng loại provision dưới 20 ký tự dù parser đã giữ lại. Đã bỏ ngưỡng này, thêm audit toàn bộ provision phải có retrieval unit.
- Cắt ngữ cảnh cha ở 1.500 ký tự và text bản án ở 30.000 ký tự; search text bản án còn bỏ phần quyết định. Metadata/BM25 nay giữ toàn văn, case search có cả quyết định.
- AI bản án chỉ đọc prefix. Nay chia đoạn bao phủ toàn bộ nguồn và chỉ chấp nhận quote thực sự xuất hiện trong đoạn đã gửi.
- Cache AI không phân biệt system prompt và có thể giữ JSON/schema hỏng. Nay fingerprint có system/prompt version, kiểm schema và tái tạo cache hỏng.
- Cache extraction có thể giữ lỗi hoặc tái sử dụng kết quả với cấu hình khác. Nay kiểm source SHA/schema/settings, OCR/page-quality lỗi; cache trang và Dense hỏng được tái tạo.
- Worker retry có thể dùng response cũ. Nay xóa response trước mỗi lần và ghi lỗi rõ khi không phục hồi.
- Báo PASS extraction dù có document/page lỗi. Nay ghi extraction_integrity và dừng trước khi chạy bước nặng.
- Audit có thể đọc PASS cũ hoặc nhận stage rỗng. Nay yêu cầu báo cáo mới, checks không rỗng và đủ cả bốn stage local.
- Cài Ollama trước checkpoint nên lỗi tải model làm mất cơ hội giữ technical build mới. Nay export technical ZIP trước cài/serve/pull Ollama, có timeout và cleanup tiến trình.
- Ngân sách notebook chỉ tính từ runner, bỏ thời gian setup. Nay trừ thời gian từ cell đầu, giới hạn 10 giờ và cố recovery khi dừng có kiểm soát.
- JSONL được ghi nguyên tử; khi bị ngắt, file hoàn chỉnh trước đó được giữ lại. Recovery export chấp nhận report hỏng nhưng giữ trạng thái thất bại và loại file tạm.
- BGE download dở nhưng đủ size/sai SHA có thể bị kẹt retry Range 416. Nay bỏ partial hỏng và tải lại, metadata cache hỏng được phục hồi.
- AI fallback bị lẫn với kết quả hoàn thành. Nay xuất case/checklist quality riêng, trạng thái AI_COMPLETE/AI_DEGRADED/HEURISTIC_ONLY.
- Leiden dùng seed cố định để giảm thay đổi ngẫu nhiên giữa các lần rebuild.

## Kiểm chứng đã thực hiện

- 439 tests PASS, 0 failure/error; compileall PASS qua pycache riêng. Cache .pyc cũ trên Windows có quyền ghi bị khóa, không phải lỗi cú pháp.
- Replay 95 tài liệu bằng CPU trong thư mục tạm: 18.871 provision, 19.160 units, không provision nào thiếu unit.
- Đối chiếu 10 locator ở Điều 124 và Điều 62 của 18/VBHN-VPQH: tất cả hiện có; bốn mục vắng trong chỉ mục V8.1 đã được phục hồi.
- ZIP 262 file được đối chiếu SHA với manifest và source; kiểm CRC, SHA ZIP/notebook, alias notebook và syntax từng cell đều PASS.
- Gói không chứa .env, model cache, virtual environment hoặc bytecode.
- Không chạy toàn bộ OFFLINE, tải model, OCR corpus hoặc ghi Aura trên máy local; ZIP V8.1 và corpus gốc giữ nguyên.

## Những điều chưa được chứng nhận

Tests không bảo đảm GPU/Internet/Aura trên Kaggle không bao giờ lỗi. Notebook thêm preflight inference BGE/FAISS và OCR để phát hiện sớm lỗi tương thích tại môi trường thực tế.
Chưa chạy bản này trên Kaggle nên chưa có số thời gian hoặc thước đo độ chính xác pháp lý mới.
Corpus còn thiếu 91/2025/QH15, 51/2024/QH15, 64/2025/QH15; không tự sinh nguồn hoặc approval thay người duyệt.
Dense vẫn có giới hạn 1.024 token; AI chỉ tinh chỉnh subset, không thay việc review temporal, legal changes, quarantine hoặc Gold.
Sau lần chạy cần đọc page audit, AI quality, current technical audit và đồng bộ graph/Aura/artifact trước khi chuyển ONLINE.

## File chạy

- `build/kaggle/VN_Labor_Kaggle_V8.ipynb` (alias cùng nội dung: `ai-v9-1.ipynb`).
- `build/kaggle/vn_labor_kaggle_v8.zip` cùng `.sha256` mới.
- Checkpoint cũ `build/releases/vn_labor_results_v8_1_aura.zip` hoặc file V8.1 Aura bạn đã gắn trong Input.
- Hướng dẫn: `docs/kaggle/offline-ai-enrichment.md`.

Báo cáo máy đọc: `artifacts/reports/offline_kaggle_preparation_validation.json` và `offline_kaggle_cpu_replay_20261010.json`.
