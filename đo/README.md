# Bộ đo thống nhất Pháp Điển AI và đối chứng

Hai điểm vào chính: **`evaluate_project.py`** đo Pháp Điển AI; **`evaluate_baselines.py`** đo đối chứng. Chạy từ thư mục gốc `legal-agentic-rag`. Toàn bộ mã mới nằm ở đây; không sửa pipeline chính hoặc repository đối chứng. Các phần Gold, ghim revision embedding và truy xuất đã kiểm chứng được tái sử dụng từ `benchmarks/evaluation_suite` — cần cả repository, không chỉ chép hai file Python.

## Bắt đầu nhanh trên Kaggle — bỏ Zalo/VLSP

Import [Kaggle_Labor_Evaluation.ipynb](Kaggle_Labor_Evaluation.ipynb). Notebook riêng này dùng runner mới, không gọi Zalo/VLSP hoặc baseline upstream chưa sẵn sàng.

1. Đưa folder `đo` lên `origin/main` trước (không thêm cache/results/settings.local.json). Gold ZIP 120 đã được Git theo dõi.
2. Tạo notebook đo riêng, bật Internet và GPU T4×2; dừng notebook backend/tác vụ khác dùng chung GPU/quota.
3. Add Input đúng một `vn_labor_results.zip` cuối hoặc thư mục `artifacts` tương ứng. Không thêm technical checkpoint/recovery/bản dữ liệu cũ cùng lúc. Nếu auto phát hiện nhiều đầu vào, điền `ARTIFACT` bằng đường dẫn cụ thể.
4. Cell cấu hình: bắt đầu `PHASE='retrieval'`, `PROFILE='smoke'`, `RESUME=False`; Run All. Retrieval thuần không cần Secret Gemini, HF_TOKEN tùy chọn.
5. Khi smoke đạt, đổi `PROFILE='standard'`. Retrieval standard đo 108 câu × 6 phương pháp × 3 lần = 1.944 lượt. Chọn `PHASE='ablation'` để đo 5 cấu hình chính (600 lượt QA), hoặc `PHASE='naive_qa'` cho 3 đối chứng tối giản (360 lượt QA); QA cần `GEMINI_API_KEY`. Cả hai chạy judge sau generation. Smoke QA chỉ dùng 5 câu mỗi cấu hình, không đưa số smoke làm kết quả nghiên cứu.
6. Tải ZIP bằng cell tải kết quả. Cell này có thể chạy riêng khi phép đo dừng vì quota; ZIP chứa bundle và các run, không chứa venv/model cache. Số lượt QA không bằng số request LLM, quota có thể hết trước khi xong.
7. Tiếp tục đúng run: giữ nguyên PHASE/PROFILE/RUN_NAME/model/code/data/settings, đặt `RESUME=True`; chỉ thêm `RETRY_ERRORS=True` nếu muốn thử lại lỗi kỹ thuật. Không chạy lại câu đã thành công để chọn đáp án đẹp hơn. Đổi model/code/artifact thì dùng RUN_NAME mới.

Cell dọn dịch vụ chỉ chạy khi kết thúc mọi phase trong phiên. Khi chuyển phase trong cùng phiên, chạy lại các cell chuẩn bị Secrets/Ollama trước khi đo; không cập nhật Git giữa một run đang dở. Qua phiên Kaggle khác cần khôi phục toàn bộ output/bundle và môi trường tương thích; chỉ có CSV không đủ resume. Notebook đã kiểm cú pháp/điều phối cục bộ, chưa được chạy end-to-end trên Kaggle trong lượt tạo file.

## 1. Những gì thực sự chạy được và giới hạn

