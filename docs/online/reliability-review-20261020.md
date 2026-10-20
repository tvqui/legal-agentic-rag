# Đo thực tế và sửa lỗi ONLINE — 20/10/2026

## Kết nối và phiên bản

Đã gọi trực tiếp backend Kaggle qua HTTPS/ngrok, không cần mở frontend. `/health` trả 200 ba lần: 0,797; 0,671; 0,672 giây. `/ready` trả 200, đúng graph build `9a615f1927162fe63e73b734b6a48759596984fbf2d004ce76bc2eb94e0e5da0`, Gemini Researcher `gemini-3.5-flash-lite`, Auditor/Adjudicator `qwen3:8b`, request budget 180 giây. Đây là bằng chứng kết nối và cấu hình, chưa chứng minh chất lượng pháp lý.

## Kết quả bản đang chạy trước sửa

| Câu | Thời gian HTTP | Kết quả |
|---|---:|---|
| USER-1: Điều 1 Nghị định 145 | 99,094 giây | INSUFFICIENT_EVIDENCE; semantic review trả cấu trúc không hợp lệ |
| USER-2: luật ngày 15/12/2020 | 134,609 giây | PARTIAL_ALLOWED; còn bị yêu cầu bổ sung điều kiện chung |
| USER-3: nghỉ sau 20 ngày, chưa có thỏa thuận | 67,860 giây | INSUFFICIENT_EVIDENCE; chọn nhầm cơ chế MUTUAL_AGREEMENT |
| USER-4: thời gian và lương thử việc | 27,047 giây | INSUFFICIENT_EVIDENCE; semantic review lỗi cấu trúc |
| USER-5: thử việc lần nữa, câu nối tiếp | 180,750 giây | HTTP 504 TIMEOUT |
| OLD-5.1 đến OLD-5.5 | 0,640–0,687 giây/câu | ABSTAIN đúng phạm vi câu hỏi hình sự/đất đai |

Câu USER-1 tìm được 11 phần của Điều 1 trong khoảng 0,15 giây, còn adjudication/semantic review chiếm 98,25 giây. USER-3 có nạp model lần đầu: BM25 dependency import khoảng 14,53 giây, BGE model init 33,18 giây; không được tính các số này thành độ trễ mạng hoặc dùng làm thời gian warm.

Đầu ra đầy đủ, câu hỏi, thời gian, request history và trace ở `artifacts/online_benchmarks/reliability_20261020/baseline/responses.jsonl`. Không tự đánh dấu mọi HTTP 200 là câu trả lời đúng.

## Lỗi xác nhận và cách sửa

1. **HTTP 500 ERR_7983D2F4497D:** lịch sử có tin nhắn `f`. Resolver gọi analyzer và tạo AnswerTask có chuỗi quá ngắn. Bỏ qua turn lịch sử ngắn sau chuẩn hóa; giữ lịch sử hợp lệ; câu hỏi hiện tại quá ngắn nhận 422. Không nới schema task hoặc tự thêm dữ kiện giả.
2. **Sai phủ định:** cụm `chưa đồng ý cho nghỉ sớm` bị khớp substring `đồng ý cho nghỉ sớm`. Xét phủ định sát vị từ; không chuyển sang thỏa thuận chấm dứt. Trường hợp xác nhận đồng ý thực sự vẫn được giữ. Span dữ kiện phủ định gồm cả từ phủ định.
3. **Tra cứu điều luật bị phụ thuộc vào kết quả JSON của LLM:** thêm đường trích đúng nội dung corpus cho một citation được xác định rõ, trong phạm vi đầy đủ, đã qua provenance/date/applicability checks. Không suy luận hay sửa nguyên văn. Vẫn chạy reference audit. Các câu áp dụng vào vụ việc, so sánh hoặc có yêu cầu lập luận không được dùng đường này.
4. **Nguồn chưa duyệt:** chỉ trích bản traceable ở chế độ partial khi source authority chưa được duyệt; giữ gap `official_source` và `source_authority_approved=false`, không đổi metadata hay tự ghi phê duyệt. Trích đúng một đoạn không chứng nhận văn bản còn hiệu lực.
5. **Câu nối tiếp chỉ thời gian tương đối:** nhận dạng các cấu trúc như `nếu hết thời gian đó`, giữ dữ kiện do user cung cấp của chủ đề đang xét. Các scenario mới có reset vẫn không thừa kế sự thật cá nhân.
6. **Khó chẩn đoán semantic review:** ghi mã lỗi cố định như `CLAIM_ACCOUNTING_MISMATCH`, `GROUNDING_QUOTE_MISMATCH`, `OUTPUT_TOKEN_LIMIT`, không công khai credential/URL/payload trong mã lỗi.
7. **Lựa chọn kiểm tra độc lập:** thêm Gemini làm reviewer cho câu trả lời Qwen, bật tường minh. Mặc định vẫn `same` như bản cũ; không tự phát sinh gọi Gemini khi chưa chọn. Giữ exact quote grounding, ID accounting, kiểm tra phụ thuộc task, bounded repair và fail-closed.

