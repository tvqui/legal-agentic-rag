# Đo ONLINE sau lần khởi động lại — 20/10/2026

> Cập nhật sau khi người dùng xác nhận hạn mức 13 RPM: chính sách dừng ở 429 đầu tiên dưới đây là lịch sử. Bản hiện tại dùng pacing chung và retry có giới hạn (`paced-retry-v2`). Xem [bản sửa RPM](gemini-rate-limits-20261020.md); schema HTTP 400 và các sửa pháp lý khác vẫn giữ nguyên.

## Xác nhận triển khai

Backend chạy được, `/health` và `/ready` HTTP 200. `/ready` có `assessment_fact_gate=critical-facts-v1`, `probation_scope=dated-job-group-v1`, đúng artifact build `9a615f1927162fe63e73b734b6a48759596984fbf2d004ce76bc2eb94e0e5da0`. Researcher và answer reviewer dùng Gemini; Auditor/Adjudicator vẫn Qwen3:8b. Local commit khi bắt đầu đo: `227b48a`.

Không cần mở frontend để đo trực tiếp HTTPS. Ba health probe trước lượt chính mất 0,704; 0,656; 0,687 giây; không có dấu hiệu mất kết nối tại lúc kiểm tra. Đó không phải cam kết độ trễ mạng trong mọi thời điểm.

## Năm câu người dùng

| ID | Nội dung | HTTP | Giây | Kết quả quan sát |
|---|---|---:|---:|---|
| USER-1 | Đầy đủ Điều 1 Nghị định 145 | 200 | 0,922 | Có mở đầu và 10 khoản, 11 citation; giữ cảnh báo nguồn/hiệu lực chưa duyệt. |
| USER-2 | Luật áp dụng ngày 15/12/2020 | 200 | 4,735 | Dùng Bộ luật 2012, khoản 3 Điều 37 và ngoại lệ Điều 156; không thay bằng luật áp dụng từ 2021. |
| USER-3 | Báo trước 20 ngày và hậu quả | 200 | 3,766 | Đúng chủ thể người lao động; có Điều 35, 39 và ba khoản Điều 40; không nhầm thỏa thuận chấm dứt. |
| USER-4 | Thử việc 90 ngày, lương 80% | 200 | 2,906 | Nêu rõ 90 vượt 60 ngày đối với nhóm cao đẳng; 80% thấp hơn 85%; hai phần có căn cứ riêng. Lượt trước mất 100,063 giây. |
| USER-5 | Nối tiếp: thử việc lần nữa | 200 | 1,985 | Giữ ngữ cảnh, dẫn Điều 25 về một lần cho một công việc; không trả danh sách mọi thời hạn như trước. |

Tổng năm request: 14,314 giây; median 2,906 giây. Đây là số đo HTTP thật, không lấy thời gian fixture/local thay cho Kaggle. Các câu vẫn PARTIAL_ALLOWED vì nguồn/hiệu lực chưa được người có chuyên môn duyệt; không tự đổi thành SUFFICIENT.

## Lượt mở rộng và lý do dừng

Đã gửi 33/290 câu: 5 USER, 25 OLD và NEW-1.1 đến NEW-1.3. Tất cả nhận HTTP 200, nhưng không phải tất cả có nội dung đạt yêu cầu:

- 24 PARTIAL_ALLOWED;
- 3 NEED_MORE_FACTS;
- 5 ABSTAIN;
- 1 INSUFFICIENT_EVIDENCE.

33 request cộng 274,517 giây. Còn **257 câu chưa đo** trong lượt này. Runner dừng tại NEW-1.3 vì nhận mã `GEMINI_HTTP_429`; không gọi dồn tiếp khi provider giới hạn lượt gọi.

Trong lượt mở rộng có các probe chẩn đoán schema chạy đồng thời với benchmark; chúng cũng tiêu thụ hạn mức Gemini. Vì vậy không dùng toàn bộ lượt 33 câu làm benchmark tốc độ khi không có tải phụ, hoặc suy ra quota theo ngày từ một HTTP 429. Năm USER đã đo trước các probe này. OLD-2.3 có khoảng 53,8 giây retrieval do lần đầu nạp BM25/BGE/reranker; không gọi đó là chậm mạng hoặc thời gian warm.

Đầu ra trong `artifacts/online_benchmarks/reliability_20261020/candidate2/`:

- `responses.jsonl`: đầy đủ question, history, response, progress, trace và thời gian;
- `responses.csv`: bảng đối chiếu từng câu;
- `responses.md`: từng câu hỏi/câu trả lời cùng locator và URL nguồn;
- `summary.json`: số câu đã đo, chưa đo và phân bố trạng thái;
- `preflight.json`: cấu hình của lượt đo.

## Lỗi tiếp tục xác nhận và sửa

### Schema Gemini Researcher bị từ chối

Gemini probe đơn giản thành công, nhưng schema Researcher thật trả HTTP 400. Các probe đối chứng xác nhận schema gốc bị từ chối; bỏ `maxItems` trên bản schema gửi đi thì được chấp nhận. Bỏ riêng nhánh union số hoặc giới hạn độ dài chuỗi không giải quyết lỗi trong phép thử. Điều này khoanh vùng vấn đề ở tổ hợp schema giải mã của model hiện tại, không phải API key không hoạt động hay mọi model Gemini đều cấm `maxItems`.

