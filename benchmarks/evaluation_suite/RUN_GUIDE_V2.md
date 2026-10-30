# Chạy bộ đo v2 từ đầu đến cuối

## Chuẩn bị

Code đo nằm trong **một folder `benchmarks/evaluation_suite/`**. Notebook mới thay notebook `b-o-h-th-ng.ipynb` cũ; không cần sửa notebook cũ từng cell.

1. Trên máy, kiểm `git status` và push folder `benchmarks/evaluation_suite` cùng Gold mới `gold_dataset/PhapDienAI_Gold_100_Labor_v0_2.zip`. Giữ ZIP v0.1 để đối chiếu lịch sử. Không commit `.env`, tokens, cache hoặc các file kết quả nặng. Nếu muốn đo các sửa ONLINE chưa push thì cần push chúng nữa; notebook chỉ lấy code đã có trên origin/main. Chưa có commit/push thay bạn trong lượt rà soát Gold này.
2. Trên Kaggle, tạo notebook đo riêng, bật Internet và **GPU T4 ×2**. Dừng notebook backend/OFFLINE khác để tránh tranh VRAM hoặc cùng quota Gemini.
3. Import **`Kaggle_Evaluation.ipynb`** mới để smoke, hoặc **`Kaggle_Evaluation_Standard.ipynb`** để chạy standard sau khi đã kiểm tra. Cả hai tự lấy main mới, không đóng COMMIT cứng.
4. Add Input **chỉ ZIP kết quả cuối `result_28-10/vn_labor_results.zip`** hoặc thư mục artifacts giải nén của nó. Không thêm technical checkpoint, recovery hay bản 14-10 cùng lúc.
5. Nếu chạy QA/ablation/VLSP, cấp Secret `GEMINI_API_KEY`; `HF_TOKEN` tùy chọn. Không cần ngrok, VN_LABOR_API_KEY hoặc frontend. Nếu chỉ chạy retrieval/Zalo, notebook bỏ qua Gemini/Ollama.

## Chạy theo giai đoạn

Cell đầu có `STAGES`. Mặc định gồm retrieval → Zalo → ablation → VLSP. Có thể chia:

```python
STAGES = ['retrieval', 'zalo']       # không dùng API LLM
# hoặc
STAGES = ['retrieval', 'ablation']   # tập trung phần chính trước
# hoặc
STAGES = ['vlsp']                   # kiểm QA ngoài riêng
```

Smoke: 8 câu Gold phân tầng, một lần lặp; Zalo 10 query nhưng **toàn corpus 61.425** vẫn được index; VLSP tối đa 5 câu. Nếu chỉ muốn smoke nhanh phần chính, chọn `['retrieval','ablation']`.

Standard với Gold v0.2 mặc định: 88 câu retrieval × 6 phương pháp × 3 lần = **1.584 lượt**; 100 câu QA × 5 biến thể × 1 lần = **500 lượt tạo câu trả lời**, chấm AI sau đó. Còn 12 câu cần hỏi thêm, chỉ dùng đánh giá QA, không làm qrels dương tính cho retrieval. TD003 đã được sửa câu hỏi/đáp án nên ghi chú loại khỏi chấm của ZIP v0.1 không áp dụng cho v0.2. Tất cả vẫn là nhãn DRAFT. Zalo mặc định 100 query × 3 phương pháp × 3 lần; VLSP bộ lọc hiện cho 13 câu, không phải 50 câu chỉ vì limit=50. Số lượt API thực tế có thể nhiều hơn vì pipeline dùng nhiều model steps và sửa một lần; không bảo đảm đủ quota một phiên.

Gold v0.2 ghim ngày hỏi **15/09/2026**, đúng snapshot result_28-10; không dùng bảng này để tuyên bố dữ liệu đã cập nhật tới ngày hiện tại. Mọi căn cứ đã được đối chiếu ID, nguyên văn, ngữ cảnh cha, URL và khả năng lọc theo ngày. Điều đó không bảo đảm LLM luôn trả lời đúng hoặc nguồn đã được chuyên gia duyệt. Xem [rà soát Gold](GOLD_V0_2_REVIEW.md).

