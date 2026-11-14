# Phép đo Graph QA theo cặp

Bộ đo riêng này kiểm tra **khi nào mở rộng đồ thị giúp tìm đủ căn cứ và trả lời tốt hơn**. Không thay notebook đánh giá cũ, không chạy backend HTTP và không sửa logic ONLINE.

## Phạm vi kết luận

- Hai nhánh `graph_on` / `graph_off` giữ cùng artifact, câu hỏi, thời điểm hỏi, prompt, LLM, reranker, seed, ngân sách và phần cứng. Chỉ `graph.enabled` khác nhau.
- Đây là đóng góp của **mở rộng đồ thị trong pipeline**, không phải phép loại bỏ mọi thông tin được sinh từ đồ thị. Giữ các đường tắt exact/profile và kênh case/community/issue/exception context như nhau ở cả hai nhánh; không bỏ các cơ chế thay thế chỉ để làm Graph trông tốt hơn. Vì vậy Graph OFF vẫn có thể dùng biểu diễn phân cấp/kênh vụ án chung, nhưng không mở rộng adaptive theo chỗ thiếu.
- Nhóm câu hỏi gồm dẫn chiếu, điều kiện/ngoại lệ, nhiều văn bản và nhóm đối chứng. Câu khó không mặc nhiên cần Graph. Giữ cả trường hợp Graph bằng hoặc kém hơn.
- Nhãn được đối chiếu với artifact và đóng băng trước suy luận vẫn là **DRAFT**, cần người có chuyên môn duyệt. Bộ câu hỏi phát triển này không tự trở thành tập kiểm định độc lập.
- Artifact đang dùng có mốc dữ liệu **15/09/2026**. Thời điểm hỏi đã ghim trong từng câu; không tự đổi thành ngày chạy và không tuyên bố bao phủ luật mới sau mốc dữ liệu.
- Điểm AI-judge là đánh giá của mô hình, không phải xác nhận đúng luật. Thời gian judge được tách khỏi thời gian trả lời.

## Các file chính

| File | Chức năng |
|---|---|
| `run.py` | CLI prepare / preflight / run / judge / report / export |
| `protocol.py` | Khóa điều kiện thí nghiệm và đối chiếu nhãn với artifact |
| `questions.jsonl` | Câu hỏi và nhãn dự kiến trước khi đóng băng; xem manifest để biết tên/schema chính xác của bản đóng gói |
| `package.py` | Đóng ZIP code cần thiết để đưa lên Kaggle |
| `Kaggle_Graph_QA.ipynb` | Notebook chạy phép đo trên Kaggle |
| `make_notebook.py` | Sinh lại notebook, kiểm cú pháp mọi code cell |

## Chuẩn bị trên máy

Trong PowerShell, tại thư mục `legal-agentic-rag`, dùng Python của virtualenv:

```powershell
.\.venv\Scripts\python.exe -X utf8 benchmarks/graph_qa/package.py --output benchmarks/graph_qa/PhapDienAI_GraphQA_Code.zip
.\.venv\Scripts\python.exe -X utf8 benchmarks/graph_qa/make_notebook.py
```

Lệnh đầu tạo **`PhapDienAI_GraphQA_Code.zip`**. ZIP chỉ chứa source cần thiết và manifest SHA-256 (runtime dùng cấu hình được dựng riêng, không đóng gói .env/config cá nhân); không chứa `.env`, key, cache, model hoặc corpus luật; có sẵn 24 câu và nhãn dự kiến để chuẩn bị phép đo. Không cần push GitHub khi dùng ZIP này.

## Chạy trên Kaggle từ đầu đến cuối

