# SƠ ĐỒ CÔNG NGHỆ ONLINE VÀ LỜI THOẠI THUYẾT TRÌNH — PHÁP ĐIỂN AI


Đối chiếu mã nguồn local ngày 23/10/2026. Sơ đồ mô tả hệ thống hiện có, không phải cam kết mọi câu hỏi đều được trả lời đúng. Không suy ra model đang chạy trên Kaggle chỉ từ YAML local: biến môi trường và config ghim có thể thay provider/model. Các số là nhóm bước chức năng để thuyết trình; log runtime có thể có nhiều dòng cho một nhóm, có dòng bỏ qua và các vòng lặp. Tầng màu là trách nhiệm chức năng, không có nghĩa mỗi tầng là một dịch vụ độc lập hoặc một LLM khác nhau.

Màu xanh dương: Researcher; xanh lá: Retriever; cam: Auditor; tím: Adjudicator; hồng: Hậu kiểm; xám: frontend/API/runtime. Graph mở rộng được đặt trong Retriever; Auditor kiểm lại nguồn mới. Việc kiểm ngôn ngữ và ngữ nghĩa được tách thành tầng Hậu kiểm cho dễ giải thích, dù một phần được gọi bên trong LegalAdjudicator.generate().

Cách đọc: bắt đầu bước 1 và đi theo mũi tên. Nhánh phụ 25–29 là kết quả hoặc xử lý ngoại lệ, cuối cùng hiển thị ở 24. Bước 30 quan sát toàn bộ quá trình; không phải một bước suy luận cần chờ đến cuối. Nhấp vào node trong bản HTML để xem lời thoại và công nghệ của node đó.

## Các luồng cần trình bày

### Trả lời một lượt, không mở rộng Graph

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 hoặc 9 → 10 → 11 → 12 → 13 → 14 → 16 → 17 → 18 → 19 → 20 → 22 → 23 → 24. Bước 11/19/20 có thể bỏ qua tùy nhánh/cấu hình. Một lượt truy xuất không đồng nghĩa một lời gọi model.

### Tra cứu nguyên văn nhanh

1–7 → 8 (Exact và khoản/điểm con) → 10–14 → 16–18 → 22–24 khi đủ điều kiện literal. Không gọi model diễn giải hoặc reviewer ngữ nghĩa cho nhánh LITERAL_SOURCE_MATCH; kiểm nguồn và trích dẫn vẫn thực hiện.

### Thiếu căn cứ, phải mở rộng nhiều lần

14 → 15 → 12 → 13 → 14; lặp trong ngân sách rồi 16. Vòng này là mở rộng Graph và kiểm nguồn mới, không phải vòng bắt buộc gọi lại BM25/Dense hay tái viết truy vấn. Mode adaptive trên route STANDARD hiện có thể chỉ cho một vòng; route/cấu hình khác vẫn chịu min(max_rounds,max_hops), node/cạnh/thời gian và request budget.

### Câu hỏi ngoài domain

6 → 26 → 24. Không truy xuất/sinh đáp án lao động cho câu ngoài phạm vi. Researcher trước gate có thể đã được gọi; không nói mọi câu ngoài phạm vi đều chắc chắn không gọi AI.

### Thiếu dữ kiện hoặc ngữ cảnh mơ hồ

3 hoặc 6 → 25 → 24. Người dùng bổ sung → 1 → 3. Nếu chính sách cho phép giải thích có điều kiện, tiếp tục tìm và trả phần được kiểm cùng questions; chưa kết luận phần thiếu facts.

### Ngày chưa đủ chính xác

16 → 25 → 24 nếu khoảng thời gian giao mốc thay đổi phiên bản. Yêu cầu ngày chính xác, không mặc định áp luật mới cho sự việc cũ.

### Không đủ căn cứ sau khi tìm

16 → 27 → 24. Nếu task độc lập nào đã đủ và được phép, chỉ phần đó đi qua 17–23 rồi trả PARTIAL_ALLOWED.

### Có nguồn nhưng câu trả lời chưa đạt

19/20/22/23 có thể chặn hoặc hạ mức; 27 → 24. Không nói có citation là đủ. Các đường chặn trên sơ đồ rút gọn việc chốt envelope và kiểm đáp án an toàn trong pipeline.

### Sửa rồi review lại

20 → 21 → 20 trong semantic_repair_attempts. Bản sửa dùng cùng pack. Hết lượt thì giữ phần đã xác minh hoặc chặn, không lặp vô hạn để buộc PASS.

