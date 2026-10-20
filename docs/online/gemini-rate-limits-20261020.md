# Sửa nhịp gọi Gemini theo hạn mức RPM

Người dùng xác nhận hạn mức hiện tại là **13 request/phút**. Bản sửa trước chỉ nhận HTTP 429 rồi dừng sớm, chưa điều tiết lượt gọi và chưa thử lại sau cửa sổ phút. Cách đó tránh việc chạy Qwen nhiều phút rồi thất bại nhưng quá cứng với lỗi RPM tạm thời. Tài liệu này thay thế chính sách `fail-fast-v1`; bản sửa schema HTTP 400 vẫn giữ nguyên vì đó là lỗi khác.

Theo [tài liệu rate limits của Google](https://ai.google.dev/gemini-api/docs/rate-limits), HTTP 429 có thể do RPM, TPM hoặc hạn mức khác; quota gắn với project và model, không tách riêng theo API key. Con số 13 là cấu hình theo hạn mức người dùng cung cấp, không phải giới hạn chung của mọi model/tài khoản Gemini. Một câu hỏi có thể gọi Gemini nhiều lần: hiểu câu hỏi, kiểm từng nhóm claim, kiểm coverage, sửa và kiểm lại; 13 request không có nghĩa 13 câu hỏi.

## Hành vi sau sửa

1. Mọi `GeminiProvider.structured()` phải lấy lượt từ bộ điều tiết dùng chung theo project/model trong process, kể cả Researcher, semantic reviewer, repair và probe readiness. Không chia mỗi agent một mức 13, không tăng quota bằng cách đổi API key.
2. Giới hạn 13 lượt trong cửa sổ trượt 60 giây và giãn lượt gọi khoảng `60/13 + 0,05` giây. Nếu các bước xử lý đã đủ xa nhau thì không chờ thêm. Các nhánh tra cứu nguyên văn không cần Gemini vẫn giữ đường chạy đó.
3. Khi SDK trả 429, đọc `QuotaFailure`, `RetryInfo.retryDelay` và header `Retry-After`. RPM/TPM được thử lại có giới hạn; không tự suy ra hết quota ngày từ mã 429. Nếu không có chỉ dẫn thời gian thì dùng cooldown 60 giây. Thời gian chờ được chia sẻ giữa các agent.
4. Tối đa **2 lần thử lại**, tức tối đa 3 lần gọi thực cho mỗi lượt structured. Tổng chờ điều tiết/cooldown mặc định tối đa **70 giây/lượt structured**, nằm trong deadline của toàn câu hỏi. Mỗi lần gọi thực phải lấy lượt mới. Retry ngầm của SDK được tắt để không vượt bộ điều tiết.
5. Nếu chạm hạn mức ngày hoặc quota bằng 0, không lặp thử như lỗi phút. Nếu chưa phân loại được 429 thì ghi UNKNOWN và chỉ thử có giới hạn; không gán nhãn DAILY.
6. Nếu đã hết số lần thử/thời gian chờ, trả lỗi dịch vụ có `quota_kind` và thời gian đề nghị thử lại khi biết. Không biến lỗi dịch vụ thành “thiếu bằng chứng pháp lý”, không bỏ semantic review hay xuất bản câu trả lời chưa được kiểm. Với hạn mức ngày chưa biết thời điểm hồi phục, không tự đặt `Retry-After: 60`.

Chờ 70 giây chỉ áp dụng cho thời gian điều tiết/cooldown, không phải tổng thời gian toàn câu trả lời. Deadline toàn request và khả năng hủy vẫn có hiệu lực; không tăng deadline để che lỗi. Nếu server đề nghị chờ lâu hơn ngân sách còn lại, trả lỗi ngay thay vì ngủ hết nhiều phút hoặc rút ngắn cooldown rồi gọi dồn.

## Cấu hình

Mặc định đã là 13 RPM. Có thể cấu hình trước khi khởi động backend:

```dotenv
VN_LABOR_GEMINI_RPM=13
VN_LABOR_GEMINI_RATE_RETRIES=2
VN_LABOR_GEMINI_RATE_MAX_WAIT_SECONDS=70
```

Các biến cũng đã thêm vào `.env.example`. Trên Kaggle, `.env` ở máy local không tự được đưa lên. Nếu muốn khai báo rõ, thêm vào cell trước `subprocess.run(... online_remote.py ...)`:

```python
import os
os.environ['VN_LABOR_GEMINI_RPM'] = '13'
os.environ['VN_LABOR_GEMINI_RATE_RETRIES'] = '2'
os.environ['VN_LABOR_GEMINI_RATE_MAX_WAIT_SECONDS'] = '70'
```

Giữ API key trong Kaggle Secrets như hiện tại. Không cần thêm key mới hoặc chạy lại OFFLINE. Cập nhật code và khởi động lại backend để các thay đổi có hiệu lực.

Kiểm tra `/ready`:

```text
online_features.provider_capacity = paced-retry-v2
components.researcher.rate_limit.requests_per_minute = 13    # nếu dùng Gemini
components.answer_reviewer.rate_limit.requests_per_minute = 13
```

Readiness probe cũng tiêu thụ lượt gọi khi cần kiểm inference lần đầu; các kết quả thành công được cache trong provider. Không chạy thêm probe Gemini song song với benchmark. Một process không thể đếm request từ notebook khác hoặc ứng dụng khác cùng Google project; cần dừng các tác vụ dùng chung quota khi đo hoặc giảm `VN_LABOR_GEMINI_RPM` để chừa dư địa. Bộ này không phải bộ giới hạn phân tán cho nhiều worker/máy chủ. Giữ launcher/backend một worker như hiện tại; nếu triển khai nhiều worker cần dùng quota coordinator chung.

Giới hạn RPM không tự giải quyết TPM/RPD, lỗi mạng hoặc sai nội dung pháp lý. Việc điều tiết có thể tăng thời gian chờ khi gọi liên tục, nhưng giúp tránh gọi dồn và mất toàn bộ câu trả lời vì giới hạn phút.

## Kiểm chứng

- 16 regression tests mới bằng đồng hồ giả, không chờ phút thật và không gọi Gemini thật. Bao phủ cửa sổ trượt 13 RPM, chia sẻ giữa instance/key, cạnh tranh thread, retry rồi thành công, RetryInfo/Retry-After, TPM, daily/zero, 429 không rõ loại, giới hạn retry/wait, cancellation/deadline, schema 400, truyền lỗi qua Researcher/reviewer và API.
- Tổng nhóm Gemini: 24 tests. Log: `artifacts/reports/gemini_rpm_20261020_targeted.log`.
- Full suite: **600/600 PASS**, 0 failure/error, 10,829 giây trong lần chạy local này. Log: `artifacts/reports/gemini_rpm_20261020_full_tests.log`. `compileall` và `git diff --check` cũng đạt.
- Chưa tiêu thụ quota thật để đo lại trên backend Kaggle; cần kiểm sau khi người dùng cập nhật. Không khẳng định rằng bộ điều tiết local ngăn được mọi HTTP 429.

File chính: `gemini_quota.py`, `providers.py`, `researcher.py`, `answer_review.py`, `errors.py`, `api.py`, `tests/online/test_gemini_rate_limits.py`. Bản sửa schema và validation kết quả gốc trong `test_gemini_contract.py` vẫn được kiểm lại.

## Đưa bản sửa lên Kaggle

Chưa tự commit/push. Kiểm tra thay đổi trước khi chạy:

```powershell
cd D:\data_thô\legal-agentic-rag
git diff --stat
git add .env.example pyproject.toml src/vn_labor_online tests/online/test_gemini_contract.py tests/online/test_gemini_rate_limits.py docs/online/gemini-rate-limits-20261020.md docs/online/reliability-run2-20261020.md
git commit -m "Pace Gemini calls and retry temporary rate limits"
git push
```

Sau đó chạy lại cell cập nhật/cài code và cell backend trên Kaggle, tiếp tục dùng Input result_14-10. Không cần upload dữ liệu mới cho bản sửa này. Khi đã khởi động, kiểm `/ready` như trên trước khi đo lại các câu hỏi.
