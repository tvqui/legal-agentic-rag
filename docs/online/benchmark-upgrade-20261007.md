# Rà soát benchmark và nâng cấp ONLINE — 2026-10-07

Đã đối chiếu nhận xét với **toàn bộ 285 response JSONL** của lần chạy
`labor_285_fresh_20261007T100534Z`, đọc code hiện tại, sửa ONLINE và kiểm tra
trên bộ dữ liệu V8.1. Không chạy lại pipeline OFFLINE, không sửa nguồn,
metadata pháp lý, Gold, model/index hoặc Aura.

## 1. Đánh giá nhận xét

Nhận xét đúng ở các điểm: căn cứ dư/thừa bản gốc–VBHN; một số câu chọn sai chủ
thể hoặc thiếu chuỗi dẫn chiếu; phân loại hợp đồng nhầm thử việc thành loại thứ
ba; suy diễn quan hệ lao động từ tên thực tập; gọi mô hình quá nhiều cho câu
đã biết rõ; format lỗi và fallback làm câu trả lời dài, khó đọc.

Số đo cũ: **285 HTTP 200**, median **30.449s**,
mean **29.309s**. Có **182** warning
`ADJUDICATION_PROVIDER_FALLBACK:StructuredOutputError` và **32** warning
`APPLICABILITY_PROVIDER_ERROR:StructuredOutputError`. HTTP 200 chỉ xác nhận
request được xử lý, không chứng minh trả lời đúng pháp luật. Lần benchmark
cũ không có timing adjudication riêng: không thể quy toàn bộ thời gian còn
lại cho LLM hoặc khẳng định fallback là nguyên nhân duy nhất.

Những điểm cần hiệu chỉnh trong đề xuất:

- JSON Schema thật, `think=false`, temperature 0, Dense + BM25 + RRF, neural
  reranker, phân tách Điều/Khoản/Điểm và graph budgets **đã có trong code**.
  Lỗi còn nằm ở độ phức tạp schema, ràng buộc ngữ nghĩa và chọn căn cứ.
- `conditions_status=NOT_APPLICABLE` nghĩa là không có tiền đề đó cần chứng
  minh; **không đồng nghĩa căn cứ không áp dụng**. Phải xét relevance, support
  và audit status. Quy định định nghĩa hoặc nguyên tắc chung vẫn có thể PASS.
- Không gộp hai phiên bản chỉ vì cùng số Điều. Nội dung và khoảng hiệu lực
  khác nhau phải giữ riêng; conflict detector vẫn xem toàn bộ căn cứ trước
  khi chọn gói trả lời. VBHN không tự động có thẩm quyền cao hơn bản gốc.
- Không ép mọi câu xuống 2–3 căn cứ: chuỗi Điều 35 → 39 → 40 cần giữ đủ cả
  ba khoản hậu quả, tương ứng 5 căn cứ trong phép thử.
- Fallback ở đây là bản trả lời theo quy tắc, không phải một LLM dự phòng.
- Cache và parallel retrieval có thể nghiên cứu tiếp; chưa bật thêm trong
  vòng này vì cần đo trên T4, kiểm soát bộ nhớ/model lock và phân biệt query
  date/build/facts/context. Không đổi an toàn của truy vấn lấy tốc độ.
- Median <10s là mục tiêu cho lần benchmark mới, chưa phải kết quả đã đạt.
  Chưa có expert Gold nên chưa tính precision pháp lý như một kết quả khoa học.

## 2. Các sửa đã áp dụng

1. Taxonomy `labor-subissues-v2`: thêm 6 profile hợp đồng (27 profile tổng).
   Chỉ định đúng locators theo Bộ luật 2012/2019; câu đặt cọc chỉ cần khoản 2
   Điều 17; tra cứu lịch sử 2020 dùng khoản 3 Điều 37 và ngoại lệ Điều 156
   của Bộ luật 2012. Topic là hướng tìm căn cứ, không tự chứng minh sự kiện.