### Nguồn có thẩm quyền xung đột

16 nhận diện → đi qua các bước xử lý/kiểm cần thiết → 23 → 28 → 24 nếu nhánh xung đột còn hợp lệ. Không tự chọn theo điểm truy xuất; nếu hậu kiểm thất bại vẫn có thể hạ thành không đủ căn cứ.

### Lỗi, hết RPM, timeout, hủy, bận hoặc retry

2 hoặc một bước đang thực thi → 29 → 24; một số lỗi phụ có dự phòng với cảnh báo. Retry cùng message_id/nội dung đã DONE có thể trả kết quả cache tại 2, không chạy lại cả pipeline. Hủy là hợp tác; mất kết nối frontend không đồng nghĩa server đã dừng.

## Lời thoại theo số node

### 01. Người dùng nhập câu hỏi — Frontend

**Lời thoại:** “Ở bước 1, nhận câu hỏi mới hoặc câu bổ sung. Gửi lịch sử các lượt người dùng, facts và ngày tra cứu nếu có; không dùng câu trả lời cũ của AI như một sự thật đã được xác nhận.”

**Công nghệ và vai trò:** React, JavaScript, lịch sử hội thoại trên trình duyệt.

**Output:** QueryRequest: question, conversation_turns/context, facts, query_date, message_id; kèm capability phiên X-Client-Session.

**Đối chiếu code:** `frontend/src/pages/ChatPage.jsx; frontend/src/services/chatService.js; conversationService.js`

### 02. Tiếp nhận và bảo vệ request — API

**Lời thoại:** “Ở bước 2, proxy chuyển yêu cầu tới API. FastAPI kiểm schema, xác thực và trạng thái dịch vụ. Registry phân biệt yêu cầu mới, đang chạy, trùng đã xong hoặc trùng ID nhưng khác nội dung; semaphore giới hạn số câu xử lý đồng thời. Đường truyền Kaggle có thể đi qua ngrok, nhưng không làm thay đổi thuật toán RAG.”

**Công nghệ và vai trò:** HTTP/JSON; Vite proxy (dev); FastAPI, Pydantic; Bearer token nếu bật; RequestRegistry.

**Output:** Request hợp lệ cùng ngân sách thời gian và message_id. Retry cùng ID/nội dung có thể nhận kết quả đã xong; request sai/bận chuyển nhánh 29.

**Đối chiếu code:** `src/vn_labor_online/api.py:create_app/answer; runtime.py:RequestRegistry`

### 03. Ghép ngữ cảnh và dữ kiện nối tiếp — Researcher

**Lời thoại:** “Ở bước 3, xác định câu mới có tiếp nối vấn đề trước hay không. Hợp nhất dữ kiện từ lịch sử người dùng, giữ nguồn gốc và ưu tiên thông tin mới phù hợp. Nếu chủ đề nối tiếp còn mơ hồ, dừng để hỏi lại, không đoán hoặc tìm kiếm ngay.”

**Công nghệ và vai trò:** Python; conversation.resolve_context; quy tắc chủ đề và nguồn gốc facts.

**Output:** Câu hỏi đã giải nghĩa, facts, ngày tra cứu, các lượt được sử dụng; hoặc câu hỏi làm rõ đi tới bước 25.

**Đối chiếu code:** `src/vn_labor_online/conversation.py:resolve_context; pipeline.py:ask`

### 04. Hiểu vấn đề và tách các ý cần trả lời — Researcher

**Lời thoại:** “Ở bước 4, nhận diện chủ thể, hợp đồng, thời gian, điều luật được nêu, ý định và các yêu cầu độc lập. Quy tắc chạy trước; Researcher thích nghi chỉ yêu cầu model khi cần theo execution_path. Model trả dữ liệu có cấu trúc và được kiểm tra, không mặc nhiên biến suy đoán thành facts.”

**Công nghệ và vai trò:** Python, regex, taxonomy vấn đề lao động; LegalResearcher; Gemini/Ollama/HTTP tùy cấu hình.

**Output:** QueryAnalysis: legal_issues/subissues, facts, missing_facts, answer_tasks, retrieval_queries, ontology_features và route.

**Đối chiếu code:** `src/vn_labor_online/analysis.py:analyze; researcher.py:LegalResearcher; taxonomy.py`

### 05. Lập kế hoạch căn cứ cho từng ý — Researcher