## Triển khai lần sửa đầu — đã xác nhận

Lần sửa đầu đã được người dùng commit thành `14ba449` và đưa lên Kaggle. Các lệnh dưới là hướng dẫn của lần đó; các thay đổi tiếp theo được ghi riêng ở cuối báo cáo:

```powershell
git add src/vn_labor_online tests/online
git commit --only src/vn_labor_online tests/online -m "Fix online history, negation and verified source lookup"
git push
```

Khi đã sẵn sàng cập nhật, ngắt riêng cell backend rồi chạy cell cập nhật code hiện có. Không phải chạy lại OFFLINE hoặc upload ZIP khác. Trước cell backend, cấu hình reviewer ứng viên để đo:

```python
import os
os.environ["VN_LABOR_ADJUDICATION_REVIEW_PROVIDER"] = "gemini"
os.environ["VN_LABOR_ADJUDICATION_REVIEW_MODEL"] = os.environ["GEMINI_MODEL"]
```

Secret `GEMINI_API_KEY` và `GEMINI_MODEL` đã dùng cho Researcher được giữ. Khi bật reviewer này, Gemini được gọi thêm để kiểm tra/sửa câu trả lời; đây là thay đổi sử dụng API cần được tính khi đo. Qwen vẫn là mô hình tạo câu trả lời, Auditor vẫn theo cấu hình trước.

Sau đó chạy lại cell backend/pin artifact như hiện tại. `/ready` của bản sửa phải có:

```json
{
  "online_features": {
    "conversation_context": "user-turns-v2-short-history",
    "literal_source_lookup": "verified-excerpt-v1"
  },
  "quality_policy": {"semantic_review_provider": "gemini"},
  "components": {"answer_reviewer": {"provider": "gemini", "status": "READY"}}
}
```

Nếu không chọn Gemini reviewer, phần `semantic_review_provider` vẫn là `same`; các sửa lịch sử, phủ định và trích nguồn vẫn hoạt động. Không vô hiệu hóa semantic review để ép PASS.

## Vòng kiểm thử và giới hạn

