# Graph hữu ích khi nào? Phép thử cơ chế và đối chứng Local

Tài liệu này thay hướng diễn giải pilot trước: mục tiêu không phải làm Graph đứng đầu mọi bảng, mà kiểm tra **khi nào, nhờ quan hệ nào và ở bước nào Graph bổ sung giá trị**. Công cụ cũ và kết quả cũ giữ lại để tái lập, không dùng làm kết luận nghiên cứu độc lập.

## 1. Kết luận hiện có

Graph có tín hiệu hữu ích khi: (A) đã tìm được quy định gốc, (B) câu trả lời còn phụ thuộc quy định được dẫn tới nhưng tập ứng viên ban đầu chưa có, và (C) có quan hệ đúng trong artifact để tìm các căn cứ đó. Sau khi tìm, còn cần bước chọn căn cứ để đưa chúng vào gói bằng chứng. Đây là giả thuyết cơ chế có một ví dụ thực nghiệm hỗ trợ, chưa phải quy tắc tổng quát được chứng minh cho toàn bộ luật lao động.

Không thể chỉ nhìn thấy chữ “ngoại lệ” hay câu hỏi dài rồi kết luận cần Graph. Nếu truy xuất thường đã tìm đủ căn cứ thì Graph có thể không tăng điểm, tăng thời gian hoặc thêm nhiễu. Một câu nhiều yêu cầu độc lập cũng không mặc nhiên cần đi đồ thị.

**Chưa tích hợp các công cụ mới vào notebook/bảng đo chính và không sửa pipeline ONLINE/OFFLINE trong lượt này.**

## 2. Các dạng câu và cơ chế cần kiểm tra

| Đặc điểm cần xem xét | Vì sao truy xuất thường có thể thiếu | Quan hệ/cơ chế Graph thực tế | Bằng chứng hiện tại |
|---|---|---|---|
| Phụ thuộc dẫn chiếu sang Điều/Khoản/Điểm khác | Đích dẫn chiếu có thuật ngữ khác câu hỏi, không nằm trong tập ứng viên | REFERENCES hướng OUT | HD009: tìm thêm ba căn cứ; có trace CPU thực thi thật |
| Yêu cầu quy tắc và ngoại lệ | Điều gốc mới nêu nơi chứa ngoại lệ; chưa phải đủ nội dung ngoại lệ | REFERENCES; cấu trúc PART_OF/NEXT khi thích hợp | Hai câu có dấu hiệu yêu cầu ngoại lệ; chỉ HD009 cải thiện |
| Cần ngữ cảnh cấu trúc Điều–Khoản–Điểm | Đoạn con thiếu điều kiện hoặc cần cha/anh em | PART_OF, NEXT | Có rủi ro: HD002 thêm nút chỉ có tiêu đề, làm giảm hạng căn cứ đúng |
| Quan hệ nhiều văn bản | Quy định gốc và nội dung liên quan nằm ở hai văn bản khác nhau | REFERENCES xuyên tài liệu; code có hỗ trợ IMPLEMENTS | Artifact có 55 REFERENCES xuyên tài liệu, không có IMPLEMENTS; chưa có nhóm câu tương ứng được đo trong tập này |
| Sửa đổi, thay thế, chuyển tiếp | Cần tìm chuỗi văn bản/phiên bản và điều kiện chuyển tiếp | AMENDS, REPEALS, REPLACES, VERSION_OF | Có cạnh trong artifact nhưng chưa có mẫu phù hợp ở pilot; lọc ngày là cơ chế chung, không được gán riêng cho Graph |
| So tình huống với vụ án | Có thể cần quan hệ vụ án–vấn đề–quy định | CITES, HAS_ISSUE và các kênh case/community | Chưa đánh giá trong các nhánh retrieval này; không lấy kết quả này chứng minh lợi ích án lệ |
| Nhiều yêu cầu độc lập | Mỗi ý có thể tìm bằng truy vấn riêng, không cần nối quan hệ | Không mặc định bật Graph | Nhóm 7 câu trong frozen Hybrid đã đạt Recall nhóm@10 = 1,0 ở baseline; không ghi nhận tăng thêm |

Các nhóm do quy tắc từ nội dung câu hỏi gợi ý, **chưa được người duyệt xác nhận là nhãn “bắt buộc cần Graph”**. `coverage_catalog.csv` ghi cả nhóm không có mẫu bằng NOT_EVALUATED, không ghi điểm 0 giả. Năm trong số hiệu văn bản không bị coi là thời gian tình huống; “nêu” và “nếu” được phân biệt.