Muốn thêm 20 câu về kỷ luật, nhóm lao động đặc biệt, tranh chấp và nhiều yêu cầu, đổi cell đầu thành `LABOR_GOLD = 'gold_dataset/PhapDienAI_Gold_120_Labor_v0_2.zip'`. Bản này có 108 câu retrieval (**1.944 lượt**) và 120 câu QA (**600 lượt**). Không tự tăng cỡ đo mặc định; chọn theo ngân sách. Ba câu tương lai v0.1 giữ riêng trong ZIP, không nằm trong điểm chính của v0.2.

Notebook kiểm metadata/schema của bộ ngoài trước khi vào phép đo dài. Nếu preflight lỗi mạng/schema, nó dừng sớm và có log; có thể chỉ chạy các STAGES chính trong khi xử lý bộ ngoài, không tạo điểm giả.

Chọn **Save Version → Save & Run All**. Khi một provider hết quota, kết quả đã tạo được lưu; trạng thái `PAUSED_UPSTREAM` hoặc lỗi không được đổi thành COMPLETE. Tổng ngân sách suite 10 giờ, stage tối đa 9 giờ; vẫn chịu giới hạn phiên/quota Kaggle, model và mạng. Nếu cần, chia stages/phiên thay vì tăng deadline quá giới hạn nền tảng.

## Tải kết quả

- `comparison_tables.md`: năm bảng cố định A–E để đọc/copy.
- `comparison_tables.csv/json`: số liệu và nhãn/trạng thái để làm bảng báo cáo.
- `retrieval_by_k.csv`: nhiều K, số câu và CI.
- `paired_comparisons.csv/json`: delta và khoảng tin cậy trên các câu chung.
- `ablation/common_judged_comparison.json`: các cấu hình được chấm trên cùng câu; phải xem trước khi kết luận.
- `metric_definitions.json`, `protocol.json`, source/config hashes: định nghĩa và bằng chứng tái lập.
- ZIP `evaluation_...zip`: toàn bộ input đo đã chuẩn bị, câu hỏi, câu trả lời, thời gian, judge và traces. Giữ ZIP này để audit/resume.

Fact Coverage/Evidence Precision mặc định N/A cho đến khi bạn bổ sung annotation đúng theo PROTOCOL.md. Đây là thiếu nhãn để đo, không phải chương trình hỏng. Không lấy group recall/citation recall gán vào hai cột này.

## Tiếp tục khi gián đoạn/quota

1. Tải `evaluation_...zip` trước khi đóng phiên. Chờ quota provider hồi phục nếu bị giới hạn ngày; sửa key/quyền nếu lỗi cấu hình.
2. Add ZIP đó như một Input riêng cùng Dataset OFFLINE cũ. Notebook auto-detect artifact chỉ nhận kết quả OFFLINE, không nhận ZIP evaluation làm corpus.
3. Trong notebook v2 đặt `RESUME_EVALUATION_ZIP='/kaggle/input/.../evaluation_...zip'`.
4. Giữ code, Gold, model/provider và settings của lần đo; Run All. Suite so hash và cấu hình. Câu đã có phản hồi thành công, kể cả từ chối/partial, không được chạy lại để chọn kết quả đẹp hơn. Judge tiếp tục phần chưa chấm.
5. Nếu đổi ONLINE/OFFLINE/model hoặc Gold, để `RESUME_EVALUATION_ZIP=None` và tạo run mới. Không trộn với kết quả cũ. ZIP từ runner v1 không được resume vào v2.

Vẫn phải duyệt Gold và bổ sung nhóm lịch sử, đa yêu cầu, đối thoại nếu muốn khẳng định bao phủ miền. Code benchmark chuẩn hóa cách đo; không tự biến dữ liệu DRAFT thành chuẩn pháp lý.
