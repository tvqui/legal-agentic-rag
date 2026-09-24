# Đối chiếu nhận xét và kết quả sửa mã — 13/09/2026

Phần lớn nhận xét trong tài liệu gửi kèm đúng với mã và artifacts cũ: index có thể chạy được nhưng dữ liệu pháp lý đầu vào vẫn sai. Đã sửa các cơ chế gây lỗi và chạy bản rà soát riêng. **Chưa thể kết luận OFFLINE v1 hoàn tất hoặc sẵn sàng ONLINE.**

## Kết luận từng nhóm

| Nhận xét | Đánh giá và thay đổi |
|---|---|
| Metadata thiếu, lấy nhầm số văn bản từ trích dẫn | Đúng. Tách số văn bản pháp luật, số vụ án và số được trích dẫn; ưu tiên tên file/header của chính tài liệu. ID nguồn dựa trên SHA và đường dẫn, không phụ thuộc metadata suy đoán. |
| Title/issuer lấy nhầm từ phần căn cứ hoặc phụ lục | Đúng. Giới hạn vùng header và ưu tiên tên cơ quan đầy đủ; thêm `source_catalog.yaml` ràng buộc SHA cùng provenance và cờ xác minh. Heuristic vẫn cần người kiểm tra. |
| HISTORICAL/CONSOLIDATED đặt sai tầng | Đúng. Thêm `instrument_type`, `version_role`, `legal_status`, `instrument_number`, `version_id`. Giữ trường cũ để tương thích. Không tự gán EXPIRED chỉ vì nằm trong thư mục historical. |
| OCR theo toàn tài liệu bỏ sót PDF trộn | Đúng. Quyết định OCR theo trang, giữ thứ tự và provenance trang; cache theo nội dung/cấu hình; Docling xuất plain text. Worker có timeout thực thi theo tài liệu và checkpoint. |
| Phụ lục/mẫu bị parse thành khoản/điểm | Đúng. Thêm segmentation cho phần mở đầu, thân chính, phụ lục, mẫu, chữ ký, quy định đính kèm. Chỉ MAIN_BODY tạo Article/Clause/Point. Phần quy định đính kèm chưa parse được phải báo cần rà soát. |
| Chữa ID trùng bằng thêm thứ tự vào hash | Không áp dụng. Trùng canonical path làm cách ly provisions của tài liệu và phát lỗi; không đổi nhãn hoặc tự bỏ đoạn trùng. |
| Gộp các văn bản cùng chủ đề thành phiên bản | Đúng. `LegalInstrument` dùng số hiệu; `PolicySeries` chỉ liên kết khi được khai báo. Văn bản hợp nhất cần liên kết văn bản gốc đã xác minh. |
| Resolver nối “Điều 35” tới mọi luật, mất khoản/điểm, bỏ threshold | Đúng. Resolve đủ điểm/khoản/điều và số hiệu; tên luật dùng alias được khai báo; trường hợp mơ hồ lưu UNRESOLVED. Áp dụng threshold; chỉ lấy quan hệ sửa đổi/bãi bỏ/thay thế từ câu tác nghiệp ở thân chính. |
| Retrieval units thiếu ngữ cảnh | Đúng. Bổ sung breadcrumb, chương, ngữ cảnh tổ tiên, nguồn, phiên bản, temporal metadata, loại segment và source text. Phụ lục/mẫu có units riêng. ID trùng bị từ chối. |
| Checklist bị lặp vì mọi ancestor chứa toàn văn descendants | Không đúng một cách tổng quát với parser hiện tại: ancestor giữ phần văn bản riêng. Giữ các quy tắc mở đầu có ý nghĩa; lọc câu “nếu có vướng mắc” mang tính hành chính và kiểm tra trích đoạn do Ollama trả về. |
| Neo4j MERGE giữ node/cạnh cũ | Đúng. Thay thế dataset trong một transaction, kiểm tra chính xác ID/loại/đầu mút/số lượng, thêm semantic labels và build fingerprint. Gặp dữ liệu legacy/xung đột phải dừng, không tự xóa. |
| Graph chỉ được tạo sau Dense | Đúng. Lưu graph và validation trước index; Dense chạy worker riêng, lỗi ghi vào báo cáo. |
| Config không dùng, thiếu tests và validation yếu | Đúng. Dùng các khóa đã khai báo, từ chối khóa lạ; bổ sung kiểm thử hồi quy, semantic validation, kiểm tra index cũ và báo cáo Neo4j không khớp build. |

`effective_to` trống không tự chứng minh lỗi: có thể là khoảng hiệu lực chưa kết thúc hoặc chưa biết. Bộ lọc thời gian yêu cầu metadata đã xác minh; ngày kết thúc là biên loại trừ. Đây là helper cho giai đoạn retrieval sau này, **chưa phải hệ thống dựng đầy đủ hiệu lực từng điều qua mọi lần sửa đổi**. Văn bản hết hiệu lực một phần vẫn cần xác minh phạm vi thay đổi.

