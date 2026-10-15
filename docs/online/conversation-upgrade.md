# Hội thoại và thời gian xử lý ONLINE — 15/10/2026

## Những gì đã thay đổi

Luồng mới: tin nhắn và mã tin nhắn → phân giải ngữ cảnh từ lời người dùng → phân tích câu hỏi → chọn đường xử lý → truy xuất và kiểm chứng → trả kết quả, lưu lịch sử trên trình duyệt. Các bộ lọc nguồn, thời gian, applicability, grounding và semantic review vẫn được giữ.

- Backend nhận thêm `conversation_id`, `message_id`, `conversation_turns`. Đây là các trường tùy chọn; client cũ vẫn dùng được. Mỗi turn có `turn_id`, `role=user`, `content`. Không nhận turn assistant làm dữ kiện.
- Bộ phân giải dùng tối đa 20 lượt người dùng gần nhất. Nó phân biệt câu nối tiếp, câu bổ sung dữ kiện, thay đổi chủ đề, thay đổi chủ thể và dấu hiệu tình huống giả định. Câu mơ hồ không phân giải an toàn được sẽ được hỏi lại trước khi gọi mô hình/truy xuất.
- Dữ kiện kế thừa có turn ID, trích đoạn và vị trí ký tự, đánh dấu `USER_REPORTED`. Chúng không phải kết luận pháp lý đã xác minh. Dữ kiện mới rõ ràng ưu tiên hơn dữ kiện cũ. Khi bổ sung thông tin về công việc, hệ thống nối lại các ý hỏi trước bằng nhãn taxonomy, không chèn lại những con số đã cũ trong câu hỏi trước.
- Bổ sung nhánh kết thúc thử việc, tách khỏi thời hạn thử việc. Locator thay đổi theo chế độ luật; phiên bản taxonomy là `labor-subissues-v6`. Locator chỉ hướng dẫn truy xuất, không thay thế kiểm tra hiệu lực hay cho phép suy ra rằng cứ hết thời gian là tự động được nhận chính thức.
- Researcher trên cấu hình Kaggle chuyển sang `adaptive: true`. Câu tra cứu trực tiếp, trường hợp rõ ràng cần hỏi dữ kiện và profile đã bao phủ có thể bỏ lượt Researcher. Các kiểm tra pháp lý sau truy xuất không bị tắt.
- Các batch applicability hợp lệ trước đó không còn bị mất vì một batch độc lập chạy sau thất bại. Batch lỗi vẫn `UNRESOLVED`, không tự PASS.
- `AnswerTask` có `depends_on`. Researcher từ chối ID lạ/vòng phụ thuộc; semantic review không giữ kết luận áp dụng phụ thuộc vào một task chưa được trả lời đủ, nhưng vẫn giữ claim độc lập đã kiểm chứng.

## Lịch sử được lưu ở đâu?

Bản này lưu các cuộc trò chuyện, tin nhắn và kết quả trong `localStorage` của cùng trình duyệt/origin. Mở lại trang vẫn còn lịch sử; nút Xóa xóa cả cuộc trò chuyện lẫn tin nhắn. Câu trả lời bị gián đoạn khi tải lại trang chuyển thành trạng thái có thể thử lại. Sidebar hiển thị cả những cuộc trò chuyện mới, không còn phụ thuộc danh sách ID mẫu.

Đây là lựa chọn cho bản demo frontend local + backend Kaggle. **Không phải tài khoản đăng nhập, cơ sở dữ liệu hội thoại trên server hoặc đồng bộ đa thiết bị.** Đổi `localhost` thành `127.0.0.1`, đổi cổng frontend, xóa dữ liệu trình duyệt hoặc dùng trình duyệt khác có thể không thấy lịch sử cũ. Nên dùng một địa chỉ/cổng ổn định. Trình duyệt có giới hạn dung lượng; nếu lưu thất bại UI sẽ báo, không âm thầm xóa tin nhắn cũ. Máy/người dùng chung cùng browser profile có thể xem lịch sử đó.

Chỉ 20 lượt người dùng gần nhất được gửi lại, không phải toàn bộ lịch sử được lưu. Chưa có tóm tắt dài hạn được kiểm chứng hay bộ nhớ tự động qua mọi chủ đề. Nếu không rõ đang nói cùng vụ việc hay vụ khác, hệ thống hỏi lại. Các thành phần này không bảo đảm hiểu đúng mọi cách nói tự nhiên; cần kiểm thử thêm bằng hội thoại thực tế.

## Deadline, tiến độ, dừng và thử lại

Backend mặc định có ngân sách tổng `180` giây:

```dotenv
VN_LABOR_REQUEST_TIMEOUT_SECONDS=180
```

