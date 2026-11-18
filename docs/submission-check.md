# Kiểm tra bản bàn giao sau dọn — 18/11/2026

## Nội dung còn trong bản Git

Mã OFFLINE/ONLINE, frontend, cấu hình, script vận hành, notebook, mã đánh giá, kiểm thử, Gold nhỏ, template/bản sửa nguồn cần thiết và tài liệu hiện hành. Các bảng số liệu gọn có tên ZIP, SHA-256 và comparison_key ở `đo/results_summary/`.

Không đổi thuật toán hỏi đáp trong lần dọn. Không chạy lại toàn bộ OCR, API model thật hoặc phiên Kaggle; các kiểm tra dưới đây là local.

## Kiểm tra đã thực sự chạy

| Kiểm tra | Kết quả |
|---|---|
| Python `unittest discover -s tests` | 1.687 test; đạt, 1 bỏ qua |
| Bản đã stage trước push, kiểm thử trong thư mục riêng | 1.672 test; đạt, 1 bỏ qua |
| Frontend `npm test` | 18/18 đạt |
| Frontend `npm run lint` | Đạt |
| Frontend `npm run build` | Đạt |
| Coding Team unit tests | 86/86 đạt; dùng mock, không gọi API thật |
| Graph QA unit/integration tests | 72 test; đạt, 1 bỏ qua |
| Tệp .env thực trong danh sách dự kiến Git | Không có |
| Tệp trên 10 MiB trong danh sách dự kiến Git | Không có |
| SHA-256 bản sao tài liệu còn vướng NTFS | 49 tệp khớp |

Test snapshot riêng tư của source resolver chỉ chạy khi có hồ sơ `review/inputs/.../source_review_tracking.csv`. Hồ sơ này không thuộc bản Git; các kiểm thử resolver bằng fixture vẫn chạy. Không dựng dữ liệu thật giả hoặc đổi kỳ vọng để biến kiểm tra thành PASS.

## Lưu trữ và những gì giữ cục bộ

Kho `PhapDienAI_luu_tru_20261118` cạnh dự án có hai nhóm `đo` và `dự_án`, kèm nhật ký nguồn–đích để phục hồi. Đã chuyển 149 mục. Còn 10 mục tài liệu lịch sử (49 tệp) không chuyển được vì quyền NTFS: đã sao lưu, đối chiếu hash, bỏ theo dõi và ignore khỏi Git. Chúng có thể còn thấy trên máy nhưng không thuộc bản nộp.

Lần thử chuyển nguyên `docs` bị kiểm duyệt tự động từ chối và không được thực hiện. Kho lưu trữ có script `finish_cleanup.ps1` chỉ xử lý các tệp lịch sử đã sao lưu, dành cho người dùng đọc và chạy bằng PowerShell quản trị nếu muốn chuyển nốt bản local; script chưa được thực thi ở quyền quản trị.

`.venv`, `node_modules`, `.cache/online`, corpus, artifact làm việc và các release đang được cấu hình tham chiếu vẫn giữ trên máy để tiếp tục chạy, được Git-ignore. Giữ `.git` và lịch sử commit; không rewrite lịch sử để giảm dung lượng. Không commit/push trong lần dọn. Chỉ các tài liệu lịch sử đã sao lưu nhưng bị chặn NTFS được bỏ theo dõi Git, nên có thay đổi xóa trong index.

## Để giảng viên chạy lại

Đọc README, cung cấp corpus hoặc artifact bên ngoài Git, cài dependency và cấu hình dịch vụ/model. Chỉ `git clone` không tự đem theo dữ liệu lớn hay khóa. Xem [ONLINE](online.md), [OFFLINE](offline.md), [đầu ra artifact](offline/artifact-layout.md) và [bộ đo](../đo/README.md).

## Kiểm tra bản stage trước push

Bản stage được xuất sang thư mục riêng và chạy với mã nguồn của chính bản đó. Một số thử nghiệm/kiểm thử truy xuất cũ chưa thuộc phạm vi đóng gói và dọn repository được giữ local, nên số test khác lần chạy toàn bộ thư mục làm việc. Đã phát hiện và sửa Git chuyển LF/CRLF làm lệch SHA của Ontology/correction khi checkout trên Windows: `.gitattributes` giữ nguyên byte hai nhóm tệp được ghim hash. Không bỏ kiểm fingerprint để làm test qua.
