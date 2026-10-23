# Đối chiếu dự án luật thuế và tích hợp có kiểm soát

Ngày rà soát: 23/10/2026. Nguồn đối chiếu:
https://github.com/BuiTrongKhang0911/Temporal-Agentic-RAG-Vietnamese-Tax-Law
Commit đã đọc: `e9a9147b4aa4294634720bf96f67f1a53e2f1c0c`.
Đã đọc mã production, bộ đánh giá, báo cáo kết quả; chưa khởi chạy hệ thống thuế
với Qdrant/Gemini và không xác nhận độc lập số liệu công bố trong repository.

## Kết luận

Điểm đáng học là tổ chức công việc theo từng task/fact và giữ liên kết với
chứng cứ gốc. Thêm số lượng agent, thay FAISS bằng Qdrant hoặc dùng toàn bộ
Gemini không tự bảo đảm câu trả lời đúng/đủ. Dự án lao động đã có task, slots,
nguồn/phiên bản, audit, graph, reviewer và vòng sửa; cần nối các bước chặt hơn.
Phạm vi hiện tại vẫn là pháp luật lao động Việt Nam, không phải toàn bộ pháp luật.

## Đối chiếu và phản biện

| Cách làm ở dự án thuế | Đánh giá cho Pháp Điển AI |
|---|---|
| Agent 1 chỉ làm rõ ngôn ngữ, Agent 2 tách task rồi fact | Hợp lý khi cần; giữ dữ kiện gốc, không để bản viết lại bỏ phủ định, thời điểm hay yêu cầu. Pháp Điển đã có intake/conversation/Researcher; chưa cần thêm hai lần gọi LLM cho mọi câu. |
| Agent 3 tìm, Agent 4 kiểm từng fact, chỉ tìm lại fact còn thiếu | Đáng học. Pháp Điển đã có slots/gap-driven graph nhưng truy xuất lexical ban đầu chủ yếu dùng câu gộp và query của Researcher. Bổ sung truy vấn từng task giúp các yêu cầu độc lập có thêm cơ hội được tìm thấy. |
| StructuredRetriever phục hồi cả provision và mở rộng các khoản cùng điều có giới hạn | Hợp lý để không mất điều kiện, ngoại lệ. Pháp Điển đã có ancestor_context/full_text và hierarchy; không mở rộng tất cả khoản vô điều kiện vì tăng nhiễu, có thể trộn phiên bản. Cần đo đóng góp trước khi đổi mặc định. |
| Temporal scope exact_date/range/comparison được biên dịch bằng Python | Đáng phát triển tiếp cho so sánh hai mốc. Pháp Điển đã có lọc ngày/khoảng; chưa nhập module temporal của bên thuế vào vì schema/provenance khác nhau. |
| Lập kế hoạch số học rồi chạy Decimal/AST với biến có nguồn | Đáng làm tiếp cho lương, làm thêm, trợ cấp. Phép tính đúng không chứng minh công thức, mẫu số hoặc điều kiện pháp lý đúng; không nhập công thức thuế sang lao động. Chưa tích hợp công cụ này vào runtime trong đợt sửa này. |
| Bộ thí nghiệm riêng, frozen runtime, BM25/Dense/Hybrid/ablation | Đáng học cách lưu phiên bản và kết quả từng câu. Điểm judge bằng LLM không phải tỷ lệ đúng được luật sư xác nhận, cũng không so trực tiếp được với Risk100. |
| Qdrant + BGE-M3 + BM25 tách từ Việt + reranker | Công cụ có ích nhưng không chứng minh tốt hơn chỉ mục hiện tại. Pháp Điển đã dùng BGE-M3/BM25/FAISS/reranker; chưa chuyển DB hoặc đổi tokenizer vì cần xây lại index và đối chứng. |

Những chi tiết không sao chép:

- `orchestrator.py` cắt `state.plan[:self.max_steps]` với `max_steps=3`:
  có thể bỏ phần yêu cầu hoặc nhánh so sánh. Pháp Điển giữ toàn bộ task;
  nếu ngân sách hết phải báo phần chưa xử lý.