1. Import `Kaggle_Graph_QA.ipynb` vào notebook mới. Bật **Internet**, chọn **GPU T4 ×2**. Dừng backend và các notebook cùng project đang dùng quota Gemini để tránh nhiễu.
2. Add Input ZIP code `PhapDienAI_GraphQA_Code.zip` và **một** artifact OFFLINE cuối: `vn_labor_results.zip` hoặc thư mục `artifacts`. Kaggle có thể tự giải nén ZIP code: notebook cũng nhận thư mục có `package_manifest.json`, vẫn kiểm đủ file và SHA-256. Biến `CODE_ZIP` có thể là đường dẫn ZIP hoặc thư mục này. Không cần technical checkpoint, ngrok hoặc Neo4j.
3. Bật Secret **`GEMINI_API_KEY`**. **`HF_TOKEN`** tùy chọn để tải model công khai. Không cần Groq/coding-team key.
4. Giữ `SOURCE='attached_zip'`, `PROFILE='smoke'`, `RESUME=False`, `RETRY_ERRORS=False`. Chạy các cell theo thứ tự. Nếu tự tìm input gặp nhiều ứng viên, điền đường dẫn chính xác vào `CODE_ZIP` / `ARTIFACT`.
5. Notebook kiểm source ZIP, cài dependencies, giữ Torch/CUDA Kaggle, tải Qwen, chuẩn bị nhãn và kiểm kết nối trước khi suy luận. Chỉ chạy tiếp khi preflight đạt. Nếu model/API lỗi, xem log; không bỏ gate để lấy điểm.
6. Smoke đạt kỹ thuật: đổi `PROFILE='standard'` và chạy lại từ cell cấu hình. Hai profile có thư mục riêng; standard đo toàn bộ danh sách đã chuẩn bị.
7. Tải **`graph_qa_v1_standard_results.zip`** ở cell tải kết quả. ZIP chứa kết quả/checkpoint; cache model và virtualenv nằm ngoài thư mục run.
8. Chạy cell dọn dịch vụ khi kết thúc. Nó chỉ dừng Ollama do notebook tạo.

Mặc định Researcher/Auditor/Adjudicator dùng `qwen3:8b` qua Ollama; embedding và reranker dùng GPU 0, Ollama dùng GPU 1. Gemini `gemini-3.1-flash-lite` dùng cho semantic review; AI-judge chạy riêng sau generation (cùng họ model reviewer nên không phải giám khảo độc lập về mô hình). `VN_LABOR_GEMINI_RPM=13` chỉ là mức pacing cấu hình, không đảm bảo quota project còn đủ.

`SEMANTIC_REVIEW=False` hoặc `RUN_AI_JUDGE=False` là thí nghiệm khác, phải dùng tên run mới. Không tắt review chỉ để tăng tỷ lệ trả lời. Không đổi model giữa hai nhánh hoặc giữa lúc resume.

## Tiếp tục khi bị gián đoạn

- Giữ nguyên code, artifact, settings và model; đặt `RESUME=True`, chạy lại cùng `RUN_NAME` và `PROFILE`. Runner kiểm fingerprint và không tự xem dữ liệu lỗi là thành công.
- Nếu cần thử lại lỗi thực thi sau khi quota/API hồi phục, đặt `RETRY_ERRORS=True` có chủ đích; lịch sử attempt được giữ. Không tự thử lại câu từ chối hoặc thiếu căn cứ để chọn câu đẹp nhất.
- Sau lỗi generation/judge, notebook vẫn thử tạo report và export. Cell tải checkpoint chạy riêng được; tải ZIP trước khi đóng phiên Kaggle.
- Nếu đổi code, model, artifact, prompt hoặc settings: tạo code ZIP mới nếu cần, đặt **RUN_NAME mới**, đóng băng nhãn lại. Không trộn hai run trong một bảng trước–sau thiếu kiểm soát.
- Đổi tên Dataset không làm thay dữ liệu. Đổi nội dung artifact sẽ đổi fingerprint và cần run mới.

## CLI tương đương

```powershell
python benchmarks/graph_qa/run.py prepare --artifact PATH_TO_ARTIFACT --output RUN --cache CACHE
python benchmarks/graph_qa/run.py preflight --run RUN --settings SETTINGS.json
python benchmarks/graph_qa/run.py run --run RUN --settings SETTINGS.json --profile smoke
python benchmarks/graph_qa/run.py judge --run RUN --settings SETTINGS.json
python benchmarks/graph_qa/run.py report --run RUN
python benchmarks/graph_qa/run.py export --run RUN --output graph_qa_results.zip
```

Settings JSON được notebook ghi bên ngoài thư mục kết quả. `run --dry-run` chỉ kiểm cấu hình, không tạo câu trả lời giả và không thay phép đo inference thật.

## Đọc kết quả

Các đầu ra chính gồm `comparison.md`, `comparison.csv/json`, `paired.csv`, `per_attempt_metrics.csv`, `responses.md`, `responses.jsonl`, `human_review.csv` và các manifest/nhãn đã đóng băng.

