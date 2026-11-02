# Pháp Điển AI khác LegalGraphRAG ở đâu? — đối chiếu ngày 28/10/2026

## 1. Phạm vi và cách hiểu kết quả so sánh

Đối chiếu PDF người dùng cung cấp `legalraggraph_CN.pdf` (30 trang), đặc biệt mục 2, 4.2–4.3, 5.1 và Phụ lục B.1–B.2, với source hiện tại tại `D:/data_thô/legal-agentic-rag`. Tình trạng dữ liệu lấy từ ZIP result_28-10 đã kiểm tra độc lập. Bài báo mô tả phương pháp nghiên cứu; không thể suy từ việc một tính năng không được mô tả rằng mọi phiên bản code của tác giả đều không có tính năng đó.

“Khác/thêm” dưới đây nghĩa là thích nghi hoặc mở rộng so với phương pháp được trình bày trong bài báo, **không đồng nghĩa phát minh thuật toán mới, lần đầu xuất hiện trong nghiên cứu, hoặc đã chứng minh tốt hơn**. Lợi ích nêu là mục đích/cơ chế kỹ thuật hợp lý; muốn kết luận tăng độ chính xác hay giảm thời gian phải có đối chứng trên cùng corpus, Gold và điều kiện chạy.

## 2. Tổng thể: kế thừa bộ khung, thay bài toán và bổ sung kiểm soát

| Khía cạnh | Bài báo LegalGraphRAG | Pháp Điển AI | Ý nghĩa |
|---|---|---|---|
| Bài toán | Từ tình tiết hình sự và bị cáo để dự đoán tội danh, điều luật; có thí nghiệm hình phạt | Hỏi đáp/tra cứu/đánh giá tình huống pháp luật lao động Việt Nam, nhiều chủ thể, nhiều yêu cầu và câu hỏi nối tiếp | Chuyển từ đầu ra phán quyết sang hỗ trợ giải thích quyền, nghĩa vụ, điều kiện và thủ tục |
| Kiến trúc kế thừa | OFFLINE HierarGraph; ONLINE Researcher → Auditor → Adjudicator | Giữ bộ khung; thêm quản lý nguồn, thời gian, tasks, ngữ cảnh, vòng bổ sung evidence, hậu kiểm và vận hành | Đây là phát triển dựa trên bài báo, không phải tự đề xuất lại ba agent |
| Đầu ra | Judgment có citations từ tập chứng cứ đã kiểm | Câu trả lời, claims, citations, từng AnswerPart, phiên bản áp dụng, cảnh báo, trạng thái đủ/thiếu căn cứ và trace | Người dùng có thể phân biệt câu đã giải quyết, câu còn điều kiện và lỗi dịch vụ |
| Mô hình suy luận | Qwen3-8B mặc định; GPT-4o-mini/DeepSeek là các backbone thí nghiệm thay thế | Qwen/Ollama, HTTP-compatible; hỗ trợ Gemini cho Researcher và reviewer theo cấu hình; kết hợp các rule profile xác định | Có thể phân vai và đổi nhà cung cấp; thêm nhà cung cấp không tự tăng chất lượng |

### Những thành phần không nên nhận là điểm mới

Ba đồ thị Fact/Ontology/Rule; ba agent; checklist điều kiện; xác minh và cắt evidence không áp dụng; semantic retrieval, community retrieval; BGE-M3, k-NN, Leiden; suy luận từ nguồn và trích dẫn đều có trong nền tảng bài báo. Bài báo đã hướng đến traceable/verified evidence. Phần mở rộng của dự án là cụ thể hóa bằng các kiểm tra máy, quy tắc và quy trình phù hợp với miền lao động Việt Nam.

## 3. HierarGraph: khác ở mô hình dữ liệu và cách quản lý tri thức

