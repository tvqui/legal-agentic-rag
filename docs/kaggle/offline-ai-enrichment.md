> Cập nhật 12/10/2026: xem [hướng dẫn sửa AI và chất lượng trang](offline-quality-upgrade-20261012.md).
> Dùng notebook/ZIP code mới cùng checkpoint kết quả ngày 12/10. Timeout mới 240 giây, chunk 3.500 byte; không tăng số provision trước khi kiểm tra báo cáo AI.

# Chạy OFFLINE hoàn chỉnh trên Kaggle trong khi tiếp tục kiểm thử ONLINE

Quy trình này dành cho repository hiện tại (bản sửa 10/10/2026). Nó phục hồi checkpoint V8.1,
kiểm lại cache và chạy extraction theo cấu hình hiện tại. Cache khác schema/cấu hình hoặc bị hỏng sẽ
được tạo lại; phiên đầu có thể cần OCR lại nhiều trang. Sau đó dựng lại toàn bộ phần phụ thuộc:

`Document Registry → Structured Provisions → Knowledge/Version Graph → Dense + BM25 → Aura`

ONLINE trên máy local vẫn có thể tiếp tục dùng `vn_labor_results_v8.1(aura).zip` trong lúc Kaggle chạy.
Chỉ thay artifact ONLINE sau khi ZIP mới đã hoàn tất và vượt kiểm tra.

## Thiết kế chống mất một phiên chạy dài

Notebook mới chạy theo các mốc sau:

1. Xác minh SHA của package và đối chiếu file ID giữa corpus với extraction checkpoint.
2. Chấp nhận môi trường Kaggle Python 3.12 hoặc 3.13 và ghim Torch theo container hiện tại.
3. Chạy selective OCR/page audit, dừng sớm nếu extraction có lỗi. Dựng lại toàn bộ artifact bằng parser/code hiện tại, gồm Dense và BM25.
4. Audit toàn bộ đầu ra local.
5. Xuất `vn_labor_results_technical_checkpoint.zip` **trước khi chạy AI**.
6. Cài/tải và khởi động Ollama **sau khi đã lưu checkpoint kỹ thuật**, chạy `hybrid_ai` tối đa 250 provision. Bản án dài được chia thành các đoạn bao phủ cả phần quyết định; mỗi phản hồi hợp lệ được ghi cache nguyên tử.
7. Nạp graph cuối vào Aura, kiểm build ID và audit bốn đầu ra.
8. Xuất `vn_labor_results.zip`.

Nếu AI gặp lỗi sau khi bước 5 đã hoàn tất, file technical checkpoint đã được ghi trên đĩa. Việc file xuất hiện trong Output còn phụ thuộc Kaggle hoàn tất/lưu phiên; Stop hoặc hạ tầng kill phiên có thể không giữ output. Notebook cũng cố tạo
`vn_labor_results_recovery.zip`, chứa cache AI đã hoàn thành để phiên sau tiếp tục.

Không chương trình nào có thể bảo đảm 100% trước lỗi hạ tầng Kaggle, mất Internet hoặc Aura tạm ngừng.
Code dừng khi audit không có báo cáo mới, thiếu stage hoặc còn lỗi kỹ thuật. Technical PASS và AI COMPLETE được báo riêng; không dùng PASS kỹ thuật để chứng nhận AI hoặc tính đúng pháp lý.

## Hai file cần upload

1. `build/kaggle/vn_labor_kaggle_v8.zip` — package mới vừa tạo từ repository hiện tại.
2. `vn_labor_results_v8.1(aura).zip` — checkpoint cũ đã PASS kỹ thuật.

Tạo hoặc cập nhật hai **Private Dataset** riêng trên Kaggle. Không upload `.env`, mật khẩu Aura,
virtual environment, model cache hoặc token.

Sau khi cập nhật Dataset code, vào trang Dataset và kiểm tra timestamp/version mới. Xóa Input code cũ khỏi
Notebook rồi Add Input lại nếu Kaggle vẫn ghim phiên bản Dataset cũ.

## Bốn Kaggle Secrets bắt buộc

Trong Notebook, mở **Add-ons → Secrets** và cấp quyền cho:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

