# Tạo OFFLINE build chất lượng cao hơn trên Kaggle

Quy trình này bắt đầu từ checkpoint `vn_labor_results_v8.1(aura).zip`. Nó không OCR lại 95 tài liệu và không dựng lại Dense/BM25 nếu retrieval units không đổi. Nó chạy lại phần tri thức bằng Qwen3-8B, dựng lại graph, audit, nạp đúng graph mới vào Aura và xuất một ZIP kết quả mới.

## 1. Chọn chế độ

- `hybrid_ai` — **khuyến nghị chạy trước**: giữ checklist heuristic khi đã tạo được; chỉ gọi AI cho provision chưa có checklist heuristic. Case ontology vẫn được enrichment bằng AI.
- `ai` — vòng thử nghiệm sau: gọi AI cho mọi provision đủ dài; nếu một lời gọi lỗi hoặc không có exact quote hợp lệ thì fallback về heuristic.

Mọi checklist/feature do AI tạo chỉ được nhận khi có `source_quote` xuất hiện trong nguồn và provenance được resolve. AI không được tự phê duyệt metadata, temporal hoặc nguồn pháp lý.

## 2. Chuẩn bị trên máy local

Cần hai file:

1. `D:\data_thô\legal-agentic-rag\build\kaggle\vn_labor_kaggle_v8.zip`
2. Checkpoint đã PASS Aura: `vn_labor_results_v8.1(aura).zip`

SHA-256 của package code hiện tại:

```text
ba8028ecde4c2df9804c59f5c5fb16e117562e5773460add1e06de53c1b649c1
```

Không upload `.env`, API key, Neo4j password, cache model hoặc `.venv`.

## 3. Tạo hai Kaggle Dataset Private

### Dataset code

1. Vào Kaggle → **Datasets** → **New Dataset**.
2. Upload `vn_labor_kaggle_v8.zip`.
3. Đặt tên, ví dụ `vn-labor-kaggle-v8-ai`.
4. Chọn **Private** rồi tạo Dataset.

Kaggle thường tự giải nén ZIP. Trong Input phải nhìn thấy `vn_labor_bundle/bundle_manifest.json`, `src/`, `config/` và `kaggle/`.

### Dataset checkpoint

Nếu checkpoint V8.1 đã tồn tại trên Kaggle thì dùng lại. Nếu chưa có:

1. Tạo Dataset Private thứ hai.
2. Upload `vn_labor_results_v8.1(aura).zip`.
3. Đặt tên, ví dụ `vn-labor-results-v8-1-aura`.

Trong Input phải nhìn thấy `artifacts/00_manifest`, `artifacts/03_structure`, `artifacts/05_graph`, `artifacts/06_indexes` và `artifacts/reports`.

## 4. Tạo Notebook

1. Tạo Notebook mới hoặc import `build/kaggle/VN_Labor_Kaggle_V8.ipynb`.
2. Trong **Add Input**, thêm đúng hai Dataset ở trên.
3. Trong **Settings**:
   - Accelerator: **GPU T4 x2** nếu có; một GPU vẫn chạy được nhưng chậm hơn.
   - Internet: **On**.
   - Notebook/Dataset: **Private**.
4. Không gắn thêm checkpoint OFFLINE khác trong cùng notebook vì chế độ `AUTO` yêu cầu đúng một checkpoint.

Trong cell cấu hình đầu tiên đặt:

```python
RUN_PIPELINE = False
LOAD_AURA = False
RESTORE_ARCHIVE = "AUTO"
```

Chạy cell bootstrap/cài môi trường của notebook. Kết quả đúng phải có dạng:

```text
Checkpoint: .../artifacts
Bundle verified: 96 corpus files.
Project: /kaggle/working/vn_labor_project
```

Sau đó kiểm tra checkpoint:

```python
assert (ROOT / 'artifacts/03_structure/provisions.jsonl').is_file()
assert (ROOT / 'artifacts/05_graph/nodes.jsonl').is_file()
assert (ROOT / 'artifacts/06_indexes/retrieval_units.jsonl').is_file()
print('ROOT =', ROOT)
print('PYTHON =', PYTHON)
```

Không chạy `vn_labor_offline.cli all`; lệnh đó sẽ chạy lại toàn bộ pipeline.

## 5. Cài và khởi động Ollama/Qwen3-8B

Thêm một cell mới sau bootstrap:

```python
import os
import subprocess
import time
import urllib.request
from pathlib import Path

subprocess.run(
    'curl -fsSL https://ollama.com/install.sh | sh',
    shell=True,
    check=True,
)

gpu_lines = subprocess.check_output(
    ['nvidia-smi', '--query-gpu=index', '--format=csv,noheader'],
    text=True,
).splitlines()
ollama_gpu = '1' if len(gpu_lines) > 1 else '0'
ollama_env = dict(
    os.environ,
    OLLAMA_HOST='127.0.0.1:11434',
    OLLAMA_MODELS='/kaggle/working/ollama_models',
    CUDA_VISIBLE_DEVICES=ollama_gpu,
)

try:
    urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2)
    ollama = None
    print('Ollama đã chạy.')
except Exception:
    ollama_log = open('/kaggle/working/ollama-offline.log', 'w', encoding='utf-8')
    ollama = subprocess.Popen(
        ['ollama', 'serve'],
        env=ollama_env,
        stdout=ollama_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2)
            break
        except Exception:
            time.sleep(2)
    else:
        raise RuntimeError('Ollama không khởi động; xem /kaggle/working/ollama-offline.log')

subprocess.run(['ollama', 'pull', 'qwen3:8b'], env=ollama_env, check=True)
print('Qwen3-8B sẵn sàng trên GPU', ollama_gpu)
```

Cảnh báo `systemd is not running` khi cài Ollama trên Kaggle là bình thường vì server được khởi động trực tiếp bằng `ollama serve`.

## 6. Chạy `hybrid_ai`

Dùng `run_logged` đã được định nghĩa trong cell bootstrap để tránh output notebook quá lớn:

```python
ai_env = {
    'VN_LABOR_OFFLINE_AI_PROVIDER': 'ollama',
    'VN_LABOR_OFFLINE_AI_URL': 'http://127.0.0.1:11434/api/chat',
    'VN_LABOR_OFFLINE_AI_MODEL': 'qwen3:8b',
    'VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS': '300',
}

result = run_logged(
    ['kaggle/offline_ai_remote.py', '--mode', 'hybrid_ai'],
    'offline_ai_enrichment.log',
    ai_env,
)
if result != 0:
    log = ROOT / 'artifacts/reports/offline_ai_enrichment.log'
    print(log.read_text(encoding='utf-8', errors='replace')[-12000:])
    raise RuntimeError('OFFLINE AI enrichment thất bại')
```

Lần chạy lại trong cùng session sử dụng `.cache/offline_ai`, nên các record đã hoàn tất không phải gọi model lại.

## 7. Kiểm tra kết quả AI trước khi nạp Aura

```python
import json
from collections import Counter

def read_jsonl(path):
    with path.open(encoding='utf-8-sig') as stream:
        return [json.loads(line) for line in stream if line.strip()]

checklists = read_jsonl(ROOT / 'artifacts/04_knowledge/diagnostic_checklists.jsonl')
cases = read_jsonl(ROOT / 'artifacts/03_structure/cases.jsonl')
print('Checklist generators:', Counter(row.get('generator') for row in checklists))
print('Verified checklist:', sum(row.get('provenance_status') == 'VERIFIED' for row in checklists), '/', len(checklists))
print('AI case features:', sum(
    str(feature.get('generator', '')).startswith('structured-ai:')
    for case in cases for feature in case.get('features', [])
))

for name in ('offline_ai_enrichment.json', 'final_outputs_validation.json', 'summary.json'):
    path = ROOT / 'artifacts/reports' / name
    if path.exists():
        print('\n---', name, '---')
        print(path.read_text(encoding='utf-8', errors='replace')[:8000])
```

Trước khi nạp Aura, audit có thể báo `STALE_NEO4J_BUILD` hoặc `NEO4J_BUILD_NOT_VERIFIED`. Đây là trạng thái dự kiến vì graph vừa thay đổi nhưng Aura vẫn còn build cũ. Các lỗi cấu trúc, provenance, Dense/BM25 hoặc graph khác vẫn phải được xử lý trước khi tiếp tục.

## 8. Nạp graph mới vào Aura

Trong **Add-ons → Secrets**, bảo đảm notebook được cấp quyền đọc:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

Không cần xóa thủ công instance cũ. Loader thay dataset thuộc dự án trong đúng database.

Chạy cell:

```python
from kaggle_secrets import UserSecretsClient

secret_client = UserSecretsClient()
neo4j_env = {
    name: secret_client.get_secret(name).strip()
    for name in ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'NEO4J_DATABASE')
}
if not neo4j_env['NEO4J_URI'].startswith('neo4j+s://'):
    raise ValueError('NEO4J_URI phải bắt đầu bằng neo4j+s://')
if not all(neo4j_env.values()):
    raise ValueError('Thiếu Neo4j Secret')

result = run_logged(['kaggle/remote.py', 'aura'], 'neo4j_load.log', neo4j_env)
if result != 0:
    log = ROOT / 'artifacts/reports/neo4j_load.log'
    print(log.read_text(encoding='utf-8', errors='replace')[-12000:])
    raise RuntimeError('Nạp Aura thất bại')

subprocess.run([str(PYTHON), 'kaggle/remote.py', 'export'], cwd=ROOT, check=True)
```