| # | Phần khác/thêm | Công nghệ/cách thực hiện | Lợi ích và giới hạn |
|---|---|---|---|
| G1 | **Fact Graph chuyển từ tội danh sang tranh chấp lao động** | Parser Python tách facts/reasoning/decision; node Judgment, CassationDecision, Precedent; DERIVED_FROM tới tài liệu gốc; nối trích dẫn sang quy phạm | Giữ bối cảnh tranh chấp, nhận định, quyết định; tránh ép quan hệ lao động thành tội phạm. Quan hệ case → article là kế thừa, không phải mới |
| G2 | **Ontology lao động thay bốn chiều hình sự** | OFFLINE có PARTY_PROFILE, EMPLOYMENT_RELATIONSHIP, EMPLOYMENT_EVENT, PROTECTED_STATUS, PROCEDURE, CLAIM_OR_REMEDY, OUTCOME. ONLINE có sáu nhóm parties/relationship/events/protected statuses/procedures/remedies | Phân biệt người lao động/người sử dụng lao động, quan hệ hợp đồng, sự kiện, bảo vệ đặc biệt, thủ tục và biện pháp khắc phục. Kết quả bản án lịch sử không được coi là sự thật của tình huống mới |
| G3 | **Taxonomy vấn đề có nhiều mức** | LegalIssue, subissues, topic routing; Python/regex và crosswalk; ví dụ TERMINATION.EMPLOYEE_UNILATERAL so với EMPLOYER_UNILATERAL | Lập kế hoạch lấy đúng nhóm căn cứ cho từng vấn đề; giảm lẫn quyền của hai chủ thể. Phụ thuộc mức bao phủ và tính đúng của taxonomy |
| G4 | **Từ vựng OWL dùng có chọn lọc** | RDF/XML/OWL file, audit cấu trúc, hash, ánh xạ issue/đồng nghĩa bằng `ontology_vocabulary.py` | Mở rộng nhãn dùng phân loại OFFLINE. **Không chạy OWL reasoner**, không coi rule mẫu hay toàn bộ ABox là luật có hiệu lực |
| G5 | **Rule Graph chi tiết đến Điều/Khoản/Điểm và phụ lục** | LegalInstrument, DocumentVersion, Chapter, Section, Article, Clause, Point; PART_OF, NEXT; tách Annex/Form/AttachedRegulation | Chỉ đúng đơn vị mà câu hỏi cần, hạn chế lẫn nội dung văn bản ban hành với văn bản kèm theo. Khác với cách trình bày article/interpretation của bài báo |
| G6 | **Định danh và phiên bản điều khoản** | ProvisionIdentity, HAS_PROVISION_VERSION, valid_from/valid_to; AMENDS, REPEALS, REPLACES, IMPLEMENTS, REFERENCES | Có nơi biểu diễn phiên bản và dẫn chiếu để truy vấn theo ngày. Có schema không đồng nghĩa dữ liệu lịch sử/interval đã duyệt đủ |
| G7 | **Phân biệt văn bản gốc và văn bản hợp nhất** | DocumentVersion/ConsolidatedDocumentVersion, instrument_number và provenance | Tránh xem ngày hợp nhất như ngày mọi quy phạm bắt đầu có hiệu lực; cần giữ lịch sử thay đổi và căn cứ pháp lý gốc |
| G8 | **Tách chứng cứ nguồn khỏi thông tin suy ra** | Graph thêm nhãn lớp `document`, `derived` ngoài `fact`, `ontology`, `rule`; DiagnosticItem có evidence span/provenance | Checklist/tóm tắt không bị trình bày như nguyên văn luật. Không phải năm database hay năm graph độc lập bắt buộc |

Phân lớp trong code là cách tổ chức nội bộ; các cạnh có thể đi xuyên lớp. Article nằm trong rule layer của dự án vẫn có thể được bản án fact layer dẫn qua CITES. Bài báo cũng có article trong cấu trúc Fact Graph; không nên mô tả rằng bài báo chỉ có bản án trong Fact Graph.

## 4. OFFLINE: thêm kiểm soát chất lượng và khả năng tái lập