- `metadata_overlaps_scope` thay thiếu ngày bắt đầu bằng `0001-01-01`:
  không dùng cách đó để xem ngày hiệu lực chưa rõ là đã xác minh.
- `_match_support_span` có nhánh fuzzy: dù có bảo vệ số/phủ định, độ giống chữ
  không chứng minh tương đương pháp lý. Không tích hợp fuzzy matching.
- Agent 3 có tạo summary trước Agent 4: không cho summary thay văn bản nguồn;
  Pháp Điển tiếp tục yêu cầu quote thật và kiểm ngữ nghĩa độc lập.

## Đã tích hợp trong đợt này

### 1. Tìm lexical theo từng task

Trong nhánh truy xuất đầy đủ, nếu BM25 bật và có ít nhất hai task, pipeline
gọi BM25 cho truy vấn riêng của từng task, loại query trùng sau khi chuẩn hóa
khoảng trắng/chữ hoa thường. Tối đa bốn query bổ sung, không thêm LLM call.
Các task vượt ngân sách được ghi trong `deferred_task_ids`; chúng không bị xóa
khỏi bước kiểm độ đầy đủ. Có trace `task_scoped_retrieval` với candidate IDs.

Các kết quả vẫn là ứng viên, đi qua fusion, lọc thời gian/nguồn, audit và reviewer
bình thường. Truy xuất riêng không bảo đảm ứng viên sẽ sống qua Top-K hoặc đủ
để kết luận. Các nhánh exact/profile hiện không thay đổi; chỉ được mở rộng sau
khi có phép đo chứng minh cần thiết.

### 2. Khôi phục quote chỉ khác bố cục khoảng trắng

Reviewer có thể trả quote một dòng trong khi PDF có xuống dòng hoặc nhiều dấu
cách. Trước khi từ chối, code thử đối chiếu chỉ theo khoảng trắng, rồi khôi phục
đúng đoạn liên tục từ chính evidence ID đã dẫn. Quote lưu lại phải là substring
nguyên văn của nguồn. Không đổi chữ, dấu câu, hoa thường, số, dấu tiếng Việt,
phủ định; không ghép qua hai nguồn; không fuzzy matching.

Sau khôi phục, vẫn kiểm SUPPORTED/UNSUPPORTED, toàn bộ claim/task IDs,
điều kiện, nguồn, độ đầy đủ và các hard guards. Đây là sửa lỗi bố cục trích dẫn,
không phải cách cho câu trả lời sai vượt qua hậu kiểm.

Mã mới `query_support.py` được viết độc lập theo các nguyên tắc trên; không chép
module hoặc công thức của repository luật thuế.

## Phạm vi kiểm chứng và bước sau

- Kiểm thử trường hợp task độc lập, query trùng, hết ngân sách; quote xuống dòng,
  Unicode whitespace; số/phủ định/dấu câu bị đổi; quote gắn sai evidence ID.
- Chạy hồi quy ONLINE trước khi chép vào dự án chính. Log và hash lưu tại thư mục
  rà soát `review_packages/tax_architecture_20261023` của workspace.
- Chưa có benchmark chất lượng hoặc độ trễ sau sửa trên backend Kaggle. Không
  gọi bản này chính xác hơn nếu chưa đo.
- Không cần API key mới, không chạy lại OFFLINE để dùng hai thay đổi này.
- Để kiểm tra câu hai yêu cầu, cần lưu response JSON và trace: số task, candidate
  IDs, nguồn còn lại sau audit, claim verdict và coverage. Không suy ra nguyên
  nhân lỗi cũ chỉ từ dòng “chưa xác minh được ý nghĩa pháp lý”.
- Ưu tiên tiếp theo: kiểm task được giữ xuyên qua ranking/evidence pack, lịch sử
  hai mốc độc lập, số học có chứng cứ, rồi đối chứng trên Gold giữ riêng.
- Corpus chưa đủ hoặc metadata hiệu lực chưa duyệt vẫn phải được công bố;
  không thêm prompt để giả lập khả năng trả lời mọi câu pháp luật.