Bốn Secrets chỉ bắt buộc khi `LOAD_AURA = True`. `NEO4J_USER` thường là `neo4j`.
`NEO4J_URI` lấy nguyên Connection URI từ instance hiện tại trong Aura Console.
`NEO4J_DATABASE` là **tên database**, không phải ID instance trong hostname. Đối chiếu trường
database trong credentials/Console; không suy ra từ URL. Tên mặc định thường là `neo4j`, nhưng
phải dùng tên thực tế của instance. Theo [tài liệu kết nối Aura](https://neo4j.com/docs/aura/getting-started/connect-instance/),
URI/credentials và tên database cần được lấy từ instance tương ứng.

## Tạo và chạy Notebook

1. Import `build/kaggle/VN_Labor_Kaggle_V8.ipynb` vào Kaggle.
2. Add Input đúng hai Private Dataset nói trên.
3. Mở **Settings**:
   - Accelerator: **GPU T4 x2**.
   - Internet: **On**.
   - Notebook: **Private**.
4. Không gắn thêm checkpoint OFFLINE thứ hai; chế độ `AUTO` yêu cầu đúng một checkpoint.
5. Chọn **Save Version → Save & Run All**.

Không cần chạy từng cell. Không bấm Stop Session trong khi version đang chạy.

## Cấu hình mặc định đã chọn

```python
RESTORE_ARCHIVE = "AUTO"
REFRESH_EXTRACTION_QUALITY = True
RUN_AI_ENRICHMENT = True
OFFLINE_AI_MODEL = "qwen3:8b"
OFFLINE_AI_MAX_PROVISIONS = 250
LOAD_AURA = True
TOTAL_SECONDS = 10 * 60 * 60
```

250 là giới hạn số provision được AI tinh chỉnh trong phiên đầu, không phải giới hạn dữ liệu pháp luật.
Toàn bộ provision vẫn được parse, đưa vào graph, Dense/BM25 và có checklist heuristic khi phù hợp.
Giới hạn này tránh lặp lại lần chạy 2.000 provision đã vượt 8 giờ.

Nếu ưu tiên chắc chắn hoàn tất technical build hơn AI, đổi duy nhất:

```python
RUN_AI_ENRICHMENT = False
```

Bản này vẫn là OFFLINE technical build đầy đủ; nó chỉ không có lớp tinh chỉnh checklist/case ontology bằng Qwen.

## Thời gian dự kiến

Thời gian phụ thuộc Kaggle và tốc độ model:

- Chuẩn bị môi trường + BGE-M3: khoảng 10–40 phút.
- Rebuild structure/graph/Dense/BM25: phụ thuộc số trang cần OCR; có thể lâu hơn 3 giờ nếu nhiều PDF scan. Chưa đo thời gian bản này trên Kaggle.
- Qwen3-8B cho 250 provision và case ontology: thường khoảng 1–6 giờ.
- Aura + audit + nén ZIP: khoảng 10–60 phút.

Mục tiêu là hoàn tất trong 10 giờ. Đây là ước lượng, không phải cam kết thời gian của Kaggle.

## Kiểm tra khi chạy nền

Trong trang Version đang chạy, mở **Logs**. Heartbeat khoảng mỗi phút có dạng:

```text
HEARTBEAT elapsed=... stage=... progress=.../... ai=.../... cache=... idle=... gpu=[...]
```

Các stage hợp lệ:

- `technical_rebuild`
- `technical_checkpoint`
- `ai_enrichment`, `case_ontology`, `checklists`
- `ai_complete`
- `aura_load`
- `complete`

Log pip có dòng `dependency resolver ... conflicts` về package có sẵn của Kaggle không tự động là lỗi.
Chỉ kết luận lỗi khi cell/runner có traceback hoặc exit code khác 0.

Notebook theo dõi tiến độ mỗi phút; nếu AI không tăng tiến độ 30 phút thì dừng. Ngân sách 10 giờ được tính từ cell đầu, gồm thời gian setup đã dùng; runner dừng theo thời gian còn lại. Cài dependency, preflight và tải Ollama có timeout riêng. Dừng có kiểm soát cố tạo recovery; Kaggle kill đột ngột không được bảo đảm khôi phục.

## File cần tải sau khi chạy

Trong tab **Output**:

- `vn_labor_results.zip`: kết quả cuối, chỉ xuất sau quy trình hoàn tất.
- `vn_labor_results_technical_checkpoint.zip`: bản kỹ thuật được lưu trước AI.
- `vn_labor_results_recovery.zip`: chỉ xuất khi có lỗi hoặc timeout; dùng để tiếp tục.
- Các file `.zip.sha256` tương ứng: dùng kiểm tra tệp tải về.
- Log đầy đủ trong `vn_labor_project/artifacts/reports/offline_final_build.log`.

Ưu tiên tải `vn_labor_results.zip`. Đổi tên local thành một tên version rõ ràng, ví dụ
`vn_labor_results_v9_final_aura.zip`, nhưng không sửa nội dung ZIP.

## Dấu hiệu thành công

Mở `artifacts/reports/offline_final_run.json` trong ZIP. Kết quả cuối phải có:

```json
{
  "status": "PASS",
  "stage": "complete"
}
```

Đồng thời:

- `final_outputs_validation.json.ready_for_offline_v1 = true`
- registry, structure, graph, indexes đều PASS
- `neo4j_validation.json.passed = true`
- build ID local và Aura giống nhau
- `kaggle_run.json.pipeline_exit_code = 0`

`offline_final_run.json.quality_status` cho biết `AI_COMPLETE`, `AI_DEGRADED` hoặc `HEURISTIC_ONLY`. `AI_COMPLETE` chỉ có nghĩa kế hoạch AI trong phiên đã hoàn tất, không phải mọi provision đều qua AI hoặc human review. Kiểm `case_ai_quality.json` và `checklist_ai_quality.json`; các lỗi, fallback và phần bị bỏ qua được ghi rõ.

`offline_ready_for_online` có thể vẫn là `false` vì human legal review/Gold chưa xong. Đây không phải lỗi kỹ thuật.
ONLINE vẫn dùng provisional mode và phải giữ cảnh báo cho người dùng.

## Nếu phiên chạy lỗi hoặc hết giờ

1. Tải `vn_labor_results_recovery.zip` nếu có.
2. Nếu recovery không có, tải `vn_labor_results_technical_checkpoint.zip`.
3. Tạo Private Dataset checkpoint mới từ ZIP đó.
4. Ở Notebook phiên sau, thay Input checkpoint V8.1 bằng checkpoint mới; vẫn chỉ gắn một checkpoint.
5. Save Version → Save & Run All lại.

Cache AI nằm trong `artifacts/04_knowledge/ai_cache`. Những prompt/model/source đã hoàn thành sẽ được dùng lại.
Sau khi phiên 250 hoàn tất, có thể tăng `OFFLINE_AI_MAX_PROVISIONS` lên 500; 250 mục đầu sẽ đọc cache và
AI chỉ cần xử lý phần mới. Chỉ tăng theo từng nấc khi còn quota.

## Trong lúc Kaggle chạy

Giữ backend/frontend local dùng artifact V8.1 hiện tại và tiếp tục:

1. chạy bộ test ONLINE;
2. kiểm tra các câu hỏi Gold/edge case;
3. sửa query analysis, applicability, evidence coverage, generation và citation;
4. không đổi schema artifact OFFLINE nếu không thật sự cần.

Khi ZIP mới PASS, pin artifact mới vào ONLINE, chạy lại regression/evaluation rồi mới thay build đang dùng.
# Kiểm tra chất lượng extraction theo trang

Notebook mới chạy `apt-get update -y` và cài `zstd` trước mọi bước Python. Khi
`REFRESH_EXTRACTION_QUALITY = True`, checkpoint cũ vẫn được dùng để phục hồi,
nhưng extraction được cập nhật theo schema `page-v5-quality-audit` trước khi
dựng lại structure/graph/index. Việc này có thể làm phiên đầu tiên lâu hơn.

Pipeline kiểm `cleaned_chars` trên từng trang, phát hiện text layer có ký tự
lỗi/control, tỷ lệ chữ-số thấp, ký tự lặp bất thường và dòng trùng. Với trang
đã OCR, native text và OCR text được so bằng token overlap và tỷ lệ độ dài;
kết quả dài hơn không tự động được coi là đúng hơn. Trang đáng ngờ có preview
giới hạn 96 DPI, tối đa 12 trang mỗi tài liệu.

Các đầu ra để kiểm tra sau khi chạy:

- `artifacts/01_extracted/page_audit.jsonl`
- `artifacts/01_extracted/suspicious_page_previews/`
- `artifacts/review_queues/page_extraction_review.jsonl`
- `artifacts/reports/page_extraction_quality.json`

`ERROR` (ví dụ mất sạch nội dung sau cleaning hoặc OCR thất bại) làm technical
validation fail. `REVIEW_REQUIRED` được giữ trong hàng đợi và không bị tự động
phê duyệt hoặc tự động thay nội dung pháp lý.


## Đối chiếu trước khi upload — 10/10/2026

Đã sửa trực tiếp trong `D:/data_thô/legal-agentic-rag`. Notebook và ZIP trong `build/kaggle/`
được tạo lại từ source hiện tại; upload lại Dataset code, không dùng ZIP cũ đã có trên Kaggle.
`ai-v9-1.ipynb` và `VN_Labor_Kaggle_V8.ipynb` là hai tên của cùng nội dung, chỉ import **một** notebook.

Đã replay bằng CPU trên extraction của 95 tài liệu V8.1 trong thư mục tạm, không chạy mô hình:

- 18.871 provision được parser hiện tại giữ lại; cả 18.871 đều có retrieval unit.
- 19.160 retrieval units, gồm provision, bản án và segment; V8.1 có 18.624 units.
- Các khoản ngắn 1/3/4 Điều 124 và điểm a khoản 2 Điều 62 của 18/VBHN-VPQH xuất hiện lại.
- Đây là số từ text cũ. OCR mới có thể làm số lượng thay đổi; không yêu cầu phải bằng đúng các số này.

Chi tiết: `artifacts/reports/offline_kaggle_cpu_replay_20261010.json`.
Không sửa hoặc ghi đè ZIP V8.1, corpus, quyết định reviewer hay dữ liệu Aura trong kiểm tra local này.

## Giới hạn nội dung cần xử lý riêng

Corpus hiện tại chưa có các số văn bản `91/2025/QH15`, `51/2024/QH15`, `64/2025/QH15`.
Đây là khoảng trống đã xuất hiện trong rà soát ONLINE; chạy lại 95 tài liệu không tự bổ sung chúng.
Nếu bổ sung sau, cần đúng nguồn, metadata/hiệu lực và review; tạo package mới rồi rebuild từ corpus mới.
Không gắn text trích từ AI hoặc đổi cờ verified để thay việc bổ sung nguồn.

Dense vẫn dùng giới hạn 1.024 token cho mỗi đơn vị: văn bản dài có thể bị cắt khi tạo vector.
BM25/retrieval metadata giữ đầy đủ text và ngữ cảnh cha; không dùng vector để chứng nhận đủ nội dung.
AI chỉ tinh chỉnh subset 250 provision và các đoạn bản án; không chứng nhận legal changes,
quarantine, hiệu lực điều khoản hay độ chính xác ngữ nghĩa thay người duyệt.

Nếu ONLINE đang dùng cùng Aura instance, `LOAD_AURA = True` sẽ thay graph của dataset khi build hoàn tất.
Muốn giữ nguyên graph đang phục vụ trong lúc kiểm thử, đặt `LOAD_AURA = False`; ZIP khi đó là build
local chưa xác minh Aura. Nạp và audit Aura sau khi đã chọn được build để chuyển ONLINE đồng bộ.

Sau lần chạy, gửi `vn_labor_results.zip` cùng `.sha256`. Nếu lỗi, gửi recovery ZIP và log;
không thay artifact ONLINE bằng bản recovery chưa vượt audit.


## Lỗi Aura DNS ở preflight — 11/10/2026

Nếu thấy `DNS_UNRESOLVED` hoặc `Failed to DNS resolve address ...`, lỗi xảy ra trước
extraction/Dense/AI: hostname Aura chưa phân giải được. Secret tồn tại không chứng minh URI đúng,
mật khẩu đúng hay database tồn tại. Bản mới ghi `aura_preflight.json`, thử tối đa ba lần và
phân biệt DNS, authentication, database name, connection; chỉ chạy `RETURN 1`, không nạp graph.
Tiến trình kiểm tra bị giới hạn 180 giây bởi notebook.

1. Trong Aura Console, mở đúng instance, kiểm trạng thái Running và copy Connection URI.
2. Sửa `NEO4J_URI` trong Kaggle Secrets; giữ `neo4j+s://`. Kiểm tên database riêng.
3. Bật Internet và cấp quyền Secrets. Không đổi sang IP hay bỏ kiểm chứng TLS.
4. Nếu cần dựng dữ liệu ngay, đặt `LOAD_AURA = False` ở cell cấu hình.
   Với Save & Run All bị lỗi, chọn Edit, đổi cấu hình, Save Version → Save & Run All cho phiên mới.
   Không chạy lại cell restore vào thư mục artifacts đã có dữ liệu trong cùng session.

`LOAD_AURA = False` vẫn chạy extraction/structure/graph/Dense/BM25/AI và xuất ZIP, nhưng **chưa
nạp/xác minh Aura**. Local technical checks có thể PASS trong `offline_final_run.json`, còn
`ready_for_offline_v1`/summary vẫn chưa PASS đầy đủ do thiếu live Neo4j verification.

Nếu build đã hoàn tất trong session còn sống, sau khi sửa kết nối có thể nạp/audit lại graph
đã sinh mà không dựng lại OCR/Dense/AI. Thêm cell sau (chỉ chạy khi sẵn sàng thay graph đang phục vụ):

```python
from kaggle_secrets import UserSecretsClient
client = UserSecretsClient()
names = ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'NEO4J_DATABASE')
aura_env = dict(os.environ)
try:
    aura_env.update({name: client.get_secret(name).strip() for name in names})
    subprocess.run([str(PYTHON), 'kaggle/aura_preflight.py', '--report',
                    str(REPORTS / 'aura_preflight.json')],
                   cwd=ROOT, env=aura_env, check=True, timeout=180)
    subprocess.run([str(PYTHON), 'kaggle/remote.py', 'aura'],
                   cwd=ROOT, env=aura_env, check=True, timeout=1800)
    subprocess.run([str(PYTHON), 'kaggle/remote.py', 'export'],
                   cwd=ROOT, check=True, timeout=600)
finally:
    aura_env.clear()
```

Cell này chỉ dùng trên **package mới có `aura_preflight.py`**, sau build hoàn tất; nó không tự
phục hồi session đã đóng. Nếu session đã kết thúc, cần restore ZIP kết quả trong phiên mới,
chuẩn bị environment bằng bootstrap rồi chạy preflight/nạp/audit/export, không chạy lại runner rebuild.
Luôn kiểm build ID mới và báo cáo validation trước khi chuyển ONLINE.


## Tiếp tục từ recovery extraction ngày 11/10/2026

Lần chạy vừa gửi đã trích xuất đủ 95 tài liệu/3.116 trang. Một lỗi quality gate xuất hiện ở
trang 5 `judicial_corpus/cassation_decisions/02-2021-LĐ-GĐT.pdf`: native và OCR đều chỉ đọc
được số trang `5`; cleaning bỏ số đó, nhưng audit nhầm thành mất nội dung.
Ảnh nguồn đã được đối chiếu với đúng SHA corpus. Đây không phải lỗi timeout, CUDA hay Aura.

Code mới chỉ miễn lỗi EMPTY_AFTER_CLEANING khi native/OCR cùng là đúng số trang vật lý,
tất cả text nằm ở lề trên/dưới và PDF không có ảnh/vector khác. Bằng chứng hình học được
ghi trong provenance/page_audit; trạng thái giữ REVIEW_REQUIRED, không tự ghi reviewer.
Số ở giữa trang, scan có ảnh, mất body text và OCR thất bại vẫn bị chặn.
Không thay OCR/settings/schema cache, nên cache hợp lệ của 94 tài liệu được giữ khả năng dùng lại.

Cách chạy tiếp:

1. Upload lại `build/kaggle/vn_labor_kaggle_v8.zip` vào Private Dataset code và chọn version mới.
2. Tạo Private Dataset checkpoint từ `vn_labor_results_recovery.zip` bạn vừa tải.
3. Import lại `build/kaggle/VN_Labor_Kaggle_V8.ipynb` mới.
4. Add Input gồm **code mới + recovery checkpoint**. Gỡ Input checkpoint V8.1 cũ;
   `RESTORE_ARCHIVE = "AUTO"` chỉ được có một checkpoint.
5. Giữ `REFRESH_EXTRACTION_QUALITY = True`. Đừng bỏ extraction audit bằng cách tắt cờ này.
6. Nếu `LOAD_AURA = True`, đợi Aura chuyển Running, kiểm Secrets trước khi Save & Run All.
7. Chạy bằng session mới: bootstrap không ghi đè thư mục artifacts đang có dữ liệu.

Recovery chứa 94 document cache của schema hiện tại và page cache cho tài liệu còn lại.
Đừng đổi OCR/cleaning settings nếu muốn dùng lại cache. Dữ liệu vẫn đi qua kiểm tra SHA,
attachment/review và integrity trước khi rebuild. Đây là tiếp tục build, không coi recovery
là artifact đủ điều kiện chuyển ONLINE.
