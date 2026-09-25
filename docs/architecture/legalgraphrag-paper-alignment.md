# Đối chiếu bài báo LegalGraphRAG và hệ thống VN Labor

## Kết luận

Bảng mô tả ban đầu đúng về ba nhóm model chính nhưng dễ gây hiểu nhầm rằng phải dùng đồng thời nhiều API LLM. Bài báo dùng **một backbone LLM tại một lần chạy**; Qwen3-8B là cấu hình mặc định, GPT-4o-mini và DeepSeek-V3.1 là các backbone thay thế trong thí nghiệm. BGE-M3 là model embedding, không phải agent suy luận.

Bài báo giải bài toán dự đoán bản án hình sự Trung Quốc. Hệ thống này trả lời pháp luật lao động Việt Nam, nên không sao chép bốn chiều ontology hình sự hay `charge anchor`. Các cơ chế tương ứng được chuyển thành ontology quan hệ lao động, issue/policy anchors, kiểm tra chủ thể, điều kiện, ngoại lệ, hiệu lực và hậu quả pháp lý.

## OFFLINE hiện tại

- Parse tài liệu thành Document Registry, Article/Clause/Point có provenance, version và temporal metadata.
- Dựng graph ba lớp: document/fact, ontology và rule; có DiagnosticItem, LegalIssue, CaseFeature, Community và các quan hệ pháp lý.
- BGE-M3 tạo Dense index và vector case; k-NN cùng Leiden tạo liên kết/cộng đồng vụ án.
- BM25 tạo lexical index độc lập.
- Checklist heuristic vẫn là baseline xác định. Enrichment mới hỗ trợ `hybrid_ai` hoặc `ai`, dùng Ollama hay HTTP OpenAI-compatible, cache/resume theo hash, và chỉ nhận checklist có trích đoạn định vị được trong nguồn.
- Judicial corpus có thể được bổ sung ontology chuyên biệt lao động: chủ thể, quan hệ lao động, sự kiện, tình trạng được bảo vệ, thủ tục, yêu cầu/biện pháp khắc phục và kết quả. Mọi feature AI phải có quote định vị được; ontology hình sự của bài báo không được dùng.

Không bắt buộc chạy enrichment AI để ONLINE hoạt động. Build V8.1 hiện tại đã có graph, Dense, BM25 và checklist. Enrichment làm graph thay đổi nên phải nạp lại Aura và lấy build ID mới; Dense/BM25 được tái sử dụng khi retrieval units không đổi.

## ONLINE hiện tại

1. Query Analyzer xác định vấn đề, chủ thể, facts, ngày áp dụng, route và các slot bằng chứng bắt buộc.
2. **Researcher Agent** dùng Qwen có structured output để ánh xạ ontology lao động và sinh tối đa hai truy vấn mở rộng. Nó chỉ tăng recall, không được xác nhận facts hay phê duyệt nguồn.
3. Retrieval hợp nhất exact hierarchy, policy anchor, BM25, BGE-M3 Dense, issue anchor, case channel và graph expansion bằng RRF.
4. **BGE reranker v2 M3** tùy chọn chấm lại tối đa 30 candidates trước authority/temporal scoring. Kaggle bật model này; nếu model lỗi, hệ thống giữ retrieval cũ và ghi cảnh báo.
5. Authority và temporal filters loại evidence không đúng nguồn hoặc phiên bản trước khi suy luận.
6. **Hybrid Auditor Agent** chạy luật cứng trước. Điều bị loại vì sai chủ thể, sai loại hợp đồng hoặc thiếu fact đặc thù không bao giờ được LLM phục hồi. Qwen chỉ kiểm các candidate còn lại theo facts và Diagnostic Checklist, trả đúng ID theo JSON Schema.
7. Graph traversal mở rộng có ngân sách node/edge/hop/time và audit lại evidence ở từng vòng.
8. **Adjudicator Agent** nhận Verified Evidence Pack, lập claim gắn ID evidence. Reference audit loại URL, Điều/Khoản/Điểm hoặc marker không có trong evidence.

Kaggle dùng Qwen3-8B cho cả Researcher, Auditor và Adjudicator theo thứ tự; BGE-M3 và BGE reranker chạy trên GPU 0, Ollama/Qwen ưu tiên GPU 1. Không cần OpenAI API cho ONLINE mặc định.

## API và biến môi trường

- ONLINE Kaggle mặc định không cần API thương mại: Qwen3-8B chạy qua Ollama.
- `HF_TOKEN` tùy chọn để tránh rate limit khi tải BGE-M3 và BGE reranker.
- Có thể thay từng agent bằng endpoint OpenAI-compatible qua `VN_LABOR_RESEARCHER_*`, `VN_LABOR_APPLICABILITY_*`, `VN_LABOR_ADJUDICATION_*`.
- OFFLINE enrichment dùng `VN_LABOR_OFFLINE_AI_PROVIDER=ollama` hoặc `http`; khi dùng HTTP, người vận hành tự đặt `VN_LABOR_OFFLINE_AI_API_KEY` trong `.env` hoặc Kaggle Secret.

## Giới hạn chưa thể giải quyết bằng cách thêm model

- Source catalog, temporal ở cấp provision và Gold set chưa được người có chuyên môn duyệt đầy đủ.
- Judicial corpus chỉ có 24 hồ sơ, nên community/case retrieval có recall hạn chế.
- Chưa có Gold được duyệt để chứng minh bằng số rằng model hay prompt mới tăng độ chính xác. Vì vậy không được tuyên bố “độ chính xác tối đa” chỉ từ việc thêm API.
- Chất lượng cuối phải được đo bằng recall@k, nDCG/MRR, actor/applicability accuracy, temporal accuracy, citation precision và abstention correctness trên cùng build.