Đối chiếu từng cặp cùng question ID: câu trả lời, Evidence ID/locator, nguồn, thay đổi căn cứ khi mở rộng, lỗi, trạng thái từ chối và thời gian. Đọc kết quả theo từng nhóm cơ chế, không chỉ trung bình chung. Lỗi API/quota là lỗi thực thi; không đổi thành điểm pháp lý 0 hoặc âm thầm loại bỏ. Báo số mẫu hợp lệ và tỷ lệ lỗi cùng mọi điểm chất lượng.

Recall/citation coverage chỉ cho biết thu hồi nhãn đã định; không tự chứng minh lập luận đúng hoặc đầy đủ. Muốn kết luận lợi ích QA cần cả câu trả lời và đánh giá bám bằng chứng, độ đủ từng yêu cầu, đúng thời điểm. Nếu chưa đủ cặp hợp lệ hoặc nhãn chưa duyệt, trình bày kết quả là thăm dò.

## Xác minh trước khi phát hành

Generator kiểm cú pháp tất cả cell và notebook không có output lưu sẵn. Kiểm fixture local bao gồm hash sai, path traversal, symlink, tên đường dẫn không chuẩn và không ghi đè source đã sửa. Những kiểm tra này không chứng minh môi trường Kaggle/API hoạt động hoặc chất lượng câu trả lời; inference thực phải được đo và lưu riêng.

## Giới hạn giao thức và sự cố

- Standard gồm **24 câu × 2 nhánh = 48 lượt** khi `REPETITIONS=1`; smoke 4 câu × 2 nhánh = 8 lượt. Mỗi câu có thể cần nhiều cuộc gọi LLM; không đồng nghĩa 48 API calls.
- Cùng ngân sách thời gian: Graph tốn thời gian thì phần sinh/kiểm có thể còn ít ngân sách hơn. Đây là phép đo lợi ích ròng trong pipeline, không phải cấp thêm thời gian riêng cho Graph.
- Nhánh STANDARD của pipeline hiện chỉ mở rộng tối đa một vòng adaptive; các route khác mới có thể dùng giới hạn cao hơn. Không suy ra bốn vòng được chạy từ giá trị cấu hình.
- Mặc định `REPETITIONS=1` để kiểm khả thi và tiết kiệm quota. Muốn đo dao động, đặt 3 trước lần chạy mới; không coi lặp 3 lần là có thêm 3 câu độc lập. Mỗi nhóm chỉ 6 câu nên chưa đủ suy rộng toàn lĩnh vực.
- Parent đã xuất hiện nguyên văn trong ancestor context của child không bị ép thành một hit riêng. Căn cứ cha vẫn được lưu trong `context_support`. Các nhãn phiên bản đang chốt không tự coi bản OCR khác là tương đương.
- Sau retry, bảng chính mô tả lượt cuối của lịch đo; `attempt_journal.jsonl`, `retry_history.jsonl`, `attempt_history_summary.json` giữ tổng số lỗi, lượt thử lại và chi phí thời gian. Không tuyên bố chạy không lỗi nếu lịch sử có lỗi.
- Hard timeout làm dừng phép đo trước câu tiếp theo. Chạy cell dọn dịch vụ do notebook sở hữu, rồi Run All với RESUME=True để khởi động lại Ollama. Việc hủy Python không chứng minh suy luận phía Ollama đã dừng.
- Nếu lock còn sau khi kernel bị dừng, chỉ gỡ `.controller.lock` khi xác nhận controller cũ đã kết thúc; không chạy hai controller chung một OUT. Giữ checkpoint trước khi gỡ lock.
- Không gộp latency khi chuyển GPU/driver/phần mềm; runner khóa metadata môi trường khi bắt đầu và từ chối runtime khác. Cloud model chỉ ghim được tên API, không đảm bảo nhà cung cấp giữ nguyên weights.

`paired_questions.md/csv/json` giữ từng cặp, căn cứ thêm/mất và số vòng thực tế. `elapsed_ms` là thời gian suy luận warm trong worker, `controller_round_trip_ms` bao gồm IPC; đây không phải latency frontend/Internet.

Mọi câu trong phép thử này được ghim cùng ngày 15/09/2026; đây chưa phải phép đối chứng riêng về thay đổi hiệu lực qua nhiều mốc. `seed=42` điều khiển lịch câu hỏi; provider Ollama hiện ghim seed sinh bằng 0 và temperature=0 ở cả hai nhánh. Khi AI-judge lỗi, dừng hậu chấm và giữ nguyên toàn bộ câu trả lời đã đo.
