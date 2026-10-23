# Đo với Gold 100 từ đầu đến cuối

## 1. Kết quả kiểm tra bộ bạn cung cấp

Giữ nguyên `gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip`. **Không cần giải nén**;
code đọc JSONL/catalog trong ZIP, không chạy nội dung Excel và không sửa ZIP gốc.
Không dùng trực tiếp CSV/XLSX làm đầu vào cho công cụ.

Đã đối chiếu bản `result_14-10`:

| Kiểm tra | Kết quả |
|---|---:|
| Câu hỏi, không trùng ID hoặc nguyên văn | 100 |
| Có đáp án, dùng cho truy xuất | 85 |
| Cần bổ sung dữ kiện | 12 |
| Thiếu căn cứ tương lai theo corpus | 3 |
| Mã bằng chứng khác nhau | 83 |
| Mã, văn bản, Điều/Khoản/Điểm, URL và nguyên văn bằng chứng khớp corpus | 83/83 |
| Chuyên gia pháp lý đã duyệt toàn bộ Gold | Chưa |

“Khớp” chỉ chuẩn hóa Unicode/khoảng trắng; không thay số, từ, dấu phủ định.
Đường dẫn nguồn chính là [văn bản hợp nhất 18/VBHN-VPQH trên Công báo](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm).

Bộ này **phù hợp làm Gold ứng viên để phát triển/so sánh**, chưa được gọi là bộ
chuẩn pháp lý đã nghiệm thu. Các giới hạn cần giữ trong báo cáo:

- Chỉ một văn bản hợp nhất, 7 nhóm chủ đề; chưa đại diện toàn bộ luật lao động,
  văn bản hướng dẫn, bản án, lịch sử hiệu lực, nhiều yêu cầu hoặc hội thoại nối tiếp.
- Manifest Gold ghi chốt 23/10/2026; artifact thật chốt **15/09/2026**. Không tự
  sửa metadata để coi artifact đã cập nhật tới tháng 10. Ngày hỏi vẫn được giữ
  nguyên để quan sát giới hạn; mọi câu sau snapshot đều có cờ cảnh báo.
- Nhãn `TD013`–`TD015` là thiếu chứng cứ **so với corpus này**; không khẳng định
  không thể có văn bản tương lai đã ban hành ở bên ngoài corpus.
- `TD003` cần duyệt lại: 6 triệu đồng, nếu là lương công việc cho đủ giờ bình thường,
  cao hơn mức tối thiểu tháng cao nhất 5,31 triệu theo khoản 1 Điều 3
  [Nghị định 293/2025/NĐ-CP](https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-293-2025-nd-cp-quy-dinh-muc-luong-toi-thieu-doi-voi-nguoi-lao-dong-lam-viec-theo-hop-dong-lao-dong-119251110172808433.htm).
  Bắt buộc hỏi vùng/ngày trong mọi câu trả lời không phải nhãn chắc chắn, nhất là
  ngày tra cứu đã được gửi riêng. Công cụ **vẫn chạy câu này**, giữ đáp án gốc để
  kiểm tra, nhưng chưa chấm tự động trạng thái/AI judge của riêng nó. Còn phải
  làm rõ thành phần lương/giờ làm trước khi kết luận toàn diện.
- `CD007`, `TG009` có căn cứ tối thiểu, chưa đủ để chấm mọi nghĩa vụ/thủ tục liên
  quan. `HD007`, `TV004`, `NP005` cần cho phép điều kiện/ngoại lệ đúng. Xem
  `gold100_annotation_notes.json`; ghi chú gắn SHA của ZIP, không áp dụng mù cho
  bộ Gold khác cùng tên/mã câu.
- Qrels hiện là các ID được gán nhãn, không phải toàn bộ đoạn pháp luật có thể
  trả lời đúng. Đo đúng ID/cấp Điều–Khoản–Điểm có thể phạt một phiên bản/đoạn cha
  hợp lệ chưa được gán nhãn. Chưa gọi precision này là đánh giá chuyên gia đầy đủ.

## 2. Các file cần chuẩn bị trên máy

Trong repository phải có:

```text
legal-agentic-rag/
  benchmarks/evaluation_suite/       # toàn bộ thư mục code đo mới nhất
    Kaggle_Evaluation.ipynb
    settings.yaml
    gold.py
    gold100_annotation_notes.json
    GOLD100_GUIDE.md
    ...
  gold_dataset/
    PhapDienAI_Gold_100_Labor_v0_1.zip
```

