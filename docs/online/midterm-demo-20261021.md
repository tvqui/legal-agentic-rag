# Đánh giá và kịch bản demo giữa kỳ — 21/10/2026

**Đủ để báo cáo tiến độ kỹ thuật dưới dạng bản thử nghiệm có giới hạn rõ ràng. Chưa đủ để giới thiệu là chatbot pháp lý hoàn thiện hoặc có độ chính xác cao đã được chứng nhận.** Đây là đánh giá từ code và lần chạy thực tế, không phải bảo đảm điểm số; yêu cầu cụ thể của giảng viên vẫn quyết định phạm vi nghiệm thu giữa kỳ.

## Bằng chứng hiện có

| Nội dung | Bằng chứng | Đánh giá cho demo |
| --- | --- | --- |
| Backend Kaggle và kết nối | 100/100 yêu cầu HTTP 200; `/ready` đầu/cuối READY, cùng v9/model/build | Có thể trình diễn luồng tích hợp trong điều kiện kết nối tương tự; không bảo đảm dịch vụ luôn sẵn sàng |
| Chat frontend → proxy → Kaggle → nguồn | Chrome thật gửi một câu, nhận HTTP 200, 11 nguồn, mở drawer có liên kết nguồn chính thức; khoảng 1.075 giây | Luồng chat và mở bảng nguồn đã chạy thật, không dùng đáp án giả lập; chưa kiểm tra phản hồi HTTP của website nguồn trong phép smoke này |
| Truy xuất | Trace có EXACT 1, PROFILE 43, HYBRID 46; 10 câu còn lại dừng sớm | Đã có nhiều luồng; không đúng khi nói chỉ đang chạy BM25 |
| Chất lượng câu trả lời | 37 đáp án một phần, 53 chưa có đáp án xác minh, 5 hỏi thêm, 5 ngoài phạm vi | Chưa đạt mục tiêu trả lời rộng, đúng và đủ |
| Tốc độ | Trung vị 32.367 giây; câu lâu nhất 190.250 giây | Phải trình bày biến động độ trễ, không dùng riêng câu nhanh nhất |
| Trích dẫn | 110 lượt citation, 63 ID trong release; không thấy sai locator hoặc sai bản trích trong phép kiểm tra đã chạy | Đúng ID/vị trí không chứng minh đúng lập luận; đã thấy nhận định sai phạm vi dù reviewer PASS |
| Kiểm thử code mới | 780 tests local PASS; bản sửa v10 chưa được đo trên Kaggle | Đây là kết quả kiểm thử phần mềm, không phải độ chính xác pháp lý |
| Phần quản lý tài liệu/cấu hình AI trên UI | Trang Tài liệu chưa có API duyệt registry; lựa chọn AI ở Cài đặt chưa nối backend | Báo rõ là phần chưa hoàn thiện, không trình bày như tính năng đã xong |

Đã đo đủ 100 câu trong **75 phút 34,128 giây**; tổng thời gian HTTP **4506,038 giây**, không trộn với phép thử giao diện bổ sung. Lần trước tổng HTTP 6557,256 giây. Code và model cùng thay đổi nên không quy chênh lệch cho riêng Gemini 3.1, cũng không suy ra độ chính xác tăng. Toàn bộ câu hỏi/đáp án/thời gian/nguồn/trace nằm trong thư mục `artifacts/online_benchmarks/risk100_20261020/round4_gemini31`.

## Những gì nên nói với thầy

> Em đã xây dựng bản thử nghiệm trợ lý tra cứu pháp luật lao động có giao diện chat, backend FastAPI và bộ dữ liệu OFFLINE. Luồng ONLINE phân tích câu hỏi, chọn căn cứ theo ngày áp dụng, truy xuất BM25/vector/graph, kiểm tra khả năng áp dụng và dựng đáp án có dẫn nguồn. Backend đang chạy trên Kaggle, frontend chạy trên máy cá nhân. Lần đánh giá mới chạy đủ 100 câu có rủi ro cao: không có lỗi HTTP, nhưng mới 37 câu có đáp án một phần và còn 53 câu chưa vượt được các bước xác minh. Em đã xác định lỗi kiểm tra ID nhận định, rơi căn cứ sau truy xuất và một số lỗi phạm vi lập luận; bản sửa mới đã qua kiểm thử local và đang chờ đo lại trên môi trường thật. Mục tiêu tiếp theo là tăng độ đúng và đủ bằng kiểm thử hồi quy và bộ chuẩn do người có chuyên môn duyệt.

