# Bộ đánh giá thống nhất — Pháp Điển AI

Toàn bộ code cần chạy nằm trong **một thư mục `benchmarks/evaluation_suite/`**.
Import notebook `Kaggle_Evaluation.ipynb` một lần; những lần sau chỉ Run All.
Không cần frontend, ngrok hoặc notebook backend đang chạy cùng lúc.

**Đã tích hợp ZIP Gold 100 bạn cung cấp, không cần giải nén.** Xem
[hướng dẫn Gold 100 từ đầu đến cuối](GOLD100_GUIDE.md) để chuẩn bị GitHub, Kaggle,
chọn smoke/standard và tải kết quả. Gold này là candidate DRAFT, chưa duyệt pháp lý.

## Thiết lập lần đầu trên Kaggle

1. Push thư mục này và `gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip` lên `main`.
2. Import `Kaggle_Evaluation.ipynb`, chọn **GPU T4 ×2**, bật Internet. Dừng cell
   backend trước khi đo để không tranh RAM/VRAM hoặc quota API.
3. Add Input **một** bộ kết quả OFFLINE. ZIP `vn_labor_results.zip` hoặc thư mục
   `artifacts/` đã được Kaggle giải nén đều dùng được. Không Add cả bản cũ và mới;
   nếu cần nhiều input, đặt `ARTIFACT` trong cell cấu hình thành đường dẫn cụ thể.
4. Thêm và bật Secret `GEMINI_API_KEY`; `HF_TOKEN` tùy chọn cho tải Hugging Face.
   `NGROK_AUTHTOKEN` và `VN_LABOR_API_KEY` không cần vì không mở API ra Internet.
5. Cell đầu để `PROFILE='smoke'` cho lần kiểm tra đầu. Nó chạy đủ các nhóm nhưng
   chỉ một lần lặp, 8 câu chọn theo nhóm từ Gold, tối đa 10 câu Zalo và 5 câu VLSP lọc được.
6. Run All / Save Version. Xem log có `HEARTBEAT` và tiến độ từng lượt.
7. Cuối notebook tải **`comparison_tables.md`**, **`comparison_tables.csv`**
   hoặc ZIP toàn bộ run. Bốn bảng có thể đưa vào báo cáo **kèm nhãn/phạm vi**.

Để chạy lớn hơn: `PROFILE='standard'`, chỉnh `settings.yaml` hoặc các biến đầu
notebook. Mặc định standard dùng ZIP Gold: 85 câu retrieval × 4 cách × 3 lần;
100 câu QA × 5 cấu hình × 1 lần. `TD003` vẫn chạy nhưng tạm không chấm tự động
do nhãn cần duyệt; xem ghi chú. Tăng số lần lặp không biến DRAFT thành Gold đã duyệt.
Các bước QA/judge dùng quota API thật. Chạy smoke trước khi tăng cỡ mẫu.
`labor_seed_date` là mốc so sánh cố định, không tự đổi sang ngày hiện tại mỗi lần chạy.

## Bốn phần được đo

| Phần | Cấu hình / phạm vi | Đầu ra chính |
|---|---|---|
| 1. Truy xuất lao động | BM25; Dense BGE-M3; RRF Hybrid; Hybrid + graph cố định 2 hop. Không LLM/anchors/reranker | Recall/MRR/nDCG theo nhóm căn cứ; độ trễ retrieval |
| 2. Đóng góp thành phần | Full; bỏ Graph; bỏ reranker; bỏ applicability Auditor; bỏ semantic reviewer. Cùng model/corpus/Gold | Câu trả lời, nguồn, trace, số câu có nội dung, lỗi, thời gian, điểm AI judge nếu khả dụng |
| 3. Zalo độc lập | BM25; Dense; Hybrid trên **toàn bộ corpus Zalo**, qrels test; chỉ giới hạn số query | Recall@k, Precision@k, MRR@k, nDCG@k; không dùng corpus lao động hay graph giả |
| 4. VLSP QA thích nghi | Public-Test / `syllogism_questions`, split HF tên `train`; lọc keyword lao động mặc định | Đáp án tham chiếu, trả lời thực tế, số mẫu, thời gian và điểm AI judge |

Hai phép đo graph **khác nhau có chủ đích**: phần 1 đo mở rộng cấu trúc cố định;
phần 2 đo pipeline adaptive hiện có khi bật/tắt graph. Không gộp điểm chúng.
Phần 2 tắt exact/profile fast paths cho **mọi biến thể** để giảm trường hợp thành
phần chưa chạy; model, nguồn, thời điểm, các gate còn lại vẫn giữ. Đây không phải
đo thời gian triển khai của chatbot. Xem trace để biết component thực sự đã chạy.

