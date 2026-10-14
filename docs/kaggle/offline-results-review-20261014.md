# Đánh giá trực tiếp kết quả OFFLINE ngày 14/10/2026

**Bản này tốt hơn về khối lượng AI đã khớp nguồn và độ ổn định yêu cầu. Dùng được cho ONLINE provisional/benchmark; chưa chứng minh câu trả lời chính xác hơn và chưa đạt readiness pháp lý đầy đủ.** Đã đọc cả ZIP cuối và technical checkpoint, so với ZIP cuối ngày 13/10. Không đổi code/config ONLINE đang dùng, corpus, catalog hoặc Aura.

## So sánh thực tế

| Hạng mục | Final 13/10 | Final 14/10 |
| --- | ---: | ---: |
| Tài liệu / provision / retrieval units | 95 / 18.871 / 19.160 | không đổi |
| Diagnostic items tổng | 15.145 | 16.241 |
| Checklist AI lưu và khớp nguồn | 132 | 1.255 |
| Provision có kết quả AI trong nhóm chọn lọc 250 | 17 | 93 |
| Provision hoàn tất theo gate checklist | 5 | 6 |
| Provision còn partial / chưa thử | 12 / 229 | 87 / 156 |
| Case features AI lưu và khớp nguồn | 2.036 | 5.360 |
| Case có feature AI trong artifact | 22/24 | 22/24 |
| Case hoàn tất theo gate hiện tại | 0/24 | 0/24 |
| Graph nodes / edges | 52.876 / 80.204 | 57.296 / 84.624 |
| Trang chờ review | 174 | 174 |

Giữ lại đủ 2.036 feature và 132 checklist AI cũ, không mất mục nào theo khóa dữ liệu. Case `ai_succeeded=15` chỉ là 15 case có kết quả được chấp nhận trong lượt xử lý mới; artifact cuối vẫn có feature AI ở 22 case. Không hiểu nó là giảm từ 22 xuống 15 case usable. `unprocessed_cases=0` nghĩa vòng lặp đã đi qua các record, không nghĩa mọi đoạn đều được xử lý.

Nguồn SHA của 95 tài liệu, provisions JSONL và retrieval units JSONL không đổi. Dense vectors có cùng CRC và fingerprint; FAISS được kiểm tra độc lập. Đây là bổ sung knowledge/graph/checklist, không phải bổ sung corpus mới hoặc cập nhật pháp luật đến ngày 14/10. Ngày chốt ONLINE hiện vẫn 15/09/2026.

## Kỹ thuật và provenance

- Hai ZIP CRC PASS, không entry trùng hoặc đường dẫn không an toàn. SHA được tính trực tiếp; không thay ZIP nguồn.
- Final registry/structure/graph/indexes PASS, INFO 1 + WARN 43, không có ERROR validation.
- Bộ nạp ONLINE độc lập `compatible=true`, `issues=[]`; graph fingerprint tính lại trùng proof Aura và số node/edge trong ZIP. Không truy vấn Aura live trong lượt đánh giá này.
- Kiểm lại **18.871 provenance**: 0 lỗi. **5.360 feature AI**: source SHA, coordinate space và quote offsets khớp. **1.255 checklist AI**: định vị lại quote và evidence span bằng code, 0 mismatch.
- Dense có 19.160 vector x 1.024 chiều, hữu hạn và chuẩn hóa; self-query đầu/giữa/cuối trả đúng ID. Đây là kiểm cấu trúc chỉ mục, không phải đánh giá độ đúng retrieval cho mọi câu hỏi.
- 106 chú thích vẫn được giữ riêng; trạng thái trang vẫn 2.927 PASS, 15 REVIEWED, 174 REVIEW_REQUIRED.

Quote/span đúng chỉ chứng minh trích dẫn khớp text nguồn đang lưu; không chứng minh OCR giống PDF ở mọi trang hoặc value/type/question AI có đủ ý pháp lý.

## Vì sao AI vẫn DEGRADED

Lượt 14/10 có **1.161 network calls case và 732 calls checklist**, tất cả thành công theo structured-output validation. Không có timeout/output-token/HTTP-provider failure trong hai run_id mới. Các lỗi output-token/circuit còn trong log là lịch sử được phục hồi từ run trước; phải lọc run_id và thời gian.

Mean request duration mới khoảng 9,10 giây cho case và 14,36 giây cho checklist, so với 43,46 và 53,77 giây ở run trước. Payload/chunk khác nhau nên không dùng tỷ lệ này để kết luận model suy luận nhanh hơn cùng một tác vụ. Tổng runner thực tế **6 giờ 04 phút 30 giây**, chưa tính bootstrap; nhiều request hơn khiến tổng lâu hơn.

Các gate còn báo:

- Case: **836 `AI_FRAGMENT_CAPACITY_REACHED`**, 487 `AI_STAGE_BUDGET_EXHAUSTED`, 6 `AI_GROUNDING_REPAIR_INCOMPLETE`; 844/1.325 fragment có response.
- Checklist: **502 `AI_FRAGMENT_CAPACITY_REACHED`**, 166 `AI_STAGE_BUDGET_EXHAUSTED`, 22 `AI_GROUNDING_REPAIR_INCOMPLETE`; 514/680 fragment có response. Có 94 provision đã thử, trong đó 93 có item; 156 chưa thử.