Mỗi lần gọi HTTP/SDK nhận timeout không vượt thời gian còn lại; retry dùng chung ngân sách. Checkpoint giữa các bước ngăn bắt đầu tiếp công việc khi đã hết giờ hoặc được yêu cầu dừng. Hết giờ trước khi có kết quả qua đủ kiểm chứng trả JSON `504/TIMEOUT`, không giả thành thiếu dữ kiện hay thiếu căn cứ. Có `X-Request-ID` trong phản hồi từ ứng dụng.

Đây là giới hạn phối hợp giữa các bước, **không phải cơ chế cưỡng chế dừng CPU/GPU đúng tại một mili giây**. Tác vụ native CPU và lượt Ollama đang chạy có thể còn tiếp tục đến lúc trở về/timeout; đóng kết nối không bảo đảm GPU phía xa dừng ngay. Kết quả đến muộn bị từ chối, các lượt tiếp theo không được bắt đầu.

Frontend gửi capability ngẫu nhiên `X-Client-Session`, chỉ để ràng buộc trạng thái request và retry trong tab đó. Nó không thay thế Bearer API key hay tài khoản người dùng. Server không mở API đọc lịch sử theo `user_id` tùy ý.

- `GET /v1/requests/{message_id}` trả trạng thái và stage thật.
- `POST /v1/requests/{message_id}/cancel` đánh dấu yêu cầu dừng.
- Retry cùng mã tin nhắn và cùng payload trong lúc đang chạy nhận 429; khi đã hoàn thành dùng lại kết quả. Đổi payload mà giữ mã cũ nhận 409. Request đã thất bại có thể thử lại.
- Bộ nhớ retry giới hạn 64 request, TTL một giờ cho request kết thúc, nằm trong RAM của **một process**. Khởi động lại backend sẽ mất bộ nhớ này. Không phải cache pháp lý dùng chung giữa các người dùng. Chạy một Uvicorn worker với launcher hiện tại; nhiều process cần state backend chung trước khi sử dụng tính năng này.
- Nút dừng và việc rời cuộc trò chuyện gửi yêu cầu cancel. Thử lại không thêm một bản sao tin nhắn người dùng.
- UI hiển thị tiến độ nhận được từ server. Không stream câu trả lời pháp lý chưa kiểm chứng.

Ví dụ frontend/.env, giữ nguyên URL/key của bạn:

```dotenv
VITE_API_TIMEOUT_MS=210000
BACKEND_PROXY_TIMEOUT_MS=220000
```

Nếu tăng ngân sách backend cho câu phức tạp, tăng hai giá trị frontend/proxy tương ứng. Tăng timeout không phải biện pháp tăng chất lượng. Không tắt semantic review chỉ để trả nhanh hơn. Các giá trị trong `.env` thật chưa bị chỉnh sửa tự động.

## Gemini tùy chọn

Không cần Gemini để sử dụng các thay đổi về lịch sử, context, tiến độ và deadline. Mặc định giữ provider hiện tại. Nếu muốn đánh giá Gemini cho bước Researcher, dùng SDK chính thức `google-genai`, đã thêm vào extras `online`/`full`:

```powershell
python -m pip install -e ".[retrieval,online]"
```

Trong `.env` gốc, sửa giá trị Researcher hiện có, tránh khai báo các giá trị trái nhau:

```dotenv
VN_LABOR_RESEARCHER_MODE=gemini
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=YOUR_EVALUATED_MODEL_ID
VN_LABOR_RESEARCHER_TIMEOUT_SECONDS=20
```

Thay hai giá trị `YOUR_...` bằng thông tin thật. Không đưa key vào `frontend/.env` hoặc biến `VITE_*`. Model ID cần chọn từ tài khoản của bạn; không khóa cứng vào một model có thể ngừng phục vụ. Nếu giữ `ollama`/`deterministic`, bỏ qua các biến Gemini.

Gemini chỉ hỗ trợ phân tích và mở rộng truy xuất. Fact mới vẫn phải qua kiểm tra trích đoạn và nội dung; Gemini không có quyền phê duyệt source, đổi phiên bản luật hoặc bỏ audit. Khi lượt phân tích lỗi/quota/sai schema, Researcher quay về phân tích deterministic. `/ready` có một probe inference rất nhỏ cho Gemini để kiểm tra cấu hình; probe thành công được ghi nhớ trong process. Probe này sử dụng API, không chỉ kiểm tra có tên model. Cấu hình sai có thể khiến launcher từ chối mở tunnel; cần sửa key/model thay vì ép READY.

Trên Kaggle, thêm và bật quyền truy cập Secret `GEMINI_API_KEY` nếu chọn Gemini. Launcher mới tự nạp secret tùy chọn đó. Trước cell chạy backend:

```python
import os
os.environ['VN_LABOR_RESEARCHER_MODE'] = 'gemini'
os.environ['GEMINI_MODEL'] = 'YOUR_EVALUATED_MODEL_ID'
os.environ['VN_LABOR_RESEARCHER_TIMEOUT_SECONDS'] = '20'
```

Ollama vẫn phục vụ auditor/adjudicator theo cấu hình hiện tại. Không có thêm một Gemini Researcher chạy nối tiếp một Ollama Researcher. Chưa có đo A/B thực tế bằng API key của bạn nên chưa khẳng định Gemini nhanh hoặc chính xác hơn.

Tài liệu SDK/structured output: https://ai.google.dev/gemini-api/docs/structured-output

## Cập nhật và chạy

1. Kiểm tra và commit/push các thay đổi ONLINE/frontend lên repository của bạn nếu backend Kaggle clone từ GitHub. Chỉ sửa local sẽ chưa cập nhật code đang chạy trên Kaggle.
2. Dừng backend cũ, chạy lại cell fetch/checkout `origin/main`, cài `.[retrieval,online]` rồi chạy backend như hiện tại. Giữ artifact/config pin đúng bộ dữ liệu đang dùng; không cần chạy lại OFFLINE cho nâng cấp này.
3. Kiểm tra `/ready`: `taxonomy_version=labor-subissues-v6`, `online_features.conversation_context=user-turns-v1`, `history_storage=browser`, `request_budget_seconds=180` nếu không override. `LAZY` ở index không phải đo hiệu năng truy vấn đầu tiên.
4. Cập nhật URL ngrok vào `VITE_BACKEND_TARGET` nếu URL đổi. Giữ `BACKEND_PROXY_TOKEN` hiện tại phù hợp backend; khởi động lại frontend bằng `run.bat frontend`. Khi đã có frontend chạy, dừng phiên cũ để tránh tự đổi cổng.

## Tự kiểm tra

```powershell
run.bat test
cd frontend
npm test
npm run lint
npm run build
```

Kiểm tra thêm trên giao diện:

1. Hỏi về lương thử việc, sau đó hỏi “thử bao lâu thì được lên chính thức”. Kết quả phải nhận đúng bối cảnh thử việc, tìm cả thời hạn và kết thúc thử việc; không tự suy nhóm công việc từ ngành của công ty.
2. Bổ sung “Tôi làm công việc yêu cầu trình độ cao đẳng.”. Phải nối lại các ý đang hỏi; không coi riêng bằng cấp cá nhân là yêu cầu trình độ của công việc.
3. Hỏi câu độc lập về nghỉ phép. Không tự gán vào tình huống thử việc cũ.
4. Đổi ngày tra cứu sang trước 2021. Không dùng locator hiện hành để thay quy định lịch sử.
5. Refresh trang, tạo chat mới, chuyển chat, xóa chat; kiểm tra lịch sử đúng conversation.
6. Trong lúc chờ, xem tiến độ và thử Dừng. Sau khi tác vụ đã kết thúc, Thử lại không nhân đôi câu hỏi.
7. Kiểm tra câu nhiều ý: phần độc lập đã xác minh có thể được trả, phần chưa đủ phải ghi rõ; không tuyên bố đầy đủ khi còn thiếu điều kiện tiên quyết.

Tốc độ cần đo riêng lần đầu và các lượt đã nóng máy, kèm độ đúng/đủ và tỷ lệ lỗi. Mục tiêu hỏi làm rõ 2–5 giây là mục tiêu đo, chưa phải cam kết với mọi tình huống/mô hình/mạng. Các test local dùng fixture/mock, không chứng nhận chất lượng pháp lý của toàn corpus, không đo Qwen/Gemini trên Kaggle và không xác nhận nguồn HTTP 503 trước đây đã được sửa.

## Kết quả kiểm tra local

- Python: 508 tests PASS; 11.959 giây cho test suite, không phải tốc độ trả lời pháp lý.
- Frontend: 7 tests PASS, ESLint PASS, production build PASS.
- Compileall và git diff --check PASS.
- Probe câu nối tiếp chuyển từ GENERAL/không subissue sang PROBATION_DURATION + PROBATION_END. Chỉ bước hiểu câu/lập kế hoạch: P50 0.433 ms, P95 0.729 ms trong 50 lần chạy local; chưa gồm retrieval, audit, sinh câu trả lời hay độ trễ mạng.
- Báo cáo máy đọc: `artifacts/reports/online_conversation_upgrade_20261015.json`.
- Chưa đo toàn pipeline trên Kaggle, chưa gọi Gemini bằng key thật, chưa tự động kiểm thử giao diện trong browser. Không kết luận đã đạt chất lượng pháp lý tối đa hay sửa tận gốc HTTP 503 trước đây.
