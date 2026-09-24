"""Build a private upload bundle and beginner Notebook; never uploads or runs models."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build/kaggle'


def make_notebook():
    cells = []
    def md(text):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(keepends=True)})
    def code(text):
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': text.splitlines(keepends=True),
                      'execution_count': None, 'outputs': []})
    md('''# VN Labor — chạy trên Kaggle
Notebook và Dataset phải để **Private**. Bật **GPU T4 x2** và **Internet**.
Thêm Dataset chứa package V8 qua **Add Input** trước khi chạy, cùng một Dataset checkpoint kết quả 7.3.
Code sử dụng GPU 0 theo từng bước; GPU 1 chưa dùng. Máy local chỉ upload/download.
Không nhập mật khẩu/token vào các cell. Aura là bước tùy chọn, dùng Kaggle Secrets.
''')
    code('''# V8 chạy tiếp từ đúng một checkpoint kết quả 7.3.
RUN_PIPELINE = True
LOAD_AURA = False
RESTORE_ARCHIVE = "AUTO"
''')
    md('''## 1. Xác minh dữ liệu và cài môi trường riêng
Giữ nguyên PyTorch/CUDA do Kaggle cung cấp; cài thư viện còn lại trong môi trường riêng.
Model được tải ở server. Bước này có thể mất vài phút.
''')
    code('''import importlib.util
import json
from pathlib import Path
import subprocess
import time

matches = list(Path('/kaggle/input').rglob('bundle_manifest.json'))
matches = [p for p in matches if (p.parent / 'kaggle/bootstrap.py').exists()]
if len(matches) != 1:
    raise RuntimeError('Hãy Add Input đúng một Dataset code/corpus V8; tìm thấy: ' + str(len(matches)))
source = matches[0].parent
restore = RESTORE_ARCHIVE
if restore == 'AUTO':
    restored = [p.parents[1] for p in Path('/kaggle/input').rglob('artifacts/00_manifest/files.jsonl')
                if source not in p.parents]
    if not restored:
        restored = list(Path('/kaggle/input').rglob('vn_labor_results*.zip'))
    if len(restored) != 1:
        raise RuntimeError('RESTORE_ARCHIVE="AUTO" cần đúng một Dataset checkpoint; tìm thấy: ' + str(len(restored)))
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
    import os
    environment = dict(os.environ)
    if extra_env:
        environment.update(extra_env)
    logfile = REPORTS / name
    # Stream to a file to avoid unbounded Notebook output/RAM; print progress periodically.
    with logfile.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([str(PYTHON), *map(str, arguments)], cwd=ROOT,
                                   env=environment, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            last = ''
            while process.poll() is None:
                time.sleep(5)
                with logfile.open('rb') as tail:
                    tail.seek(max(0, logfile.stat().st_size - 1800))
                    lines = tail.read().decode('utf-8', errors='replace').replace('\\r', '\\n').strip().splitlines()
                latest = lines[-1] if lines else 'Đang xử lý...'
                if latest != last:
                    print(latest[:400], flush=True)
                    last = latest
            print(name, 'exit code:', process.returncode)
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
''')
    md('''## 2. Kiểm tra GPU, DOCX và model
Chỉ chạy khi RUN_PIPELINE=True. Không chạy toàn corpus nếu bước này lỗi.
''')
    code('''if RUN_PIPELINE:
    result = run_logged(['kaggle/remote.py', 'preflight'], 'kaggle_preflight.log')
    if result != 0:
        print((REPORTS / 'kaggle_preflight.log').read_text(encoding='utf-8')[-6000:])
        raise RuntimeError('Preflight lỗi; gửi log này để kiểm tra. Chưa chạy pipeline.')
else:
    print('Bỏ qua preflight model vì chỉ kiểm tra/nạp kết quả có sẵn.')
''')
    md('''## 3. Chạy pipeline và tạo báo cáo
OCR và Dense dùng GPU. Metadata, parsing, BM25 chạy trên CPU **của Kaggle**.
Nếu có lỗi dữ liệu, báo cáo sẽ ghi FAIL; không tự sửa nguồn hay metadata.
''')
    code('''if RUN_PIPELINE:
    started = time.time()
    result = run_logged(['-m', 'vn_labor_offline.cli', 'all', '--config', 'config/kaggle.yaml'], 'run_all_offline.log')
    (REPORTS / 'kaggle_run.json').write_text(json.dumps({
        'pipeline_exit_code': result, 'elapsed_seconds': round(time.time() - started, 1),
        'execution': 'Kaggle GPU 0',
    }, indent=2), encoding='utf-8')
else:
    if not (ROOT / 'artifacts/05_graph/nodes.jsonl').exists():
        raise RuntimeError('Chưa có graph. Bật RUN_PIPELINE hoặc khôi phục kết quả cũ.')
try:
    run_logged(['kaggle/remote.py', 'audit'], 'kaggle_audit.log')
finally:
    subprocess.run([str(PYTHON), 'kaggle/remote.py', 'export'], cwd=ROOT, check=True)
if RUN_PIPELINE and result != 0:
    print('Pipeline có lỗi thực thi. Kết quả một phần và log đã được đóng gói; xem Output.')
''')
    md('''## 4. Neo4j Aura — nạp sau khi dựng dữ liệu
Graph 7.3 có 50.272 nodes/80.912 relationships và đã nạp được vào Aura. Trước khi nạp
graph V8 mới, xem số node/edge trong summary để kiểm tra quota của instance hiện tại.
Nếu đã có artifacts V8 và muốn chỉ nạp Aura, đặt RUN_PIPELINE=False, LOAD_AURA=True;
không chạy lại OCR/Dense/BM25. Với database đã cấu hình, vào
**Add-ons → Secrets**, tạo và cấp quyền cho Notebook các secret:
`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
URI có dạng `neo4j+s://....databases.neo4j.io`; user thường là `neo4j`.
NEO4J_DATABASE lấy đúng tên database trong credentials/Aura, không phải tên hiển thị instance.
Sau đó đặt LOAD_AURA=True. Nếu đã có artifacts, đặt RUN_PIPELINE=False để tránh chạy OCR lại.
Loader thay dataset của dự án trong database này; không tự chuyển/xóa DB legacy trên máy bạn.
''')
    code('''if LOAD_AURA:
    from kaggle_secrets import UserSecretsClient
    secret_client = UserSecretsClient()
    credentials = {name: secret_client.get_secret(name)
                   for name in ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD')}
    credentials['NEO4J_DATABASE'] = secret_client.get_secret('NEO4J_DATABASE').strip()
    if not credentials['NEO4J_DATABASE']:
        raise ValueError('NEO4J_DATABASE phải là tên database trong credentials/Aura.')
    try:
        result_aura = run_logged(['kaggle/remote.py', 'aura'], 'neo4j_load.log', credentials)
        print('Aura:', 'load and audit completed' if result_aura == 0 else 'failed; see neo4j_load.log')
    finally:
        credentials.clear()
        subprocess.run([str(PYTHON), 'kaggle/remote.py', 'export'], cwd=ROOT, check=True)
else:
    print('Chưa nạp Aura. Graph export vẫn có; Graph DB chưa được xác minh, không coi OFFLINE v1 là PASS.')
''')
    md('''## 5. Xem báo cáo, lưu phiên và tải kết quả
Sau khi chạy các cell thành công, dùng **Save Version → Save & Run All** để có lần chạy nền
được Kaggle lưu Output. Lần Save & Run All là một phiên mới, có thể chạy lại từ đầu.
Để tránh chạy hai lần toàn corpus: sau khi kiểm tra cell 2 thành công, có thể chọn Save & Run All ngay.
Chờ phiên lưu kết thúc, mở tab **Output** và tải `vn_labor_results.zip`.
Trong ZIP có `artifacts/reports/tong_hop_sau_chay.md`, các báo cáo chi tiết và checkpoint.
Model, môi trường Python và secrets không nằm trong ZIP.
Khi phiên bị hết giờ đột ngột, không bảo đảm cell export đã chạy: cần lưu checkpoint/output
kịp thời; có thể chạy cell export riêng trước khi dừng phiên chủ động.
''')
    code('''from IPython.display import FileLink, Markdown, display
report = REPORTS / 'tong_hop_sau_chay.md'
if report.exists():
    display(Markdown(report.read_text(encoding='utf-8')))
archive = ROOT.parent / 'vn_labor_results.zip'
if archive.exists():
    display(FileLink(str(archive)))
    print('Nếu link không tải được, dùng tab Output sau khi Save Version hoàn tất.')
''')
    return {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                                       'language_info': {'name': 'python', 'version': '3.12.13'}},
            'nbformat': 4, 'nbformat_minor': 4}


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
                 'scripts/evaluate_gold.py', 'scripts/prepare_review_inputs.py']:
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
    notebook = make_notebook()
    for i, cell in enumerate(notebook['cells']):
        if cell['cell_type'] == 'code':
            compile(''.join(cell['source']), f'cell-{i}', 'exec')
    (DEST / 'VN_Labor_Kaggle_V8.ipynb').write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding='utf-8')
    with archive.open('rb') as stream:
        archive_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'bundle': archive.name, 'sha256': archive_sha256,
              'size_mb': round(archive.stat().st_size / 1e6, 2),
              'files': len(files), 'corpus_files': manifest['corpus_files'], 'converted_docs': len(converted),
              'zip_crc_check': 'PASS', 'notebook_code_syntax': 'PASS', 'uploaded': False, 'remote_execution_tested': False}
    (DEST / 'package_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build()