- Lượt baseline đã chạy thực tế 5 câu mới và 5 câu ngoài phạm vi từ bộ 285.
- Đã chạy đối chứng local cả 290 câu trên ZIP thật bằng deterministic/BM25, không nạp GPU model, không gọi API. Đây không phải benchmark ONLINE Kaggle: 0 exception, 110 PARTIAL_ALLOWED, 171 INSUFFICIENT_EVIDENCE, 4 NEED_MORE_FACTS, 5 ABSTAIN. Các trường hợp thiếu căn cứ phải được xét theo source/recall/coverage; không đổi nhãn thành PASS.
- Đã tái hiện USER-1 với history `f`, cấu hình generator Ollama nhưng chặn mọi model call: trả partial với đủ 11 citation, không gọi model; khoảng 0,125 giây phần xử lý sau khi ArtifactStore đã nạp. Số này không bao gồm startup và mạng, không được quảng cáo là thời gian Kaggle mới.
- Mỗi lượt remote tiếp theo phải dùng bản sửa đã được kiểm `/ready`, lưu output vào thư mục iteration riêng. Chạy lại 5 câu và nhóm quan trọng trước, mở rộng dần 285 câu; sau mỗi sửa chạy regression và xác nhận bản sửa đã triển khai. Không trộn kết quả code cũ và mới vào một số liệu.
- Một câu trả lời tốt có thể là yêu cầu thêm dữ kiện hoặc từ chối khi thiếu nguồn; không yêu cầu mọi câu đều SUFFICIENT. Kết quả đúng/đủ pháp lý cần kiểm tra độc lập và Gold có reviewer, không chỉ nhìn HTTP, số citation hoặc lời tự đánh giá của model.

## Kết quả sau khi người dùng báo đã cập nhật

**Đã cập nhật đúng.** `/ready` có `conversation_context=user-turns-v2-short-history`, `literal_source_lookup=verified-excerpt-v1`, Gemini Researcher và `answer_reviewer` đều `READY`, reviewer là `gemini-3.5-flash-lite`. Qwen vẫn làm Auditor/Adjudicator. Build dữ liệu vẫn là `9a615f19…e0e5da0`. Kiểm tra sức khỏe HTTPS ba lần mất 0,594; 0,593; 0,547 giây. Readiness không bảo đảm mọi API call tiếp theo đều thành công.

Đã chạy thật 5 câu người dùng trong cùng hội thoại, tiếp đó 25 câu OLD độc lập. Tổng **30/30 HTTP 200**, không có HTTP 500 hay timeout. Trạng thái: 23 PARTIAL_ALLOWED, 2 INSUFFICIENT_EVIDENCE, 5 ABSTAIN. Tổng thời gian HTTP 326,250 giây. Đây chưa phải 30 câu đúng và đủ về nội dung.

| Câu | Giây | Nhận xét nội dung |
|---|---:|---|
| USER-1 | 0,750 | Trích đủ 10 khoản cùng phần mở đầu Điều 1; 11 citation, giữ cảnh báo nguồn/hiệu lực chưa duyệt. Bản trước mất 99,094 giây và không có câu trả lời. |
| USER-2 | 2,562 | Chọn Bộ luật 2012, khoản 3 Điều 37 và ngoại lệ Điều 156; không dùng Bộ luật bắt đầu áp dụng năm 2021. |
| USER-3 | 3,797 | Đúng EMPLOYEE, không nhầm thỏa thuận chấm dứt; có Điều 35, 39 và cả ba khoản Điều 40. |
| USER-4 | 100,063 | Kết luận hai vi phạm nhưng còn thiếu diễn giải rõ mức 60 ngày/85%; tốn thời gian ở generation. Task duration còn bị đòi dẫn cả các nhóm công việc không liên quan. |
| USER-5 | 5,015 | Giữ ngữ cảnh cao đẳng nhưng chưa nhận ra cách nói “thêm một lần nữa”; trả danh sách thời hạn thay vì kết luận trực tiếp về thử việc lần hai. |

Hai câu INSUFFICIENT là OLD-1.1 (Gemini không trích chính xác ký tự nguồn, bị chặn bởi `GROUNDING_QUOTE_MISMATCH`) và OLD-4.1 (provider error; bản đang chạy chưa phân loại HTTP từ Gemini). OLD-2.3 bỏ mất căn cứ mức phép nền vì auditor nhầm điều kiện đủ 12 tháng với tham số của công thức tính tỷ lệ. OLD-4.2 nhận diện được hai dữ kiện còn thiếu nhưng vẫn sinh kết luận áp dụng không có điều kiện; một lời cảnh báo cuối câu không sửa được lỗi đó.