| Phương pháp | Đường chạy | Phạm vi kết luận |
|---|---|---|
| BM25, Dense, Hybrid RRF, Hybrid + reranker, Hybrid + Graph, Hybrid + Graph + reranker | Adapter truy xuất hiện có, cùng corpus và bộ lọc | So truy xuất; Graph ở đây mở rộng cố định, **không phải Microsoft GraphRAG** |
| Full, bỏ BM25/Dense/Graph/Researcher/Auditor/Adjudicator/reranker/hậu kiểm | Pipeline ONLINE trong tiến trình đo | Ablation có ghi cấu hình và dấu vết thành phần đã thực thi |
| Naive BM25/Dense/Hybrid RAG | Retriever + một reader chung | Baseline tối giản thực, không gắn tên framework khác |
| LightRAG | Adapter tùy chọn dùng `ainsert` / `aquery_data`, môi trường riêng | Đã đối chiếu API; chưa chạy end-to-end upstream trong phiên xây dựng này |
| HippoRAG2 | Adapter tùy chọn dùng `index` / `retrieve`, ánh xạ chính xác `QuerySolution.docs` | Đã đối chiếu API; chưa chạy end-to-end upstream trong phiên này |
| Microsoft GraphRAG, RAPTOR | Hiện **N/A** | Chưa có adapter được kiểm chứng nối context/report/summary về đúng canonical provision; không thay bằng đồ thị/tree tự chế |
| LegalGraphRAG gốc → QA Việt Nam | Hiện **N/A** | Code gốc dùng hình sự Trung Quốc, `law_to_crime`, `judge_res`, prompt en/zh; cần thích nghi thực sự, không chỉ đổi câu hỏi |
| LegalGraphRAG gốc → chấm LJP Trung Quốc | Lệnh `original-ljp` gọi scorer gốc trên prediction thật được cung cấp | Tách hẳn khỏi bảng QA Việt Nam; chạy scorer không đồng nghĩa tái hiện toàn bài báo |

`repository_audit.json` lưu commit, hash và API đã đọc của từng repository. Đây là **bằng chứng rà soát nguồn, không phải bằng chứng baseline đã chạy thành công**. Có thể cập nhật khảo sát bằng:

```powershell
python đo/evaluate_baselines.py audit-repos --legal-repo "D:/data_thô/legalgraphrag/LegalGraphRAG" --out đo/repository_audit.json
```

Không bật cả bộ đối chứng trước khi từng phương pháp qua smoke. `--methods all` thử toàn bộ danh sách, nhưng phương pháp thiếu điều kiện vẫn ghi N/A, không tạo điểm. Mã thoát `2` nghĩa là có ERROR/N/A hoặc lịch chưa hoàn tất; **không đồng nghĩa mọi phần đã chạy đều hỏng**.

## 2. Chuẩn bị trên máy hoặc Kaggle

1. Dùng Python tương thích dự án; cài repository và thư viện đo. Kaggle: chạy từ bản clone mới nhất đã push, bật GPU/Internet nếu dùng Dense/LLM. Lưu commit trước khi chạy; không cập nhật code trong cùng thí nghiệm.

```bash
pip install -e ".[retrieval,online]"
pip install -r đo/requirements.txt
python -m unittest discover -s đo -p "test_*.py" -v
```

2. Dữ liệu: dùng một artifact cuối `vn_labor_results.zip` hoặc thư mục `artifacts` đã giải nén. Không cần frontend, ngrok hay `VN_LABOR_API_KEY`. Retrieval thuần không gọi Gemini/Ollama. QA cần Ollama/model và các provider đúng trong ONLINE YAML; judge Gemini cần `GEMINI_API_KEY` từ môi trường/Kaggle Secret. Không ghi key vào JSON hoặc Git.

3. Copy `settings.example.json` thành `settings.local.json`. Chỉnh `online_config`, `cache`, `device` (`cpu` hoặc `cuda:0`). Mọi đường dẫn tương đối tính từ **thư mục gốc repo khi chạy lệnh**; trên Kaggle nên dùng đường dẫn tuyệt đối cho cache, bundle và output ở `/kaggle/working/`.

`reranker_revision` đã ghim commit Hugging Face cụ thể, không tự chuyển theo `main` khi cache Kaggle bị mất. Dense dùng revision trong artifact. Khi đổi reranker phải đổi revision tương ứng và tạo run mới; không resume trộn trọng số.

```python
# Chỉ dùng trong Kaggle, trước lệnh đo QA. Không in giá trị Secret.
import os
from kaggle_secrets import UserSecretsClient
os.environ['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
os.environ['GEMINI_MODEL'] = 'gemini-3.1-flash-lite'
os.environ['VN_LABOR_GEMINI_RPM'] = '13'
# Đặt rõ vai trò nếu cấu hình thực nghiệm của bạn dùng Gemini:
os.environ['VN_LABOR_RESEARCHER_MODE'] = 'gemini'
os.environ['VN_LABOR_ADJUDICATION_REVIEW_PROVIDER'] = 'gemini'
os.environ['VN_LABOR_ADJUDICATION_REVIEW_MODEL'] = os.environ['GEMINI_MODEL']
```