Không cần chép nội dung Gold vào `artifacts/`, không chạy lại OFFLINE và không
nhập Gold vào dữ liệu truy xuất. Gold chỉ là đáp án để **chấm sau khi hỏi**;
đáp án/mã nguồn/missing_facts không được gửi vào câu hỏi hay facts của agent.

Đưa code và Gold lên GitHub để notebook tự tải được. Trong PowerShell:

```powershell
cd D:\data_thô\legal-agentic-rag
git status --short
git add -- benchmarks/evaluation_suite gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip
git diff --cached --stat -- benchmarks/evaluation_suite gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip
git commit --only -m "Integrate candidate labor Gold 100 evaluation" -- benchmarks/evaluation_suite gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip
git push origin main
```

Lệnh commit giới hạn đúng hai đường dẫn, để không gộp các phần khác đã stage từ
trước. Xem thay đổi trước khi commit. Không add `.env`, API key, cache hoặc model.
Tôi chưa tự commit/push thay bạn.

## 3. Tạo notebook đo trên Kaggle

1. Tạo notebook riêng; **dừng notebook backend** để tránh tranh GPU/quota.
2. Import bản mới `benchmarks/evaluation_suite/Kaggle_Evaluation.ipynb`.
3. Settings: **GPU T4 ×2**, Internet **On**.
4. Add Input **đúng một** Dataset kết quả `result_14-10`. Có thể là ZIP
   `vn_labor_results.zip` hoặc thư mục `artifacts/` Kaggle đã giải nén.
   Đừng add cả hai bản trùng hoặc nhiều bản kết quả.
5. Secrets: thêm/bật `GEMINI_API_KEY`; `HF_TOKEN` tùy chọn khi tải dữ liệu/model.
   Không cần `NGROK_AUTHTOKEN`, `VN_LABOR_API_KEY`, frontend hoặc backend API.
6. **Không phải upload Gold riêng lên Kaggle** khi ZIP đã được push như bước 2.
   Notebook clone repository, đọc ZIP theo đường dẫn tương đối.

## 4. Chạy kiểm tra nhỏ trước

Trong cell cấu hình đầu, giữ:

```python
PROFILE = 'smoke'
ARTIFACT = 'auto'
LABOR_GOLD = 'gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip'
STAGES = ['retrieval', 'ablation', 'zalo', 'vlsp']
GEMINI_MODEL = 'gemini-3.1-flash-lite'
EVALUATION_MODEL = GEMINI_MODEL
```

Run All. Notebook sẽ cài `git`, `curl`, `zstd`, tạo môi trường Python, lấy code
mới nhất từ `origin/main`, kiểm tra Gemini, chạy Ollama, tải model khi cần.
GPU 0 dùng embedding/reranker; GPU 1 dùng Ollama. Không cần sửa commit cứng.

Smoke chỉ lấy **8 câu theo nhóm**: 6 câu có đáp án, 1 thiếu dữ kiện, 1 thiếu căn
cứ; 5 biến thể QA tương ứng **40 lượt**, tối đa 10 câu Zalo và 5 câu VLSP lọc được.
Nếu schema/dataset bên ngoài không đúng hoặc dịch vụ lỗi thì stage được đánh
dấu ERROR, không chuyển thành số 0 hay lặng lẽ thay bằng dữ liệu giả.

Xem `gold_import_validation.json`: phải có `mapping_status=PASS`,
`questions=100`, `evidence_records=83`, `retrieval_questions=85` trên bản hiện tại.
`gold_selection.json` mới là số câu thực tế được chọn để đo trong lượt smoke.
`legal_approval=NOT_APPROVED` là đúng, không phải lỗi cài đặt.

## 5. Chạy đầy đủ để lấy bảng

Sau smoke đạt, sửa đúng một dòng rồi Run All lại:

```python
PROFILE = 'standard'
```

Mặc định hiện tại:

| Phần | Cỡ mẫu / số lượt |
|---|---|
| Labour retrieval | 85 câu × 4 cách × 3 lần = 1.020 lượt; không gọi LLM |
| Ablation QA | 100 câu × 5 cấu hình × 1 lần = 500 lượt sinh câu trả lời |
| Zalo độc lập | Tối đa 100 truy vấn có qrels; giữ nguyên corpus đầy đủ |
| VLSP thích nghi | Tối đa 50 câu phù hợp từ tập QA tự luận; không phải thi chính thức |

Trong 100 câu QA, hiện có **99 câu đủ điều kiện nhãn để tính điểm tự động nháp**;
`TD003` vẫn có câu trả lời/thời gian nhưng không có điểm chấm. Judge chỉ có điểm
khi thực sự gọi thành công, không tự điền 0 khi hết quota hoặc thiếu tham chiếu.

`repeats: 3` là số lần retrieval; `qa_repeats: 1` là số lần QA, tách riêng để
không vô tình tạo 1.500 lượt QA. Muốn tăng số lần QA phải sửa rõ `qa_repeats` trong
`settings.yaml` rồi push. Ba lần đo retrieval không tương đương ba mẫu độc lập.

Gemini Researcher/reviewer và AI judge dùng API thật, có thể tốn phí/quota. Judge
cùng họ model với pipeline có thiên lệch; phải ghi đúng model và xem lại bằng người.
Không có thời gian chạy cố định: tốc độ GPU, độ dài trả lời, tải mạng và quota
API ảnh hưởng lớn. Ngân sách hiện 10 giờ/lượt, mỗi stage tối đa 5 giờ, không thể
cam kết cả bốn nhóm sẽ hoàn tất trong một phiên. Có log/heartbeat và xuất kết
quả đã có khi một stage thất bại hoặc hết ngân sách do công cụ quản lý.
Kaggle tắt máy đột ngột vẫn có thể làm mất file chưa tải; không có cam kết chống
mất dữ liệu nếu nền tảng chấm dứt phiên.

Nếu cần chia phiên, đổi `STAGES` ở cell đầu:

```python
STAGES = ['retrieval', 'zalo']  # nhóm không sinh câu trả lời
# phiên khác:
STAGES = ['ablation']
# phiên khác:
STAGES = ['vlsp']
```

Mỗi phiên tạo thư mục kết quả riêng. Chỉ so các bảng dùng cùng source, model,
Gold SHA và artifact fingerprint; lưu đủ manifest. Không coi các stage NOT_RUN
của một phiên chia nhỏ là phép đo thất bại. Nếu ablation vẫn vượt 5 giờ, tăng
`stage_timeout_seconds` trong settings trong giới hạn phiên Kaggle hoặc dùng
nhãn mẫu nhỏ hơn và báo đúng cỡ mẫu; đừng đổi nhãn để ép PASS.

## 6. Tải và đọc kết quả

Cell cuối hiện link tải:

- `comparison_tables.md`: bốn bảng để đọc/copy vào báo cáo.
- `comparison_tables.csv`: bảng số liệu cho Excel.
- `evaluation_<thời_gian>.zip`: toàn bộ kết quả, không chứa model/cache/API key.

Trong ZIP có:

```text
gold_import_validation.json   # kiểm tra toàn bộ Gold, cảnh báo, ghi chú nhãn
gold_selection.json           # câu được dùng / bỏ khỏi mỗi phép đo
labor_gold.jsonl              # Gold đã chuyển schema, ghim corpus, dùng cho QA
labor_retrieval_gold.jsonl    # chỉ câu dương tính ANSWERABLE dùng cho retrieval
compatibility.json           # snapshot, build, giới hạn pháp lý thật
run_info.json                # commit/hash và đầu vào được ghim
retrieval/responses.jsonl     # ID nguồn tìm được, điểm, thời gian từng lượt
retrieval/per_question.csv    # kết quả truy xuất và thời gian từng lượt
ablation/responses.jsonl      # toàn bộ câu hỏi, đáp án, nguồn, trace, điểm judge
ablation/answers.csv          # câu hỏi + đáp án + thời gian cho Excel
ablation/answers.md           # bản đọc dễ hiểu từng câu/cấu hình
ablation/summary.json         # ma trận trạng thái và số câu thật sự chấm được
zalo/                        # qrels và metadata tập độc lập, kết quả IR
vlsp/                        # câu đã chọn/bỏ, đáp án gốc, giả định ngày
vlsp_qa/                     # kết quả QA thích nghi
logs/                        # log riêng của từng stage
```

