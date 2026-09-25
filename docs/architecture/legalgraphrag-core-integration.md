# Tích hợp các ý phù hợp từ LegalGraphRAG/core

## Phạm vi đã tích hợp

Hệ thống không sao chép ontology hình sự, charge prediction hoặc prompt kết án của LegalGraphRAG. Các ý tưởng được chuyển sang miền pháp luật lao động Việt Nam và luôn đặt kiểm tra xác định trước LLM.

1. **Fact segmentation có provenance:** Query Analyzer và Researcher lưu trường, giá trị, đoạn trích chính xác, vị trí ký tự và nguồn span. Fact do LLM đề xuất chỉ được nhận khi đoạn trích tồn tại duy nhất trong câu hỏi hiện tại và quy tắc entailment xác nhận giá trị. Fact không được suy ra từ lịch sử hội thoại hoặc kiến thức riêng của model.
2. **Community retrieval hai tầng:** với yêu cầu tìm bản án hoặc tranh chấp, hệ thống xếp hạng Community trước rồi trả về chính các retrieval unit loại `CASE` thuộc Community đó. Evidence giữ đường đi `BELONGS_TO`; Community summary không được dùng thay cho nội dung bản án.
3. **Community summary giàu tín hiệu hơn:** bước OFFLINE tạo summary từ số bản án, loại tranh chấp, tòa án và các CaseFeature có provenance.
4. **Applicability audit dễ kiểm tra:** trace ghi quyết định theo từng evidence, gồm trạng thái, kết quả relevant/supports-claim và lý do.
5. **Đánh giá rộng hơn:** ablation report có thêm fact exact accuracy, issue precision/recall, applicability accuracy và answer-status accuracy bên cạnh retrieval/citation/temporal metrics.
6. **Chế độ OFFLINE AI rõ ràng:** `hybrid_ai` giữ checklist xác định làm nền và bổ sung kết quả AI đã kiểm quote; `ai` yêu cầu AI cho toàn bộ checklist đủ điều kiện. Cả hai có cache/resume và fail closed.

## Những phần không đưa vào

- Ontology bị cáo, hành vi phạm tội, nạn nhân, tâm lý chủ quan và charge anchor không phù hợp pháp luật lao động.
- `eval()`, free-form LLM output, mutable insight memory và LLM tự phê duyệt evidence không đáp ứng yêu cầu an toàn.
- GPT-4o-mini, DeepSeek và Qwen không cần chạy đồng thời. Cấu hình mặc định dùng Qwen3-8B làm backbone cho ba agent theo thứ tự; endpoint OpenAI-compatible chỉ là phương án thay thế.

## Chạy bản cải tiến trên Kaggle

### A. Chỉ chạy ONLINE với build V8.1 hiện có

Không cần dựng lại OFFLINE để dùng fact provenance và Community retrieval cơ bản. Trên Kaggle, cập nhật repository rồi chạy:

```bash
cd /kaggle/working/legal-agentic-rag
git pull --ff-only
python kaggle/online_remote.py
```

Notebook phải bật GPU và Internet, đồng thời có Dataset chứa `artifacts/` của `vn_labor_results_v8.1(aura).zip`. Secrets bắt buộc là `VN_LABOR_API_KEY` và `NGROK_AUTHTOKEN`; `HF_TOKEN` chỉ giúp tải model ổn định hơn.

### B. Tạo build OFFLINE mới với AI enrichment

Chỉ làm bước này khi cần checklist/ontology/community summary mới. Đây là tác vụ nên chạy trên Kaggle T4 x2:

```bash
cd /kaggle/working/legal-agentic-rag
git pull --ff-only
python kaggle/offline_ai_remote.py --mode hybrid_ai
```

`hybrid_ai` là lựa chọn khuyến nghị vì giữ baseline xác định nếu model lỗi. Muốn kiểm thử chế độ AI nghiêm ngặt dùng:

```bash
python kaggle/offline_ai_remote.py --mode ai
```

Sau khi enrichment PASS, nạp đúng build mới vào Aura rồi export lại kết quả. Không dùng Aura cũ với graph build mới. Tải ZIP kết quả về và cập nhật `VN_LABOR_ARTIFACT_SOURCE` hoặc Dataset đầu vào ONLINE.

## Việc người vận hành phải tự làm

1. Đưa package/repository mới lên Kaggle hoặc `git pull` commit mới nhất.
2. Bật **GPU T4 x2** và **Internet**.
3. Giữ Dataset kết quả V8.1 hoặc build mới ở chế độ Private.
4. Tạo Kaggle Secrets cho backend ONLINE; nếu nạp Aura, thêm `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
5. Nếu dùng API OpenAI-compatible cho OFFLINE, tự đặt `VN_LABOR_OFFLINE_AI_API_KEY`; không ghi token vào notebook, Git hoặc `.env.example`.
6. Duyệt báo cáo validation và một bộ Gold có người chuyên môn trước khi kết luận model mới chính xác hơn. Thêm API/model không thay thế source review, temporal review và Gold approval.

## Tiêu chí kiểm tra

- Test ONLINE, OFFLINE AI và source resolver phải PASS.
- `final_outputs_validation.json`, Dense, BM25, graph và Neo4j phải cùng build ID.
- Fact candidate không có exact quote/span phải bị loại.
- Evidence sai actor, loại hợp đồng, điều kiện đặc thù hoặc thời điểm phải bị hard-filter trước Adjudicator.
- Community retrieval chỉ trả retrieval unit CASE gốc có provenance.
- So sánh cấu hình bằng cùng Gold set và cùng build; không chọn model dựa trên một vài câu hỏi thủ công.