Gate hiện tại coi `len(items)>=4` là chưa có bằng chứng hết nội dung, rồi chia nguồn tiếp tới giới hạn depth/size. Vì model thường trả đủ 4 mục, cơ chế này tạo nhiều đoạn/request và vẫn không chứng minh hoàn tất. Đây là điểm chưa hiệu quả trong bản sửa 13/10 của tôi. Các mã capacity không tự chứng minh từng đoạn chắc chắn mất nội dung; nó biểu thị chưa chứng minh được coverage sau khi chạm trần. Không thể xóa gate hoặc coi mọi response HTTP 200 là COMPLETE.

`stop_reason=null` dù record có budget error là một bất nhất báo cáo: `observe(before)` chặn khi thời gian còn lại ít hơn timeout 240 giây, còn `stop_reason` chỉ kiểm đã vượt hẳn 10.800 giây. `circuit_open=false` là đúng: dịch vụ không hỏng. Đây là ngân sách stage không đủ để bắt đầu request tiếp, không có bằng chứng Kaggle kill phiên hoặc thiếu API key/GPU.

## Cải thiện tiếp theo nên ưu tiên

1. Sửa completion/continuation trước khi tăng 250 hoặc kéo thời gian chạy: theo dõi source-unit/rule coverage và những mục còn lại, loại kết quả trùng, phân trang có giới hạn khi thực sự còn nội dung. Có thể bổ sung `has_more`/source IDs để lập kế hoạch, nhưng lời model nói đã hết không được dùng làm bằng chứng duy nhất để PASS.
2. Bảo toàn quote/SHA/offset và cache đã có, chỉ retry phần thiếu. Đừng tăng số lượng output hoặc token đơn thuần rồi bỏ coverage guard; nguồn dài và exceptions vẫn phải được bao phủ.
3. Báo thống nhất stop reason và phân biệt restored/partial/complete trong summary. Technical checkpoint đã ghi `ai_quality_scope=RESTORED_BASELINE`, vì vậy các case/checklist quality trong đó là dữ liệu 13/10, không phải đánh giá AI mới.
4. Dùng ZIP cuối ngày 14/10 cho ONLINE và chạy lại cùng benchmark/Gold, kiểm actor, thời gian, ngoại lệ, hậu quả pháp lý và claim→citation. Nhiều feature/node hơn không chứng minh accuracy tăng; Dense/BM25 retrieval text chưa thay đổi.
5. Tiếp tục đối chiếu 174 trang và human source/temporal/quarantine/Gold review. Không tự sửa số/chữ dựa trên một OCR hay tự điền reviewer.

Chưa cần thêm API AI chỉ để sửa lỗi này: provider của lượt mới đã chạy ổn. Một model khác chỉ nên được chọn sau đánh giá chất lượng/cost trên mẫu đã duyệt, không dựa vào số node hay HTTP success.

## Có thể dùng ngay không?

**Có: chọn `D:/data_thô/result/result_14-10/vn_labor_results.zip` cho ONLINE provisional.** Checkpoint dành cho khôi phục, final validation trong đó vẫn `indexes=false` vì chưa chạy lại Aura/index query final. Dù giữ proof Aura của baseline 13/10, nó không thay thế final mới và loader hiện tại không chấp nhận các stage chưa PASS.

Tạo pin riêng, không dùng fingerprint graph của config 13/10/V8.1:

```powershell
cd D:\data_thô\legal-agentic-rag
.\.venv\Scripts\python.exe scripts/pin_online_artifact.py `
  --artifact "D:/data_thô/result/result_14-10/vn_labor_results.zip" `
  --base-config config/online.yaml `
  --output config/online_release_20261014.yaml

.\run.bat online-check -Config config/online_release_20261014.yaml
.\run.bat online -Config config/online_release_20261014.yaml
```

Nếu `.env` có `VN_LABOR_ARTIFACT_SOURCE` thì cập nhật nó hoặc bỏ override của ZIP cũ; pin mới phải khóa đúng artifact. Trên Kaggle ONLINE dùng đường dẫn Input thực tế với `--artifact`, không mang path Windows sang. Chỉ gắn một build kết quả. Cấu hình local pin mới cần do người dùng tạo/chọn; lần kiểm tra này chưa chuyển backend đang chạy.

Vẫn chưa đạt readiness pháp lý: **0/95 source human verified, 25 legal changes pending, 18.871 provision intervals chưa duyệt, Gold 0 approved**, cùng 33 ambiguous path và 9 short-provision quarantine. Cảnh báo Aura cuối Markdown là đoạn hướng dẫn điều kiện chung; final actual proof ngày 14/10 đã PASS, không có nghĩa Aura của lượt này chưa được cấu hình.

Build ID: `9a615f1927162fe63e73b734b6a48759596984fbf2d004ce76bc2eb94e0e5da0`.

SHA final: `895db689d0cb60f6a76042a70452cedadfb80151bc1d9818b1cb54c182d19071`.

SHA checkpoint: `a8d870668d4cf197c9f31d336189f3763e168668ffc0c5240db3b6d76ecdfece`.

Bằng chứng machine-readable: `artifacts/reports/offline_results_review_20261014.json`. Đánh giá này không chạy LLM, OFFLINE rebuild, benchmark câu trả lời hoặc tạo approval.