| # | Phần khác/thêm | Công nghệ/cách thực hiện | Lợi ích và giới hạn |
|---|---|---|---|
| O1 | **Luồng xử lý PDF/DOC/DOCX/HTML thực tế** | PyMuPDF native text; Docling + EasyOCR chọn lọc; python-docx, BeautifulSoup; xử lý trang xoay/trang ít nội dung | Đưa hồ sơ quét và nhiều định dạng vào corpus, thay vì mặc định đầu vào luôn là text sạch. Không tự bảo đảm OCR đúng hoàn toàn |
| O2 | **Kiểm chất lượng từng trang** | cleaned_chars, native/OCR agreement, ký tự lặp/lạ, page quality, ảnh đối chiếu, hàng đợi human review; chú thích giữ tọa độ riêng khi đủ bằng chứng | Phát hiện nguy cơ mất/sai chữ/số và lẫn chú thích; giữ việc sửa có thể kiểm lại. REVIEW_REQUIRED không tự đổi thành PASS |
| O3 | **Chứng cứ đến vị trí cụ thể** | SHA-256, document/page/segment IDs, char spans; kiểm nguyên văn có nằm trong nguồn và hierarchy provenance | Truy ngược từng điều khoản/checklist/feature, phát hiện AI trích sai; đây là bổ sung kiểm tra máy cụ thể cho mục tiêu traceability vốn đã có trong bài báo |
| O4 | **AI enrichment có đối soát và tiếp tục phần thiếu** | JSON Schema, source-accounting theo excerpt/quote/ID; cache theo nguồn/cấu hình, chia chunks, continuation, bounded retries, stage budget, circuit breaker, fallback | Giữ phần hợp lệ khi job dài bị gián đoạn; không nhận quote lệch nguồn. Chạy xong tiến trình vẫn có thể AI_DEGRADED |
| O5 | **Quản lý link nguồn có lịch sử** | YAML SourceCatalog, Excel/openpyxl nhập có baseline/SHA và backup; kiểm URL qua registry/catalog/graph/retrieval units; công cụ source resolver | Tránh đổi link một nơi nhưng citation vẫn dùng link cũ. Link khớp cấu hình chưa xác nhận đúng toàn văn/hiệu lực hoặc trang luôn truy cập được |
| O6 | **Build đóng gói và kiểm tương thích** | JSONL + BM25/FAISS + Neo4j; ZIP, SHA, build/fingerprints; technical checkpoint/recovery; validation riêng kỹ thuật/pháp lý | Dùng một bản dữ liệu đã chốt cho ONLINE, phát hiện trộn index/graph khác build. Là cải tiến triển khai, không phải thuật toán suy luận mới |
| O7 | **Đầu nối corpus bên ngoài có vùng chờ** | Hugging Face/Parquet streaming, SQLite metadata/content/relationships, revision pin, lọc/dedup và review | Có đường mở rộng dữ liệu có kiểm soát. Bộ result_28-10 vẫn cùng 95 file nguồn so với result_14-10; không được nói đã nhập toàn bộ hai dataset Hugging Face |

## 5. ONLINE và các agent: khác ở điều khiển và kiểm chứng

### Researcher và lớp lập kế hoạch

| # | Khác/thêm | Công nghệ/cách thực hiện | Lợi ích |
|---|---|---|---|
| R1 | **Lọc phạm vi, loại yêu cầu, dữ kiện và ngày** | Analyzer Python/regex/taxonomy, Pydantic QueryAnalysis, FactCandidate có exact quote + offsets; candidate LLM chỉ dùng khi app kiểm được | Hạn chế câu hỏi ngoài lao động, giả định thiếu căn cứ và chọn nhầm chế độ pháp luật |
| R2 | **Tách nhiều yêu cầu thành task** | AnswerTask, request_quote, dependency DAG, query theo task, EvidencePlan/LegalLocator/mandatory slots | Câu hỏi hai vấn đề được theo dõi hai nhiệm vụ; không coi trả lời một ý là hoàn thành cả câu. Quy tắc/profile vẫn cần mở rộng cho các vấn đề chưa bao phủ |
| R3 | **Ngữ cảnh nhiều lượt và hỏi lại** | Context resolver chỉ lấy dữ kiện từ user turns; lịch sử browser; phát hiện thay tình huống; missing-fact gate và đáp có điều kiện | Giữ loại hợp đồng hoặc nhóm công việc đã cung cấp, hỗ trợ câu nối tiếp. Không lấy câu AI đã trả lời làm sự thật, không phải long-term memory tự học |
| R4 | **Gọi LLM thích nghi** | Researcher.execution_path, exact/profile fast path; provider Ollama/HTTP/Gemini; schema validation | Câu định vị rõ không bắt buộc gọi Researcher LLM; giảm số lần gọi và chi phí. Không có nghĩa mọi câu đều nhanh hoặc luôn dùng đủ ba LLM |