Không tự chuyển model khi hết quota. Dừng tác vụ khác dùng cùng quota/GPU. Tham số `reader` phải khớp provider, model, output/context token budget của Adjudicator chính; runner kiểm điều này. Các provider hiện dùng temperature=0, Ollama seed=0; seed CLI chỉ điều khiển thứ tự chạy/bootstrap, không giả định API cloud bảo đảm đầu ra bit-for-bit. Cấu hình ONLINE hiệu lực được ghi sau khi đọc biến môi trường, đã che secret.

Nếu dùng notebook cũ: giữ các cell cài môi trường/Secrets/Ollama, **thay cell gọi `benchmarks/evaluation_suite/suite.py` bằng các lệnh đo mới** bên dưới. Retrieval thuần đặt `STAGES=['retrieval']` ở cell đầu để không bắt Gemini/Ollama; QA dùng chuẩn bị môi trường tương ứng. Các lệnh `python` trong hướng dẫn phải dùng đúng biến `PYTHON` (venv) của notebook, không dùng nhầm Python hệ thống. Ví dụ cell mới:

```python
import json, subprocess
from pathlib import Path
cfg = json.loads((ROOT/'đo/settings.example.json').read_text(encoding='utf-8'))
cfg.update(online_config=str(ROOT/'config/online_kaggle.yaml'),
           cache=str(WORK/'unified_cache'), device='cuda:0')
SETTINGS = WORK/'unified_settings.json'
SETTINGS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
def evaluate(*args):
    return subprocess.run([str(PYTHON), '-u', *map(str,args)], cwd=ROOT, check=True)
# ARTIFACT phải là đường dẫn thật, không để chuỗi 'auto' ở CLI mới.
# Ví dụ prepare (chỉ chạy lần đầu với folder bundle mới):
evaluate('đo/evaluate_project.py', 'prepare', '--artifact', ARTIFACT,
         '--gold', ROOT/'gold_dataset/PhapDienAI_Gold_120_Labor_v0_2.zip',
         '--bundle', WORK/'unified_bundle120', '--cache', WORK/'unified_cache', '--allow-draft')
evaluate('đo/evaluate_project.py', 'run', '--bundle', WORK/'unified_bundle120',
         '--config', SETTINGS, '--out', WORK/'unified_ir_smoke', '--task', 'retrieval',
         '--methods', 'bm25', '--limit', '5', '--allow-draft')
```

Nếu chưa dùng notebook: cài công cụ hệ thống trước bằng `apt-get update -y` và `apt-get install -y git curl zstd`. QA cần khởi chạy `ollama serve` riêng và tải `ollama pull qwen3:8b`; trên T4×2 nên dành GPU1 cho Ollama, GPU0 cho embedding/reranker. Bộ đo không tự chiếm hay dừng một Ollama server đang phục vụ tác vụ khác.

## 3. Đóng băng bundle dữ liệu chung

```powershell
python đo/evaluate_project.py prepare --artifact "D:/data_thô/result/result_28-10/vn_labor_results.zip" --gold gold_dataset/PhapDienAI_Gold_120_Labor_v0_2.zip --bundle đo/work/bundle120 --cache đo/cache --allow-draft
```

Kaggle thay `--artifact` bằng đường dẫn Input, `--bundle /kaggle/working/eval_bundle120`, `--cache /kaggle/working/eval_cache`. Gold ZIP đọc trực tiếp, không cần tự giải nén.

Kết quả: `corpus.jsonl` (chỉ dữ liệu nguồn), `questions.jsonl` (Gold cho scorer), `inference_questions.jsonl` (chỉ dữ kiện người dùng), `manifest.json`, `gold_audit.json`. Không đưa `questions.jsonl` có đáp án cho baseline indexing. Worker upstream chỉ nhận corpus, câu hỏi và ngày, không nhận qrels/đáp án/trạng thái chuẩn.

