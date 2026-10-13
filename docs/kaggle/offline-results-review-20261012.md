# Đánh giá kết quả OFFLINE ngày 12/10/2026

Bản `vn_labor_results.zip` mới **dùng được cho phát triển và kiểm thử ONLINE ở chế độ provisional**. Bộ nạp ONLINE kiểm tra độc lập cho kết quả `compatible=true`, `issues=[]`. Registry, structure, graph, Dense, BM25 và bản xác minh Aura trong ZIP đều PASS. **AI enrichment chưa hoàn tất; chất lượng pháp lý/câu trả lời chưa được chứng nhận.**

## So sánh với V8.1 Aura

| Chỉ số | V8.1 | Bản mới |
| --- | ---: | ---: |
| File nguồn | 95 | 95, cùng SHA từng file |
| Điều/khoản/điểm đã đưa vào cấu trúc | 18.449 | 18.871 |
| Bản ghi tra cứu, gồm provision/case/annex/form | 18.624 | 19.160 |
| Provision có trong cấu trúc nhưng thiếu bản ghi tra cứu | 113 | 0 |
| Bản án | 24 | 24 |
| Diagnostic items | 15.130 | 15.178 |
| Graph nodes | 50.118 | 50.900 |
| Graph edges | 76.844 | 78.227 |

Số lượng tăng và đủ bản ghi tra cứu là cải thiện có thể đo được. Không đồng nghĩa mọi đoạn OCR hoặc cấu trúc đều đúng. Đây vẫn là cùng bộ nguồn, chưa bổ sung tài liệu pháp luật mới chỉ vì ngày chạy mới hơn.

## Kiểm tra thực hiện

- Cả ba ZIP (V8.1, checkpoint, final): kiểm CRC toàn bộ, không có entry trùng tên.
- Đối chiếu SHA của cả 95 file nguồn giữa V8.1 và final: giống nhau.
- Bộ nạp ONLINE hiện tại đọc ZIP final bằng thư mục tạm; tính lại fingerprint graph/retrieval, kiểm node/edge/nguồn và thứ tự Dense/BM25. Không dùng fingerprint V8.1 để ép bản mới qua gate.
- Đọc FAISS index thực tế: 19.160 vector, 1.024 chiều. Thử tự tìm lại 3 vector đầu/giữa/cuối: trả đúng ID, điểm xấp xỉ 1, vector hữu hạn và đã chuẩn hóa. Đây là smoke test tính nhất quán, không phải đánh giá độ đúng của truy xuất pháp lý.
- Báo cáo validation có 1 INFO, 43 WARN, không có ERROR.
- Aura validation trong ZIP xác nhận 50.900 node, 78.227 edge và cùng build graph. Không truy cập lại Aura trực tiếp trong lần đánh giá này.

## Những điểm chưa đạt

### 1. AI enrichment bị giới hạn bởi nhiều yêu cầu không hoàn thành

`quality_status=AI_DEGRADED`, `ai_quality.complete=false`.

- Checklist: kế hoạch 250 provision; thử 31; thành công 11; fallback 20; chưa thử 219 do circuit breaker mở.
- Case ontology: kế hoạch 56 chunk cho 24 bản án; hoàn thành 3 chunk, tạo 29 thuộc tính được chấp nhận. Có 3 bản án được xử lý một phần; **0/24 bản án hoàn tất toàn bộ chunk**.
- Ollama log: 45 request `/api/chat`, 14 HTTP 200 và 31 HTTP 500. Cả 31 lỗi xảy ra ở đúng `2m0s`; log có thao tác hủy request.
- Đây là bằng chứng mạnh về giới hạn 120 giây cho từng request. Báo cáo chất lượng chỉ lưu `LLMProviderError`, chưa giữ nguyên thông điệp lỗi, nên không thể khẳng định nguyên nhân nội bộ của từng request.
- Model được offload 37/37 layer lên GPU, context 32.768; không có bằng chứng model chạy toàn bộ trên CPU. Có cảnh báo áp lực RAM host khi nạp model. Không nên kết luận lỗi do thiếu API key hoặc thiếu GPU từ các log này.

Ưu tiên kế tiếp: lưu loại/nguyên nhân lỗi và thời gian từng chunk; thử nhỏ các chunk từng thất bại; chia nhỏ đầu vào nhưng giữ đầy đủ coverage, source quotes và liên kết giữa chunk; chọn thời hạn request từ thời gian đo thực tế và ngân sách tổng. Code hiện đã gửi `think=false`, nên bật lại tùy chọn này không phải một sửa chữa mới. Chỉ tăng ngân sách 250/2.000 provision sau khi smoke test chứng minh tỷ lệ thành công ổn định. Tăng timeout đơn thuần có thể làm hết giờ Kaggle; vẫn cần checkpoint/resume và circuit breaker.

### 2. Extraction có cơ chế phát hiện vấn đề, chưa bảo đảm nội dung hoàn hảo