## 3. Đối chứng không lẫn tác dụng bộ chọn căn cứ

| Nhánh | Mở rộng ứng viên Graph | Bộ chọn REFERENCES |
|---|---|---|
| A | Tắt | Tắt |
| B | Bật | Tắt |
| C | Tắt | Bật |
| D | Bật | Bật |

- A → B: tác động mở rộng Graph khi cùng tắt bộ chọn.
- C → D: tác động mở rộng Graph khi giữ **cùng một bộ chọn**.
- C vẫn đọc quan hệ REFERENCES: chỉ được gọi “không mở rộng ứng viên”, không gọi “hoàn toàn không dùng Graph”.
- A → D là tác động phối hợp, không phải tác dụng riêng của mở rộng Graph.

Cùng corpus, câu hỏi, query_date, BM25 hoặc thứ hạng Hybrid nền, K và bộ lọc nguồn/ngày trong mỗi cặp. Không đổi prompt/model giữa hai nhánh. Trong phép thử CPU không có LLM hay prompt sinh câu trả lời; không giả là đã đánh giá QA. Graph thêm tối đa 10 ứng viên, do đó lợi ích có kèm ngân sách tính toán/candidate tăng; đây không phải phép đo cân bằng chi phí ứng viên.

## 4. Những gì đã thực sự chạy

1. **Frozen Hybrid + reranker:** tính lại kết quả 108 câu × 3 lượt từ ZIP, bốn nhánh A–D. Bộ chọn mới chạy trên local; embedding/reranker không chạy lại. Thời gian nhánh gốc được ghi rõ là quan sát từ lần Kaggle cũ; thời gian nhánh selector mới không được bịa từ thời gian cũ.
2. **Fresh CPU BM25 + Graph:** 9 câu được chọn theo đặc điểm văn bản và seed 42 trước khi đọc kết quả; 4 nhánh × 3 lượt = 108 dự đoán. Dùng Graph artifact và BM25 thật; không gọi Dense, reranker hay LLM. Những câu còn lỗi/không tăng đều được giữ.

Không có GPU và dịch vụ Ollama hoạt động trên local; không thể gọi phép thử này là fresh Hybrid/LLM QA. Cả hai phần đều dùng Gold DRAFT, tập đã từng được xem khi phát triển, không phải held-out. Ba lần lặp dùng để xem tính ổn định/thời gian; bootstrap theo **câu hỏi**, không coi các lần lặp là câu độc lập.

## 5. Kết quả Fresh CPU cuối cùng

| Nhánh | Recall nhóm@10 | nDCG nhóm@10 | Bao phủ nhóm căn cứ toàn pool | Thời gian thành phần ghép, ms |
|---|---:|---:|---:|---:|
| BM25, không Graph | 0.7500 | 0.6739 | 0.9167 | 1.650 |
| BM25 + mở rộng Graph | 0.7500 | 0.6739 | 1.0000 | 5.816 |
| BM25 + chọn theo REFERENCES, không mở rộng | 0.7500 | 0.6739 | 0.9167 | 1.720 |
| BM25 + Graph + cùng bộ chọn REFERENCES | 0.8333 | 0.7416 | 1.0000 | 8.477 |

Thời gian là BM25 dùng chung cho từng câu/lượt cộng phép biến đổi đo riêng của nhánh, sau warm-up; không phải thời gian trả lời HTTP/LLM hoặc bốn lần chạy end-to-end độc lập. Lần cuối chạy riêng sau khi tests kết thúc để giảm tranh CPU. Đo ít mẫu nên không dùng các mili giây này làm cam kết hiệu năng.

Graph-only dùng candidate-union nối vào cuối danh sách BM25. Khi baseline có ≥10 mục, top10 không đổi **theo cấu trúc thuật toán**, không phải bằng chứng Graph không có thông tin hữu ích. Phải đọc thêm bao phủ toàn pool và đối chứng giữ cùng bộ chọn C → D.

Đối chứng C → D: Recall nhóm@10 tăng ở **1 câu**, không đổi 8 câu, không giảm; delta trung bình +0,08333, CI bootstrap 95% [0; 0,25]. Khoảng tin cậy vẫn bao gồm 0; chưa đủ để suy rộng. Các thứ hạng và đường Graph ổn định giữa ba lượt trong lần chạy cuối.

### Từng câu trong mẫu nhỏ