### Retriever và vòng bổ sung căn cứ

| # | Khác/thêm | Công nghệ/cách thực hiện | Lợi ích |
|---|---|---|---|
| T1 | **Tìm trực tiếp quy phạm và hợp nhất nhiều kênh** | Exact hierarchy lookup, profile/policy/issue anchors, BM25S, BGE-M3 + FAISS, RRF, tùy câu có case/community channel | Giữ khả năng tìm chính xác số hiệu và bao phủ cách nói khác nhau; ít phụ thuộc bản án tương tự hơn cơ chế charge-anchored của bài báo |
| T2 | **Chấm lại độ liên quan** | BGE-reranker-v2-m3, kết hợp temporal/authority filters và giữ mandatory anchors | Giảm nguồn đúng từ khóa nhưng sai mục đích, vẫn giữ căn cứ bắt buộc. Đây là mục tiêu, phải đo chứ không mặc định tốt hơn |
| T3 | **Thiếu căn cứ thì duyệt graph theo phần thiếu** | Coverage/gaps, priority queue, typed/directed edges, node/edge/hop/time budgets, novelty/hub/redundancy scoring, audit lại mỗi vòng | Tìm ngoại lệ, quy định hướng dẫn hoặc hậu quả còn thiếu; có lý do dừng. Khác vòng kiểm từng checklist: đây là vòng điều khiển lấy thêm evidence |

Bài báo đã có semantic/community/charge-anchored retrieval, nên không nhận “truy xuất nhiều kênh” hay k-NN/Leiden là sáng tạo của dự án. Khác biệt là kênh truy xuất trực tiếp quy phạm, lexical+dense fusion và điều khiển bằng evidence slots của nhiệm vụ lao động. ONLINE hiện duyệt danh sách kề từ JSONL nạp trong RAM; Neo4j lưu/kiểm graph OFFLINE, không phải mọi câu đều gửi Cypher.

### Auditor

| # | Khác/thêm | Công nghệ/cách thực hiện | Lợi ích |
|---|---|---|---|
| A1 | **Luật cứng trước LLM** | deterministic_audit về IDs/span/nguồn/phiên bản; hybrid applicability theo chủ thể, loại hợp đồng, điều kiện/ngoại lệ; LLM/schema chỉ xét phần được phép | Không để LLM phục hồi nguồn đã vi phạm kiểm tra cứng; giảm áp quy định người sử dụng lao động cho người lao động |
| A2 | **Thể hiện điều chưa biết** | audit PASS/FAIL/UNRESOLVED; điều kiện UNKNOWN/NOT_SATISFIED/NOT_APPLICABLE và trạng thái ngoại lệ riêng | Không biến thiếu dữ kiện thành “không có ngoại lệ”. Có thể giải thích có điều kiện nhưng không kết luận cá nhân hóa quá mức |
| A3 | **Kiểm thời gian và độ tin cậy độc lập** | valid intervals, query date/range, source authority review, provisional policy và document-level temporal fallback có cảnh báo | Phân biệt “đã qua kiểm tra máy” với “được chuyên gia duyệt”. Trong provisional mode có thể giữ nguồn chưa duyệt, không nên nói mọi evidence đã human-verified |

Verify-and-prune và checklist đã có trong bài báo; phần mở rộng là cấu trúc hybrid, kiểm tra xác định, trạng thái chưa biết và kiểm soát thời gian/nguồn cụ thể cho corpus lao động.

### Adjudicator và hậu kiểm

