# Đánh giá kết quả OFFLINE ngày 13/10/2026

**Dùng được cho phát triển/benchmark ONLINE ở chế độ provisional. Chưa đạt readiness pháp lý đầy đủ và AI vẫn DEGRADED.** Đã kiểm trực tiếp hai ZIP, không chỉ dựa trên ảnh/log người dùng dán. Không thay config ONLINE đang dùng, corpus, catalog, ZIP hoặc Aura.

## Cải thiện đã xác nhận

- Hai ZIP đều CRC PASS, không có entry trùng.
- Final: registry, structure, graph, indexes đều PASS. Tính lại fingerprint graph trùng proof Aura trong ZIP: 52.876 node, 80.204 edge. Không truy vấn Aura live trong lần đánh giá này.
- 18.871 provision và 19.160 retrieval units, không thiếu provision nào trong retrieval. Provenance toàn bộ PASS; 38 provision có explicit note exclusions hợp lệ.
- 75 trang biểu mẫu dùng native text đã được giữ lại. 106 chú thích đã tách và giữ bằng chứng. Điều 62 khoản 2 điểm đ, 18/VBHN-VPQH, chỉ còn “đ) Trách nhiệm của người sử dụng lao động;”, không còn chú thích 33 trong nội dung điều khoản.
- Đối chiếu 95 SHA nguồn với snapshot ngày 12/10: không đổi. Đây không phải corpus mới cập nhật pháp luật đến 13/10; config đang dùng ngày chốt 15/09/2026.
- Bộ nạp ONLINE kiểm tra độc lập: `compatible=true`, `issues=[]`. FAISS có 19.160 vector x 1.024 chiều, hữu hạn và chuẩn hóa; 3 self-query đầu/giữa/cuối trả đúng ID.
- ZIP final đã bỏ vector partial trùng lặp; checkpoint vẫn dùng để khôi phục.

## So sánh công bằng với lần 12/10

| Hạng mục | 12/10 trước sửa | Final mới |
| --- | ---: | ---: |
| Provision / retrieval units | 18.871 / 19.160 | 18.871 / 19.160 |
| Graph nodes / edges | 50.900 / 78.227 | 52.876 / 80.204 |
| Diagnostic items | 15.178 | 15.145 |
| Phần bản án tạo được structured output | 3/56 | 226/243 |
| Bản án có feature AI được chấp nhận | 3 | 22 |
| Bản án hoàn tất toàn bộ theo gate hiện hành | 0/24 | 0/24 |
| Checklist có ít nhất một kết quả AI được chấp nhận | 11 | 17: 5 complete + 12 partial |
| Trang chờ review | 174 | 174 |

Chunk đã được chia nhỏ và success definition đã nghiêm ngặt hơn. Không so sánh 56 với 243 như cùng kích thước. `ai_succeeded=22` cho case nghĩa là có feature được chấp nhận, không phải 22 case hoàn tất. `succeeded=5` cho checklist là complete theo gate mới, không cùng semantics với `succeeded=11` cũ. Diagnostic count giảm nhẹ sau thay đổi grounding/tách chú thích không tự chứng minh chất lượng xấu hơn; tăng node/edge cũng không tự chứng minh trả lời đúng hơn.

## Blocker AI còn lại

Case: 236 logical network calls, 226/243 fragment có JSON hợp lệ, 22 case có feature AI, nhưng 0/24 complete. Có 162 fragment bị `UNGROUNDED_AI_FEATURES`, 16 fragment chưa gọi vì ngân sách stage hết, 1 fragment còn lỗi output-token sau split. Sau dedup, 2.036 feature AI được lưu; kiểm lại toàn bộ source quotes/spans: 0 mismatch. Feature không có quote khớp/định vị duy nhất bị loại, không đưa vào graph. Quote đúng vẫn chưa chứng nhận value/type đúng về pháp lý.

Checklist: 250 planned; 21 record attempted, 45 logical network calls; 5 complete, 12 partial, 229 chưa thử. `fallback=245` là số record chưa complete, gồm cả chưa thử, không phải 245 network errors. 21 network calls kết thúc bằng `AI_OUTPUT_TOKEN_LIMIT`, rồi circuit mở. Không nên tăng 250 lên 2.000 lúc này.