| ID | Câu hỏi | Recall@10 A | Recall@10 D |
|---|---|---:|---:|
| CD004 | Công ty không trả lương đúng hạn mà không thuộc ngoại lệ bất khả kháng của khoản 4 Điều 97. Tôi có quyền nghỉ mà không báo trước không? | 1.00 | 1.00 |
| CD014 | Trong trường hợp thuộc ngoại lệ luật định khi doanh nghiệp giải thể, thời hạn thanh toán quyền lợi khi chấm dứt hợp đồng có thể kéo dài tối đa bao nhiêu ngày? | 1.00 | 1.00 |
| HD003 | Hợp đồng lao động ký qua phương tiện điện tử dưới dạng thông điệp dữ liệu có giá trị như hợp đồng giấy không? | 1.00 | 1.00 |
| HD009 | Theo quy tắc chung, sau hai hợp đồng xác định thời hạn liên tiếp, nếu người lao động tiếp tục làm việc thì phải ký loại hợp đồng nào? Nêu các nhóm ngoại lệ được dẫn tại điểm c khoản 2 Điều 20. | 0.25 | 1.00 |
| MR020 | Tôi thử việc lần đầu ở vị trí chuyên môn yêu cầu cao đẳng, không phải người quản lý doanh nghiệp; hợp đồng không thuộc loại dưới một tháng. Công ty yêu cầu thử việc 90 ngày và trả 80% lương của công việc. Hãy đánh giá riêng thời gian và mức lương. | 0.50 | 0.50 |
| TG008 | Theo giới hạn làm thêm giờ chung, một năm được làm thêm tối đa bao nhiêu giờ nếu không thuộc ngoại lệ? | 0.00 | 0.00 |
| TG011 | Người làm việc ban ngày 8 giờ/ngày được nghỉ giữa giờ ít nhất bao nhiêu phút? | 1.00 | 1.00 |
| TG012 | Người làm ca liên tục 8 giờ/ngày, thời gian nghỉ giữa giờ có được tính vào giờ làm việc không? | 1.00 | 1.00 |
| TV012 | Tôi ký hợp đồng lao động thời hạn 20 ngày. Công ty có được áp dụng thử việc không? | 1.00 | 1.00 |

MR020 và TG008 vẫn thiếu căn cứ top10 trong phép thử BM25 này. Không xóa chúng khỏi mẫu và không kết luận hệ thống đã xử lý tốt toàn bộ.

## 6. Ví dụ cho thấy nguyên nhân khác biệt

**HD009 — quy tắc sau hai hợp đồng xác định thời hạn và ngoại lệ được dẫn tại điểm c khoản 2 Điều 20.** Theo Gold hiện có, cần bốn nhóm: điểm c khoản 2 Điều 20; khoản 1 Điều 149; khoản 2 Điều 151; khoản 4 Điều 177.

| Căn cứ trong artifact | Hạng trong BM25 không Graph | Hạng sau mở rộng + selector CPU |
|---|---:|---:|
| Điểm c khoản 2 Điều 20 | 1 | 1 |
| Khoản 1 Điều 149 | Không có trong pool | 4 |
| Khoản 2 Điều 151 | Không có trong pool | 2 |
| Khoản 4 Điều 177 | Không có trong pool | 3 |

Ba đích có nội dung về lao động cao tuổi, lao động nước ngoài và thành viên ban lãnh đạo tổ chức đại diện người lao động. Chúng không nhất thiết giống từ ngữ câu hỏi “hai hợp đồng liên tiếp”. Graph theo REFERENCES từ quy định gốc để tìm đúng đích. `predictions.jsonl` CPU lưu trace cạnh thật, ví dụ edge_16fd2a7a402009bb, edge_a490ef79d4f9391e, edge_6d61595efff2cbb4.

Chỉ bật selector trên tập BM25 cũ vẫn thiếu cả ba đích, vì không thể chọn tài liệu chưa tìm ra. Chỉ mở rộng mà không chọn thì các đích nằm ngoài top10. Hai việc có vai trò khác nhau và cần phối hợp trong trường hợp này.

**HD002 — hợp đồng 6 tháng giao kết bằng miệng (phân tích frozen toàn tập, không thuộc mẫu CPU 9 câu).** Graph thêm nút `prov_20c7d6a91ea43d3a` chỉ chứa tiêu đề Điều 14. Reranker đặt nút này hạng 3, đẩy khoản 1 Điều 14 từ hạng 3 xuống 4. Đây là nhiễu cấu trúc, không có căn cứ để nói sự giảm hạng được bù bằng QA tốt hơn.