Gold v0.2 hiện có **120 câu QA, 108 câu retrieval dương tính, 12 câu hỏi bổ sung**, tất cả DRAFT. Bộ này đã dùng cải tiến dự án nên **không phải held-out độc lập**. `--allow-draft` là chấp nhận đo phát triển, không phải phê duyệt Gold. Muốn kết luận nghiên cứu tổng quát hóa: chuyên gia duyệt nguồn/đáp án, tạo tập mới độc lập, khóa trước khi đo. Không sửa nhãn vì hệ thống trả lời khác.

Để nạp Gold độc lập: cung cấp JSONL chuẩn, mỗi dòng có `id`, `question`, `query_date`, `expected_status`, `required_groups`, `corpus_fingerprint`, `review_status`, `reviewer`, `reviewed_at`, `evaluation_scope`; kèm file cùng tên đuôi `.manifest.json` khai báo nguồn gốc, cách chia dữ liệu và `evaluation_scope`. Qrels phải là ID thật và các nhóm không giao nhau. Ngày bắt buộc cố định để các phương pháp không bị đo ở các ngày mặc định khác nhau. Đối thoại dùng `conversation_turns` chỉ gồm user turns theo schema dự án. Nếu không có qrels dương tính, đặt `retrieval_eligible=false`.

`gold_tasks` tùy chọn là danh sách `{task_id, description, ...}` **do người gán nhãn xác định**. Không có nhãn này thì điểm độc lập cho từng yêu cầu là N/A; số `parts` do hệ thống tự báo chỉ để chẩn đoán. Không suy ra Fact Coverage hoặc Evidence Precision từ recall nhóm.

## 4. Đo truy xuất trước — không dùng LLM

```powershell
# Smoke 5 câu, dùng toàn corpus; không dùng điểm smoke cho báo cáo chất lượng.
python đo/evaluate_project.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/ir_smoke --task retrieval --methods bm25 --limit 5 --k 10 --allow-draft

# Đo chính 108 câu × 6 cấu hình × 3 lần; cần tải model Dense/reranker theo revision.
python đo/evaluate_project.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/ir_main --task retrieval --methods all --repeats 3 --k 10 --allow-draft

python đo/evaluate_baselines.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/baseline_ir --task retrieval --methods naive_bm25 naive_dense naive_hybrid --repeats 3 --k 10 --allow-draft
```

Ba dòng Naive retrieval này tương đương ba retriever BM25/Dense/Hybrid; không coi đó là ba thuật toán mới. Có thể bỏ lần đo trùng nếu chỉ cần bảng IR. Dùng cùng `--limit`, `--k`, `--seed`, `--repeats`, settings, môi trường và bundle khi so sánh. Mỗi K là một thí nghiệm cố định: tạo output khác nếu muốn K=5/20; không ghi đè/resume đổi K.

## 5. Đo QA và ablation

```powershell
python đo/evaluate_project.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/qa_smoke --task qa --methods full without_graph --limit 5 --allow-draft --allow-llm

python đo/evaluate_project.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/qa_main --task qa --methods all --repeats 1 --allow-draft --allow-llm

python đo/evaluate_baselines.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/naive_qa --task qa --methods naive_bm25 naive_dense naive_hybrid --repeats 1 --allow-draft --allow-llm
```

Chi phí full 120 × 9 = **1.080 lượt pipeline**, chưa kể các lượt gọi agent/review/repair và judge; đừng chạy all ngay khi quota chưa đủ. Từng phương pháp chạy độc lập bằng `--methods full` hay `--methods without_graph`. Giữ cùng lịch câu hỏi; một ablation không được chỉ chạy tập con dễ hơn.

Các ablation dùng cùng chính sách tắt exact/profile fast path, tắt cache yêu cầu, Researcher không bỏ qua vì known profile, và tắt recovery đổi provider. Đây là **thí nghiệm cô lập**, không đại diện latency frontend sản phẩm. Các cổng ngoài phạm vi/thiếu dữ kiện vẫn hoạt động. Full dùng cấu hình gốc được ghi lại; nếu bản gốc vốn không có Researcher LLM thì `without_researcher` là N/A. Adapter bỏ Adjudicator giữ reviewer độc lập, tránh việc chỉ đổi mode=deterministic sẽ vô tình tắt cả reviewer trong mã production.