Kết quả cuối cần thỏa:

- `registry = PASS`
- `structure = PASS`
- `graph = PASS`
- `indexes = PASS`
- `neo4j_validation.json.passed = true`
- Graph và Aura có cùng build ID

`ONLINE-ready` vẫn có thể là `CHƯA ĐẠT` vì source/temporal/Gold human review chưa hoàn tất. Điều đó không có nghĩa enrichment thất bại; ONLINE có thể tiếp tục ở provisional mode và phải giữ cảnh báo.

## 9. Tải kết quả

```python
from IPython.display import FileLink, display

archive = ROOT.parent / 'vn_labor_results.zip'
assert archive.is_file()
display(FileLink(str(archive)))
print('Size MiB:', round(archive.stat().st_size / 1024**2, 1))
```

Tải `vn_labor_results.zip` về máy. Nên đổi tên thành `vn_labor_results_v9_ai_aura.zip` để không ghi đè V8.1 trước khi test ONLINE.

Nếu bấm **Save & Run All**, Kaggle sẽ tạo một phiên mới và chạy lại toàn bộ cell. Sau khi đã chạy tương tác thành công, tải ZIP trực tiếp bằng link trên để tránh tiêu tốn thêm quota.

## 10. Đưa build mới vào ONLINE

1. Upload ZIP mới thành một Dataset Private mới.
2. Mở notebook ONLINE, thêm Dataset đó làm Input.
3. Cập nhật repository:

```bash
cd /kaggle/working/legal-agentic-rag
git pull --ff-only
python -m pip install -q -e ".[retrieval,online,llm,community]" ngrok
```

4. Tìm thư mục artifact và tạo config pin:

```python
from pathlib import Path
import subprocess

markers = list(Path('/kaggle/input').rglob('artifacts/reports/final_outputs_validation.json'))
if len(markers) != 1:
    raise RuntimeError('Cần đúng một Dataset kết quả OFFLINE mới; tìm thấy: ' + str(len(markers)))
ARTIFACT = markers[0].parents[2]

subprocess.run([
    'python', 'scripts/pin_online_artifact.py',
    '--artifact', str(ARTIFACT),
    '--output', '/kaggle/working/online_pinned.yaml',
], check=True)
```

5. Chạy backend bằng đúng artifact/config vừa pin. Gọi bằng `subprocess.run` vì `ARTIFACT` là biến Python:

```python
subprocess.run([
    'python', 'kaggle/online_remote.py',
    '--artifact', str(ARTIFACT),
    '--config', '/kaggle/working/online_pinned.yaml',
], check=True)
```

## 11. Khi nào thử chế độ `ai`

Chỉ chạy sau khi hybrid đã hoàn tất và được giữ làm mốc so sánh:

```python
result = run_logged(
    ['kaggle/offline_ai_remote.py', '--mode', 'ai'],
    'offline_ai_full.log',
    ai_env,
)
```

Không thay production build chỉ vì số checklist tăng. So sánh hai build trên cùng Gold set bằng recall@k, MRR/nDCG, fact accuracy, applicability accuracy, citation precision, temporal accuracy và abstention correctness. Giữ build hybrid nếu full-AI không cải thiện rõ ràng hoặc tạo nhiều review queue hơn.

## 12. Xử lý lỗi thường gặp

- `Restore the V8.1 checkpoint before enrichment`: checkpoint chưa được Add Input hoặc chưa chạy cell bootstrap.
- `found 0`/`found 2`: thiếu Input hoặc đang gắn nhiều checkpoint/package cùng lúc.
- `Connection refused 127.0.0.1:11434`: Ollama chưa chạy; xem `/kaggle/working/ollama-offline.log`.
- `Missing Kaggle Secret`: tạo secret và bật quyền cho notebook.
- `DatabaseNotFound`: `NEO4J_DATABASE` sai; dùng đúng database name/ID trong credentials Aura.
- `STALE_NEO4J_BUILD`: graph mới chưa được nạp Aura; chạy bước 8.
- Notebook hết thời gian: tải/export checkpoint hiện có; không xóa cache trong session. Chạy `hybrid_ai` trước thay vì `ai`.
- CUDA OOM: bảo đảm Ollama dùng GPU 1; nếu chỉ có một GPU, dùng Qwen nhỏ hơn là thay đổi cần đánh giá lại, không tự coi tương đương Qwen3-8B.
