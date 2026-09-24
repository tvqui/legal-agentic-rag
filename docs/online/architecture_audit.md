# Kiểm tra kiến trúc ONLINE theo đặc tả 26 phần

Ngày kiểm tra: 2026-09-24. Phạm vi: mã nguồn hiện tại và OFFLINE build V8.1 có build ID
`7b33c8206124e32d423ddfc02adbf58ad26cce68e8ac0154329d51b5dd667d38`.

## Kết luận

Luồng ONLINE trong đặc tả đã được triển khai đầy đủ ở mức kỹ thuật để chạy demo có kiểm
soát: từ query intake, fact gate, evidence plan, hybrid retrieval, temporal/authority
filter, adaptive graph loop, hai tầng audit, Verified Evidence Pack, adjudication, reference
audit đến output và research trace. Hệ thống vẫn chưa được coi là hoàn tất về chuyên môn
pháp lý hoặc nghiên cứu vì Source Catalog, provision-level temporal metadata và Gold chưa
được người có chuyên môn phê duyệt.

## Đối chiếu từng phần

| # | Yêu cầu | Thiếu hoặc sai trước khi sửa | Trạng thái sau sửa |
|---:|---|---|---|
| 1 | Chỉ đọc OFFLINE build đóng băng | Có kiểm build ID nhưng chưa kiểm đủ Source Catalog và hai fingerprint index | PASS: kiểm SHA ZIP, CRC, build graph/Aura, retrieval fingerprint, Dense fingerprint, thứ tự Dense/BM25, endpoint graph và file ID trong Source Catalog; giải nén chống path traversal/symlink/zip bomb và ghi cache atomically |
| 2 | Luồng end-to-end | Luồng cũ đi thẳng từ retrieval sang answer | PASS: pipeline theo đúng các stage và ghi trace từng stage |
| 3 | Query intake và safety | Chưa dùng facts/context; safety boundary chưa rõ | PASS: giữ raw query, tạo normalized query, nhận `facts`, dùng conversation context; evidence được đánh dấu là dữ liệu và LLM boundary cô lập instruction |
| 4 | Legal Query Analyzer | Facts gần như rỗng; tháng/ngày có thể nhầm với số hiệu văn bản | PASS: trích issue, reference, ngày/tháng/năm, notice days, contract/protected status, intent và độ chính xác mốc thời gian; query chỉ có tháng/năm được giữ thành khoảng thay vì giả định ngày đầu kỳ |
| 5 | Fact Completeness Gate | Câu hỏi đánh giá chấm dứt vẫn retrieve khi thiếu facts | PASS: trả `NEED_MORE_FACTS` trước retrieval; kiểm ngày, loại hợp đồng, lý do, thời gian báo trước và tình trạng được bảo vệ; request không thể tự khai `human_reviewed` hay bypass gate |
| 6 | Freshness | Chỉ có cảnh báo theo từ khóa, không có snapshot | PASS có điều kiện: cấu hình `corpus_snapshot_as_of=2026-09-15`; câu hỏi hiện hành sau snapshot trả `CORPUS_MAY_BE_STALE`. Chưa chạy Source Resolver trên request path |
| 7 | Evidence Planner | Slot cố định, không theo issue | PASS: mandatory/conditional slot theo issue, intent và route |
| 8 | DIRECT/STANDARD/COMPLEX | Ngày quá khứ từng ép mọi câu hỏi sang COMPLEX | PASS: exact citation đi DIRECT; một issue đi STANDARD; historical legality/multi-issue/change đi COMPLEX |
| 9 | Hybrid seed retrieval | Thiếu LegalIssue anchor và kênh án lệ riêng | PASS: Exact + BM25 + BGE-M3/FAISS + LegalIssue anchor + dedicated case-law channel + RRF |
| 10 | Temporal filter | Query có ngày loại gần hết evidence hoặc dùng document date như provision date mà không báo | PASS có điều kiện: strict mode yêu cầu provision interval đã review; provisional mode chỉ cho document fallback và bắt buộc gắn limitation/warning; query tháng/năm dùng interval-overlap, yêu cầu ngày chính xác nếu cắt qua ranh giới phiên bản và không nhầm hai phiên bản kế tiếp thành xung đột; lọc lại sau graph |
| 11 | Authority filter | Authority chưa tham gia rerank đầy đủ | PASS có điều kiện: authority, binding, official status và relevance cùng tham gia; catalog chưa review không được coi là official verified |
| 12 | Adaptive typed graph | Trước đây chỉ là một lượt mở rộng chung | PASS: gap quyết định loại cạnh, lặp từng round và tính lại coverage; graph export đóng băng cùng build thay cho truy vấn Aura trực tiếp |
| 13 | Graph scoring | Thiếu temporal/gap/cost, novelty và redundancy | PASS: score có legal importance, relevance, authority, temporal, gap, novelty, redundancy, hub penalty và traversal cost; weight cấu hình được |
| 14 | Evidence Coverage State | Trạng thái chưa bám evidence plan | PASS: mỗi slot có status/evidence IDs; coverage và gaps được tính lại sau mỗi round |
| 15 | Evidence Gap Controller | Graph mở rộng dù không biết thiếu gì | PASS: chỉ đi các relation phục vụ gap hiện hành |
| 16 | Stopping Policy | Chưa có đủ stop reasons và conflict check | PASS: `SUFFICIENT`, `PARTIAL_ALLOWED`, `NEED_MORE_FACTS`, `INSUFFICIENT_EVIDENCE`, `CONFLICTING_EVIDENCE`; có budget nodes/edges/hops/rounds và một wall-clock budget chung cho toàn bộ graph loop; nhánh insufficient/thiếu ngày abstain và không xuất claims/citations như một kết luận |
| 17 | Reranking | Chủ yếu dựa retrieval score | PASS: relevance + authority + temporal, loại trùng provision identity và giới hạn evidence theo route |
| 18 | Evidence compression | Generator nhận toàn văn candidate | PASS: chỉ pack đoạn phù hợp, giữ câu chứa negation, exception, condition và reference |
| 19 | Deterministic audit | Chưa kiểm catalog, source span và graph structure | PASS: kiểm unit/document/file ID, URL, source span khớp unit gốc, Article/Clause/Point, interval kể cả khi query không có ngày và graph structure; evidence fail bị loại |
| 20 | Legal Applicability Auditor | Chỉ có lexical filter, chưa có structured boundary | PASS kỹ thuật: output Pydantic có relevant/support/conditions/exception/status; mặc định deterministic và fail-closed với điều kiện/ngoại lệ chưa thể suy ra; request bị cấm truyền các decision flag để tự phê duyệt; tùy chọn Ollama/HTTP structured fail-closed. Chưa được Gold pháp lý đánh giá |
| 21 | Verified Evidence Pack | Không có object riêng | PASS: generator chỉ nhận pack gồm facts, date, coverage và evidence đã audit |
| 22 | Adjudicator | Output chỉ là chuỗi và citation rời | PASS: tạo claims gắn evidence IDs, applicable versions, assumptions và limitations; có deterministic mode và structured Ollama/HTTP mode. Provider chỉ nhận Verified Evidence Pack, không thể thêm evidence/version/assumption/limitation ngoài pack; prose công khai được dựng lại từ structured claims rồi mới qua Reference Audit; lỗi provider fail-closed về extractive fallback |
| 23 | Reference Audit | Chỉ kiểm marker cơ bản | PASS: kiểm ID, URL, số hiệu, Điều/Khoản/Điểm, version, source span và claim support; thử một lần sửa giảm thiểu có kiểm soát, sau đó abstain nếu vẫn lỗi |
| 24 | Structured final output | Thiếu claims, versions, assumptions và trace ID riêng | PASS: `AnswerResponse` đã có đầy đủ các trường trong đặc tả và source spans |
| 25 | Research trace | Thiếu seed count, per-round gaps, edge types và stop reason | PASS: trace có route, seeds, rounds, nodes/edges, critical edges, gaps từng round, stop reason, verified count, reference audit và timing |
| 26 | Đánh giá/ablation | Chỉ có recall/latency/nodes/rounds | PASS về công cụ: runner có citation precision/recall, wrong-version rate, abstention, fabricated citations, kích thước context sau compression, critical edges, stop reasons, p50/p95 latency và graph cost; Gold phải có approval hợp lệ và đúng evaluation fingerprint mới được ghi `OFFICIAL`. Kết quả hiện vẫn `PROVISIONAL_DRAFT_GOLD` |