3.116 trang: 2.927 PASS, 15 có trạng thái REVIEWED sẵn, **174 REVIEW_REQUIRED**, 0 ERROR. Trạng thái REVIEWED sẵn không phải approval do người đánh giá này tạo.

Các lý do đáng chú ý: native/OCR ít tương đồng, tỉ lệ chữ/số thấp, ký tự lặp. Tổng số lượt lý do có thể lớn hơn 174 vì một trang có nhiều lý do. Trang chỉ chứa số trang đã được phân biệt với mất nội dung nhưng vẫn cần review.

Quarantine có 33 cảnh báo đường dẫn điều khoản mơ hồ và 9 cảnh báo provision quá ngắn, tăng so với 32 và 4 ở V8.1. Không lấy việc tăng quarantine làm bằng chứng chắc chắn chất lượng xấu hơn hay tốt hơn; cần đối chiếu các case với ảnh nguồn.

Mẫu đọc trực tiếp: Điều 124 của `18/VBHN-VPQH` có đủ bốn khoản trong retrieval, gồm các khoản rất ngắn. Tuy nhiên, Điều 62 khoản 2 điểm đ của cùng văn bản vẫn chứa dòng chú thích cuối trang bắt đầu `33 Khoản này được sửa đổi, bổ sung...` trong text của bản ghi tra cứu. Nên tách chú thích thành metadata/evidence sửa đổi với liên kết vị trí; không xóa mù vì nó có thông tin hiệu lực quan trọng. Đây là vấn đề tổng quát cần kiểm tra trên corpus, không sửa đáp án riêng cho một câu hỏi.

### 3. Chất lượng pháp lý và truy xuất chưa được đánh giá bằng Gold được duyệt

- Source catalog: 0/95 verified; 61 nguồn thuộc nhóm authority chưa xác minh.
- Temporal: 25 thay đổi chờ duyệt; 18.871 provision versions chưa được review hiệu lực.
- Gold: 0 approved queries; `NOT_EVALUATED`.
- Corpus bản án vẫn chỉ có 24 bản án.

`offline_ready_for_online=false` là kết luận đúng về readiness đầy đủ. Vẫn có thể kiểm thử ONLINE provisional, giữ cảnh báo nguồn/hiệu lực và không trình bày một câu trả lời thiếu bằng chứng như kết luận đã xác minh. Cần chạy lại cùng bộ benchmark ONLINE trên build mới, so sánh đúng chủ thể, ngày áp dụng, coverage của yêu cầu, trích dẫn và lỗi OCR; tốc độ hoặc số citation không thay thế chất lượng nội dung.

### 4. Có thể giảm kích thước ZIP final

`06_indexes/dense/vectors.partial.npy` trùng SHA với `vectors.npy`, mỗi file 78.479.488 byte chưa nén. Khi export final đã xác minh, có thể bỏ bản partial khỏi ZIP final; giữ nó trong cache/checkpoint để resume khi cần. Đây là tối ưu dung lượng, không làm nội dung pháp lý chính xác hơn.

## Dùng file nào và chuyển ONLINE thế nào

1. Dùng **`D:/data_thô/result_12-10/vn_labor_results.zip`** cho ONLINE. Checkpoint kỹ thuật là bản trước AI/Aura cuối, giữ để khôi phục, không thay cho final đã xác minh.
2. Tạo cấu hình pin riêng cho artifact mới, không chỉ đổi đường dẫn ZIP mà giữ các fingerprint cũ. Ví dụ tại thư mục repo:

```powershell
.\.venv\Scripts\python.exe scripts/pin_online_artifact.py `
  --artifact "D:/data_thô/result_12-10/vn_labor_results.zip" `
  --base-config config/online.yaml `
  --output config/online_release_20261012.yaml
```

Sau đó chọn config mới khi chạy ONLINE theo launcher hiện hành. Cấu hình pin không tự cập nhật corpus snapshot date: ngày chạy 12/10 không chứng minh dữ liệu được cập nhật pháp luật đến 12/10. Với Kaggle, tạo pin từ đường dẫn Input thực tế bằng base config `config/online_kaggle.yaml`. Không trộn graph/index của hai build.

3. Kiểm `online-check`/readiness bằng config mới, sau đó benchmark. Lần đánh giá này chưa chuyển config đang dùng hoặc gọi API trả lời câu hỏi.

Build mới:

```text
0097f69c34331ab8dfe715d6caf01ef79a57f34964e901ed8cba6ce66cc25060
```

SHA-256 ZIP final:

```text
f2cc20f15050fd4c3faaf79c21673ee22188aed32028d60786cab32cd415c569
```

Báo cáo máy đọc: `artifacts/reports/offline_results_review_20261012.json`. Không sửa corpus, catalog, ZIP đầu vào, cấu hình ONLINE đang dùng hoặc Aura trong lần đánh giá này. Không chạy lại OFFLINE, tải model, gọi LLM hay tạo approval thay reviewer.