Sửa `GeminiProvider`: tạo bản sao schema cho request, bỏ `maxItems` trên bản gửi đi, sau đó kiểm tra kết quả với **toàn bộ schema gốc** bằng `Draft202012Validator`. Pydantic và các kiểm tra dữ kiện/grounding vẫn chạy như cũ. Giới hạn số phần tử, kiểu, enum, required, cấm trường lạ và ràng buộc lồng nhau vẫn được thực thi; dữ liệu không hợp lệ bị chặn. Không đổi schema nghiệp vụ, không bỏ số task hay tự duyệt claim.

Đã thêm `jsonschema>=4.23.0,<5` vào extras `online` và `full`. Probe thật qua provider đã sửa và validation gốc thành công trong 2,000 giây; đây là probe tương thích, không phải phép chứng minh suy luận pháp lý đúng.

Tài liệu tham khảo: [Gemini structured output và giới hạn độ phức tạp schema](https://ai.google.dev/gemini-api/docs/structured-output), [kiểm schema gốc bằng jsonschema](https://python-jsonschema.readthedocs.io/en/stable/validate/).

### Quota bị diễn giải thành thiếu bằng chứng và chờ dài

NEW-1.3 gặp Gemini HTTP 429 ở Researcher, sau đó vẫn chờ Qwen applicability khoảng 125,7 giây và trả INSUFFICIENT_EVIDENCE. Khi reviewer bắt buộc cũng dùng Gemini, nhánh này không thể cung cấp câu trả lời đã kiểm trong lúc cùng provider không nhận thêm request.

Sửa để dừng sớm khi có rate limit trong trường hợp đó, hoặc khi reviewer bị rate limit. API trả HTTP 503 với category `PROVIDER_RATE_LIMIT`, mã lỗi riêng và thông báo tiếng Việt; không nói thiếu căn cứ pháp lý cho một lỗi dịch vụ. `Retry-After: 60` là thời gian chờ tối thiểu của ứng dụng, không đảm bảo quota đã phục hồi sau 60 giây. Không tự chuyển model, bỏ semantic review hoặc gọi retry vô hạn. Researcher dự phòng vẫn được giữ khi reviewer dùng provider khác.

### Phân biệt bối cảnh với yêu cầu độc lập

Một câu xác định bản chất hợp đồng có thể chỉ nhắc tiền lương như một dấu hiệu của quan hệ lao động. Bổ sung các cách nói hợp đồng dịch vụ/cộng tác viên, doanh nghiệp và “mang tên”; không tự biến mọi câu đó thành yêu cầu tính/trả lương độc lập. Nếu hỏi thêm tiền lương tối thiểu, tính/trả/đòi lương thì yêu cầu đó vẫn phải giữ riêng.

Đăng ký căn cứ mức nghỉ năm dùng làm tham số tỷ lệ vào đường truy xuất đã kiểm chứng; vẫn đòi đủ chain mức nền + quy định tỷ lệ + công thức. Không nạp model/truy xuất rộng nếu chain đã đầy đủ và kiểm tra ngày/nguồn đã thực hiện.

### Bản OCR lỗi bị thêm lại sau khi đã chọn nguồn sạch

OLD-4.1 còn trích thêm một bản có “Đỉều 1l4”, dù đã có bản cùng căn cứ rõ chữ. Giữ đoạn đã thỏa slot, chỉ thêm đoạn mới khi nó nâng cấp mức xác minh; không thêm duplicate chưa duyệt chỉ vì score cao. Bổ sung phát hiện số điều/khoản lẫn chữ ở giữa các chữ số. Không tự sửa `1l4` thành `114`, không viết lại corpus, không gán authority PASS cho nguồn chưa duyệt.

## Kiểm chứng và triển khai tiếp

Toàn bộ suite: **566/566 PASS**, 0 failure/error; log `artifacts/reports/reliability_20261020_gemini_contract_tests.log`. Các test gồm schema gốc bất biến, array quá giới hạn bị chặn sau khi nhận, giữ required/type/enum, quota dừng trước fallback đắt, API báo riêng lỗi provider, không đánh rơi yêu cầu lương độc lập và không đưa lại bản OCR lỗi.

Đối chứng trên ZIP thật ở `local_source_control_gemini_contract.json`: 8 câu, không model call; các rule chain thử việc, nghỉ tỷ lệ và bản chất hợp đồng không gọi broad retrieval. Đây không phải remote benchmark hay phê duyệt chuyên môn.

Code đã sửa trong `D:\data_thô\legal-agentic-rag`, chưa tự commit/push. Giữ nguyên API key, model và Input result_14-10; không chạy lại OFFLINE.

```powershell
cd D:\data_thô\legal-agentic-rag
git add pyproject.toml src/vn_labor_online tests/online/test_gemini_contract.py docs/online/reliability-run2-20261020.md docs/online/reliability-review-20261020.md
git commit --only pyproject.toml src/vn_labor_online tests/online/test_gemini_contract.py docs/online/reliability-run2-20261020.md docs/online/reliability-review-20261020.md -m "Fix Gemini schema compatibility and fail fast on provider quota"
git push
```

Trên Kaggle chạy lại cell cập nhật/cài thư viện rồi cell backend. `/ready.online_features` phải thêm `gemini_schema_contract=local-validation-v1` và `provider_capacity=fail-fast-v1`. Không cần thêm API hay upload dữ liệu khác.

Lượt tiếp theo ghi vào `candidate3/`, không trộn kết quả phiên bản cũ. Đo lại 5 câu và các câu lỗi trước, sau đó mở rộng tiếp toàn bộ bộ câu hỏi với nhịp gọi phù hợp hạn mức API. Chưa kết luận toàn bộ 290 câu đúng/đủ; các queue human review/Gold chưa hoàn tất.