Phát hiện thêm: bước nối dòng trong cleaning có thể nuốt ranh giới tiêu đề bắt đầu bằng “Đ”, khiến dòng chương và Điều dính nhau. Đã bỏ cách nối dòng này và thêm xử lý bảo thủ cho cache cũ; đọc lại native text cho kết quả tốt hơn.

## Metadata đối chiếu nguồn chính thức

- `06/2020/TT-BLĐTBXH`: đã sửa tên, cơ quan ban hành, ngày ban hành 20/08/2020 và ngày hiệu lực 05/10/2020 trong catalog, có SHA của file. [Thuộc tính tại CSDL VBPL](https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID=143667).
- `08/2023/TT-BLĐTBXH`: đã bổ sung cơ quan, ngày ban hành 29/08/2023, ngày hiệu lực 12/10/2023 và trạng thái hết hiệu lực một phần; chưa đánh dấu xác minh đầy đủ metadata/temporal vì cần rà soát tiêu đề và phạm vi bãi bỏ. [Lịch sử tại CSDL VBPL](https://vbpl.vn/TW/Pages/vbpq-lichsu.aspx?ItemID=167031).

Hai mục này không thay thế việc xác minh toàn bộ corpus. Không tự điền ngày hoặc trạng thái chỉ để xóa cảnh báo.

## Kiểm tra thực tế

- Kiểm thử hồi quy: 47 tests; log `artifacts/reports/refactor_tests.log`.
- Biên dịch kiểm tra `src`, `scripts`, `tests` không có lỗi cú pháp.
- Chạy `scripts/review_existing_extraction.py --refresh-native`: đọc lại text sẵn có trên PDF, dùng DOCX đã chuyển đổi nếu có; **tắt OCR**, không chạy Dense/BM25 hoặc nạp Neo4j. Kết quả nằm ở `artifacts/review_v3`.

| Thành phần của bản rà soát | Số lượng |
|---|---:|
| Document Registry | 95 |
| Structured Provisions | 7.857 |
| Tài liệu tư pháp | 24 |
| Diagnostic items | 6.895 |
| Graph nodes | 15.190 |
| Graph edges | 28.091 |

Không còn ID provision trùng trong đầu ra được chấp nhận, nhưng có **một tài liệu bị cách ly** do hai điểm “a” khác nội dung tại khoản 2 Điều 27: `326-2016-UBTVQH14_text_copy.doc`. Cần đối chiếu bản gốc; không tự đổi một điểm thành “b”. Một provision ngắn chỉ có “Điều 19.” cũng được báo lỗi.

Các vấn đề còn thấy: 11 tài liệu không có machine text; 43 văn bản pháp luật có trang trích xuất chưa hoàn chỉnh; 45 văn bản chưa parse được Điều; 60 văn bản chưa xác minh đầy đủ metadata và 60 chưa xác minh temporal metadata. Các nhóm này chồng lấp, không cộng thành số tài liệu lỗi.

Audit bốn đầu ra của bản rà soát hiện **FAIL**. Thiếu Dense/BM25 và chứng nhận Neo4j là dự kiến vì lần rà soát không xây các thành phần đó; đồng thời còn lỗi dữ liệu thực sự ở phía trên. Xem `artifacts/review_v3/reports/summary.json` và `final_outputs_validation.md`.

Kiểm thử OCR routing/timeout và transaction Neo4j dùng mock; chưa chứng minh chất lượng nhận dạng OCR thật hoặc migration trên DB đang chạy. Chưa có gold set đã duyệt, nên không công bố precision hoặc chất lượng retrieval đạt chuẩn. `reviewed_quality_evaluation.json` là đầu vào đánh giá độc lập gắn với build; chương trình không tự tạo chứng nhận PASS.

## Có cần chạy lại toàn bộ không?

**Cần chạy lại pipeline để áp dụng các thay đổi vào bộ dữ liệu chính**, vì identity, segmentation, provisions và retrieval text đã đổi. Chạy riêng Dense sẽ không sửa được metadata/parsing cũ. Không cần cài lại môi trường hoặc tải lại BGE-M3 nếu môi trường hiện có vẫn dùng được.

Chưa chạy lại `RUN_ALL_OFFLINE.bat` trong lần sửa mã này. Dense và Graph DB chính chưa bị ghi đè. Trước lần build chính cần xử lý metadata/source ambiguity và chuẩn bị OCR; sau đó xây lại graph, Dense, BM25, nạp Neo4j và audit trực tiếp. Có thể cần nhiều vòng sửa dữ liệu và chạy lại, không bảo đảm một lần chạy là PASS.

Loader mới yêu cầu migration rõ ràng nếu gặp Entity của bản cũ. Cờ CLI `load-neo4j --replace-legacy` có thể xóa Entity legacy trong database chuyên dụng; chỉ dùng khi đã chọn đúng DB và quyết định thay thế dữ liệu cũ. Lần này chưa thực hiện migration.

Ollama enrichment nên để sau khi dữ liệu nguồn đạt yêu cầu. Bộ lọc temporal và resolver bảo thủ giảm nối sai nhưng còn bỏ sót trích dẫn phức tạp; cần đánh giá trên mẫu thực trước ONLINE.