2. Fast path: thử chuỗi nguồn hiện có qua temporal, authority, structural,
   applicability và slot checks. Chỉ bỏ tìm kiếm neural khi chuỗi đã đủ và
   được quy tắc có phạm vi rõ nhận diện. Nếu thiếu, vẫn chạy hybrid/graph.
3. Researcher adaptive: bỏ gọi mô hình cho scope/fact gate, exact lookup và
   profile rõ ràng; giữ mô hình cho câu mơ hồ, so sánh và tìm án lệ.
4. Lean structured output: Adjudicator chỉ trả `claims[text,evidence_ids]`.
   Code cấp claim IDs, law versions, assumptions, limitations và render.
   Auditor trả object keyed by candidate IDs; code suy ra PASS/FAIL/UNRESOLVED
   từ relevance/support/condition/exception. Không nhận IDs thừa hoặc thiếu.
5. Giới hạn sinh Ollama theo từng vai trò: Researcher 1024, Auditor 1536,
   Adjudicator 2048 tokens. Có thể cấu hình `max_output_tokens` hoặc
   `VN_LABOR_{ROLE}_MAX_OUTPUT_TOKENS`. Truncation/JSON key trùng bị từ chối.
6. Fail-closed: model auditor lỗi không được nâng lexical match yếu thành
   bằng chứng đạt. Chỉ giữ quy tắc deterministic đã chứng minh và hard exclusions.
   Pack cuối loại FAIL, UNRESOLVED, irrelevant/unsupported và decision bị thiếu.
7. Gói profile giữ đủ các nhóm căn cứ bắt buộc, không thêm căn cứ chỉ để đủ
   Top-6/12. Dedup cùng nội dung/vị trí/khoảng hiệu lực trong cùng code family;
   không gộp fuzzy OCR hoặc bỏ các nội dung thay đổi.
8. Chọn nguồn cùng locator ưu tiên metadata đã duyệt/thẩm quyền trước, rồi
   dấu hiệu OCR và điểm truy xuất. Ví dụ khoản 2 Điều 3 lấy bản hiện có đủ
   “năng lực hành vi dân sự”, thay vì sửa đoán bản OCR đang thiếu chữ.
9. Rule answers cho các khái niệm hợp đồng trọng điểm. Không coi thử việc là
   loại hợp đồng thứ ba; không kết luận thực tập sinh chắc chắn là/không là
   NLĐ chỉ từ tên; khoản tiền bảo đảm phải xét bản chất. Thông tin tuyển dụng
   sai cần kiểm tra ảnh hưởng đến thực hiện hợp đồng trước khi kết luận được
   nghỉ ngay. Không tự tạo approval/source/temporal verification.
10. Answer coverage: claims cuối phải thực sự dẫn các locators bắt buộc.
    Nếu thiếu, thử một bản theo quy tắc với cùng pack; vẫn thiếu thì chặn.
    Chuỗi Điều 16 + điểm g khoản 2 Điều 35 không bị nhánh hợp đồng làm mất.
11. Trace thêm execution path Researcher; profile probe; các kênh được yêu
    cầu/bỏ qua; timing BM25, Dense, fusion, reranker, adjudication; selected IDs.

Files chính: `analysis.py`, `taxonomy.py`, `researcher.py`, `applicability.py`,
`evidence.py`, `models.py`, `providers.py`, `generation.py`, `pipeline.py`,
`config.py` trong `src/vn_labor_online/`.

## 3. Kiểm chứng

- Repository: **315/315 tests PASS**, gồm **21 test mới** về precision,
  fail-closed, schema, OCR alternative, historical locators, required output
  coverage và việc không gọi mô hình khi không cần.
- Dữ liệu thật V8.1: 9 câu, đúng bộ locators mong đợi, 9 reference audits PASS,
  0 call Dense/reranker/LLM. Mọi câu vẫn `PARTIAL_ALLOWED` do review chưa xong.