**Lời thoại:** “Ở bước 5, xác định phải có những nhóm căn cứ nào, gồm quy tắc chính, điều kiện, ngoại lệ và hậu quả khi cần. Phân biệt ô bắt buộc và có điều kiện. Nếu thiếu ngày, dùng ngày chốt corpus theo chính sách và ghi cảnh báo; không tự coi đó là ngày luật mới nhất.”

**Công nghệ và vai trò:** Python; plan_evidence; taxonomy/profile; bộ định vị Điều/Khoản/Điểm.

**Output:** EvidencePlan: mandatory_slots, conditional_slots, slot_requirements và mốc/khoảng ngày cần áp dụng.

**Đối chiếu code:** `src/vn_labor_online/analysis.py:plan_evidence; pipeline.py:_ask; retrieval.py:resolve_article_plan`

### 06. Kiểm tra domain và dữ kiện quyết định — Researcher

**Lời thoại:** “Ở bước 6, câu ngoài pháp luật lao động đi tới 26. Thiếu dữ kiện có thể làm đổi kết luận cụ thể thì tới 25. Trong trường hợp được chính sách cho phép, hệ thống tiếp tục tìm để giải thích có điều kiện, đồng thời hỏi bổ sung; không kết luận chắc chắn về phần chưa rõ.”

**Công nghệ và vai trò:** Python; in_scope, missing_facts, route, requested_outcome; answer_while_clarifying.

**Output:** Tiếp tục tra cứu, NEED_MORE_FACTS, ABSTAIN; hoặc cờ chỉ giải thích có điều kiện.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:_ask; analysis.py`

### 07. Chọn đường truy xuất — Retriever

**Lời thoại:** “Ở bước 7, ưu tiên thử định vị điều khoản khi người dùng nêu rõ văn bản/điều; hoặc thử profile cho chuỗi quy tắc đã biết. Những câu không đi đường tắt hoặc không đạt điều kiện sẽ chạy truy xuất nhiều kênh. Đường tắt không bỏ các kiểm tra bằng chứng và hậu kiểm cần thiết.”

**Công nghệ và vai trò:** Python; route DIRECT/STANDARD/COMPLEX theo phân tích và cấu hình; exact/profile fast path.

**Output:** Lựa chọn thử bước 8 hoặc vào bước 9; flags exact_only/profile_only.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:_ask`

### 08. Tra cứu chính xác / thử chuỗi profile — Retriever

**Lời thoại:** “Ở bước 8, exact khớp số văn bản và Điều/Khoản/Điểm, lấy thêm khoản/điểm con theo thứ tự nguồn để không mất phần liệt kê. Profile thử các căn cứ đã định vị, lọc và kiểm áp dụng sơ bộ. Profile chỉ bật đường tắt nếu chuỗi được nhận diện và không còn thiếu phần phải tìm. Có nguồn exact chưa đồng nghĩa câu trả lời đã đủ.”

**Công nghệ và vai trò:** Python; exact, hierarchy_descendants, PART_OF; policy_anchor, kiểm thử profile bằng quy tắc.

**Output:** Evidence hạt giống; exact_only/profile_only. Nếu không dùng được đường tắt thì chuyển 9; nếu dùng được vẫn qua 10–14.

**Đối chiếu code:** `src/vn_labor_online/retrieval.py:exact/hierarchy_descendants/policy_anchor; pipeline.py`

### 09. Truy xuất Hybrid và các kênh bổ sung — Retriever

**Lời thoại:** “Ở bước 9, bM25S tìm theo từ khóa. BGE-M3 mã hóa câu hỏi thành vector; FAISS tìm vector gần trong chỉ mục đã xây OFFLINE. Kênh issue/profile giữ neo pháp lý; case và community chỉ thêm khi câu hỏi và cấu hình cần đến. Câu nhiều ý có thể bổ sung truy vấn theo task. Trong code hiện tại các kênh được gọi theo thứ tự, không mặc định chạy song song.”

**Công nghệ và vai trò:** BM25S; BAAI/bge-m3 (FlagEmbedding/PyTorch); FAISS; neo vấn đề, case/community.

**Output:** Các danh sách Evidence, mỗi nguồn có unit_id, điểm/rank và retrieval_method; chưa là bằng chứng đã kiểm.

**Đối chiếu code:** `src/vn_labor_online/retrieval.py:Retriever; query_support.py:task_bm25_channels; pipeline.py`

### 10. Gộp nguồn và lọc thời điểm / thẩm quyền — Retriever

