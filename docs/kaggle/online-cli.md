# Một lệnh chạy toàn bộ ONLINE trên Kaggle

Luồng này dùng Kaggle CLI làm trình điều phối. Docker không được dùng vì Kaggle
đã chạy Notebook trong container do Kaggle quản lý; một notebook bootstrap có
vai trò tương đương entrypoint và tương thích GPU/Input/Secrets của Kaggle hơn.

## Phần được tự động hóa

- Dùng cố định kernel `qutrnvinh3/vn-labor-online-full`.
- Nếu kernel đang chạy thì tái sử dụng, không push version mới.
- Nếu kernel chưa tồn tại thì tạo; nếu đã dừng thì cập nhật đúng kernel đó và
  tạo một run mới.
- Bật Internet, GPU T4 x2 (`NvidiaTeslaT4`) và gắn Dataset artifacts qua
  `kernel-metadata.json`.
- Clone đúng commit Git hiện tại, cài dependencies, Ollama, Qwen, Dense và
  reranker rồi chạy backend.
- Poll log về `artifacts/kaggle_online/`, lấy `REMOTE_BACKEND_URL`, cập nhật
  `frontend/.env`, kiểm `/ready` và mở frontend local.

Kaggle CLI không có trường metadata để cấp quyền Secret. Với kernel mới, mở
`https://www.kaggle.com/code/qutrnvinh3/vn-labor-online-full` đúng một lần,
vào **Add-ons → Secrets** và bật `VN_LABOR_API_KEY`, `NGROK_AUTHTOKEN`;
`HF_TOKEN` và `NGROK_DOMAIN` là tùy chọn. Các lần cập nhật sau giữ nguyên kernel
ID nên không cần làm lại. Không đưa `.env`, token hay `kaggle.json` vào Notebook.

## Chạy

Lần đầu và các lần sau đều dùng:

```bat
cd /d D:\data_thô\legal-agentic-rag
run.bat kaggle-online
```

Lần đầu, script tự cài Kaggle CLI. Nếu chưa đăng nhập, làm theo luồng
`kaggle auth login` được mở trong terminal. Nếu run đầu báo thiếu Secret, bật
Secrets một lần trên trang kernel rồi chạy lại cùng lệnh.

Kiểm tra trạng thái hoặc lấy log thủ công:

```bat
run.bat kaggle-online-status
run.bat kaggle-online-logs
```

Muốn chỉ dựng backend mà chưa mở Vite:

```bat
.venv\Scripts\python scripts\kaggle_online_cli.py start --no-frontend
```

Các slug và timeout nằm trong `config/kaggle_online_cli.yaml`.

## URL ngrok

Không code cứng URL được in từ một phiên ngẫu nhiên. Trình điều phối luôn đọc
`REMOTE_BACKEND_URL` từ log và ghi lại `VITE_BACKEND_TARGET` trước khi mở Vite.

Muốn URL cố định, reserve một free static domain trong ngrok, tạo Kaggle Secret
`NGROK_DOMAIN` có giá trị chỉ gồm hostname, ví dụ
`dividend-hasty-backed.ngrok-free.dev`, rồi bật Secret đó cho kernel. Launcher
sẽ yêu cầu đúng domain này ở mọi phiên. Nếu không có `NGROK_DOMAIN`, luồng tự
cập nhật `.env` nên vẫn không cần sửa tay.

## Giới hạn còn lại

- Secret phải bật trên Web một lần vì Kaggle CLI không hỗ trợ attachment này.
- Mỗi lần backend đã dừng và cần chạy lại, Kaggle phải tạo một kernel **version/run**
  mới; đây vẫn là cùng một Notebook, không phải Notebook trùng.
- Phiên chạy vẫn chịu quota, giới hạn thời gian và khả năng cấp GPU của Kaggle.
- Frontend local phải còn đúng `BACKEND_PROXY_TOKEN` tương ứng
  `VN_LABOR_API_KEY`; script không đọc Secret từ Kaggle về máy.