- Python compile và `git diff --check` được kiểm riêng.

| Câu | Thời gian local (s) | Số căn cứ | Locator/reference check |
| --- | ---: | ---: | --- |
| NEW-1.1 | 0.062 | 2 | PASS |
| NEW-2.3 | 0.114 | 2 | PASS |
| NEW-2.4 | 0.051 | 1 | PASS |
| NEW-2.5 | 0.053 | 1 | PASS |
| NEW-3.1 | 0.082 | 2 | PASS |
| NEW-5.5 | 0.030 | 1 | PASS |
| ANNUAL | 0.079 | 3 | PASS |
| EMPLOYEE_EXIT | 0.146 | 5 | PASS |
| HISTORICAL | 0.109 | 2 | PASS |

**Giới hạn phép đo:** thời gian trong bảng chỉ tính `ask()` sau khi nạp
artifacts, trên máy local, với provider bị chặn và đường deterministic.
Không bao gồm startup, mạng, mô hình, Kaggle hoặc cold inference. Không dùng
bảng này để tính speedup so với 285 câu chạy T4 trước đó hoặc tuyên bố accuracy
toàn hệ thống. Cần chạy lại benchmark đầy đủ trên cùng Kaggle sau cập nhật.

Artifacts kiểm chứng: `artifacts/reports/online_benchmark_upgrade_validation.json`,
`artifacts/online_benchmarks/online_upgrade_local_smoke_20261007.jsonl`.

## 4. Đưa sửa lên backend Kaggle

1. Trên local, kiểm diff, commit và push các thay đổi trong `legal-agentic-rag`.
   Không commit `.env`, API keys, model/cache hoặc dữ liệu runtime.
2. Dừng **cell server ONLINE** đang chạy trên Kaggle để phiên cũ không còn
   giữ port. Trong checkout hiện tại chạy:

```python
%cd /kaggle/working/legal-agentic-rag
!git pull --ff-only
!python -m pip install -q -e ".[retrieval,online]"
!python -u kaggle/online_remote.py --skip-pull
```

`--skip-pull` chỉ bỏ tải lại model Ollama; dùng khi model đã có trong phiên.
Nếu runtime mới chưa có model, bỏ flag này. Secrets và Input V8.1 giữ như
trong hướng dẫn hiện có. Không chạy hai cell server cùng lúc.

3. Chờ backend/tunnel READY. Nếu URL đổi, cập nhật `VITE_BACKEND_TARGET` và
   khởi động lại frontend; nếu URL giữ nguyên thì frontend không cần sửa code.
4. Gửi thử câu hỏi; trace phải có `taxonomy_version=labor-subissues-v2`.
   Với câu rõ ràng, event `profile_fast_path.used=true` là chủ đích; không
   phải thiếu hiệu suất. Câu phức tạp chưa đủ slot vẫn dùng các kênh neural.
5. Chạy lại bộ 285 câu trên backend mới, lưu response JSONL và timing từng
   stage. Đánh giá required/forbidden locators trước, rồi nhờ reviewer duyệt
   gold/qrels để kết luận về độ chính xác pháp lý. Không dùng lại kết quả cũ
   như kết quả của bản code mới.

**Không cần chạy lại OFFLINE để sử dụng các sửa này.** Input review, OCR nguồn
thực sự và Gold vẫn là công việc riêng; ONLINE chưa tự biến dữ liệu provisional
thành dữ liệu pháp lý đã xác minh.

## 5. Tài liệu kỹ thuật đối chiếu

[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
giải thích schema và validation; dự án vốn đã gửi schema vào `format`.
[LegalBench-RAG](https://arxiv.org/abs/2408.10343) là cơ sở tham khảo cho truy
xuất các đoạn pháp lý liên quan tối thiểu; chưa phải benchmark đã chạy trên
corpus Việt Nam này. Mọi citation trong output vẫn phải trỏ về nguồn legal
thực có trong artifacts, không lấy model hoặc paper làm nguồn luật.