Không nói “đạt 100%”, “đúng 37%”, “Gemini đã xác minh pháp luật” hoặc “mọi phase đã hoàn tất”. 100% ở đây chỉ là số yêu cầu HTTP kết thúc thành công. Các mốc DONE của kế hoạch cũ chủ yếu ghi nhận triển khai code, không thay thế số liệu kiểm chứng mới này.

## Trình tự trình bày khoảng 10–12 phút

1. **Bài toán và phạm vi — 1 phút.** Tra cứu pháp luật lao động Việt Nam; có ngày áp dụng, chủ thể và căn cứ nguồn. Giải thích vì sao cần giữ cảnh báo và từ chối khi chưa đủ, đồng thời thừa nhận từ chối nhiều vẫn là hạn chế.
2. **Kiến trúc — 2 phút.** OFFLINE: tài liệu → trích xuất/cấu trúc/metadata → graph và chỉ mục → release. ONLINE: frontend → FastAPI → phân tích/ngữ cảnh → chọn luồng truy xuất → kiểm tra căn cứ → tạo đáp án → reviewer → citations/trạng thái. Phân biệt FastAPI là framework API, Gemini/Qwen là mô hình/dịch vụ AI.
3. **Demo luồng thật — 4 phút.** Dùng các câu dưới đây; bấm vào citation để mở nguồn. Không che các cảnh báo PROVISIONAL và không gọi link metadata là phê duyệt pháp lý.
4. **Đánh giá — 2 phút.** Đưa bảng tổng hợp đủ 100 câu, trung vị/thời gian lớn nhất và một ví dụ thất bại. Có thể dùng `NEW-8.4` để chỉ ra hệ thống cần hỏi vùng/thời điểm/điều kiện làm việc nhưng hiện còn mắc lỗi reviewer.
5. **Việc tiếp theo — 1–3 phút.** Đo v10; sửa độ bao phủ câu đa vấn đề và câu thiếu dữ kiện; kiểm tra dữ liệu hiệu lực/canonical; xây Gold được duyệt; sau đó mới tối ưu độ trễ và mở rộng chức năng UI.

## Năm câu demo đã có kết quả trong lượt đo

| Câu | Nội dung | Thời gian HTTP đã đo |
| --- | --- | ---: |
| USER-1 | Điều 1 Nghị định 145/2020/NĐ-CP, đầy đủ phạm vi và nguồn | 0,859 giây |
| USER-2 | Nghỉ việc tại ngày 15/12/2020, phải chọn luật có hiệu lực đúng ngày | 2,641 giây |
| USER-3 | Hợp đồng không xác định thời hạn, không ngoại lệ/đặc thù, báo 20 thay vì 45 ngày và hậu quả | 5,844 giây |
| USER-4 | Thử việc công việc cần cao đẳng: 90 ngày, lương 80%; đánh giá riêng hai phần | 2,937 giây |
| USER-5 | Hỏi nối tiếp USER-4: thử thêm một lần nữa cùng công việc | 3,938 giây |

Lấy nguyên văn câu hỏi từ `responses.md`. Mở cuộc trò chuyện mới cho từng câu độc lập. Riêng USER-5 hỏi ngay sau USER-4 trong cùng cuộc trò chuyện. Các thời gian này là lịch sử một lần đo, không bảo đảm lần demo sau vẫn bằng như vậy. USER-1 đã được thử thêm bằng Chrome, mở nguồn thành công; không tính phép thử này thành câu thứ 101 của benchmark.

Để thể hiện hệ thống không chỉ trả câu mẫu, có thể dùng thêm `OLD-4.2` (cần dữ kiện về nghỉ việc) hoặc `OLD-5.1` (ngoài phạm vi). Đồng thời trình bày công khai một lỗi trong báo cáo 100 câu; không dùng năm câu thuận lợi để mô tả chất lượng toàn hệ thống.