**Lời thoại:** “Ở bước 10, gộp thứ hạng các kênh rồi loại trùng. Một kênh thì dùng kết quả kênh đó, không giả vờ chạy RRF. Lọc theo khoảng hiệu lực, ngày hỏi, nguồn/thẩm quyền và giữ neo bắt buộc. Chính sách provisional có thể cho fallback cấp văn bản kèm cảnh báo, không chứng nhận hiệu lực từng điều khoản đã duyệt.”

**Công nghệ và vai trò:** RRF khi nhiều kênh; Python dedup; temporal_filter, authority_filter, retain_required_anchors.

**Output:** Nguồn còn lại, ID bị loại và lý do; các neo căn cứ cần thiết được giữ khi phù hợp.

**Đối chiếu code:** `src/vn_labor_online/retrieval.py:fusion/temporal_filter/authority_filter/retain_required_anchors`

### 11. Xếp hạng lại các nguồn — Retriever

**Lời thoại:** “Ở bước 11, reranker chấm trực tiếp cặp câu hỏi–đoạn nguồn, giúp đưa đoạn liên quan lên trên. Exact/profile có thể bỏ qua model này; khi bị tắt thì không sử dụng. Nếu model reranker không khả dụng, code có nhánh cảnh báo và tiếp tục với kết quả có sẵn, thay vì tuyên bố rerank thành công.”

**Công nghệ và vai trò:** BAAI/bge-reranker-v2-m3; PyTorch/FlagEmbedding; rerank quy tắc.

**Output:** Danh sách ứng viên đã sắp lại, hoặc kết quả cũ kèm NEURAL_RERANKER_UNAVAILABLE.

**Đối chiếu code:** `src/vn_labor_online/retrieval.py:neural_rerank/rerank; pipeline.py`

### 12. Kiểm tra nguồn và dấu vết bằng chứng — Auditor

**Lời thoại:** “Ở bước 12, đối chiếu đoạn chứng cứ với dữ liệu artifact, đường dẫn gốc, dấu vết vị trí và metadata thời gian/nguồn. Lỗi cứng không được đưa tiếp như bằng chứng hợp lệ. Cảnh báo chưa duyệt nguồn/hiệu lực phải được giữ. Bằng chứng mở rộng từ Graph cũng phải qua bước này.”

**Công nghệ và vai trò:** Python; deterministic_audit; provenance, source span, catalog, temporal metadata.

**Output:** Evidence có verified/audit_warnings; nguồn đạt kiểm tra máy đi tới 13, nguồn lỗi bị loại.

**Đối chiếu code:** `src/vn_labor_online/audit.py:deterministic_audit; pipeline.py`

### 13. Kiểm tra khả năng áp dụng — Auditor

**Lời thoại:** “Ở bước 13, kiểm tra nguồn có liên quan, điều kiện nào được xác nhận, có hỗ trợ nhận định pháp lý hay chỉ là đoạn giống từ khóa. Mode hybrid ưu tiên quy tắc, đưa phần cần kiểm sang model theo batch và giới hạn. Quyết định của model vẫn được kiểm cấu trúc; nội dung không xác định không được coi là PASS.”

**Công nghệ và vai trò:** LegalApplicabilityAuditor; quy tắc/profile; diagnostic checklist; Ollama hoặc HTTP LLM nếu cấu hình.

**Output:** ApplicabilityDecision: PASS/FAIL/UNRESOLVED, relevant, supports_claim, reasons; tập evidence được chấp nhận.

**Đối chiếu code:** `src/vn_labor_online/applicability.py:LegalApplicabilityAuditor.audit/_hybrid/_deterministic`

### 14. Đo độ phủ và xác định căn cứ còn thiếu — Auditor

**Lời thoại:** “Ở bước 14, so bằng chứng đã được chấp nhận với các ô căn cứ trong kế hoạch. Khi chuỗi pháp lý đòi hỏi căn cứ bổ sung, kế hoạch có thể được mở rộng. Phân biệt khoảng thiếu có thể tìm thêm với metadata chờ duyệt. Khi không cần mở rộng, đi 16; còn khoảng thiếu và còn ngân sách thì sang 15.”

**Công nghệ và vai trò:** Python; extend_plan_for_evidence, state_for, _actionable_gaps.

**Output:** EvidenceState: slots, coverage, gaps; quyết định cần Graph hay đủ để đánh giá đầu ra cuối.

**Đối chiếu code:** `src/vn_labor_online/evidence.py:state_for/extend_plan_for_evidence; pipeline.py`

### 15. Mở rộng đồ thị có giới hạn — Retriever