`without_graph` tắt gap traversal, issue-anchor dựa trên graph và các kênh case/community. Metadata gốc, ngữ cảnh cha và bộ phân loại vấn đề vẫn giữ để không vô tình đổi cả dữ liệu/phân tích đầu vào; đây là ablation **sử dụng graph lúc truy vấn**, không xóa ảnh hưởng của graph đã xây OFFLINE. `without_auditor` trả UNRESOLVED, không tạo PASS giả. `without_adjudicator` bỏ bước soạn/sửa câu chữ của Adjudicator, dùng bộ sinh xác định có sẵn rồi gọi reviewer cùng cấu hình như các nhánh khác; **không phải một hệ thống không hề sinh đầu ra**. Sửa semantic của reviewer vẫn theo policy đã ghi. Hậu kiểm và kiểm trích dẫn còn lại vẫn có thể chặn đầu ra; đó là một kết quả thực nghiệm cần diễn giải, không sửa thành PASS để đẹp bảng.

Lượt nào đã trả lời thành công, kể cả hỏi lại/từ chối/partial, được giữ nguyên. Không lặp đến khi có câu trả lời đẹp nhất.

## 6. Judge độc lập chạy sau khi sinh xong

```powershell
python đo/evaluate_project.py judge --run đo/results/qa_main --allow-llm
python đo/evaluate_baselines.py judge --run đo/results/naive_qa --allow-llm
```

Hoặc thêm `--judge` vào lệnh QA để chấm sau generation. Judge dùng cùng model/rubric, nhận đáp án tham khảo và ngữ cảnh nguồn đầy đủ sau inference; thời gian judge lưu riêng. Chấm đúng, đủ, hỗ trợ bằng chứng, liên quan và áp dụng thời gian ở mức 0–1. Không có task annotation thì task score N/A. Vượt ngân sách ngữ cảnh: N/A, không tự cắt bỏ điều kiện pháp lý. Nếu judge lỗi/quota: lưu lỗi, tiếp tục lệnh judge sau; không đánh giá lỗi đó thành câu trả lời sai luật.

Điểm này là **AI-judge**, không phải chuyên gia pháp lý, không phải chạy nguyên giao thức RAGAS/RAGChecker. Nên duyệt mù một mẫu phân tầng bởi hai người có chuyên môn, ghi mức đồng thuận và giải quyết bất đồng; đặc biệt duyệt tất cả trường hợp điểm/căn cứ mâu thuẫn. Không lấy phán quyết PASS trong trace của hệ thống làm nhãn chuẩn.

`clarification_match` và `out_of_scope_match` chỉ là khớp quyết định hỏi lại/từ chối với nhãn. Hỏi lại đúng dữ kiện hay hỏi thừa/sai phải xem nội dung `clarification_questions` mà judge/chuyên gia chấm, không suy từ status. Ngày `query_date` trong bundle là thời điểm áp dụng được cấp tường minh: bộ 120 hiện tại không đo riêng khả năng tự nhận diện ngày mặc định của người dùng. Muốn đánh giá rộng cần thêm bộ lịch sử, ngày mơ hồ, câu hỏi ngoài miền và đối thoại độc lập đã duyệt.

## 7. LightRAG và HippoRAG2 — chỉ bật sau khi chuẩn bị đúng

1. Clone repository chính thức tại commit đã ghi trong `repository_audit.json`; cài **venv riêng** theo requirements upstream. HippoRAG2 pin Torch/Transformers khác môi trường Kaggle hiện có, không pip install đè vào venv Pháp Điển AI.
2. Trong `baselines.<tên>`, điền đường dẫn `repo`, `python`, `work_dir` riêng, commit thật, URL phục vụ LLM/embedding và tên biến môi trường key. Đặt `enabled=true`.
3. Embedding phải cùng trọng số/revision với `bundle/manifest.json.embedding_identity`. **Không mặc định Ollama `bge-m3` quantized = BAAI checkpoint trong artifact**. Có cầu nối đã viết sẵn, chạy trong môi trường Pháp Điển AI, giữ terminal/cell riêng hoạt động:

```powershell
python đo/evaluate_baselines.py embedding-server --bundle đo/work/bundle120 --cache đo/cache --device cuda:0 --port 8801
```

