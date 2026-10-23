# Nhật ký từng bước để demo và chẩn đoán ONLINE

Đã thêm bảng **Tiến trình xử lý** bên dưới từng câu trả lời. Bảng cập nhật trong
lúc backend xử lý và giữ lại khi đã trả lời hoặc gặp lỗi. Có nút **Tải log** JSON.
Không cần chạy lại OFFLINE, đổi Dataset, thêm Secret hoặc mở một cổng Kaggle mới.

## Cách hoạt động khi backend chạy trên Kaggle

1. React tiếp tục POST `/api/v1/answer` qua Vite/ngrok như đang dùng.
2. Backend ghi các mốc vào nhật ký của chính request, trong bộ nhớ tiến trình.
3. Frontend dùng API tiến trình đã có `/v1/requests/{message_id}`, cùng
   `X-Client-Session`, để lấy snapshot. Lần thăm dò đầu khoảng 1 giây; các lượt
   tiếp theo sau khoảng 2,5 giây kể từ khi lượt trước xong.
4. Snapshot chứa các bước đã qua, không chỉ tên bước hiện tại. Bước quá nhanh
   giữa hai lần poll vẫn có trong log; phản hồi cuối còn mang log trong
   `trace.execution_steps` nên câu trả lời xong dưới một giây vẫn có nhật ký.
5. Log gắn vào tin nhắn và được lưu cùng lịch sử trình duyệt. Đóng/mở bảng không
   gọi lại AI. Bấm Tải log chỉ tải JSON đã có, không mở một request LLM mới.

Không cần xem `backend.log` trong lúc cell Kaggle đang giữ server chạy. Cách này
không thêm lượt gọi model và không yêu cầu kết nối trực tiếp vào cổng nội bộ
Kaggle. API tiến trình đọc trạng thái trong bộ nhớ, không chạy Gemini readiness.

## Các cột và ý nghĩa

| Cột | Nội dung |
|---|---|
| Bước / tầng | Tên công việc và thành phần phụ trách: Pipeline, Retriever, Researcher, Auditor, Adjudicator, Graph, hậu kiểm, API. |
| Công nghệ | Công nghệ của bước thực sự được yêu cầu. Bước SKIPPED ghi rõ không thực hiện. Model cấu hình sẵn không đồng nghĩa đã gọi model. |
| Output tóm tắt | Nhãn vấn đề, số task/query, các trường facts đã nhận, nguồn/ID đã tìm, số nguồn bị loại, PASS/FAIL/UNRESOLVED, coverage/gaps, số node/cạnh, claims, kiểm trích dẫn hoặc mã lỗi an toàn. |
| Thời gian | Thời gian bước trên máy chủ. Bước cha có thể gồm bước con; không cộng tất cả các dòng. Không phải thời gian từ phím Enter đến màn hình. |

Trạng thái:

- **Đang chạy:** đã đi vào thao tác, chưa nhận output. Số ms tiếp tục tăng trong snapshot.
- **Đã xong bước:** thao tác đã trả kết quả, không phải chứng nhận pháp luật đúng.
- **Bỏ qua:** exact/profile đã đủ, kênh đã tắt hoặc gate đã dừng trước khi đến bước.
- **Có giới hạn:** có dữ kiện/căn cứ/độ kiểm chứng còn thiếu, hoặc chưa đủ để kết luận.
- **Lỗi bước:** một thao tác/provider ném lỗi hoặc reviewer báo ERROR. Pipeline
  có thể vẫn dùng dự phòng; phải đọc cả kết quả cuối.
- **Đã dừng:** có hủy hợp tác phía server. Nếu trình duyệt đã ngắt kết nối trước,
  bảng có thể chỉ giữ snapshot cuối và không được coi bước RUNNING là hoàn tất.

