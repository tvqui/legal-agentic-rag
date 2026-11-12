# Đánh giá và áp dụng đề xuất phân công model

## Kết luận

Áp dụng cơ chế chọn model riêng từng vai trò, chưa thay mặc định toàn hệ thống.
Không có phép đo inference thật chứng minh bốn model đề xuất tốt hơn cấu hình đang chạy.
Số tham số, RPM hoặc số yêu cầu/ngày không phải thước đo độ đúng pháp lý.

| Đề xuất | Đánh giá và xử lý |
|---|---|
| Gemini 3.5 Flash-Lite cho Researcher và trích xuất | Có thể thử; hỗ trợ đầu ra có cấu trúc. Bổ sung cấu hình thử ONLINE; chưa chuyển toàn bộ OFFLINE vì cần đo chất lượng trích xuất, ngân sách và khả năng tiếp tục. |
| Gemma 4 31B cho Auditor/Adjudicator | Google xác nhận có API. Chưa xác minh hợp đồng JSON schema cho các tác vụ thực tế, độ đúng luật tiếng Việt và quota tài khoản, nên chưa bật. Không suy ra model tốt hơn từ 31B hoặc hạn mức ngày cao. |
| Gemini 3.8 Flash cho hậu kiểm/đánh giá | Có thể cấu hình riêng; đã sửa request để bỏ sampling cũ. Chưa bật mặc định, chưa thêm chuyển model tự động. Dùng làm AI judge chỉ là chấm tham khảo; phải cố định judge khi so sánh. |
| Gemini Embedding 2 thay BGE-M3 | Chưa thay: không gian vector khác, cần mã hóa lại cả corpus và truy vấn, xây lại FAISS và fingerprint rồi đo Retrieval. Cùng số chiều cũng không làm hai không gian tương thích. |
| Antigravity thay agent nghiệp vụ | Không thay: công cụ phát triển không thay thế kiểm tra nguồn/hiệu lực và vai trò agent hiện tại. |

Quotas trong đề xuất chưa được xác thực cho tài khoản đang dùng. Quota thuộc project/model,
không nhân lên bằng nhiều API key hoặc nhiều agent. RPM, TPM và hạn mức ngày độc lập.
Ví dụ 16.000 token đầu vào/phút với 2.500 token mỗi lượt chỉ cho khoảng 6 lượt/phút
duy trì, dù RPM là 30. Bộ điều tiết hiện tại giới hạn RPM và xử lý phản hồi TPM/RPD;
**chưa đặt trước ngân sách token TPM**, chưa phối hợp hạn mức giữa nhiều tiến trình.

## Đã sửa trong mã

- Model riêng theo vai trò không còn bị biến `GEMINI_MODEL` chung ghi đè. Khi đổi
  provider Ollama sang Gemini bằng ENV, vẫn lấy model Gemini chung thay vì giữ tên Qwen.
- Auditor và Adjudicator có thể dùng Google API trực tiếp. Auditor vẫn qua cổng
  quy tắc cứng/hybrid trước; không bỏ kiểm tra nguồn, thời gian hoặc hậu kiểm kết luận.
- Bỏ sampling cũ cho các họ Gemini mới; giữ JSON schema và validation tại máy chủ.
  HTTP 400 không tự hạ xuống trả văn bản tự do.
- Thêm `VN_LABOR_GEMINI_MODEL_RPM` để đặt RPM riêng từng model, vẫn dùng cổng chung
  giữa các vai trò cùng project/model, giữ deadline và giới hạn thử lại.
- Script tạo cấu hình thử không gọi API, không đổi artifact/fingerprint/embedding,
  không sao chép API key và không ghi đè cấu hình gốc.

## Cách dùng sau khi đã chốt phép đo hiện tại

Chạy tại thư mục gốc repository. Dùng **config đã pin đúng artifact hiện tại**:

```bash
python scripts/configure_online_models.py \
  --base-config /kaggle/working/online_pinned.yaml \
  --output /kaggle/working/online_models_trial.yaml
```

Mặc định bốn vai trò dùng `gemini-3.5-flash-lite` để có một mốc thử đơn giản.
Muốn thử riêng hậu kiểm 3.8, thêm `--reviewer gemini-3.8-flash` và dùng tên output mới.
Script từ chối Gemma trong profile này cho đến khi xác minh hỗ trợ schema;
không tự giảm yêu cầu kiểm chứng để ép model chạy.

Trước khởi động trong notebook, lấy `GEMINI_API_KEY` từ Kaggle Secrets như hiện tại.
Xóa các `VN_LABOR_RESEARCHER_*`, `VN_LABOR_APPLICABILITY_*`,
`VN_LABOR_ADJUDICATION_*` ghi đè mode/model/provider cũ nếu muốn dùng đúng profile.
Không xóa API key. Ví dụ RPM dưới đây chỉ minh họa, cần đối chiếu AI Studio:

```python
import os, json
os.environ['VN_LABOR_GEMINI_MODEL_RPM'] = json.dumps({
    'gemini-3.5-flash-lite': 13,
    'gemini-3.8-flash': 4,
})
```

Đưa config thử vào tham số `--config` của cell backend. Lưu ý `kaggle/online_remote.py`
hiện vẫn khởi động Ollama ngay cả khi profile dùng toàn API; tính năng bỏ Ollama của
launcher chưa được triển khai. Có thể chạy API trực tiếp trong môi trường đã chuẩn bị:

```bash
python -m vn_labor_online.cli --config /kaggle/working/online_models_trial.yaml serve --host 0.0.0.0 --port 8000
```

Lệnh trên chỉ mở API, không tạo ngrok. Profile toàn API không cần VRAM cho LLM nhưng
embedding/reranker vẫn dùng GPU theo config gốc. Khởi động và kiểm tra `/ready` trước
khi gửi câu hỏi; probe đạt chỉ chứng minh khả dụng, không chứng nhận độ đúng pháp lý.
Nếu không đạt thì quay lại config gốc, không bỏ validation hoặc tắt semantic review.

## Điều kiện kết luận có cải thiện

Đo A/B trong thư mục kết quả mới: cùng artifact, tập câu hỏi, nhãn, truy xuất, prompt,
phần cứng và giới hạn thời gian; chỉ đổi model ở một vai trò mỗi lần. Ghi tỷ lệ lỗi,
câu được kiểm chứng, đúng/đủ từng yêu cầu, trích dẫn, thời gian p50/p95, số gọi/token.
Giữ câu hỏi mới ngoài tập phát triển. Không gộp kết quả trước/sau đổi model thành một
lần chạy đồng nhất. Giữ cấu hình cũ nếu cải thiện chưa vượt biến động hoặc chỉ nhanh
hơn vì từ chối nhiều hơn.

## Nguồn chính thức đã đối chiếu

- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://aistudio.google.com/docs/whats-new-gemini-3.8
- https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api
- https://ai.google.dev/gemini-api/docs/embeddings
- https://ai.google.dev/gemini-api/docs/rate-limits

Kiểm thử local dùng SDK giả lập; không gọi model thật, không tiêu quota người dùng.