Log mới có HTTP 200, không có kiểu 31 HTTP 500 sau 120 giây của run cũ. `AI_OUTPUT_TOKEN_LIMIT` nghĩa output chạm giới hạn 2.048 token, dù HTTP request thành công. Mô hình vẫn offload 37/37 layers lên GPU và context 16.384. Không có bằng chứng lỗi do thiếu GPU hay API key.

Ưu tiên sửa tiếp: giảm độ dài quote/value/question, chia nhiệm vụ để JSON nhỏ hơn; nếu cần nhiều mục thì chia tiếp với coverage tracking, không cắt bỏ quy tắc để ép complete. Sửa/định vị lại những quotes không khớp hoặc quá ngắn gây ambiguity; chỉ repair phần thất bại, giữ cache và features hợp lệ. Tăng output budget có thể giúp một số request nhưng kéo dài thời gian và không giải quyết grounding. Không hạ gate SHA/evidence hoặc tắt circuit để làm PASS giả. Cần benchmark độ đúng nội dung, không chỉ tỷ lệ JSON hợp lệ.

Runner mất khoảng 4 giờ 02 phút 08 giây, chưa tính toàn bộ bootstrap notebook. Resume giúp 16 fragment chưa chạy, nhưng chỉ chạy lại nguyên cấu hình không chắc sửa được grounding/output cap; cache còn chứa những response cần repair.

## Những việc còn cần review

174 trang có ảnh/raw-selected evidence đầy đủ, nhưng vẫn REVIEW_REQUIRED: 70 native layer bất thường, 35 chỉ có text chữ ký, 68 cần đối chiếu khác biệt chữ số, 1 trang số trang. Khác biệt native/OCR không tự có nghĩa OCR sai, nhất là native chỉ có chữ ký. Không còn ERROR extraction tự động không có nghĩa hết sai chữ/số.

Nguồn 0/95 được human-verified; 25 legal changes và 18.871 provision intervals chờ duyệt; Gold 0 approved. 33 ambiguous path và 9 short-provision warnings vẫn được quarantine. Đúng khi `offline_ready_for_online=false`.

## Dùng bản mới cho ONLINE

Chọn `D:/data_thô/result/result_13-10/vn_labor_results.zip`; giữ technical checkpoint cho restore. Checkpoint trước AI/Aura không đáp ứng loader ONLINE hiện tại vì thiếu proof Aura final; trong checkpoint còn case quality report cũ, nên không dùng nó để đo AI của run mới.

Không đổi mỗi đường dẫn ZIP rồi giữ fingerprint V8.1. Tạo pin riêng tại repo:

```powershell
.\.venv\Scripts\python.exe scripts/pin_online_artifact.py `
  --artifact "D:/data_thô/result/result_13-10/vn_labor_results.zip" `
  --base-config config/online.yaml `
  --output config/online_release_20261013.yaml

.\.venv\Scripts\python.exe -m vn_labor_online.cli `
  --config config/online_release_20261013.yaml check
```

Sau đó chọn config mới khi chạy backend và chạy lại cùng benchmark câu hỏi. Giữ provisional và cảnh báo nguồn/temporal. Không thay corpus_snapshot_as_of thành ngày chạy notebook.

Trên Kaggle ONLINE, gắn chỉ Dataset final mới. `online_remote.py` tự dò thư mục unpacked có artifacts; nếu giữ ZIP tên `vn_labor_results.zip`, dùng `--artifact` với đúng đường dẫn Input thay vì trông vào auto-detect chỉ hỗ trợ tên V8.1 ZIP. Không gắn hai build làm AUTO chọn nhầm. Tạo pin với base config Kaggle và đường dẫn Input thực tế; pin local không mang nguyên sang Kaggle.

Build ID: `1836aa6ece8e0fda4f81b05492424217fe7ebd175fde5eb671232e8895b5c33a`.

SHA final: `ee128bcbc47d14212f07188a29d27d736f18bac6752951c0989c0b6ce891e3c0`.

Báo cáo chi tiết: `artifacts/reports/offline_results_review_20261013.json`. Lần này không gọi LLM, không chạy lại OFFLINE hoặc benchmark câu trả lời, không tạo approval. Chưa có bằng chứng cho phép khẳng định câu trả lời ONLINE đã chính xác hơn trên toàn bộ luật lao động.