Các row `model_call` được ghi khi code thực sự đi vào `structured()` của provider,
gồm Gemini/Ollama/HTTP và tên model. Đây là lượt yêu cầu qua ranh giới provider,
không chứng nhận HTTP/inference đã thành công; kiểm tra status/Output. Một lời
gọi structured có thể chứa retry nội bộ, không lấy số row làm số HTTP attempts.
Các lần readiness không thuộc request trả lời không bị gộp vào nhật ký của user.

## Phân biệt graph và đối tượng runtime

- Output `Loại nguồn trong kết quả` đọc thuộc tính `layer` của node có cùng
  unit ID trong artifact, không biến facts hay task thành node graph.
- Khi thực sự có vòng duyệt, `Các tầng node mới đã duyệt` đếm node frontier mới
  thuộc Fact Graph, Ontology Graph, Rule Graph, Document, Derived theo dữ liệu
  thật. Node trung gian có thể không tạo Evidence; hai số đếm này khác nhau.
- Rule Graph xuất hiện trong nguồn được chọn không chứng minh đã chạy mở rộng
  graph. Xem riêng row `graph` và `graph_round`, số vòng/node/cạnh đã xét.
- `EVIDENCE_SUFFICIENT` là lý do dừng tìm thêm của graph. Trong provisional,
  vẫn có thể còn metadata nguồn/hiệu lực chờ duyệt và kết quả chỉ PARTIAL_ALLOWED.

## Đưa thay đổi lên Kaggle

Các tệp được thêm/sửa:

```text
src/vn_labor_online/demo_progress.py
src/vn_labor_online/runtime.py
src/vn_labor_online/models.py
src/vn_labor_online/api.py
src/vn_labor_online/pipeline.py
src/vn_labor_online/providers.py
src/vn_labor_online/generation.py
frontend/src/services/executionLog.js
frontend/src/services/chatService.js
frontend/src/components/chat/ExecutionLog.jsx
frontend/src/components/chat/Message.jsx
frontend/src/pages/ChatPage.jsx
frontend/src/styles/app.css
tests/online/test_demo_progress.py
frontend/tests/executionLog.test.mjs
docs/online/demo-execution-log.md
```

1. Tại repository local, xem diff và commit/push các tệp trên. Một số tệp đã có
   sửa đổi từ trước, nên xem nội dung trước khi commit; không dùng `git add .`
   khi chưa kiểm tra các file khác đang stage. Tôi chưa tự commit/push.
2. Trên Kaggle, dừng backend cũ, chạy lại cell cập nhật `origin/main` và cell
   backend, hoặc Run All notebook backend đang tự lấy code mới. Giữ nguyên
   `result_14-10`, cấu hình provider và Secrets đang dùng.
3. Trên máy, chạy lại `run.bat frontend`, mở đúng URL/port Vite in ra; nếu server
   cũ vẫn chạy cổng khác thì tránh mở nhầm. Refresh trình duyệt để dùng frontend mới.
4. Hỏi một câu mới. Mở bảng **Tiến trình xử lý** bên dưới tin nhắn AI. Trong khi
   chạy bảng tự mở; người xem có thể cuộn xem bước cũ, dừng tự kéo xuống khi đã
   cuộn lên và tiếp tục theo cuối bảng khi trở lại gần đáy.
5. Kiểm tra phiên bản backend qua frontend proxy (đổi 5173 theo cổng thật):

```powershell
(Invoke-RestMethod -Uri "http://localhost:5173/api/ready").online_features.execution_log
```

Phải trả `execution-steps-v1`. Backend cũ vẫn trả lời được với frontend mới nhưng
bảng sẽ ghi rõ chưa có log chi tiết, không tự dựng một timeline giả.

## Gợi ý demo

**Câu 1:** “Tôi đang thử việc tại một công ty, được trả 70% mức lương của công
việc. Công ty trả như vậy có đúng quy định pháp luật không?”

Quan sát nhãn CONTRACT.PROBATION_PAY, slot Điều 26, profile probe, nguồn được
chọn, warning nguồn/hiệu lực, hậu kiểm và trạng thái cuối. Nếu profile đủ, Dense,
BM25 và graph có thể SKIPPED. Giải thích đây là tối ưu theo mức đủ căn cứ, không
phải giao diện giả vờ đã sử dụng đủ công nghệ. Nếu cấu hình chọn reviewer, vẫn
phải chờ kiểm nội dung khi nhánh này yêu cầu.

