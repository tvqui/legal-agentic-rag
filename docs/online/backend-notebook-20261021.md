# Kiểm tra backend-1-2.ipynb: probe Gemini 3.1 timeout

Notebook người dùng gửi ở `C:/Users/Acer/Downloads/backend-1-2.ipynb` có JSON và các cell hợp lệ, chọn `gemini-3.1-flash-lite` đúng. Input đã pin, model được đặt cho cả Researcher và reviewer. Lỗi được lưu trong chính notebook này là **GEMINI_PROBE_TIMEOUT**, không phải HTTP 400 của lượt trước. Không gộp hai lỗi thành một nguyên nhân.

## Lỗi và thay đổi

1. Probe trong provider bị giới hạn cứng 20 giây. Dù cell `run_step` cho phép 120 giây, giới hạn nội bộ vẫn ngắt probe sau 20 giây. Sửa thành cấu hình `VN_LABOR_GEMINI_PROBE_TIMEOUT_SECONDS`: mặc định ngoài notebook vẫn 20, chỉ chấp nhận số nguyên 1–60 giây. Provider timeout nhỏ hơn vẫn được giữ làm giới hạn trên. Notebook mới đặt 60 cho khởi động. Đây không phải bằng chứng timeout là nguyên nhân duy nhất hay cam kết 60 giây sẽ thành công.
2. Launcher `/ready` trước đây chờ HTTP tối đa 45 giây. Khi hai role phải probe tuần tự, giá trị này phải khớp ngân sách mới: tối đa `2*probe + 5`, đồng thời không vượt phần thời gian startup còn lại. Notebook cho startup tối đa 240 giây. Ngân sách trả lời câu hỏi vẫn là 180 giây, không tăng trong đợt sửa này.
3. `check_gemini.py` nhận `--probe-timeout`; notebook truyền giá trị đã chọn và `--diagnose`. Chỉ khi HTTP 400 mới có thêm một plain probe có giới hạn. Timeout hoặc JSON thất bại vẫn chặn backend, không coi key có trong Secrets hay plain probe thành công là đạt.
4. Kiểm tra cấu hình thực tế bắt buộc cả Researcher và reviewer cùng model đã chọn. Giữ kiểm fingerprint, chế độ provisional, semantic review, quota 13 RPM và bộ giới hạn chung. Không tự chuyển model hay thay key.
5. Cell setup kiểm code mới đã có chức năng probe tương ứng. Nếu chưa push code, notebook dừng và hướng dẫn cập nhật thay vì chạy nhầm bản cũ.
6. Xóa outputs và execution count cũ; giữ nội dung nguồn của notebook sạch. Bản gửi người dùng tiếp tục dùng Gemini 3.1, Qwen3:8b, Dense, reranker, graph và cùng result_14-10. Không chứa Secrets. Không chạy OCR hay OFFLINE.

Generator mặc định `kaggle/ONLINE_Backend.ipynb` vẫn là Gemini 3.5. Để tạo bản 3.1 rõ ràng:

```powershell
.venv\Scripts\python.exe kaggle/online_notebook.py --gemini-model gemini-3.1-flash-lite --output build/kaggle/ONLINE_Backend_Gemini31.ipynb
```

## File đã sửa

- `C:/Users/Acer/Downloads/backend-1-2.ipynb`: bản sửa dùng 3.1 để import lại Kaggle, có `.sha256` cạnh file.
- File gốc được giữ nguyên byte ở `backend-1-2.original-20261021-<SHA12>.ipynb` cùng thư mục Downloads; bản này giữ outputs lỗi để đối chiếu, không cần upload làm notebook chạy.
- `build/kaggle/ONLINE_Backend_Gemini31.ipynb` trong repository: bản sao sạch và SHA.
- `kaggle/ONLINE_Backend.ipynb` và generator được cập nhật cùng cơ chế chờ; file mặc định này tiếp tục dùng 3.5.

## Cách chạy

Đầu tiên đưa code sửa mới lên GitHub, vì notebook lấy backend từ `origin/main`, không mang toàn bộ backend trong file ipynb:

```powershell
cd D:\data_thô\legal-agentic-rag
git add src/vn_labor_online/providers.py kaggle/check_gemini.py kaggle/online_remote.py kaggle/online_notebook.py
git add kaggle/ONLINE_Backend.ipynb kaggle/ONLINE_Backend.ipynb.sha256
git add tests/online/test_gemini_probe_budget.py tests/online/test_kaggle_online_notebook.py
git add docs/online/backend-notebook-20261021.md
git diff --cached --stat
git commit -m "Allow bounded cold-start Gemini probes in Kaggle notebooks"
git push
```

Tôi chưa tự commit/push. Bản chẩn đoán lỗi 400 ở commit trước vẫn là điều kiện cần; không chỉ copy một file provider sang repo cũ thiếu module.

Sau đó:

1. Import lại **file Downloads `backend-1-2.ipynb` đã sửa** vào Kaggle.
2. Internet ON, GPU T4 x2, một Input `vn-labor-results-14-10`; bật quyền dùng GEMINI_API_KEY, VN_LABOR_API_KEY và NGROK_AUTHTOKEN. HF_TOKEN tùy chọn.
3. Dừng cell backend cũ nếu còn chạy; Run All phiên tương tác. Không bật Run All & Save với kỳ vọng server tiếp tục phục vụ khi notebook kết thúc.
4. Xem `Effective ONLINE profile`: hai model Gemini phải đều là 3.1. Probe phải đạt; backend sau đó cũng phải đạt `/ready`.
5. Khi thấy `VITE_BACKEND_TARGET=https://...`, cập nhật frontend local nếu URL thay đổi, khởi động lại frontend và giữ cell cuối đang chạy.

Nếu probe vẫn lỗi sau ngân sách 60 giây, gửi dòng JSON mới và mã lỗi. Không tăng thời gian vô hạn, không tắt Gemini/JSON review để khởi động cho qua. Nếu là 400 thì xem `error_reason` và kết quả plain probe; nếu là 429 thì kiểm tra quota, không suy luận từ timeout rằng hết RPM.

## Kiểm chứng

- **747/747 kiểm thử local PASS**. Log: `artifacts/reports/backend12_20261021_tests.log`.
- Mọi code cell trong notebook sạch được compile, SHA được tính lại và đối chiếu; bản gốc được sao lưu trước khi thay thế.
- Các kiểm thử mới kiểm ngân sách default/configured/invalid/provider bound, thời gian chờ HTTP của launcher, giữ tên model, chặn code injection trong tham số generator và truyền cấu hình chẩn đoán.
- Không gọi Gemini thật, không tải model hoặc chạy GPU trên máy local. Chưa thực thi bản notebook sửa trên Kaggle; không cam kết model hoặc mạng/dịch vụ bên ngoài sẽ luôn hoạt động.
