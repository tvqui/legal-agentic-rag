"""Build a private upload bundle and beginner Notebook; never uploads or runs models."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build/kaggle'


def make_notebook():
    # Create the one-click V8.1 -> hybrid-AI -> Aura build notebook.
    cells = []
    def md(text):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(keepends=True)})
    def code(text):
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': text.splitlines(keepends=True),
                      'execution_count': None, 'outputs': []})

    md('''# VN Labor — OFFLINE AI one-click build

Notebook này dùng đúng hai Kaggle Input đã gắn: package `vn_labor_kaggle_v8.zip` và checkpoint
`vn_labor_results_v8.1(aura).zip`. Nó **không chạy lại OCR/Dense/BM25**. Một lần
**Save Version → Save & Run All** sẽ khôi phục V8.1, chạy Qwen3-8B ở chế độ `hybrid_ai`,
dựng lại knowledge/graph, nạp đúng build mới vào Aura, audit và xuất `vn_labor_results.zip`.

Notebook và hai Dataset phải là **Private**. Bật **GPU T4 x2** và **Internet**. Cấp quyền
cho bốn Kaggle Secrets: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
Không nhập secret trực tiếp vào cell.
''')
    code('''# Cấu hình one-click đã chốt. Không bật full pipeline trong notebook này.
RESTORE_ARCHIVE = "AUTO"
OFFLINE_AI_MODE = "hybrid_ai"
OFFLINE_AI_MODEL = "qwen3:8b"
LOAD_AURA = True
''')

    md('''## 1. Xác minh hai Input, khôi phục checkpoint và cài môi trường

Cell sẽ dừng nếu có thiếu/thừa package hoặc checkpoint. Output cũ không bị ghi vào Kaggle Input;
mọi thay đổi nằm trong `/kaggle/working`.
''')
    code('''import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

matches = list(Path('/kaggle/input').rglob('bundle_manifest.json'))
matches = [p for p in matches if (p.parent / 'kaggle/bootstrap.py').exists()]
if len(matches) != 1:
    raise RuntimeError('Cần đúng một Dataset package VN Labor; tìm thấy: ' + str(len(matches)))
source = matches[0].parent

restore = RESTORE_ARCHIVE
if restore == 'AUTO':
    restored = sorted({p.parents[1] for p in Path('/kaggle/input').rglob('artifacts/00_manifest/files.jsonl')
                       if source not in p.parents})
    if not restored:
        restored = sorted(Path('/kaggle/input').rglob('vn_labor_results*.zip'))
    if len(restored) != 1:
        raise RuntimeError('Cần đúng một checkpoint V8.1; tìm thấy: ' + str(len(restored)))
    restore = str(restored[0])
print('Checkpoint:', restore)

spec = importlib.util.spec_from_file_location('vn_kaggle_bootstrap', source / 'kaggle/bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
ROOT = bootstrap.prepare(source, restore=restore)
PYTHON = bootstrap.install(ROOT)
REPORTS = ROOT / 'artifacts/reports'
REPORTS.mkdir(parents=True, exist_ok=True)

def run_logged(arguments, name, extra_env=None):
    environment = dict(os.environ)
    if extra_env:
        environment.update(extra_env)
    logfile = REPORTS / name
    with logfile.open('w', encoding='utf-8') as output:
        process = subprocess.Popen(
            [str(PYTHON), *map(str, arguments)], cwd=ROOT, env=environment,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            last = ''
            while process.poll() is None:
                time.sleep(5)
                with logfile.open('rb') as tail:
                    tail.seek(max(0, logfile.stat().st_size - 2400))
                    lines = tail.read().decode('utf-8', errors='replace').replace('\\r', '\\n').strip().splitlines()
                latest = lines[-1] if lines else 'Đang xử lý...'
                if latest != last:
                    print(latest[:500], flush=True)
                    last = latest
            print(name, 'exit code:', process.returncode, flush=True)
            return process.returncode
        except BaseException:
            import signal
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
            raise

subprocess.run([str(PYTHON), 'kaggle/remote.py', 'configure'], cwd=ROOT, check=True)
print('Bundle verified. Project:', ROOT)
''')

    md('''## 2. Kiểm checkpoint, GPU và Aura Secrets trước khi chạy model

Secret chỉ được chuyển vào subprocess nạp Aura và không được in ra log.
''')
    code('''required_artifacts = (
    'artifacts/03_structure/provisions.jsonl',
    'artifacts/03_structure/cases.jsonl',
    'artifacts/05_graph/nodes.jsonl',
    'artifacts/06_indexes/retrieval_units.jsonl',
    'artifacts/reports/dense_validation.json',
)
missing = [name for name in required_artifacts if not (ROOT / name).is_file()]
if missing:
    raise RuntimeError('Checkpoint thiếu file: ' + ', '.join(missing))

gpu_lines = subprocess.check_output(
    ['nvidia-smi', '--query-gpu=index,name', '--format=csv,noheader'], text=True
).splitlines()
if not gpu_lines:
    raise RuntimeError('Chưa bật GPU trong Notebook Settings.')
print('GPU:', *gpu_lines, sep='\\n- ')

NEO4J_ENV = {}
if LOAD_AURA:
    from kaggle_secrets import UserSecretsClient
    secret_client = UserSecretsClient()
    for name in ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'NEO4J_DATABASE'):
        try:
            NEO4J_ENV[name] = secret_client.get_secret(name).strip()
        except Exception as exc:
            raise RuntimeError('Thiếu hoặc Notebook chưa được cấp quyền Secret: ' + name) from exc
    if not all(NEO4J_ENV.values()):
        raise RuntimeError('Một Neo4j Secret đang rỗng.')
    if not NEO4J_ENV['NEO4J_URI'].startswith('neo4j+s://'):
        raise RuntimeError('NEO4J_URI phải bắt đầu bằng neo4j+s://')
    print('Aura Secrets: OK; database =', NEO4J_ENV['NEO4J_DATABASE'])
''')

    md('''## 3. Khởi động Ollama trên GPU riêng và tải Qwen3-8B

Cảnh báo `systemd is not running` của installer là bình thường trên Kaggle.
''')
    code('''if not shutil.which('ollama'):
    installer = Path('/tmp/install_ollama.sh')
    urllib.request.urlretrieve('https://ollama.com/install.sh', installer)
    subprocess.run(['bash', str(installer)], check=True)

ollama_gpu = '1' if len(gpu_lines) > 1 else '0'
OLLAMA_ENV = dict(
    os.environ,
    OLLAMA_HOST='127.0.0.1:11434',
    OLLAMA_MODELS='/kaggle/working/ollama_models',
    CUDA_VISIBLE_DEVICES=ollama_gpu,
)
OLLAMA_PROCESS = None
OLLAMA_LOG_HANDLE = None
try:
    urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2).close()
    print('Ollama đã chạy.')
except Exception:
    OLLAMA_LOG_HANDLE = open('/kaggle/working/ollama-offline.log', 'w', encoding='utf-8')
    OLLAMA_PROCESS = subprocess.Popen(
        ['ollama', 'serve'], env=OLLAMA_ENV, stdout=OLLAMA_LOG_HANDLE,
        stderr=subprocess.STDOUT, start_new_session=True,
    )
    for _ in range(90):
        if OLLAMA_PROCESS.poll() is not None:
            raise RuntimeError('Ollama dừng sớm; xem /kaggle/working/ollama-offline.log')
        try:
            urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2).close()
            break
        except Exception:
            time.sleep(2)
    else:
        raise RuntimeError('Ollama không khởi động; xem /kaggle/working/ollama-offline.log')

PULL_LOG_PATH = Path('/kaggle/working/ollama-pull.log')
PULL_STALL_SECONDS = 15 * 60
PULL_TOTAL_SECONDS = 90 * 60
with PULL_LOG_PATH.open('w', encoding='utf-8') as pull_log:
    pull_process = subprocess.Popen(
        ['ollama', 'pull', OFFLINE_AI_MODEL], env=OLLAMA_ENV,
        stdout=pull_log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    pull_started = pull_activity = last_printed = time.monotonic()
    previous_size = -1
    try:
        while pull_process.poll() is None:
            time.sleep(10)
            size = PULL_LOG_PATH.stat().st_size
            now = time.monotonic()
            if size != previous_size:
                previous_size = size
                pull_activity = now
            if now - last_printed >= 20:
                with PULL_LOG_PATH.open('rb') as tail:
                    tail.seek(max(0, size - 2000))
                    lines = tail.read().decode('utf-8', errors='replace').replace('\\r', '\\n').strip().splitlines()
                print('Ollama pull:', (lines[-1] if lines else 'đang kết nối...')[:500], flush=True)
                last_printed = now
            if now - pull_activity > PULL_STALL_SECONDS:
                raise TimeoutError('ollama pull không tạo thêm log trong 15 phút')
            if now - pull_started > PULL_TOTAL_SECONDS:
                raise TimeoutError('ollama pull vượt quá 90 phút')
    except BaseException:
        if pull_process.poll() is None:
            pull_process.terminate()
            try:
                pull_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pull_process.kill()
        raise

if pull_process.returncode != 0:
    print(PULL_LOG_PATH.read_text(encoding='utf-8', errors='replace')[-12000:])
    raise RuntimeError('ollama pull thất bại với exit code ' + str(pull_process.returncode))

with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=10) as response:
    installed = json.loads(response.read()).get('models', [])
installed_names = {str(item.get('name') or '') for item in installed}
if not any(name == OFFLINE_AI_MODEL or name.startswith(OFFLINE_AI_MODEL + '-') for name in installed_names):
    raise RuntimeError('Ollama API không xác nhận model đã tải: ' + OFFLINE_AI_MODEL)
print(OFFLINE_AI_MODEL, 'sẵn sàng trên GPU', ollama_gpu)
''')

    md('''## 4. Enrichment → graph → Aura → audit → export

Đây là bước dài nhất. Log được ghi vào file thay vì đẩy toàn bộ ra Notebook để tránh tăng RAM.
Nếu lỗi, cell in phần cuối của log rồi dừng; không báo PASS giả.
''')
    code('''AI_ENV = {
    'VN_LABOR_OFFLINE_AI_PROVIDER': 'ollama',
    'VN_LABOR_OFFLINE_AI_URL': 'http://127.0.0.1:11434/api/chat',
    'VN_LABOR_OFFLINE_AI_MODEL': OFFLINE_AI_MODEL,
    'VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS': '300',
    **NEO4J_ENV,
}
arguments = ['kaggle/offline_ai_remote.py', '--mode', OFFLINE_AI_MODE]
if LOAD_AURA:
    arguments.append('--load-aura')

try:
    result = run_logged(arguments, 'offline_ai_build.log', AI_ENV)
    if result != 0:
        log = REPORTS / 'offline_ai_build.log'
        print(log.read_text(encoding='utf-8', errors='replace')[-16000:])
        raise RuntimeError('OFFLINE AI one-click build thất bại; xem log ở trên.')
finally:
    for key in list(NEO4J_ENV):
        NEO4J_ENV[key] = ''
    AI_ENV.clear()
    if OLLAMA_PROCESS is not None and OLLAMA_PROCESS.poll() is None:
        OLLAMA_PROCESS.terminate()
        try:
            OLLAMA_PROCESS.wait(timeout=15)
        except subprocess.TimeoutExpired:
            OLLAMA_PROCESS.kill()
    if OLLAMA_LOG_HANDLE is not None:
        OLLAMA_LOG_HANDLE.close()

validation = json.loads((REPORTS / 'final_outputs_validation.json').read_text(encoding='utf-8'))
neo4j = json.loads((REPORTS / 'neo4j_validation.json').read_text(encoding='utf-8'))
if not validation.get('ready_for_offline_v1'):
    raise RuntimeError('Bốn đầu ra OFFLINE chưa PASS; xem final_outputs_validation.json.')
if neo4j.get('passed') is not True:
    raise RuntimeError('Aura validation chưa PASS; xem neo4j_validation.json.')
print('OFFLINE v1 technical build: PASS')
print('Build ID:', neo4j.get('build_id'))
''')

    md('''## 5. Báo cáo và file tải

`ONLINE-ready` có thể vẫn `CHƯA ĐẠT` do human review chưa hoàn tất. Điều đó không làm hỏng
technical build; backend phải tiếp tục chạy ở provisional mode và giữ cảnh báo.
''')
    code('''from collections import Counter
from IPython.display import FileLink, Markdown, display

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

report = REPORTS / 'tong_hop_sau_chay.md'
if report.exists():
    display(Markdown(report.read_text(encoding='utf-8')))
archive = ROOT.parent / 'vn_labor_results.zip'
if not archive.is_file():
    raise RuntimeError('Thiếu vn_labor_results.zip dù build đã hoàn tất.')
display(FileLink(str(archive)))
print('Output:', archive)
print('Size MiB:', round(archive.stat().st_size / 1024**2, 1))
print('Nếu link không tải được, chờ Save Version hoàn tất rồi tải trong tab Output.')
''')

    return {'cells': cells, 'metadata': {
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.12.13'}},
        'nbformat': 4, 'nbformat_minor': 4}


def write_notebook():
    DEST.mkdir(parents=True, exist_ok=True)
    notebook = make_notebook()
    for i, cell in enumerate(notebook['cells']):
        if cell['cell_type'] == 'code':
            compile(''.join(cell['source']), f'cell-{i}', 'exec')
    destination = DEST / 'VN_Labor_Kaggle_V8.ipynb'
    destination.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'notebook': str(destination), 'code_syntax': 'PASS', 'workflow': 'V8.1_HYBRID_AI_AURA_ONE_CLICK'}, ensure_ascii=False, indent=2))
    return destination


def build():
    DEST.mkdir(parents=True, exist_ok=True)
    files = {}
    for folder, suffixes in [('src', {'.py'}), ('config', {'.yaml', '.json'}), ('review/templates', {'.json', '.jsonl'}),
                             ('kaggle', {'.py', '.txt'}),
                             ('tests', {'.py'}), ('review/attachments', {'.pdf'}), ('data', {'.pdf', '.doc', '.docx', '.html', '.htm', '.txt', '.json'})]:
        for p in sorted((ROOT / folder).rglob('*')):
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in suffixes and '__pycache__' not in p.parts:
                files[p.relative_to(ROOT).as_posix()] = p
    for name in ['pyproject.toml', 'scripts/prepare_dense_model.py', 'scripts/validate_outputs.py', 'scripts/package_kaggle.py',
                 'scripts/prepare_source_attachments.py', 'scripts/review_kaggle_extraction.py',
                 'scripts/evaluate_gold.py', 'scripts/prepare_review_inputs.py', 'scripts/pin_online_artifact.py']:
        files[name] = ROOT / name
    converted = []
    stems = set()
    for raw in sorted((ROOT / 'data').rglob('*')):
        if raw.suffix.lower() != '.doc':
            continue
        if raw.stem.casefold() in stems:
            raise ValueError('DOC names collide; conversion cache needs a path-aware mapping first.')
        stems.add(raw.stem.casefold())
        cached = ROOT / 'artifacts/01_extracted/converted_docx' / (raw.stem + '.docx')
        if not cached.exists():
            raise FileNotFoundError(f'Convert this DOC locally before packaging: {raw.name}')
        seed = 'seed_converted/' + cached.name
        files[seed] = cached
        converted.append({'source': raw.relative_to(ROOT).as_posix(), 'seed': seed, 'output_name': cached.name})
    entries = []
    for name, p in sorted(files.items()):
        with p.open('rb') as f:
            sha = hashlib.file_digest(f, 'sha256').hexdigest()
        entries.append({'path': name, 'bytes': p.stat().st_size, 'sha256': sha})
    manifest = {'schema': 1, 'owner': 'qutrnvinh3', 'privacy': 'PRIVATE',
                'corpus_files': sum(n.startswith('data/') for n in files),
                'converted_docs': converted, 'files': entries}
    archive = DEST / 'vn_labor_kaggle_v8.zip'
    temporary = archive.with_suffix('.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for name, p in sorted(files.items()):
            z.write(p, 'vn_labor_bundle/' + name)
        z.writestr('vn_labor_bundle/bundle_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(temporary) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f'Bad ZIP member: {bad}')
    try:
        temporary.replace(archive)
    except PermissionError:
        # A package created by another Windows identity may be locked/read-only.
        # Preserve the new build instead of deleting or overwriting it.
        archive = DEST / 'vn_labor_kaggle_v8_rebuilt.zip'
        temporary.replace(archive)
    write_notebook()
    with archive.open('rb') as stream:
        archive_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'bundle': archive.name, 'sha256': archive_sha256,
              'size_mb': round(archive.stat().st_size / 1e6, 2),
              'files': len(files), 'corpus_files': manifest['corpus_files'], 'converted_docs': len(converted),
              'zip_crc_check': 'PASS', 'notebook_code_syntax': 'PASS', 'uploaded': False, 'remote_execution_tested': False}
    (DEST / 'package_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notebook-only', action='store_true')
    arguments = parser.parse_args()
    write_notebook() if arguments.notebook_only else build()