**Lời thoại:** “Ở bước 15, từ frontier bằng chứng hiện có, tìm node/cạnh giúp lấp khoảng thiếu: REFERENCES, AMENDS, REPEALS, VERSION_OF, PART_OF, CITES, HAS_ISSUE, SIMILAR_TO… Các tầng Fact/Ontology/Rule/Document/Derived tham gia tùy đường đi thực tế. Nguồn mới được lọc thời điểm/thẩm quyền rồi quay lại 12–14. Dừng theo số vòng, hop, node, cạnh, thời gian hoặc hết frontier; không lặp vô hạn và không nhất thiết chạy lại BM25/Dense mỗi vòng.”

**Công nghệ và vai trò:** GraphExplorer; adjacency từ nodes.jsonl/edges.jsonl trong RAM; duyệt quan hệ và xếp ưu tiên.

**Output:** Bằng chứng mới, frontier, graph_path/relations, thống kê node/cạnh và stop_reason. Nếu đã hết khả năng tìm, chuyển tới đánh giá cuối ở 16.

**Đối chiếu code:** `src/vn_labor_online/graph.py:GraphExplorer.expand_round; pipeline.py:_ask; artifact_store.py`

### 16. Chọn nguồn và phân loại mức đủ cuối — Auditor

**Lời thoại:** “Ở bước 16, chọn căn cứ đáp ứng từng ô và phát hiện nguồn có thẩm quyền xung đột. Khoảng ngày vắt qua mốc thay đổi luật có thể yêu cầu ngày chính xác. Không đủ toàn bộ nhưng có task độc lập đã đủ thì chỉ cho phép phần đó theo chính sách; không dựa duy nhất vào tỷ lệ coverage để kết luận đủ.”

**Công nghệ và vai trò:** Python; select_for_plan, detect_authoritative_conflicts; kiểm giao khoảng hiệu lực.