“Bỏ Auditor” chỉ diễn ra trong worker benchmark: nhận candidate sau kiểm tra
nguồn/thời gian, ghi quyết định **UNRESOLVED / EXPERIMENT_AUDITOR_DISABLED**,
không giả PASS. “Bỏ hậu kiểm” bỏ semantic review, giữ các kiểm tra cấu trúc/nguồn/
câu chữ và completeness còn lại. Pipeline production không bị sửa hay tắt bảo vệ.
Kết quả các ablation không được phục vụ người dùng như tư vấn đã xác minh.

## Bảng nào được dùng trong báo cáo?

- **DRAFT / smoke:** chứng minh công cụ chạy được, không dùng làm tỷ lệ chính xác
  đã được chuyên gia xác nhận hoặc kết luận phương pháp thắng trên toàn miền.
  Gold candidate và bộ seed sáu câu có qrels tối thiểu theo locator,
  chưa đảm bảo đủ cả căn cứ cha, ngoại lệ, quan hệ bổ sung cho mọi lập luận.
- **AI judge:** các cột `ai_correctness`, `ai_completeness`, `ai_evidence_support`
  là điểm 0–1 của một lần gọi mô hình chấm riêng, **không phải** tỷ lệ đúng do luật
  sư xác nhận. Lưu model/reason; phải đọc số `ai_judged` và lỗi. Cùng họ model có
  thể thiên lệch; cần người rà soát hoặc judge khác khi làm nghiên cứu chính thức.
- Không có judge/key hoặc judge lỗi thì điểm là **N/A**, không mặc định 0 hoặc 1.
- `reference_id_audit_pass_rate` chỉ kiểm ID/trích dẫn kỹ thuật, không gọi nó là
  groundedness hay độ đúng pháp lý. “Có câu trả lời” khác “trả lời đúng và đủ”.
- Zalo là bản phân phối lại công khai; lưu URL, revision, license metadata.
  Không suy từ điểm trên Zalo ra độ chính xác hệ thống lao động.
- VLSP ở đây là **thích nghi**: RAG + model/API của dự án không theo giao thức
  chính thức (≤4B, không external retrieval/API khi suy luận). Không so bảng xếp
  hạng chính thức. Mặc định chỉ lấy câu liên quan lao động bằng keyword; đây là
  lọc tự động, chưa phải duyệt domain. Danh sách chọn/loại và số lượng đều được lưu.
- Nhãn VLSP không cung cấp ngày sự việc riêng cho mọi câu: config dùng giả định
  ngày phát hành public test `2025-07-15`. **Cần rà soát câu nhạy thời điểm**;
  bản tham chiếu có thể không khớp corpus hiện tại. Không dùng nhãn đó chứng minh
  pháp luật hiện hành năm 2026 mà chưa đối chiếu.
- Các bảng chưa đo/nhánh lỗi ghi NOT_EVALUATED hoặc N/A. Không chỉ copy số đẹp;
  giữ tên tập, cỡ mẫu, scope, nhãn và trạng thái lỗi cùng bảng.

Nguồn: https://vlsp.org.vn/vlsp2025/eval/legalSLM ;
https://huggingface.co/datasets/VLSP2025-LegalSML/Public-Test ;
https://huggingface.co/datasets/minhnguyent546/zalo-ai-legal-text-retrieval-2021 .
Việc tải/schema adapter chưa thay thế kiểm tra quyền sử dụng dữ liệu khi công bố.

## Những lần cập nhật tiếp theo

**ONLINE mới:** commit/push code, Run All lại notebook. Notebook fetch `origin/main`
và ghi commit/hash toàn bộ source ONLINE và code đo. Không giữ COMMIT cứng. Nếu
code trong notebook đã sửa, notebook dừng thay vì xóa sửa đổi của bạn.

**OFFLINE mới:** thay Dataset Input bằng gói mới, Run All. Suite kiểm tra artifact,
tạo bản cấu hình ghim build/hash riêng cho lần chạy, không sửa config production.
Schema/model/index phải tương thích. Nếu đổi embedding model, cần cập nhật config
cho model đó, không thể dùng chỉ mục sai model rồi vẫn xem phép đo là hợp lệ.

**Gold:** mặc định đọc ZIP candidate 100. `labor_gold=null` mới tạo seed sáu câu
theo locator. ZIP gốc không bị giải nén/sửa. Raw JSONL trong ZIP có schema khác;
dùng ZIP nguyên gốc hoặc JSONL portable do suite xuất. File Gold do suite xuất có
`required_group_locators`, giúp ánh xạ ID khi đổi OFFLINE. Khi build thay đổi,
suite ánh xạ lại theo instrument/Điều/Khoản/Điểm/cấp + ngày và **hạ về DRAFT**.
Với ZIP candidate, còn đối chiếu nguyên văn để chặn ánh xạ sai phiên bản.
Nếu không ánh xạ được, dừng để sửa Gold. Không thể bảo đảm đổi OFFLINE bất kỳ mà
vẫn giữ nguyên nhãn đã duyệt. Không tự gọi dữ liệu là APPROVED bằng AI.