Trong frozen toàn tập: chỉ mở rộng Graph không tăng Recall@10 ở câu nào và làm giảm MRR/nDCG ở HD002. Giữ cùng selector rồi bật mở rộng giúp HD009 tăng Recall; HD002 vẫn giảm thứ hạng. Chưa sử dụng định tuyến để né câu bị giảm trong đối chứng chính, vì cần cô lập thay đổi Graph. Các kết quả cũ có định tuyến chỉ là phép thử chính sách khác, không trộn vào bảng này.

| Frozen 108 câu | Recall nhóm@10 | MRR@10 | nDCG nhóm@10 |
|---|---:|---:|---:|
| A: Hybrid + reranker | 0,945525 | 0,783047 | 0,801902 |
| B: thêm mở rộng Graph | 0,945525 | 0,782275 | 0,801260 |
| C: cùng selector, không mở rộng | 0,945525 | 0,783047 | 0,801902 |
| D: mở rộng + cùng selector | 0,952469 | 0,782275 | 0,806905 |

Không lấy điểm CPU so tuyệt đối với frozen Hybrid để kết luận phương pháp nào tốt hơn: cấu hình model và phạm vi thực thi khác nhau.

## 7. Đầu ra, giới hạn và quyết định

- `frozen_v2/selection.json`: đặc điểm và danh sách mẫu, được ghi trước khi đọc kết quả.
- `frozen_v2/tables.csv`, `paired.csv`, `coverage_catalog.csv`: toàn tập, mẫu nhỏ, từng nhóm và mức bao phủ thí nghiệm.
- `frozen_v2/cases.json`, `evidence.json`: căn cứ thiếu/tìm thêm, nguyên văn, Điều–Khoản–Điểm, URL, khoảng hiệu lực và thứ hạng bốn nhánh. Đường nối ở đây được tái dựng từ cấu trúc, **không giả là execution trace cũ**.
- `fresh_cpu_v4/predictions.jsonl`: các dự đoán và trace Graph thực thi CPU, ghi trước khi chấm Gold.
- `fresh_cpu_v4/summary.json`, `per_query.csv`, `subgroup_tables.csv`, `paired.csv`: kết quả cuối, thời gian có giới hạn rõ và fingerprint để tái lập.

QA Accuracy, độ đầy đủ câu trả lời và Citation Accuracy: **NOT_EVALUATED**. Có URL/Điều/Khoản trong metadata không có nghĩa một câu trả lời đã trích dẫn đúng hoặc hợp pháp. Không dùng Recall thay “độ đúng pháp lý”. Chưa có mô hình sinh câu trả lời và người duyệt pháp lý trong thí nghiệm này.

**Quyết định: giữ thành công cụ nghiên cứu thử nghiệm riêng, chưa đưa vào bảng kết luận chính thức.** Có bằng chứng cơ chế tìm thêm căn cứ ở một câu dẫn chiếu; chưa chứng minh đa dạng trường hợp, QA hay tốc độ. Cần bổ sung câu mới theo giả thuyết quan hệ, chốt nhãn độc lập trước khi đo, bao gồm nhóm đối chứng không cần Graph, duyệt Gold và chạy fresh paired Hybrid + reranker + QA. Chỉ mở rộng kết luận nếu có lợi ích lặp lại trên đủ mẫu, không gây suy giảm đáng kể ở nhóm khác và chi phí chấp nhận được. Giữ cả những kết quả không tăng/giảm.

## 8. Chạy lại từ đầu

Từ thư mục gốc dự án, dùng output mới, không chạy benchmark khác đồng thời khi đo thời gian. Trên Windows dùng `-X utf8` để tránh lỗi console tiếng Việt.

```powershell
.\.venv\Scripts\python.exe -X utf8 benchmarks/evaluation_suite/graph_mechanism_pilot.py --archive "đo/result_kaggle/standard_results(2).zip" --artifact "D:/data_thô/result/result_28-10/vn_labor_results.zip" --output "đo/result_kaggle/graph_mechanism_NEW/frozen"
.\.venv\Scripts\python.exe -X utf8 benchmarks/evaluation_suite/graph_local_bm25.py --archive "đo/result_kaggle/standard_results(2).zip" --artifact "D:/data_thô/result/result_28-10/vn_labor_results.zip" --selection "đo/result_kaggle/graph_mechanism_NEW/frozen/selection.json" --output "đo/result_kaggle/graph_mechanism_NEW/fresh_cpu" --cache "đo/result_kaggle/graph_mechanism_NEW/cache" --repeats 3
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s benchmarks/evaluation_suite -p "test_graph_*.py"
```

Không commit cache, artifact hoặc kết quả nặng. Công cụ không đổi Gold, không tải model, không sửa notebook chính và không tự push.