**Output:** Trạng thái dự kiến: SUFFICIENT, PARTIAL_ALLOWED, CONFLICTING_EVIDENCE; hoặc NEED_MORE_FACTS/INSUFFICIENT_EVIDENCE. Tập nguồn đã chọn đi 17 nếu được tiếp tục.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:_ask; evidence.py; tasks.py:independent_partial_plan`

### 17. Đóng gói bằng chứng đã kiểm — Auditor

**Lời thoại:** “Ở bước 17, chỉ đóng gói câu hỏi đã hiểu, facts, ngày, tasks, bằng chứng được chọn, quyết định Auditor và các ô còn thiếu. Gắn ID bằng chứng để câu trả lời có thể truy nguyên. Đây là dữ liệu trích dẫn cho model, không phải chỉ dẫn được phép thay đổi vai trò hệ thống.”

**Công nghệ và vai trò:** Python, Pydantic; VerifiedEvidencePack; build_verified_pack.

**Output:** VerifiedEvidencePack gửi sang Adjudicator; có lookup_reference khi đủ điều kiện trích nguyên văn.

**Đối chiếu code:** `src/vn_labor_online/evidence.py:build_verified_pack; models.py:VerifiedEvidencePack; pipeline.py`

### 18. Tạo bản nháp có căn cứ — Adjudicator

**Lời thoại:** “Ở bước 18, nhánh tra cứu đủ điều kiện trích chính xác nội dung nguồn, không cần LLM diễn giải. Nhánh quy tắc đã biết có thể dựng đáp án từ profile. Các trường hợp khác yêu cầu model trả claims theo JSON schema, chỉ được dùng evidence_ids có trong pack. Không phải câu nào cũng gọi Qwen; Gemini reviewer không mặc nhiên là model sinh bản nháp.”

**Công nghệ và vai trò:** LegalAdjudicator; trích nguyên văn, rule/profile renderer; Qwen qua Ollama hoặc LLM HTTP khi cần.

**Output:** AdjudicationDraft: claims gắn evidence_ids, bản trình bày, phiên bản luật, giả định/giới hạn; hoặc nhánh literal đi thẳng 22.

**Đối chiếu code:** `src/vn_labor_online/generation.py:LegalAdjudicator.generate/_generate/literal_lookup_draft`

### 19. Kiểm tra câu chữ và cấu trúc bản nháp — Hậu kiểm

**Lời thoại:** “Ở bước 19, kiểm lỗi câu chữ, ký tự, định dạng, nội dung thừa, claims và giới hạn an toàn. Không tự sửa đoán số điều hoặc chữ OCR pháp lý. Khi cần có thể yêu cầu sửa ngôn ngữ trong giới hạn cho phép và kiểm lại; chỉ dùng bản dựng dự phòng nếu đạt điều kiện. Nhánh trích nguyên văn có kiểm literal riêng nên bỏ bước này.”

**Công nghệ và vai trò:** Python; answer_quality, clean_draft, render_claims; JSON/Pydantic; model sửa câu nếu cần.

**Output:** Bản nháp đã làm sạch/được sửa an toàn; hoặc cờ ANSWER_QUALITY_BLOCKED, đi nhánh không kết luận.

**Đối chiếu code:** `src/vn_labor_online/generation.py:_generate_with_layout; answer_quality.py`

### 20. Đối chiếu ý nghĩa và độ đủ từng ý — Hậu kiểm

**Lời thoại:** “Ở bước 20, reviewer đối chiếu từng claim với nguồn đầy đủ và kiểm các tasks đã được trả lời hay chưa. Báo cáo phải đúng ID, đúng trích đoạn nguồn và đúng cách tính phần đã trả lời. PASS mới qua; PARTIAL chỉ giữ claims đã kiểm; FAIL/ERROR không được lén trả bản nháp cũ. Nếu reviewer tắt/deterministic thì không gọi LLM và phải thể hiện giới hạn đó.”

**Công nghệ và vai trò:** answer_review; reviewer Gemini nếu chọn, hoặc provider sinh câu trả lời; schema và kiểm quote bằng Python.

**Output:** semantic_review: PASS/PARTIAL/FAIL/ERROR, claims được hỗ trợ, ý còn thiếu. Có thể đi 21 để sửa trong ngân sách, hoặc chặn tại 27.

**Đối chiếu code:** `src/vn_labor_online/answer_review.py:review_answer/audit_in_batches/validate_review; generation.py`

### 21. Sửa bản nháp rồi kiểm lại — Hậu kiểm

**Lời thoại:** “Ở bước 21, khi review phát hiện nội dung thiếu/sai và còn lượt sửa, yêu cầu sửa trong phạm vi bằng chứng đã có rồi quay lại reviewer. Báo cáo review sai schema có thể được yêu cầu kiểm lại trong cùng ngân sách. Không bổ sung nguồn giả, không mở một vòng tìm kiếm Graph mới tại đây và không nới tiêu chuẩn để buộc PASS.”

**Công nghệ và vai trò:** Python; review_answer, repair; cùng pack và giới hạn semantic_repair_attempts.

**Output:** Bản nháp mới hoặc yêu cầu kiểm lại về bước 20. Hết lượt thì giữ phần độc lập đã xác minh hoặc chặn kết luận.

**Đối chiếu code:** `src/vn_labor_online/answer_review.py:review_answer (vòng repair bên trong)`

### 22. Hậu kiểm trích dẫn và căn cứ bắt buộc — Hậu kiểm

**Lời thoại:** “Ở bước 22, kiểm marker, evidence ID, link và claims có khớp nguồn; kiểm đủ các nhóm căn cứ cần nêu trong đáp án, không chỉ trong tập đã truy xuất. Có một nhánh sửa tham chiếu hữu hạn bằng claims vốn đã gắn nguồn hợp lệ rồi audit lại. Nếu vẫn không đạt, bỏ claims/kết luận không xác minh. Không có LLM judge là đủ để bỏ bước kiểm máy.”

**Công nghệ và vai trò:** Python; reference_audit, claim_validation; missing_answer_slots; sửa tham chiếu xác định.

**Output:** Câu trả lời và citations đạt audit hoặc bị hạ mức/chặn. Sửa xong vẫn phải tính lại mức đủ căn cứ.

**Đối chiếu code:** `src/vn_labor_online/audit.py:reference_audit; claim_validation.py; pipeline.py:_repair_references`

### 23. Chốt trạng thái và độ đủ từng task — Hậu kiểm

**Lời thoại:** “Ở bước 23, đánh giá từng ý đã được trả lời, còn thiếu hay chỉ có giải thích có điều kiện. Chọn trạng thái cuối và giữ cảnh báo nguồn/hiệu lực chưa duyệt. Xung đột được trình bày là xung đột, không tự chọn một kết luận chắc chắn. Lỗi reviewer có thể làm chặn đáp án dù đã tìm được đúng điều luật.”

**Công nghệ và vai trò:** Python; assess_parts; AnswerResponse/Trace; chính sách provisional.

**Output:** AnswerResponse: status, answer, claims, citations, parts, questions, limitations, warnings, legal_status, trace. SUFFICIENT không tự đồng nghĩa legal_ready.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:_ask; tasks.py:assess_parts; models.py:AnswerResponse`