**Câu 2:** “Tôi ký hợp đồng không xác định thời hạn và chỉ báo trước 20 ngày rồi
nghỉ. Tôi nghỉ như vậy có trái pháp luật không?”

Quan sát gate dữ kiện: chưa xác định ngoại lệ/nghề đặc thù thì có thể hỏi lại và
không chạy các bước tìm sâu. Không gán đây là lỗi phần mềm chỉ vì chưa có đáp án.

**Câu 3:** “Hành vi trộm cắp tài sản bị xử lý hình sự thế nào?”

Quan sát scope gate ABSTAIN và các bước bị bỏ qua; câu hỏi này không yêu cầu giải
quyết kỷ luật lao động tại nơi làm việc nên nằm ngoài phạm vi lao động của hệ thống.

Khi lỗi reviewer/Dense thật xảy ra, log đánh dấu bước tương ứng, thời gian và loại
lỗi/mã lỗi có thể công khai. Không cố gây lỗi bằng cách làm sai dữ liệu hoặc sửa
quy tắc pháp luật chỉ để demo. Log giúp xác định khâu bị chặn; độ đúng pháp lý
vẫn cần đối chiếu claims/nguồn và đánh giá có chuẩn tham chiếu.

## Giới hạn và dữ liệu riêng tư

Log mới chỉ lưu metadata/tóm tắt theo danh sách trường được code cung cấp. Không
đưa prompt hệ thống, suy nghĩ nội bộ, raw response LLM, API key, header xác thực
hoặc URL endpoint của provider lên bảng. Loại lỗi được công khai thay cho
`str(exception)`; không lấy lỗi provider tự do làm nội dung giao diện.

API poll/cancel vẫn kiểm Bearer (nếu bật) và capability của phiên + message ID;
phiên khác không xem được request bằng cách đoán message ID. Giới hạn 160 row
mỗi request, output có giới hạn độ sâu/độ dài và có thông báo khi sự kiện cũ bị
bỏ. Registry vẫn là RAM, TTL mặc định một giờ, không phải cơ sở dữ liệu audit bền
vững và mất khi restart backend. Lịch sử trên trình duyệt chỉ giữ nếu lưu được;
Tải log trước khi xóa cuộc trò chuyện nếu cần mang đi trình bày.

Nếu ngrok/backend mất kết nối, giao diện nói snapshot đã cũ, không khẳng định
máy chủ đã dừng. Tiến trình máy không thể tự chứng minh một câu trả lời luật là
đúng; DONE không thay cho review pháp lý hoặc legal_ready.

## Log ở file backend (tùy chọn)

Nếu muốn đồng thời ghi `ONLINE_STEP {...}` ra stdout của backend, thêm trước
cell khởi động backend:

```python
os.environ["VN_LABOR_DEMO_CONSOLE"] = "1"
```

Launcher hiện chuyển stdout backend vào `/kaggle/working/vn_labor_online/logs/backend.log`.
Vì vậy bật cờ này không tự làm Kaggle cell in từng dòng lên màn hình notebook.
Giao diện là cách xem trực tiếp được triển khai; cờ console chỉ giúp giữ log file.
Không cần bật cờ này để bảng trên giao diện hoạt động.

## Kiểm thử

```powershell
python -m unittest discover -s tests/online -p test_demo_progress.py -v
cd frontend
npm test
npm run lint
npm run build
```

Có kiểm thử không lộ prompt/exception tự do, giới hạn bộ nhớ, snapshot độc lập,
request đồng thời, poll đang chạy, quyền xem theo phiên, hủy/lỗi và final log cho
câu trả lời quá nhanh để poll. Việc ghi log không thay thuật toán truy xuất hoặc
quyết định pháp lý và không thêm yêu cầu AI.