| # | Khác/thêm | Công nghệ/cách thực hiện | Lợi ích |
|---|---|---|---|
| J1 | **Sinh câu trả lời có cấu trúc và các nhánh** | VerifiedEvidencePack, Claim/evidence_ids, Pydantic/JSON Schema; LLM và deterministic profile rendering; nhánh literal excerpt | Có thể kiểm từng nhận định, trình bày riêng từng ý; câu tra cứu nguyên văn không bắt buộc paraphrase bằng LLM |
| J2 | **Kiểm nghĩa sau khi đã sinh** | answer_review: reviewer cùng provider hoặc Gemini, claim grounding, task coverage, số lần sửa có giới hạn | Kiểm câu có nguồn nhưng diễn giải sai, thiếu điều kiện, nhầm kết luận. Reviewer vẫn là mô hình, không chứng nhận đúng luật tuyệt đối; có thể tăng độ trễ hoặc lỗi quota |
| J3 | **Kiểm lại trích dẫn và câu chữ** | reference_audit đối chiếu locator/URL/ID/claim; answer_quality kiểm câu lạc đề, ký hiệu lặp, bố cục; không tự sửa nguyên văn nguồn bằng đoán chữ | Giảm citation bịa, dẫn đúng văn bản nhưng sai khoản/điểm và lỗi hiển thị; không che lỗi OCR bên dưới bằng viết lại |
| J4 | **Trạng thái trả lời và độ đủ từng ý** | AnswerPart, assessed task dependencies, PARTIAL/clarification/insufficient evidence, phân biệt lỗi dịch vụ | Không ép một câu trả lời dứt khoát khi thiếu bằng chứng; biết phần nào đã giải quyết. Đổi lại có thể từ chối nhiều hơn và cần đo cả tỷ lệ từ chối đúng/sai |

## 6. Công nghệ sản phẩm, vận hành và đánh giá

| Phần thêm | Công nghệ | Lợi ích và giới hạn |
|---|---|---|
| Giao diện hỏi đáp và xem nguồn | React, Vite, source drawer, browser history | Đọc câu trả lời, mở căn cứ và hỏi tiếp; là phần sản phẩm, không phải đóng góp thuật toán |
| API và giám sát | FastAPI, Uvicorn, Pydantic; /health, /ready, progress/cancel, request IDs, idempotent retry, cooperative deadline | Phát hiện component lỗi, giảm request chạy trùng, chủ động dừng. Cooperative cancel không dừng tức thì mọi thao tác bên ngoài |
| Log trình diễn theo bước | demo_progress + Trace JSON, timings, technology/output summary, graph paths và stop reasons | Giải thích được bước đang chạy, nguồn được lấy và lỗi ở lớp nào. Đây là dấu vết thực thi quan sát được, không phải chain-of-thought nội bộ model |
| Quản lý API LLM | google-genai/Ollama/HTTP providers, schema validation, shared-process RPM pacing/retry/cooldown | Hạn chế dồn request, báo lỗi quota và response lỗi rõ hơn; vẫn chịu giới hạn tài khoản, mạng và dịch vụ |
| Bộ đo tái sử dụng | BM25/Dense/Hybrid/Hybrid+Graph; ablations graph/reranker/Auditor/review; Zalo retrieval và VLSP QA adapters; Gold/build pin | Có công cụ kiểm tra đóng góp từng phần. Không so trực tiếp điểm retrieval với QA hoặc accuracy tội danh của bài báo |

Bài báo đã có thực nghiệm đối chứng/ablation/đánh giá retrieval và reliability. Dự án không mới ở ý tưởng “có benchmark”; khác ở thiết kế bộ đo phù hợp corpus lao động và pipeline thực tế. Lượt evaluation 23/10 chỉ có Labour retrieval COMPLETE; ablation/Zalo/VLSP ERROR nên không được đưa các điểm lỗi thành bằng chứng cải thiện. Lượt đó còn DRAFT Gold và khác build 28-10. Hybrid+Graph fixed ở lượt đó kém Hybrid, nên càng không thể khẳng định Graph luôn tăng chất lượng hoặc tốc độ.

## 7. Các giới hạn thực tế cần nói khi báo cáo

