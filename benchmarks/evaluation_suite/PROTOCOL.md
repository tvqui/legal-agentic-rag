# Giao thức đo đã chốt — Pháp Điển AI

**Phiên bản:** `labor-evaluation-v2-20261028`. Giữ cấu trúc này cho các lần cập nhật; mỗi lần tạo run mới có commit, SHA corpus/Gold, model revisions, settings, dự đoán và lỗi. Không sửa số liệu run cũ.

## 1. Kết luận khi đối chiếu hai báo cáo

Bảng bạn cung cấp đủ tốt để bắt đầu so sánh **truy xuất**, nhưng chưa đủ đánh giá toàn bộ hệ thống hỏi đáp. Cần phân biệt retrieval, QA, ablation, lỗi kỹ thuật và tỷ lệ thực sự được chấm. Bảng của dự án bạn bạn cũng là một phần thực nghiệm: báo cáo còn có bảng QA, thay model và kiểm thời gian ở các mục sau, không chỉ một bảng retrieval.

Điểm đáng học là cố định corpus, lưu qrels/support spans, đo cả chất lượng lẫn context size và tách retrieval khỏi end-to-end. Tuy nhiên:

- Trong báo cáo bạn bạn, hai cấu hình fact-aware còn được cung cấp mô tả fact đã khóa, trong khi các baseline chỉ có query. Đó là thí nghiệm có điều kiện được công bố rõ, **không phải** bằng chứng mọi cải thiện chỉ do thuật toán tìm kiếm. Suite này không cấp fact Gold, qrels hay đáp án cho phương pháp khi inference.
- Fact Coverage cần nhãn fact→đoạn hỗ trợ; Evidence Precision cần biết context unit nào thực sự hỗ trợ fact. Qrels/citations hiện tại chưa thay thế các nhãn đó.
- Context tokens của báo cáo đó là ước lượng chars/4, không phải token do tokenizer đếm. Suite dùng cùng loại ước lượng và ghi rõ tên, không suy thành chi phí API chính xác.
- Bài báo LegalGraphRAG đánh giá cả retrieval, generation, reliability và ablation. Accuracy/Micro-F1 tội danh không thể bê nguyên sang QA mở lao động Việt Nam. Suite không tạo nhãn “đúng luật” bằng việc có trích dẫn.

## 2. Bảng A — truy xuất lao động, không LLM sinh câu trả lời

Sáu cấu hình: **BM25; Dense; Hybrid RRF; Hybrid + reranker; Hybrid + Graph; Hybrid + Graph + reranker.**

- Cùng câu hỏi/ngày/corpus/Gold, cùng temporal/authority policy. Không dùng exact/profile/issue/case anchors trong track này.
- BM25 và Dense mỗi kênh tối đa 30 candidates, RRF k=60; fusion tối đa 60. Bản rerank dùng BGE-reranker-v2-m3 trên pool tối đa 60, không thêm oracle labels.
- Graph ở đây là **mở rộng cấu trúc cố định**: 5 hybrid seeds đầu, 2 hop, giới hạn 50 node/150 cạnh/1.500 ms; hợp nhất và có thể rerank. Không đổi nó thành tên mơ hồ “Graph” hoặc đồng nhất với adaptive graph của production.
- **K chính = 10**; bảng phụ K = 1, 3, 5, 10, 20. Chọn trước khi xem kết quả, không chọn K có số đẹp nhất.
- Warmup và tải model không nằm trong thời gian truy xuất. Đồng bộ CUDA quanh vùng đo; scoring và ghi file không nằm trong latency retrieval. Cold start nếu cần phải đo riêng.
- Dense query dùng đúng model revision đã tạo artifact, không tự thay trọng số mới nhất rồi vẫn tìm trên index cũ. Reranker revision được pin.