### 24. Hiển thị kết quả và nguồn trên màn hình — Frontend

**Lời thoại:** “Ở bước 24, aPI trả dữ liệu có cấu trúc; frontend đánh số trích dẫn, hiện các phần đáp án, nguồn, câu hỏi bổ sung và cảnh báo. Câu bị chặn vẫn hiện lý do. Nếu cần bổ sung thì lượt người dùng tiếp theo quay về bước 1 và đi qua giải nghĩa ngữ cảnh ở bước 3. Giao diện không tự suy luận thêm luật.”

**Công nghệ và vai trò:** FastAPI JSON; React; chatService; Source Drawer; lịch sử localStorage.

**Output:** Tin nhắn người dùng đọc được, nguồn chính thức có thể mở, nhật ký xử lý và các thao tác thử lại/bổ sung.

**Đối chiếu code:** `src/vn_labor_online/api.py:answer; frontend/src/services/chatService.js; Message.jsx; SourceDrawer.jsx`

### 25. Hỏi bổ sung dữ kiện / ngày chính xác — Researcher

**Lời thoại:** “Ở bước 25, đây là một kết quả hợp lệ, không phải lỗi mạng. Hỏi đúng thông tin làm thay đổi kết luận như loại hợp đồng, ngoại lệ, nhóm công việc hoặc ngày hiệu lực. Với câu nối tiếp chưa rõ chủ đề, yêu cầu làm rõ trước. Người dùng trả lời tạo request mới, quay lại 1 → 3. Nếu được giải thích có điều kiện, câu hỏi có thể kèm phần đáp án tại 24.”

**Công nghệ và vai trò:** Python tạo questions; React hiển thị; conversation_context ở lượt kế tiếp.

**Output:** NEED_MORE_FACTS hoặc questions kèm PARTIAL_ALLOWED; không tự điền dữ kiện thiếu.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:ask/_ask; conversation.py`

### 26. Từ chối câu hỏi ngoài phạm vi — Researcher

**Lời thoại:** “Ở bước 26, thông báo câu hỏi nằm ngoài pháp luật lao động, không ép lấy quy tắc lao động trả lời hình sự, thuế hay vấn đề khác. Không chạy các bước truy xuất/sinh đáp án sau gate chỉ để có nội dung. Phân tích sơ bộ/Researcher trước gate có thể đã chạy theo cấu hình.”

**Công nghệ và vai trò:** Python scope gate; React.

**Output:** ABSTAIN, OUT_OF_SCOPE; lý do hiển thị ở 24.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:_ask`

### 27. Không trả kết luận chưa được xác minh — Hậu kiểm

**Lời thoại:** “Ở bước 27, có hai nguồn chặn cần phân biệt: không đủ chuỗi căn cứ sau tìm kiếm; hoặc đã có nguồn nhưng đáp án/reviewer chưa đạt. Chỉ thông báo lý do, phần thiếu và khả năng thử lại; không biến lỗi dịch vụ kiểm tra thành khẳng định pháp luật không có quy định. Nếu một phần độc lập đã được kiểm và chính sách cho phép, có thể trả PARTIAL_ALLOWED thay vì chặn toàn bộ.”

**Công nghệ và vai trò:** Python; chính sách evidence/quality fail-closed; React.

**Output:** INSUFFICIENT_EVIDENCE, hoặc phần đã xác minh kèm giới hạn. Đưa thông tin ra màn hình tại 24.

**Đối chiếu code:** `src/vn_labor_online/pipeline.py:_ask; generation.py; answer_review.py`

### 28. Thông báo nguồn xung đột — Auditor

**Lời thoại:** “Ở bước 28, nếu các nguồn có thẩm quyền được hệ thống nhận diện là xung đột, kết quả cuối nêu rõ tình trạng và nguồn liên quan. Không dùng điểm similarity để giải quyết xung đột pháp lý. Kiểm trích dẫn và khả năng trình bày an toàn vẫn áp dụng; nếu không qua kiểm tra, trạng thái có thể bị hạ xuống không đủ căn cứ.”

**Công nghệ và vai trò:** Python; detect_authoritative_conflicts; citations.

**Output:** CONFLICTING_EVIDENCE nếu giữ được nhánh xung đột; chưa có kết luận pháp lý dứt khoát.

**Đối chiếu code:** `src/vn_labor_online/evidence.py:detect_authoritative_conflicts; pipeline.py:_ask`

### 29. Lỗi kỹ thuật / quá tải / hết giờ / hủy — Runtime

