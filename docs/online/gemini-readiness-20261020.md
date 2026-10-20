# Gemini DEGRADED làm launcher thoát trước khi mở tunnel

Log người dùng gửi xác nhận bản RPM `paced-retry-v2` đã được nạp. Artifact `result_14-10` tương thích kỹ thuật, Ollama auditor/adjudicator READY; cả Gemini Researcher và answer reviewer DEGRADED. Dòng “Model ready: ...bge-reranker...” là tải model retrieval thành công, không phải lỗi này.

Chưa biết lỗi Gemini cụ thể từ log cũ: provider readiness bắt mọi exception và chỉ trả DEGRADED. Không thể kết luận chắc đó là RPM, key sai, model sai hay timeout. Các cảnh báo legal review/Gold vẫn là giới hạn dữ liệu nhưng không phải lý do launcher dừng trong log này; hệ thống đang cho phép provisional mode.

## Đã xác nhận và sửa trong mã

- `wait_json()` trả ngay khi đọc được JSON từ `/ready`; endpoint có thể trả HTTP 200 với `ready=false`. Launcher cũ thấy snapshot đầu tiên DEGRADED rồi thoát, không chờ trạng thái hồi phục.
- Thêm `wait_ready()` có deadline 180 giây mặc định, polling có giới hạn và heartbeat `ONLINE_READY_WAIT`. Chỉ mở tunnel sau khi `ready=true` và cả Researcher, auditor, adjudicator, answer reviewer READY. Có thể đặt `--ready-timeout`, tối đa 1800 giây; không dùng tăng timeout để bỏ qua key/model/quota ngày sai.
- Gemini readiness hiện trả `error_code`, `quota_kind`, `retry_after_seconds`, `error_type` an toàn. Không trả raw SDK error, request URL hoặc key. Backend log cũng ghi mã lỗi an toàn.
- Mỗi provider chỉ chạy một probe tại một thời điểm. Probe thành công được cache; lỗi/cooldown cũng được cache để polling `/ready` không gọi Gemini dồn dập. Giới hạn 13 RPM dùng chung vẫn có hiệu lực.
- Tăng ngân sách probe từ tối đa 10 lên tối đa 20 giây khi timeout provider cho phép. HTTP client của launcher cho phép tối đa 45 giây cho một lần `/ready`, vì có thể có hai probe tuần tự. Toàn bộ startup vẫn chịu deadline riêng.
- Nếu probe hết deadline vì phải đợi cooldown 429, giữ lại nguyên nhân quota thay vì chỉ báo timeout. Mất mạng/timeout không có cooldown vẫn báo timeout, không tự gán thành RPM.
- Lỗi cấu hình/key/model rõ ràng hoặc quota ngày/bằng 0 dừng với hướng dẫn chẩn đoán, không retry vô hạn. Không đổi model, không tắt Gemini và không gán READY giả.

## Thực hiện tiếp

Tại máy local:

```powershell
cd D:\data_thô\legal-agentic-rag
git add src/vn_labor_online/providers.py src/vn_labor_online/gemini_quota.py src/vn_labor_online/api.py kaggle/online_remote.py kaggle/check_gemini.py tests/online/test_gemini_readiness.py docs/online/gemini-readiness-20261020.md
git commit -m "Retry Gemini readiness and report safe diagnostics"
git push
```

Trên Kaggle chạy lại cell cập nhật/cài code đã có. Vì cell backend trước đã kết thúc, có thể chạy một cell chẩn đoán trước khi khởi động lại:

```python
%cd /kaggle/working/legal-agentic-rag
!python -u kaggle/check_gemini.py --config /kaggle/working/online_pinned.yaml --model gemini-3.5-flash-lite
```

Model trong lệnh là model xuất hiện ở log người dùng, không phải lựa chọn model thay thế. Script đọc GEMINI_API_KEY từ môi trường/Kaggle Secrets; không in giá trị. Đây là probe nhỏ, có thể tiêu thụ một vài lượt trong giới hạn retry, không phải kiểm chất lượng mọi câu trả lời. Không chạy song song với backend/benchmark khác dùng cùng quota.

Nếu `status=READY`, chạy lại cell backend hiện có với `--artifact` và `--config` như trước. Có thể bỏ cell chẩn đoán nếu muốn launcher tự thử và hiện mã lỗi. Không cần chạy lại OFFLINE hay upload ZIP khác.

Nếu tiếp tục DEGRADED, gửi JSON chẩn đoán hoặc các dòng `Gemini readiness failed`/`ONLINE_READY_WAIT`, không gửi key:

| Mã/loại | Việc cần kiểm tra |
|---|---|
| `GEMINI_API_KEY_MISSING` | Gắn và bật quyền sử dụng Secret GEMINI_API_KEY cho notebook. |
| `GEMINI_SDK_MISSING` | Cài lại `python -m pip install -e ".[retrieval,online]"`. |
| `GEMINI_HTTP_400` | Request/model/schema không được chấp nhận; cần kiểm thêm, không gọi đó là RPM. |
| `GEMINI_HTTP_401` / `403` | Kiểm tra key, quyền truy cập/project hoặc hạn chế dịch vụ; không tự suy ra một nguyên nhân duy nhất. |
| `GEMINI_HTTP_404` | Kiểm model ID và quyền truy cập model đang cấu hình. |
| `GEMINI_HTTP_429`, RPM/TPM | Dừng các tác vụ khác dùng chung project; chờ cooldown. Launcher mới chờ có giới hạn. |
| DAILY / QUOTA_DISABLED | Chờ/reset hoặc kiểm hạn mức tài khoản; không xử lý bằng chờ vài giây. |
| `GEMINI_PROBE_TIMEOUT` | Kiểm mạng/độ trễ; chưa có bằng chứng đó là RPM. |

Nếu vừa thay Secret mà đã gán key cũ trong `os.environ`, phải cập nhật hoặc bỏ biến cũ trước khi chạy launcher; helper ưu tiên biến môi trường. Không cần dán key vào notebook để chẩn đoán.

Sau khi startup thành công, `/ready.online_features.gemini_readiness` phải là `diagnostic-probe-v2`. Cập nhật `frontend/.env` nếu URL ngrok thay đổi. Sau đó mới tiếp tục vòng đo 5 + 285 câu; chưa có lượt benchmark mới nào được xác nhận chạy trên backend đang lỗi này.

## Kiểm chứng local

14 test readiness mới, tổng nhóm Gemini 38 test; mô phỏng quota → cooldown → READY, lỗi key/SDK, timeout, probe trả false, polling đồng thời, reviewer chưa sẵn sàng, backend chết, transport hồi phục và deadline startup. Không gọi Gemini thật và không tiêu thụ quota khi chạy các test này.

Log: `artifacts/reports/gemini_readiness_20261020_targeted.log` và `artifacts/reports/gemini_readiness_20261020_full_tests.log`. Kiểm thử local không xác nhận key/model/kết nối thực tế trên Kaggle đã hoạt động.

Kết quả: **38/38 test Gemini PASS; 614/614 test toàn repository PASS**, 0 failure/error. `compileall` và `git diff --check` đạt. Chưa tự commit/push hoặc chạy probe Gemini thật.