Đầu ra thực tế:

- `artifacts/online_benchmarks/reliability_20261020/candidate/responses.jsonl`: request, output nguyên vẹn, progress và trace.
- `candidate/responses.csv`: câu hỏi, thời gian HTTP, câu trả lời, trạng thái, nguồn/cảnh báo.
- `candidate/responses.md`: kết quả đọc trực tiếp cùng liên kết nguồn cho từng câu.
- `candidate/preflight.json`: cấu hình của lượt đo, không chứa credential.

## Sửa tiếp từ kết quả đo — đang chờ triển khai lên Kaggle

Các sửa nằm trực tiếp trong repository `D:\data_thô\legal-agentic-rag`, không chỉ trong thư mục staging:

1. Nhận dạng các cách nói thử việc thêm lần/đợt nữa; không biến mốc “hết thời gian đó” thành câu hỏi liệt kê mọi thời hạn. Vẫn giữ hai issue nếu người dùng hỏi cả thử việc lại và thời gian cụ thể.
2. Với nhóm công việc đã biết, lấy đúng khoản về thời hạn của nhóm đó. Câu so sánh hoặc hỏi các nhóm vẫn giữ đầy đủ các nhóm; câu hỏi lịch sử dùng đúng sơ đồ khoản của Bộ luật 2012.
3. Kết hợp hai rule chain thời gian và lương thử việc từ nguồn đã kiểm; so sánh số ngày và phần trăm người dùng thực sự nêu. Kết luận so sánh nằm trong claim có citation, không chỉ trong phần mở đầu bị mất sau review. Không đổi tháng thành số ngày hoặc trộn ngày thường với ngày làm việc. Gemini vẫn kiểm tra độc lập; không bỏ semantic review để tăng tốc.
4. Nếu đang xin kết luận cho vụ việc mà còn thiếu dữ kiện trọng yếu, trả NEED_MORE_FACTS trước khi gọi model thay vì sinh kết luận vô điều kiện. Việc giải thích quy tắc chung trong khi hỏi thêm vẫn được giữ cho yêu cầu EXPLAIN. Không đòi thêm dữ kiện đã được cung cấp.
5. Giữ mức nghỉ cả năm làm tham số trong chain tính nghỉ tỷ lệ, không gán điều kiện đủ 12 tháng thành SATISFIED. Vẫn phải có quy định tỷ lệ và quy định tính toán riêng trước khi tính quyền lợi.
6. Review sai cấu trúc/grounding có thể kiểm tra lại trong cùng ngân sách sửa hữu hạn. Trích dẫn vẫn phải đúng nguyên văn; không sửa nguồn để hợp thức hóa lời model. Lỗi provider không được tự coi là PASS.
7. Phân loại lỗi Gemini thành mã HTTP an toàn hoặc lỗi client/timeout; không đưa raw SDK message, URL chứa key hay credential vào trace. Benchmark dừng khi nhận mã rate limit, không gọi dồn tiếp cả bộ.

Validation: **552/552 tests PASS**, 0 failure/error. Log UTF-8: `artifacts/reports/reliability_20261020_recheck_tests.log`. Đối chứng trên ZIP thật, chặn mọi model call, đã xác nhận USER-4 có so sánh 90 > 60 ngày và 80% < 85%; USER-5 có quy tắc chỉ một lần cho cùng công việc; OLD-2.3 giữ đủ ba căn cứ để tính tỷ lệ; OLD-4.2 hỏi thêm hai dữ kiện trọng yếu. Kết quả ở `local_source_control_recheck.json`; đây không phải thời gian hoặc verdict Gemini trên Kaggle.

Chưa chạy lại remote các sửa ở mục này. Hai feature mới để xác nhận phiên bản sau triển khai:

```json
{"assessment_fact_gate":"critical-facts-v1","probation_scope":"dated-job-group-v1"}
```

Người dùng đưa code mới lên GitHub rồi khởi động lại backend như lần trước:

```powershell
cd D:\data_thô\legal-agentic-rag
git add src/vn_labor_online tests/online docs/online/reliability-review-20261020.md scripts/benchmark_online_reliability.py
git commit --only src/vn_labor_online tests/online docs/online/reliability-review-20261020.md scripts/benchmark_online_reliability.py -m "Fix scoped rule composition and critical fact gating"
git push
```

Giữ nguyên hai biến chọn Gemini reviewer và Input result_14-10. Chỉ cần chạy lại cell cập nhật code và cell backend; không chạy lại OFFLINE. Nếu URL đổi, cập nhật `frontend/.env`. Lượt remote tiếp theo phải ghi vào `candidate2/` để không trộn số liệu của hai phiên bản.

**Chưa hoàn tất kiểm thử remote toàn bộ 290 câu: đã đo 30, còn 260 câu chưa đo trong phiên bản này.** Chỉ tiếp tục mở rộng sau khi sửa các lỗi đã xác nhận và kiểm tra phiên bản triển khai. Không chứng nhận độ đúng luật chỉ bằng HTTP 200, số citation hoặc verdict tự động; các queue human review/Gold vẫn còn hiệu lực.

## Gián đoạn khi khởi động lần 2: Ollama pull trả HTTP 503

Người dùng đã commit `f00e743` và chạy lại trên Kaggle. Launcher dừng tại `ollama pull qwen3:8b` vì upstream trả HTTP 503, trước khi backend khởi động. Đây là lỗi tải model; chưa có phép đo remote nào của vòng candidate2. Không suy ra lỗi dữ liệu, ngrok hoặc Gemini từ traceback này.

Đã sửa `kaggle/online_remote.py`:

- Kiểm tra đúng model và đúng model cache của launcher bằng `ollama show`; nếu có sẵn thì không gọi lại registry để tải.
- Khi chưa có model, tải tối đa ba lần trong ngân sách tải tổng cộng 600 giây; chờ 5 rồi 10 giây giữa các lần lỗi. Timeout/failure vẫn dừng rõ ràng, không treo vô hạn hoặc đổi sang model khác.
- `--skip-pull` chỉ được dùng khi model có sẵn; nếu thiếu thì dừng ngay. Manifest có sẵn không chứng nhận chất lượng inference; các bước readiness/kiểm thử sau đó vẫn giữ.
- Không xóa cache/model, không chạy lại OFFLINE, không thay Input dữ liệu.

Các test mới giả lập cache, download thất bại rồi thành công, lỗi kéo dài, timeout, và lệnh kết thúc 0 nhưng model còn thiếu. Cập nhật launcher lên GitHub:

Toàn bộ suite sau sửa launcher: **558/558 PASS**, 0 failure/error. Log: `artifacts/reports/reliability_20261020_launcher_tests.log`. Đây là kiểm thử mô phỏng đường lỗi, không phải xác nhận registry Ollama đã hết HTTP 503.

```powershell
cd D:\data_thô\legal-agentic-rag
git add kaggle/online_remote.py tests/online/test_ollama_startup.py docs/online/reliability-review-20261020.md
git commit --only kaggle/online_remote.py tests/online/test_ollama_startup.py docs/online/reliability-review-20261020.md -m "Reuse cached Ollama models and bound download retries"
git push
```

Trên Kaggle giữ phiên hiện tại để giữ cache, chạy lại cell cập nhật code rồi cell backend hiện có. Không cần thêm biến môi trường, đổi lệnh backend hay tải lại dataset. Nếu model thực sự chưa có và registry tiếp tục lỗi thì vẫn cần đợi dịch vụ tải hoạt động trở lại; không có code nào bảo đảm một dịch vụ ngoài hệ thống luôn sẵn sàng.