**Lời thoại:** “Ở bước 29, nhánh này có thể xảy ra ở API, model, chỉ mục hay đường truyền. Schema sai/không xác thực/bận có mã HTTP riêng; Gemini hết RPM là lỗi dịch vụ/quota, không phải thiếu luật. Hủy và timeout có kiểm tra hợp tác, bước đang chờ provider có thể cần thời gian kết thúc. Dự phòng chỉ chạy ở nơi code cho phép. Ngrok/proxy có thể trả lỗi ngoài backend nên không phải lúc nào cũng có trace.”

**Công nghệ và vai trò:** FastAPI error handlers; RequestBudget/checkpoint; provider pacing/retry; AbortController và cancel API.

**Output:** Thông báo lỗi an toàn, mã/trace nếu có và log gần nhất; hoặc kết quả dự phòng có cảnh báo nếu nhánh đó được phép. Trình duyệt không mặc nhiên biết server đã dừng khi mất mạng.

**Đối chiếu code:** `src/vn_labor_online/api.py:error handlers; runtime.py; providers.py; frontend chatService.js`

### 30. Nhật ký thực thi xuyên suốt — Runtime

**Lời thoại:** “Ở bước 30, mỗi bước thực sự chạy ghi tên tầng, công nghệ, output tóm tắt, trạng thái và thời gian. Frontend lấy snapshot qua API cùng capability phiên; phản hồi cuối còn mang execution_steps. Bước bỏ qua ghi SKIPPED, không dựng như đã gọi model. Không công khai prompt/suy nghĩ nội bộ/API key; thời gian bước cha có thể gồm bước con nên không cộng mọi dòng.”

**Công nghệ và vai trò:** Python ProgressLog/Trace; API tiến trình; React ExecutionLog; JSON.

**Output:** Bảng Tiến trình xử lý, log JSON tải được và Trace. Đây là dữ liệu quan sát, không là phép chứng minh kết luận luật đúng.

**Đối chiếu code:** `src/vn_labor_online/demo_progress.py; api.py:progress; frontend ExecutionLog.jsx`

## Các điểm không nên trình bày sai

- Không mô tả FastAPI là mô hình AI. FastAPI là lớp API; Gemini/Qwen mới là model/provider khi được chọn.

- BGE-M3 dùng tạo embedding truy vấn, FAISS tìm vector; BGE reranker chấm lại cặp query–nguồn. Ba phần có vai trò khác nhau.

- RRF hợp nhất thứ hạng, không tự xác minh hiệu lực hay tính đúng pháp luật. Auditor và hậu kiểm mới xử lý các tiêu chí đó.

- Rule/Fact/Ontology xuất hiện trong artifact không chứng minh mọi tầng đã được duyệt trong từng câu. Xem graph_round, đường đi và log thật.

- Neo4j là thành phần xây/lưu/kiểm đồ thị của hệ thống, nhưng đường ONLINE được xem ở đây đọc đồ thị JSONL vào bộ nhớ; không gắn Cypher vào mỗi mũi tên truy xuất.

- SUFFICIENT là đủ theo kế hoạch/kiểm tra hiện có. legal_status có thể vẫn PROVISIONAL do nguồn, hiệu lực từng điều khoản hoặc Gold chưa được người chuyên môn duyệt.

- Lỗi reviewer hoặc RPM là lỗi kỹ thuật/công suất dịch vụ; không phải bằng chứng rằng corpus không có điều luật trả lời.

- Sơ đồ không bao gồm chạy OCR, tạo vector tài liệu hay chạy Leiden lúc người dùng hỏi. Đó là công việc OFFLINE hoặc chỉ mục đã xây trước.

- Không đọc cứng tên/phiên bản Gemini hoặc Qwen từ sơ đồ thành cấu hình live. Dùng /ready và nhật ký model_call để xác nhận provider/model thực sự.

## Lưu ý về log mới và bản triển khai

Bảng execution-steps-v1 giúp đối chiếu sơ đồ với bước thực sự chạy. Nếu Kaggle chưa cập nhật code log thì cần commit/push, cập nhật và khởi động lại backend; sơ đồ và lời thoại không thay đổi cấu hình hay thuật toán. Không cần rebuild OFFLINE để dùng các tệp tài liệu này.

Kết quả và tốc độ phải dựa trên lượt đo thực tế. Sơ đồ không gán số giây cố định, không cam kết mọi bước đều dùng GPU và không khẳng định mọi câu đã qua Gemini reviewer.