Cầu nối tải đúng revision từ artifact, dùng BGEM3FlagModel, max_length=1024, L2 normalization và precision giống Retriever. Nó chỉ lắng nghe localhost. Baseline venv gọi `http://127.0.0.1:8801/v1` với model `BAAI/bge-m3`. Đặt `embedding_model_identity` trong mỗi baseline thành object model/revision đọc từ manifest; runner còn đối chiếu `/identity` của server, không chỉ tin tên model. Key cho dịch vụ local có thể đặt `BASELINE_API_KEY=ollama` (giá trị giả cho giao thức, không phải key Gemini). Trên Kaggle, khởi chạy server bằng subprocess nền rồi đợi `/identity` trước lệnh đo; lưu stdout/stderr vào file và dừng đúng process do bạn tạo sau khi đo. Không mở server ra Internet.

Nếu muốn so embedding khác, tạo thí nghiệm riêng và nêu khác biệt, không dùng bảng controlled này. Cấu hình mẫu cố ý giữ placeholder identity nên không tự chạy nhầm trọng số.
4. Worker index **toàn bộ corpus**, không chỉ điều có trong Gold. LightRAG gắn file_path=unit_id và kiểm chunk nằm trong nguồn; HippoRAG gắn SOURCE_ID và đối chiếu toàn văn chính xác. Ánh xạ không chắc chắn là ERROR, không tìm gần đúng để được qrel hit. Worker có index manifest kiểm corpus/model/commit; thay dữ liệu/model phải dùng work_dir mới.
5. Chạy smoke riêng rồi mới tăng số câu:

```powershell
python đo/evaluate_baselines.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/light_ir_smoke --task retrieval --methods lightrag --limit 5 --allow-draft --allow-llm
python đo/evaluate_baselines.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/hippo_ir_smoke --task retrieval --methods hipporag2 --limit 5 --allow-draft --allow-llm
```

`--allow-llm` cần ngay cả retrieval vì trích xuất graph hoặc truy xuất upstream có thể gọi LLM. QA hai baseline này là **retrieval upstream + common reader**, không ghi là nguyên pipeline QA native. Thời gian xây graph nằm trong initialization, không lẫn thời gian query. Số model call HippoRAG upstream hiện N/A nếu không instrument được; tuyệt đối không gán 0.

## 8. LegalGraphRAG gốc

```powershell
python đo/evaluate_baselines.py original-ljp --repo "D:/data_thô/legalgraphrag/LegalGraphRAG" --results "D:/duong_dan/predictions_that.json" --out đo/results/chinese_ljp
```

Lệnh chấm prediction LJP thật bằng scorer gốc, copy input ra folder đo để không sửa repo gốc. Muốn tái hiện paper còn phải chạy đúng corpus/CAIL/CMDL, model, embedding, xây graph và cách chia tập của tác giả; xem README và `docs/TABLE2_REPRODUCTION.md` upstream. Không gọi metric charge/law/sentence accuracy là QA correctness Việt Nam. Framework hiện không tự tạo tập hình sự hay thích nghi nhãn tội danh sang lao động.

## 9. Tiếp tục và tổng hợp

```powershell
# Chạy lại đúng lệnh cũ, thêm --resume. Muốn thử lại lỗi kỹ thuật: thêm --retry-errors.
python đo/evaluate_project.py run --bundle đo/work/bundle120 --config đo/settings.local.json --out đo/results/ir_main --task retrieval --methods all --repeats 3 --k 10 --allow-draft --resume --retry-errors

python đo/evaluate_project.py report --runs đo/results/ir_main đo/results/baseline_ir --out đo/results/comparison_ir
python đo/evaluate_project.py report --runs đo/results/qa_main đo/results/naive_qa --out đo/results/comparison_qa
```

Giữ nguyên code, config, corpus, Gold, package/hardware và lịch. Run đổi chúng bị chặn resume. Sau quota reset dùng model cũ; đổi model tạo run mới. `responses.jsonl` ghi atomically sau mỗi câu; lỗi cũ chuyển `attempt_history.jsonl` khi retry. Trạng thái quota ở `progress.json`; không đổi ERROR/N/A thành COMPLETE. Kaggle qua phiên khác: đưa lại **cùng bundle, toàn run dir**, giữ environment/đường dẫn tương thích; nếu kiểm tra không khớp, tạo run mới. Không chỉ upload bảng CSV để resume.

Đầu ra chính:

- `run_manifest.json`: lịch cố định, cấu hình, Git/source hashes, package, hardware, fingerprint data/Gold, comparison key.
- `responses.jsonl`: câu hỏi, đáp án, claim, citation, tasks, trace, thời gian, tài nguyên, lỗi và judge từng câu.
- `methods/*/initialization.json`: cost chuẩn bị, model revisions và định nghĩa ablation.
- `report/comparison.md`, `.json`, `.csv`: bảng tổng hợp, mẫu số, số lỗi/chưa chạy/số được chấm.
- `report/paired_deltas.json/csv`: delta theo câu chung và CI bootstrap 95%; chỉ tạo khi cùng comparison key.
- `report/by_category.csv`, `component_exposure.json`: thành phần giúp/hại ở nhóm nào và thực sự đã chạy chưa.
- `report/human_review_template.jsonl`: mẫu chấm câu trả lời đã ẩn tên phương pháp; giữ file `human_review_key_KEEP_FROM_REVIEWERS.json` khỏi người chấm để duyệt mù. Điền nhận xét không tự biến Gold thành APPROVED.
- PNG cho recall nhóm, AI correctness, latency theo từng nhóm so sánh nếu có đủ số liệu và matplotlib.

## 10. Đọc số liệu đúng trước khi viết báo cáo

Precision@K = số ID liên quan trong top K / **K**, kể cả trả thiếu K; Recall@K = số ID liên quan tìm được / tổng ID qrel. MRR@K dùng hạng hit đầu; nDCG@K dùng binary relevance, không giả có graded qrels. Các ID nguồn thay thế cùng một yêu cầu còn có **group recall/nDCG/novel precision**: không thưởng hai lần cho hai bản cùng điều. Công bố rõ cả hai cách, vì qrels nhóm không phải nhãn relevance đầy đủ của mọi văn bản.

Trích dẫn chỉ chấm ID tồn tại, locator và URL **khớp metadata**, interval `[valid_from, valid_to)` và phần được duyệt hiệu lực. Không gọi đó là đã kiểm nguồn web, hiệu lực thực tế hoặc đúng ngữ nghĩa. Với Naive, locator/URL được dựng từ ID nên metric này chủ yếu kiểm ràng buộc kỹ thuật; dùng gold citation recall + kiểm entailment/AI/chuyên gia để đánh giá chất lượng. Nếu pipeline trả lời HTTP-thành-công nhưng trace cho thấy model/reviewer timeout hoặc unavailable và không còn claim, runner đánh **lỗi hạ tầng**, không chấm nhầm thành từ chối pháp lý. Lượt đã phục hồi và có claim được giữ lại cùng trace.

Latency mean/p50/p95 tính trên lượt thành công; lỗi, missing và N/A ghi riêng. RAM là RSS process tree của harness/worker, **không gồm Ollama đã chạy trước hay server Gemini**. GPU là sampled device-wide memory/utilization, gồm tác vụ khác; không gán thành VRAM riêng của một agent. Tần suất RAM 0,2 s, GPU khoảng 1 s; đo có overhead, không phải profiler kernel. Query không gồm startup/index/judge/HTTP/frontend.

`llm_calls` của Pháp Điển AI là số lần gọi structured provider được trace ghi nhận, có thể gồm lượt thất bại nhưng không tách từng HTTP retry bên trong SDK. Trace bị cắt thì trả N/A. LightRAG đếm callback LLM; HippoRAG chưa instrument được thì N/A. Không cộng chúng thành một số request API chính xác khi định nghĩa khác nhau.

Không cần Graph thắng ở mọi câu. Tra nguyên văn, so phiên bản, nối ngoại lệ và tìm vụ án có nhu cầu khác nhau. Đọc điểm theo nhóm, paired CI, lỗi và exposure. Nếu thêm thành phần làm tệ trên đúng nhóm nó được thiết kế hỗ trợ, ghi nhận thẳng và phân tích nguyên nhân. Một bảng trên DRAFT không đủ để chứng minh kiến trúc luôn tốt hơn.

Nguồn phương pháp tham khảo: [RAGAS](https://arxiv.org/abs/2309.15217), [RAGChecker](https://arxiv.org/abs/2408.08067), [giới hạn LLM-as-a-judge](https://arxiv.org/abs/2306.05685). Nguồn baseline chính thức và commit/hash nằm trong `repository_audit.json`. Bộ công cụ này tách retrieval/generation và dùng chấm độc lập theo tinh thần các nghiên cứu trên; **không tuyên bố tái hiện metric chính thức của chúng**.
