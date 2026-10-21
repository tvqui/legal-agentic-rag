# Kiểm tra và sửa notebook ONLINE Kaggle — 20/10/2026

Notebook nguồn: `C:\Users\Acer\Downloads\backend-1-1.ipynb`.
Notebook chuẩn trong repo: `kaggle/ONLINE_Backend.ipynb`.
Đây là notebook ONLINE; không chạy lại OFFLINE, OCR hoặc nạp lại Aura.

## Những điểm đã sửa

- Metadata notebook nguồn ghi GPU/Internet tắt và chưa có Input. Metadata xuất file không đủ chứng minh runtime thực tế; bản sửa yêu cầu kiểm Settings và tự kiểm GPU, Internet, Input, Secrets trước khi cài model.
- Cài hệ thống bị lặp. Bản sửa chạy `apt-get update -y` và `apt-get install -y git curl zstd` một lần trong luồng setup.
- Clone/fetch nhánh `main` mới nhất, in commit thật, không ghim commit cũ. Không xóa repo/cache; dừng nếu repo sai origin hoặc có tracked file đã sửa.
- Môi trường Python riêng tái sử dụng Torch/CUDA của Kaggle, ràng buộc phiên bản Torch đang có; kiểm import thư viện và CUDA sau khi cài. Không dùng bộ dependency OFFLINE cho ONLINE.
- Đọc lại Secrets mỗi lần chạy, đồng bộ khóa Researcher với Gemini key mới; không in key hoặc nhúng key trong notebook. Giữ Gemini 13 RPM, retry có giới hạn, Researcher và answer reviewer dùng Gemini.
- Không ưu tiên ZIP trước thư mục giải nén một cách im lặng. Nếu có nhiều ứng viên, yêu cầu chọn `ARTIFACT`; pin dữ liệu rồi so ba fingerprint thật với release trong `config/online_kaggle.yaml`. Human review chưa duyệt vẫn là PROVISIONAL.
- Probe Gemini trước khi launcher tải BGE/Qwen. Probe thất bại ngăn khởi động backend, kể cả khi lần chạy trước đã thành công. Không bỏ semantic review để qua readiness.
- Các bước setup có thời hạn và heartbeat. Cell backend cuối chạy liên tục, in URL tunnel thật dưới dạng `VITE_BACKEND_TARGET=...`; khi dừng/lỗi tự hiện phần cuối log đã che key. Không đặt cell chẩn đoán bắt buộc phía sau server chạy liên tục.
- Xóa output cũ và execution count. SHA-256 được tính từ đúng byte notebook đã ghi, nhất quán trên Windows/Linux.

## Cách sử dụng

1. Import notebook đã sửa lên Kaggle. Chọn **Internet ON**, **GPU T4 x2**. Notebook không tự cấp GPU, quota hay quyền Secrets.
2. Add Input dataset kết quả cuối `vn-labor-results-14-10`: ZIP `vn_labor_results.zip` hoặc thư mục `artifacts/` đã giải nén. Không thêm technical checkpoint, recovery hay package OFFLINE vào notebook ONLINE này.
3. Bật quyền dùng ba Secrets: `GEMINI_API_KEY`, `VN_LABOR_API_KEY`, `NGROK_AUTHTOKEN`. `HF_TOKEN` tùy chọn. `VN_LABOR_API_KEY` phải khớp `BACKEND_PROXY_TOKEN` ở frontend local.
4. Model Gemini mặc định giữ nguyên `gemini-3.5-flash-lite` mà bạn đang cấu hình. Nếu tài khoản không có quyền dùng model đó, sửa `GEMINI_MODEL` trong cell settings theo model tài khoản thực sự truy cập được. Probe sẽ kiểm tra; không coi tên model trong notebook là chứng nhận model sẵn có.
5. Run All trong phiên tương tác. Nếu còn service cũ dùng cổng 8000/11434, dừng cell backend cũ hoặc Restart Session trước; notebook không tự kill process không rõ chủ.
6. Chờ xuất `VITE_BACKEND_TARGET=https://...`, cập nhật dòng đó trong `frontend/.env` local và khởi động lại frontend. Giữ cell cuối chạy. URL được lưu thêm ở `/kaggle/working/vn_labor_online/remote_backend_url.txt` và không chứa token.

Nếu có nhiều Input kết quả, đặt `ARTIFACT` trong cell settings thành đường dẫn thực tế dưới `/kaggle/input/...`. Không bỏ kiểm fingerprint để dùng một bộ dữ liệu khác phiên bản.

Khi lỗi, gửi phần chẩn đoán đã che key. Log setup ở `/kaggle/working/vn_labor_online/notebook_logs/`; log backend/Ollama ở `logs/` cùng thư mục. Không gửi Secrets hoặc notebook cũ có output chứa thông tin riêng.

## Kiểm chứng và giới hạn

Các test thực thi helper và luồng notebook với fixture/mocks: chọn Input, fingerprint, cô lập dependency, Secrets, Gemini failure, cổng cũ, URL tunnel, log che key và process exit. Các cell đều được kiểm cú pháp. Không tải model hoặc chạy inference GPU trên máy local khi kiểm tra này.

Kết quả local: **16/16 test notebook PASS**, toàn bộ suite **630/630 PASS**.
Log suite: `artifacts/reports/kaggle_online_notebook_20261020_tests.log`.

Chưa thực thi notebook trên một phiên Kaggle thật. GPU quota, mạng tải model, quyền Gemini, quota API và thay đổi image Kaggle vẫn có thể gây lỗi; các bước kiểm tra sớm giúp phát hiện rõ nguyên nhân, không bảo đảm dịch vụ bên ngoài luôn hoạt động. Readiness kỹ thuật không thay thế kiểm duyệt pháp lý hoặc benchmark chất lượng.

Tạo lại notebook và SHA từ generator:

```powershell
.venv\Scripts\python.exe kaggle/online_notebook.py
```

Generator chỉ ghi notebook, không cài thư viện, gọi API hoặc khởi động server.