Gold portable gồm: id, question, query_date, required_groups (nhóm AND, ID trong
nhóm OR), corpus_fingerprint, required_group_locators, review_status, reviewer,
reviewed_at; có thể bổ sung reference_answer, facts, conversation_context cho QA.
Gold IR thuần không sử dụng facts/hội thoại, vì vậy câu phải tự chứa ngữ cảnh.

**Dataset đánh giá ngoài:** revision main được resolve thành SHA, giữ trong cache
để so sánh qua các bản dự án trên cùng dữ liệu. Muốn thay tập benchmark phải đổi
revision rõ ràng và ghi trong báo cáo, không gộp kết quả cũ/mới.

## Cách tổ chức và các lệnh

```text
evaluation_suite/
  Kaggle_Evaluation.ipynb  # notebook dùng lại
  settings.yaml           # cấu hình chung
  suite.py                # điều phối, log, timeout, bảng tổng hợp, ZIP
  labor_retrieval.py       # bốn baseline retrieval lao động
  qa.py                   # ablation và QA thích nghi
  external.py             # import Zalo/VLSP và IR trên corpus riêng
  common.py               # lưu kết quả, metrics, AI judge
  gold.py                 # đọc/kiểm tra ZIP, chia retrieval/QA
  gold100_annotation_notes.json  # vấn đề nhãn, ghim SHA ZIP
  GOLD100_GUIDE.md         # hướng dẫn đầy đủ với bộ 100 câu
  make_notebook.py         # tái tạo notebook
  test_suite.py
  README.md
```

Từ gốc project, sau khi đã cài `.[retrieval,online]` và `datasets`:

```bash
python -u benchmarks/evaluation_suite/suite.py run \
  --artifact /kaggle/input/DUONG_DAN_THUC_TE/artifacts \
  --output /kaggle/working/evaluation_run1

# Chỉ chạy một số phần:
python -u benchmarks/evaluation_suite/suite.py run \
  --settings /kaggle/working/settings.yaml \
  --output /kaggle/working/retrieval_only --stages retrieval

# Chạy lại những stage chưa hoàn thành, giữ nguyên code/config/dữ liệu:
python -u benchmarks/evaluation_suite/suite.py run \
  --settings /kaggle/working/settings.yaml \
  --output /kaggle/working/evaluation_run1 --resume

# Tạo lại bảng từ kết quả hiện có, không gọi AI:
python benchmarks/evaluation_suite/suite.py report \
  --output /kaggle/working/evaluation_run1
```

`--resume` ở cấp stage, không phải từng câu QA: stage bị lỗi chạy lại từ đầu;
Zalo có checkpoint embedding để không encode lại các batch đã xong. Chỉ resume
khi source hashes, settings, artifact path/build không thay đổi. Đổi code hoặc
OFFLINE thì dùng output mới. Không cần upload lại notebook nếu giao diện cấu hình
không đổi; khi code đo nâng cấp notebook generator, import notebook mới nếu cần.

Giới hạn mặc định 10 giờ cho các stage trong một lượt, mỗi stage tối đa 5 giờ,
heartbeat 15 giây. Không bảo đảm hoàn tất mọi cỡ dữ liệu trong một phiên Kaggle;
khi hết ngân sách, bảng giữ phần đã chạy và đánh dấu còn thiếu. Timeout model
là cooperative trong pipeline, có thêm timeout cứng ở tiến trình stage.

Output chứa responses từng câu, JSON summary, CSV/Markdown tổng hợp, logs,
trace, cấu hình đã che secret, hashes, migration và metadata dataset. Cache/model
để ngoài output, không đóng vào ZIP. Không commit API key, model hoặc cache.
Các output mặc định nằm ở `/kaggle/working`, tải về trước khi đóng phiên nếu cần.

## Kiểm thử và giới hạn xác nhận

```bash
python -m unittest discover -s benchmarks/evaluation_suite -p "test_*.py" -v
```

Kiểm thử local dùng fixture/mocks, không tiêu quota AI. Phải phân biệt việc test
code PASS với việc đã đo đủ bốn nhóm trên dữ liệu thật. Kết nối Hugging Face,
download model, inference Gemini/Ollama, GPU, license và chất lượng nhãn vẫn cần
được xác nhận tại môi trường chạy. Công cụ không cam kết “không bao giờ lỗi”.