- Bản result_28-10: kỹ thuật PASS và nạp ONLINE compatible, nhưng legal-ready=false/PROVISIONAL; 84/95 tài liệu có link, 0/95 hồ sơ được quy trình source review ghi nhận đạt.
- AI complete 128/250 checklist được chọn; 0/24 bản án complete, 18 partial. Không nói Fact/Ontology đã được AI khai thác đầy đủ.
- 173 trang cần đối chiếu, 28 thay đổi pháp luật chờ duyệt, Gold chưa APPROVED. Không biến kiểm exact span thành chứng nhận nội dung/hiệu lực đúng.
- Có hỗ trợ nhiều chủ đề lao động, nhưng một phần deterministic profiles/exception chains phụ thuộc chủ đề đã mô hình hóa; không phải suy luận hình thức bao phủ toàn bộ luật Việt Nam.
- Chưa có so sánh công bằng cùng dữ liệu/giao thức với LegalGraphRAG để kết luận vượt bài báo về độ đúng hay thời gian. Các khác biệt nguồn luật, ngôn ngữ, nhãn đầu ra và metric khiến bảng điểm không thể đối chiếu trực tiếp.

## 8. Năm điểm nên nhấn mạnh trong thuyết trình

1. **Thích nghi miền lao động Việt Nam:** thay ontology và charge anchor bằng chủ thể, quan hệ, issue và quy phạm áp dụng.
2. **Quản lý quy phạm theo cấu trúc và thời gian:** cây Chương/Mục/Điều/Khoản/Điểm, phiên bản và quan hệ sửa đổi.
3. **Tập trung độ đủ theo nhiệm vụ:** tách nhiều ý, theo dõi các ô căn cứ, bổ sung truy xuất có kiểm soát.
4. **Kiểm chứng nhiều lớp:** nguồn/span → applicability → claims/coverage → citations/câu chữ, với UNKNOWN và provisional minh bạch.
5. **Tái lập và quan sát được:** build có hash, checkpoint, audit dữ liệu, trace và bộ đo riêng.

Cách trình bày đề xuất: “Pháp Điển AI kế thừa kiến trúc HierarGraph và ba agent của LegalGraphRAG, đồng thời thích nghi cho hỏi đáp luật lao động Việt Nam bằng mô hình dữ liệu có cấu trúc và phiên bản, lập kế hoạch căn cứ theo từng yêu cầu, kiểm tra điều kiện–ngoại lệ, hội thoại nhiều lượt và hậu kiểm nhận định. Các mở rộng hướng đến câu trả lời đúng, đủ và truy nguyên được; hiệu quả định lượng vẫn cần kiểm chứng bằng đối chứng và Gold đã duyệt.”

## 9. Nguồn để kiểm lại

- Bài báo PDF: trang 2–3 (bài toán), 4–6 (mô hình/ba agent), 7 (model/metric), 15–18 (Phụ lục B). “Trang” là thứ tự trang PDF, không phải số trang kỷ yếu 37455…
- OFFLINE: `graph_builder.py`, `cases.py`, `communities.py`, `legal_structure.py`, `provision_versions.py`, `ontology_vocabulary.py`, `extract.py`, `page_quality.py`, `source_accounting.py`, `source_links.py`, `external_sources.py`.
- ONLINE: `pipeline.py`, `models.py`, `researcher.py`, `taxonomy.py`, `tasks.py`, `conversation.py`, `retrieval.py`, `evidence.py`, `graph.py`, `audit.py`, `applicability.py`, `generation.py`, `profile_generation.py`, `answer_review.py`, `answer_quality.py`, `artifact_store.py`.
- Vận hành: `api.py`, `runtime.py`, `demo_progress.py`, `providers.py`, `gemini_quota.py`; `frontend/package.json`; `benchmarks/evaluation_suite`; `gold_dataset/result/comparison_tables.json`.
- Dữ liệu thực chạy: [review result_28-10](../kaggle/offline-results-review-20261028.md).

Không sửa code hay chạy benchmark/LLM trong lượt đối chiếu tài liệu này. Không đọc hoặc sao chép .env/API key. Các mô hình đang thực sự chạy phụ thuộc cấu hình và biến môi trường của phiên backend, không chỉ YAML mặc định.