## Chuẩn bị trước buổi báo cáo

1. **Giữ một phiên bản đã kiểm chứng.** V9 hiện đã đo đủ 100 câu và có smoke UI. V10 đang nằm trong repository local, chưa có benchmark Kaggle. Nếu sát giờ demo, giữ v9 để báo cáo; không thay sang v10 rồi coi như đã được xác nhận. Ghi commit thực tế trên Kaggle bằng `!git -C /kaggle/working/legal-agentic-rag rev-parse HEAD`. Nếu có cập nhật code trước demo, phải chạy lại ít nhất năm câu và kiểm tra nguồn/ngữ cảnh trên đúng phiên bản đó; không dùng bảng thời gian v9 như số đo v10.
2. **Kiểm tra Kaggle trước buổi báo cáo.** Chạy backend và kiểm tra `/ready`, model, dataset đã ghim. Dành thời gian chuẩn bị trước buổi báo cáo vì phiên Kaggle, tải model, ngrok và API ngoài có thể gián đoạn. Không mong một phiên để qua đêm sẽ chắc chắn còn hoạt động.
3. **Khởi động frontend trên máy:**

```powershell
cd D:\data_thô\legal-agentic-rag
.\run.bat frontend
```

Mở đúng URL Vite in ra. Nếu ngrok thay đổi, cập nhật `VITE_BACKEND_TARGET` trong `frontend/.env` rồi khởi động lại frontend. Dùng `/api` làm base qua proxy; token dùng `BACKEND_PROXY_TOKEN`, không đưa token vào biến có tiền tố `VITE_`. Không chiếu màn hình `.env`, Kaggle Secrets hay token khi báo cáo.

4. **Kiểm tra đúng qua frontend.** Thay cổng nếu Vite in cổng khác:

```powershell
Invoke-RestMethod -Uri "http://localhost:5173/api/ready"
```

Sau đó gửi USER-1 và mở citation, gửi USER-4 → USER-5 để kiểm tra nối tiếp. Chỉ `/health` thành công chưa đủ chứng minh luồng chat/proxy/reviewer đang hoạt động.
5. **Lưu bằng chứng dự phòng:** `responses.md`, `responses.csv`, ZIP kèm SHA, `demo-live-source.png`. Nếu mạng gián đoạn, nói rõ đang trình bày kết quả đã ghi lại, không mô tả ảnh hoặc log cũ là phản hồi trực tiếp. Giao diện thử được mở ở cổng tạm 5187 đã được đóng sau kiểm tra; bạn dùng lệnh frontend như bình thường.

## Phần còn phải làm sau giữa kỳ

- **ONLINE:** đo các sửa đổi v10; 25 câu vòng này có lỗi ID ở bước semantic review cuối. Ngoài schema, còn câu thiếu lập luận áp dụng, mất ngoại lệ hoặc sai giai đoạn thủ tục. Hai guard đã tái hiện không chứng minh mọi trường hợp đã được xử lý.
- **Dữ liệu:** nguồn/hiệu lực/Gold chưa duyệt; cần kiểm tra các unit canonical BHTN và khoảng hiệu lực BHXH đã nêu trong báo cáo kỹ thuật. Không xóa cảnh báo để “làm đẹp” demo. Không cần chạy lại OFFLINE chỉ để demo luồng hiện có.
- **Đánh giá:** xây đáp án chuẩn và qrels được duyệt, đo recall và chất lượng claim theo ngày/chủ thể/ngoại lệ; thêm lỗi thực tế vào regression mà không viết đáp án cứng cho từng câu.
- **Sản phẩm:** hoàn thiện quản lý tài liệu và nối cấu hình UI với hành vi thật; kiểm chứng hiệu năng/độ ổn định ngoài một phiên Kaggle.

**Kết luận sử dụng:** bản hiện tại cho thấy một luồng tích hợp thật và có quy trình đo, truy vết lỗi, sửa và kiểm thử. Đây là nội dung có thể báo cáo tiến độ. Mục tiêu trả lời đúng và đủ trên phạm vi rộng vẫn chưa đạt.