## Những việc còn thiếu không thể sửa đúng chỉ bằng code

1. **Source Catalog:** build hiện có 95 record nhưng chưa có record nào được reviewer pháp lý
   xác nhận. URL có thể tồn tại nhưng chưa được coi là nguồn chính thức đã kiểm chứng.
2. **Temporal:** 18.449 provision versions chưa được review ở cấp điều/khoản/điểm. Vì vậy
   dated query chỉ có thể trả `PARTIAL_ALLOWED` bằng document-level fallback trong chế độ
   demo; strict mode sẽ abstain.
3. **Gold:** chưa có Gold record được con người phê duyệt. Mọi metric ablation chỉ là số liệu
   nháp, không phải kết quả nghiên cứu chính thức.
4. **OCR/structure:** bản gốc 45/2019/QH14 trong build hiện tại có trường hợp ký hiệu `c)`
   của khoản 1 Điều 113 bị OCR mất, làm phần “16 ngày” dính vào unit điểm b. Bản hợp nhất
   tách đúng điểm c. Cần reviewer quyết định và rebuild OFFLINE; ONLINE giữ source span và
   không tự sửa nội dung pháp luật.
5. **Freshness:** snapshot là 2026-09-15, sớm hơn ngày chạy 2026-09-23. Câu hỏi “hiện nay”
   phải giữ cảnh báo cho tới khi Source Resolver cập nhật và build mới được đóng băng.
6. **Applicability/Adjudication model:** hai boundary LLM đã có schema và fail-closed
   nhưng chưa được đánh giá trên Gold đã duyệt. Mặc định deterministic là lựa chọn an toàn hiện tại.
7. **Judicial corpus:** mới có 24 case, nên recall cho câu hỏi án lệ/bản án vẫn bị giới hạn
   bởi độ phủ dữ liệu.

## Mức sẵn sàng

- `ONLINE_CODE_COMPLETE_FOR_SPEC = true`
- `OFFLINE_BUILD_COMPATIBLE = true`
- `READY_FOR_PROVISIONAL_DEMO = true`
- `READY_FOR_HUMAN_REVIEWED_LEGAL_USE = false`
- `READY_FOR_OFFICIAL_RESEARCH_REPORT = false`

Không nên thay ba trạng thái cuối bằng PASS giả. Khi review hoàn tất, cần merge quyết định,
rebuild OFFLINE, cập nhật fingerprint trong `config/online*.yaml`, chạy toàn bộ test và chạy
ablation bằng Gold đã APPROVED.