| Cột chính | Ý nghĩa |
|---|---|
| unique_queries | Số câu độc lập; 85 câu × 3 lặp là 255 lượt, không phải 255 câu |
| group_recall_at_k | Số nhóm căn cứ bắt buộc được tìm thấy / số nhóm Gold |
| novel_group_precision_at_k | Số nhóm được tìm thấy lần đầu / **K cố định**; không phải precision ngữ nghĩa đã duyệt |
| group_ndcg_at_k | Gain 1 cho lần xuất hiện đầu của mỗi nhóm, 0 cho trùng/không liên quan; discount log2; chia ideal DCG |
| mrr_at_k | Nghịch đảo hạng của nhóm liên quan đầu tiên |
| all_groups_found | Tìm đủ các nhóm căn cứ đã gán nhãn; qrels chưa đầy đủ vẫn có giới hạn |
| estimated_context_tokens | ceil(tổng ký tự nguồn được trả / 4); không bao gồm toàn system prompt và không phải tokenizer tokens |
| fact_coverage / evidence_precision | Chỉ chấm khi có fact/support annotations; nếu thiếu: N/A |
| mean_ms / p95_ms | Trung bình/phân vị 95 thời gian thành công; số lỗi phải hiện riêng |
| successful_attempts / errors | Không giấu các lượt thất bại khỏi bảng |

Các ID trong một required group là căn cứ có thể thay thế nhau. Một nhóm chỉ nhận gain một lần. Không gọi group precision là Precision@k theo văn bản độc lập mà không giải thích khác biệt.

**Thống kê:** lấy trung bình theo từng câu trước khi macro-average và bootstrap 95% CI, seed 42, 2.000 lần lấy mẫu. Query là đơn vị bootstrap, không phải repeat. Paired delta dùng cùng câu thành công ở cả hai cấu hình, lưu danh sách câu bị loại. Một câu không có CI đáng tin nên CI=N/A.

## 3. Bảng B/C — QA và bỏ từng thành phần

Cấu hình: **full; without_graph; without_reranker; without_auditor; without_review**. Cùng câu hỏi, ngày, provider/model, ngân sách và cấu hình khác.

Tắt exact/profile fast paths cho tất cả biến thể để bớt bỏ qua component; bởi vậy thời gian ở track này không phải thời gian tối ưu của chatbot đang triển khai. Mỗi component chỉ được diễn giải đóng góp nếu `component_exposure` cho thấy nó đã thực sự được dùng.

- `without_auditor` bỏ applicability Auditor trong worker, giữ kiểm nguồn/thời gian; quyết định mang UNRESOLVED/EXPERIMENT_AUDITOR_DISABLED, không giả PASS. Các gate còn lại có thể từ chối vì component bị bỏ. Đây là tác động hệ thống khi bỏ component, không phải cam kết một baseline “bỏ kiểm mà vẫn luôn sinh kết luận”.
- `without_review` bỏ **semantic reviewer**, giữ kiểm nguồn/ID/câu chữ/completeness. Không được gọi là bỏ mọi cơ chế kiểm chứng.
- Chia query thành block 10 câu và xoay thứ tự cấu hình giữa các block. Chỉ giữ một pipeline tại một thời điểm để tránh nhân RAM/VRAM.
- Warm BM25/Dense/reranker trước vùng đo; model initialization được loại khỏi QA latency. Cuộc gọi suy luận, chờ quota và logic trong request được tính; AI judge độc lập không tính.
- **Tạo xong các câu trả lời trước, chấm AI sau.** Đầu ra đã tạo được lưu ngay. Không để judge dùng quota trước các biến thể chưa được chạy.
- Gặp 429/hết quota hoặc lỗi cấu hình provider: dừng lưu tiến độ, không bắn tiếp vài trăm request lỗi. Resume chỉ chạy các lượt lỗi/chưa chạy; không chạy lại câu đã trả lời một phần/từ chối để chọn câu đẹp hơn.

**Bảng B — chất lượng:** AI correctness/completeness/evidence support (điểm mô hình 0–1), số được chấm/số dự kiến, citation-group recall, task answered rate. Các proxy máy không được đổi tên thành độ chính xác pháp lý.

**Bảng C — độ ổn định/chi phí:** số câu/lượt có nội dung, lỗi/chưa chạy, trạng thái, tỷ lệ kỹ thuật thành công, thời gian trung bình/p95 và thời gian riêng câu có nội dung. Cấu hình trả lời được ít câu không được coi là nhanh hơn chỉ vì từ chối nhanh.

