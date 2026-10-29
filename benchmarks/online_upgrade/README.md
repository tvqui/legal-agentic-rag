# Kiểm tra ONLINE sau nâng cấp

`questions.json` chứa 28 câu/tình huống **chỉ có đầu vào**, không phải Gold pháp lý. Gồm tra nguyên văn, nhiều yêu cầu, thời điểm, thiếu dữ kiện, ngoại lệ, nối tiếp, đổi vụ việc, đính chính, xác nhận mâu thuẫn và câu ngoài phạm vi. File được đặt ở đây để có thể đưa lên Git; thư mục `artifacts/` chứa kết quả và bị bỏ qua bởi Git.

## Local không gọi model

Chạy từ thư mục gốc dự án. Dùng config đã pin đúng artifact muốn kiểm tra; không mặc định coi artifact trong máy là result_28-10.

```powershell
.\.venv\Scripts\python.exe scripts\run_local_online_smoke.py --config config\YOUR_PINNED_CONFIG.yaml --questions benchmarks\online_upgrade\questions.json --out artifacts\online_benchmarks\upgrade_local_new
```

Script tắt Dense/reranker và model, không rebuild OFFLINE. Kết quả chỉ kiểm tra logic/quy trình deterministic, không đo chất lượng hay độ trễ LLM. Resume yêu cầu plan, code và effective config không đổi. Đổi code/config phải tạo `--out` mới.

## Backend có inference thật

Sau khi đưa **bản sửa mới** lên backend riêng, cấu hình URL/token bằng cơ chế hiện có. Không ghi bí mật vào câu hỏi hoặc báo cáo.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_online_reliability.py --questions benchmarks\online_upgrade\questions.json --out artifacts\online_benchmarks\upgrade_candidate_new --preflight-only
.\.venv\Scripts\python.exe scripts\benchmark_online_reliability.py --questions benchmarks\online_upgrade\questions.json --out artifacts\online_benchmarks\upgrade_candidate_new --timeout 230 --resume
```

Kiểm tra `preflight.json`: `online_source_fingerprint`, `online_config_fingerprint`, build, model và policy. Runner từ chối tiếp tục khi code/config nhận diện khác phiên trước. Không so điểm model/code mới với phản hồi cũ như cùng một run. Chưa tự chạy inference thật trong đợt rà soát này.

## Đánh giá theo vai trò

| Thành phần | Nhóm phù hợp để kiểm tra | Dấu hiệu cần ghi |
|---|---|---|
| Hội thoại | bổ sung, đính chính, xác nhận, đổi vụ việc | dữ kiện kế thừa đúng, hỏi lại thừa, provenance |
| Task | nhiều yêu cầu và kết quả tính | đủ từng ý trong văn bản cuối, không dùng reason reviewer bù đáp án |
| Graph | thiếu căn cứ cần nối dẫn chiếu/ngoại lệ/hiệu lực | có cạnh thực sự duyệt, căn cứ mới đóng khoảng trống, chi phí và nhiễu |
| Auditor | điều kiện, ngoại lệ, chủ thể | căn cứ loại đúng/nhầm; UNKNOWN không tự thành PASS |
| Hậu kiểm | JSON hợp lệ nhưng nội dung sai hoặc thiếu | chặn lỗi và bỏ sót lỗi; không chỉ tỷ lệ JSON hợp lệ |
| Index | tra vị trí điều/khoản và anchor | tương đương scan, cold/warm, RAM |
| Cache thử nghiệm | cùng truy vấn kênh lặp trong một request | hit/miss, kết quả bất biến, thời gian; mặc định tắt |

Không coi 0 cạnh Graph hoặc cache 0 hit là bằng chứng thành phần đã góp ích. Không ép bật mọi thành phần cho mọi câu. Nếu thành phần gây hại ngay trong nhóm đúng vai trò, ghi rõ và điều chỉnh/tắt.

## Cache mới chưa bật mặc định

`retrieval.request_cache_enabled: false` là mặc định. Cache thử nghiệm giới hạn 16 entry, tối đa 64 Evidence/entry, chỉ tồn tại trong một request và xóa khi kết thúc/lỗi; không cache phán quyết, không dùng lại đáp án giữa người dùng. Có checkpoint cancel/deadline cả khi cache hit. ArtifactStore/config phải bất biến trong request.

Trong microbenchmark BM25 local trên result_28-10 (20 lần/cấu hình, 3 truy vấn/lần), dùng cache làm trung vị tăng từ khoảng 4,87 lên 6,38 ms ở truy vấn lặp, và từ 3,80 lên 8,49 ms ở truy vấn khác nhau. Chi phí copy vượt phần tiết kiệm. Vì vậy không bật để tuyên bố nhanh hơn. Dense chưa được đo inference thật; chỉ bật thử ở run riêng nếu có giả thuyết và đối chứng phù hợp.