Lưu ý các chỉ số:

- Retrieval: group Recall@10, MRR@10, group nDCG@10 đo tìm căn cứ đã gán nhãn.
  Không gọi đó là tỷ lệ trả lời pháp luật đúng. Mỗi nhóm căn cứ là yêu cầu AND;
  các ID trong một nhóm là thay thế OR. Mã được lặp lại không tăng điểm.
- QA: correctness/completeness/evidence_support là **điểm AI judge nháp**, không
  phải kết quả chuyên gia. Xem số `ai_judged` cùng điểm; lỗi và câu chưa chấm không
  được giấu khỏi mẫu báo cáo.
- `draft_disposition_match_rate`: mức khớp trạng thái tham khảo ở các câu đủ
  điều kiện; lỗi kỹ thuật vẫn nằm trong mẫu số. `ANSWERABLE` chỉ khớp chặt với
  `SUFFICIENT`; `PARTIAL_ALLOWED` chưa tính hoàn thành. Đây không phải điểm đúng
  nội dung: hệ thống có thể trả nội dung đúng nhưng bị giới hạn chứng cứ.
- `gold_citation_group_recall`: độ bao phủ các nhóm ID căn cứ đã gán nhãn trong
  câu có đáp án; không áp cho câu thiếu dữ kiện/căn cứ. Chưa phải đủ mọi căn cứ.
- Thời gian QA gồm pipeline đến phản hồi, **không gồm AI judge và frontend**;
  có thêm trường thời gian tính cả judge. Thời gian warmup retrieval được tách ra.
- Ablation tắt exact/profile shortcuts ở tất cả cấu hình để đo thành phần. Đây
  không phải phép đo độ trễ của frontend khi triển khai thông thường.
- Zalo có corpus riêng; VLSP là QA thích nghi. Không gộp bốn bảng thành một độ
  chính xác duy nhất. Stage lỗi/chưa chạy phải giữ ERROR/NOT_EVALUATED/N/A.

## 7. Các lần cập nhật sau

- **Chỉ sửa ONLINE:** git push; Run All. Không sửa notebook nếu các cell cấu
  hình không thay đổi. Lượt mới ghi version và hash riêng, không trộn với lượt cũ.
- **OFFLINE mới:** thay đúng một Dataset Input. Nếu cùng nội dung mà ID đổi,
  importer chỉ ánh xạ khi cùng luật, locator, nguyên văn và còn phù hợp ngày;
  vẫn giữ DRAFT. Nếu nội dung đổi/không ánh xạ được thì dừng để rà soát Gold.
- **Gold mới:** giữ bản cũ, tạo ZIP/JSONL portable tên mới, cập nhật `LABOR_GOLD`.
  Raw JSONL `labor_gold_100.jsonl` trong ZIP **khác schema** suite; dùng ZIP
  nguyên gốc hoặc `labor_gold.jsonl` portable do suite xuất, không đổi đuôi tên.
- Chưa nên vừa dùng cả 100 câu để sửa hệ thống vừa gọi cả 100 là tập kiểm thử
  độc lập. Chia dev/test theo nhóm vấn đề/căn cứ trước khi nghiên cứu tiếp; các
  câu diễn đạt khác nhưng cùng điều khoản nên ở cùng nhóm để giảm rò rỉ.

## 8. Kiểm tra đầu vào không cần GPU/API

Có thể chạy local từ gốc repository trước khi lên Kaggle:

```powershell
.venv\Scripts\python.exe benchmarks/evaluation_suite/suite.py prepare --artifact "D:\data_thô\result\result_14-10\vn_labor_results.zip" --device cpu --output artifacts/evaluation_gold100_check
.venv\Scripts\python.exe -m unittest discover -s benchmarks/evaluation_suite -p "test_*.py" -v
```

Dùng thư mục output mới nếu đã tồn tại. `prepare` chỉ kiểm tra/ghim đầu vào,
không gọi Gemini/Ollama và không tính điểm các bảng chưa chạy.

Đã kiểm tra thật BM25 local trên **85/85 câu hợp lệ**, không lỗi kỹ thuật. Đây là
kiểm tra tích hợp dữ liệu và runner, chưa phải bằng chứng đã đo đủ Dense/Hybrid,
Graph, các ablation, Zalo hay VLSP trên Kaggle.
