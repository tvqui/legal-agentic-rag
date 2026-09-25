# Chạy toàn bộ ONLINE backend trên Kaggle

## Kết luận kiến trúc

Kaggle API Token hoặc Legacy API Credentials chỉ xác thực Kaggle CLI/SDK để
upload dataset, tải output hay chạy notebook tự động. Chúng không biến notebook
thành inference API. Runtime này cần hai Kaggle Secrets:

- `NGROK_AUTHTOKEN`: token của tài khoản ngrok.
- `VN_LABOR_API_KEY`: chuỗi bí mật tự tạo, tối thiểu 32 byte.

`HF_TOKEN` là tùy chọn để tránh rate limit khi tải BGE-M3.

Toàn bộ FastAPI, registry, graph, Dense/BM25 và Qwen chạy trong phiên Kaggle.
Máy local chỉ chạy Vite; token được Vite dev proxy gắn ở phía Node và không nằm
trong bundle JavaScript gửi cho trình duyệt.

Kaggle phù hợp cho phát triển, đánh giá và demo. Một phiên CPU/GPU tối đa khoảng
12 giờ, có giới hạn idle/quota và URL tunnel có thể đổi sau khi restart. Không
dùng cấu hình này như server production 24/7.

## 1. Chuẩn bị Kaggle

1. Tạo Notebook Private, bật Internet và GPU. T4 x2 là lựa chọn tốt nhất; P100
   vẫn chạy được nhưng Dense và Qwen dùng chung GPU.
2. Add Input một Dataset Private chứa đúng `vn_labor_results_v8.1(aura).zip`.
   Kaggle có thể tự giải nén ZIP và hiển thị trực tiếp thư mục `artifacts/`; launcher
   hỗ trợ cả file ZIP lẫn Dataset đã giải nén.
3. Trong **Add-ons → Secrets**, tạo `NGROK_AUTHTOKEN` và
   `VN_LABOR_API_KEY`. Có thể tạo key local bằng:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Không cần đưa Kaggle API token hoặc `kaggle.json` vào Notebook Secrets để chạy
backend.

## 2. Cell cài đặt

```python
!git clone https://github.com/tvqui/legal-agentic-rag.git /kaggle/working/legal-agentic-rag
%cd /kaggle/working/legal-agentic-rag
!python -m pip install -q -e ".[retrieval,online]" ngrok
!curl -fsSL https://ollama.com/install.sh | sh
```

## 3. Cell chạy server

Cell này phải tiếp tục chạy để giữ backend và tunnel sống:

```python
%cd /kaggle/working/legal-agentic-rag
!python kaggle/online_remote.py
```

Chờ dòng `REMOTE_BACKEND_URL=https://...ngrok...`. Nếu khởi động thất bại, xem:

```python
!tail -n 100 /kaggle/working/vn_labor_online/logs/ollama.log
!tail -n 100 /kaggle/working/vn_labor_online/logs/backend.log
```

## 4. Nối frontend local

Tạo `frontend/.env`:

```dotenv
VITE_BACKEND_TARGET=https://URL-VUA-NHAN.ngrok-free.app
BACKEND_PROXY_TOKEN=CHINH_XAC_GIA_TRI_VN_LABOR_API_KEY
```

Sau đó chỉ chạy trên máy local:

```bat
run.bat frontend
```

Không cần chạy `run.bat online`. Mở `http://127.0.0.1:5173`; request đi qua
Vite proxy, được gắn Bearer token rồi chuyển đến Kaggle.

## 5. Kiểm tra

```powershell
$headers = @{ Authorization = "Bearer YOUR_VN_LABOR_API_KEY"; "ngrok-skip-browser-warning" = "true" }
Invoke-RestMethod -Uri "https://YOUR-URL/ready" -Headers $headers
```

Kết quả phải có `ready=true`, `offline_artifacts=READY` và cả `researcher`,
`auditor`, `adjudicator` đều `READY`. Dense và reranker ở trạng thái `LAZY` cho đến
truy vấn semantic đầu tiên. Launcher tải sẵn BGE-M3 và BGE reranker trước khi mở tunnel,
nên truy vấn đầu không còn phụ thuộc vào một lượt tải model chưa hoàn tất.

Sau mỗi lần Kaggle restart, chạy lại cell server và cập nhật duy nhất
`VITE_BACKEND_TARGET` nếu URL ngrok thay đổi. Không commit hai file `.env`.