Để đối chiếu AI score, đọc **`ablation/common_judged_comparison.json`**: cùng giao của các (query, repeat) được chấm thành công cho tất cả biến thể. Xem paired delta/CI full-minus-ablation và số câu chung. Nếu chỉ còn 1 câu chung, không kết luận phương pháp thắng. Không cho judge lỗi điểm 0 hoặc mặc định điểm 1. Judge cùng họ model với Researcher/reviewer có nguy cơ thiên lệch; cần human review hoặc judge khác khi công bố.

**Độ đúng do người đánh giá, groundedness thực sự và temporal accuracy** cần nhãn đã duyệt và quy tắc chấm rõ, chưa tự có từ 100 DRAFT. Không tự điền các tỷ lệ đó từ citation audit hay ngày nằm trong metadata chưa duyệt. Bộ Gold hiện chỉ có một VBHN, thiếu đại diện lịch sử, đa yêu cầu, đối thoại và bản án; khi mở rộng đánh giá phải bổ sung các nhóm này, giữ tập test độc lập khỏi tuning.

## 4. Fact Coverage / Evidence Precision có thể bổ sung thế nào?

Sau `prepare`, suite xuất `evidence_annotations_template.jsonl`. Đó là template, **không phải nhãn đã hoàn tất**. Mỗi query cần:

```json
{"id":"QUERY_ID","corpus_fingerprint":"FINGERPRINT_CUA_RUN","review_status":"DRAFT","reviewer":null,"reviewed_at":null,"facts":[{"fact_id":"f1","description":"Yêu cầu pháp lý nguyên tử cần được chứng minh","supports":[{"unit_id":"ID_NGUON_THAT","quote":"Nguyên văn liên tục thực sự nằm trong nguồn"}]}]}
```

Người duyệt xác định fact và đoạn hỗ trợ; câu trả lời của model không được dùng để tự tạo Gold. Quote được đối chiếu đúng unit, chuẩn hóa Unicode/khoảng trắng, không thay số/từ/phủ định. Mỗi fact có thể có nhiều support thay thế. Fact covered khi ít nhất một support đúng unit+quote nằm trong context trả về. Evidence Precision = số context units hỗ trợ ít nhất một fact / số context units. Nó không thay kiểm logic chuyên môn về quan hệ fact→support.

Điền file JSONL, đặt `evidence_annotations` trong settings trước run mới. Suite kiểm build, quote, ID và reviewer/date nếu APPROVED. Sai build phải duyệt/ghi lại, không tự migrate. Annotations chỉ đi vào scoring sau retrieval, không vào query/reranker/agent. Nếu chỉ annotate một phần, phải báo số câu có annotations, không trình bày trung bình subset như kết quả toàn bộ 85 câu.

## 5. D/E — bộ ngoài, tách biệt với labour Gold

**Zalo:** corpus 61.425 đoạn giữ đầy đủ, qrels test; standard chọn 100 query theo ID cố định, limit=null để đo toàn test. BM25/Dense/Hybrid, Recall/Precision/MRR/nDCG chuẩn binary qrels, cùng K; không dựng graph giả cho corpus chưa có legal graph. Tăng sample query không được thu nhỏ corpus để tăng điểm. Có multi-K và CI, cache vectors theo hash/revision, resume embedding. Kể cả smoke vẫn phải index toàn corpus lần đầu nên không rẻ như 10 query.

**VLSP:** dùng Public-Test/`syllogism_questions`, split HF tên `train` (144 câu), lọc lao động bằng keyword. Kiểm tra ngày 28/10 chọn được **13 câu** đủ điều kiện bộ lọc; standard limit 50 vẫn chỉ có 13, không tạo thêm/nhân bản. Đây là bộ nhỏ và lọc tự động, cần rà domain/ngày của từng câu. Không dùng toàn câu ngoài miền rồi coi hệ thống lao động kém.

Đây là **VLSP QA thích nghi** với RAG/provider của dự án và ngày giả định 15/07/2025; không phải giao thức/bảng xếp hạng chính thức. Không gộp điểm Zalo/VLSP với labour thành một accuracy chung. Hai revision đã đọc thực tế được pin trong settings.

## 6. Những lỗi đã xác minh và sửa

- Cả Zalo/VLSP cũ lỗi tại `dict(info.card_data or {})`: đối tượng DatasetCardData không phải mapping thông thường. Dùng `to_dict()` và kiểm schema thực tế. Đã tải/chuẩn bị được cả hai nguồn thật sau sửa; chưa chạy Dense/QA ngoài bằng GPU/LLM ở máy local.
- Ablation cũ: 249 lỗi ProviderRateLimited ở bốn biến thể, 1 RequestStopped ở full. Judge chỉ chấm lần lượt 98/28/0/1/1 câu. Điểm “1.0” của một câu không chứng minh bản bỏ review tốt nhất. Không tái sử dụng bảng này làm đối chứng cuối kỳ.
- Thêm deferred judge, dừng quota, resume từng lượt, đóng băng effective provider/config và model revisions, bảng giao các câu được chấm chung, CI theo query, nhiều K, context/annotation metrics có điều kiện và báo trạng thái chạy.
- Giữ production guards nguyên vẹn; mọi can thiệp ablation chỉ trong tiến trình đo. Không cần rebuild OFFLINE chỉ để thay bộ đo.

## 7. Quy trình tái sử dụng

1. Giữ nguyên cấu trúc bảng/chỉ số/K/selection/model settings khi so phiên bản. Đổi một điều kiện lớn thì ghi một protocol/config mới, không ghép điểm.
2. OFFLINE mới: thay Dataset Input, pin kiểm compatibility, migrate qrels theo đúng nguồn/text rồi duyệt lại. ONLINE mới: push code, notebook lấy origin/main, tạo run mới. Lưu source hashes vì commit không phản ánh các sửa chưa commit.
3. Chạy smoke để kiểm công cụ; standard để đo đủ tập đã chọn. Không tự gọi DRAFT thành Gold chuyên gia.
4. Khi quota ngắt, tải ZIP có tiến độ. Resume v2 yêu cầu cùng code/data/Gold/effective model/settings. Không dùng resume để trộn bản sửa mới hoặc model khác với kết quả cũ.
5. Đưa bảng kết quả kèm N câu, nhãn, K, phạm vi, lỗi, CI và giới hạn vào báo cáo; lưu JSONL/traces để truy lại.

Nguồn phương pháp: [LegalGraphRAG, ACL 2026](https://aclanthology.org/2026.acl-long.1738/), [VLSP LegalSLM](https://vlsp.org.vn/node/184), [Public-Test schema](https://huggingface.co/datasets/VLSP2025-LegalSML/Public-Test), [Zalo dataset card](https://huggingface.co/datasets/minhnguyent546/zalo-ai-legal-text-retrieval-2021). Báo cáo bạn cung cấp: mục 4.3, trang PDF 72–77 và các phần QA/temporal sau đó. Không so trực tiếp điểm giữa hai corpus/giao thức.

## 8. Đánh giá do người kiểm tra (tùy chọn nhưng cần cho tuyên bố pháp lý)

Khi đã có responses, suite xuất `human_review_template.csv`. Sao chép thành file riêng trước khi điền. Dùng thang binary đã chốt: `correct`, `complete`, `supported` là 0 hoặc 1; `temporal_correct` để trống nếu không chấm thời gian, nếu chấm thì 0/1. Ghi reviewer, ngày và lý do. Căn cứ đúng nhưng diễn giải sai phải chấm đúng theo tiêu chí, không dựa vào tên cấu hình. Nên chọn trước một tập câu chung cho mọi biến thể và che tên cấu hình khi có thể; không chọn chỉ các câu tốt.

```powershell
python benchmarks/evaluation_suite/human_review.py --run DUONG_DAN_RUN --reviews human_review_completed.csv
```

Tool đối chiếu ID/variant/repeat và SHA câu trả lời, không cho áp điểm của câu cũ vào câu mới. Xuất `human_review_summary.json`: số đã duyệt, correctness/completeness/support, correct-and-supported và temporal accuracy với mẫu số thời gian riêng. Dòng chưa chấm để N/A, không mặc định đúng. Việc duyệt câu trả lời không tự phê duyệt Gold, nguồn hay hiệu lực corpus.
