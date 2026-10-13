"""Generate the one-click, checkpoint-first Kaggle OFFLINE notebook."""
from __future__ import annotations


def make_notebook():
    cells = []

    def md(value: str) -> None:
        cells.append({"cell_type": "markdown", "metadata": {}, "source": value.splitlines(keepends=True)})

    def code(value: str) -> None:
        cells.append({"cell_type": "code", "metadata": {}, "source": value.splitlines(keepends=True),
                      "execution_count": None, "outputs": []})

    md("""# VN Labor — OFFLINE final build (checkpoint-first)

Notebook này dùng hai Kaggle Input Private: package code mới và một checkpoint `vn_labor_results.zip` mới nhất (hoặc V8.1 Aura).
Nó dùng checkpoint để phục hồi cache, chạy lại extraction chọn lọc theo page-v5, rồi dựng registry → structure →
knowledge → graph → Dense/BM25, lưu checkpoint kỹ thuật, chạy AI enrichment, nạp Aura, audit và xuất ZIP cuối.

Nếu Kaggle/Ollama lỗi sau khi checkpoint kỹ thuật đã tạo, Output vẫn có bản kỹ thuật hoàn chỉnh và thường có
thêm recovery ZIP chứa AI cache để tiếp tục ở phiên sau. Bật **GPU T4 x2**, **Internet** và bốn Aura Secrets.
""")
    code("""# System prerequisites must be installed before Python/package setup.
# Shell equivalents: !apt-get update -y ; !apt-get install -y zstd
import time as _clock
NOTEBOOK_STARTED = _clock.monotonic()
import subprocess as _system_setup
_system_setup.run(['apt-get', 'update', '-y'], check=True, timeout=300)
_system_setup.run(['apt-get', 'install', '-y', 'zstd'], check=True, timeout=300)
print('System prerequisite zstd: PASS', flush=True)
""")
    code("""RESTORE_ARCHIVE = "AUTO"
REFRESH_EXTRACTION_QUALITY = True
RUN_AI_ENRICHMENT = True
OFFLINE_AI_MODEL = "qwen3:8b"
OFFLINE_AI_MAX_PROVISIONS = 250
OFFLINE_AI_TIMEOUT_SECONDS = 240
LOAD_AURA = True
HEARTBEAT_SECONDS = 60
AI_STALL_SECONDS = 30 * 60
TOTAL_SECONDS = 10 * 60 * 60
""")

    md("""## 1. Xác minh Input, khôi phục checkpoint và cài môi trường

Build cài Docling/EasyOCR và chỉ OCR các trang mà kiểm tra text layer đánh dấu đáng ngờ. Trang sạch vẫn dùng native text.
""")
    code("""import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

matches = [p for p in Path('/kaggle/input').rglob('bundle_manifest.json')
           if (p.parent / 'kaggle/bootstrap.py').exists()]
if len(matches) != 1:
    raise RuntimeError('Cần đúng một Dataset package VN Labor mới; tìm thấy: ' + str(len(matches)))
source = matches[0].parent
bundle_revision = json.loads(matches[0].read_text(encoding='utf-8')).get('bundle_revision')
if bundle_revision != '20261012-footnote-provenance-v2':
    raise RuntimeError('Dataset code cũ: cần upload ZIP mới có revision 20261012-footnote-provenance-v2.')
print('Bundle revision:', bundle_revision, flush=True)

restore = RESTORE_ARCHIVE
if restore == 'AUTO':
    directories = sorted({p.parents[1] for p in Path('/kaggle/input').rglob('artifacts/00_manifest/files.jsonl')
                          if source not in p.parents})
    archives = sorted(Path('/kaggle/input').rglob('vn_labor_results*.zip'))
    candidates = directories or archives
    if len(candidates) != 1:
        raise RuntimeError('Cần đúng một checkpoint OFFLINE; tìm thấy: ' + str(len(candidates)))
    restore = str(candidates[0])
print('Checkpoint:', restore, flush=True)

spec = importlib.util.spec_from_file_location('vn_kaggle_bootstrap', source / 'kaggle/bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
ROOT = bootstrap.prepare(source, restore=restore)
PYTHON = bootstrap.install(ROOT, extras='ocr,retrieval,graph,community')
REPORTS = ROOT / 'artifacts/reports'
REPORTS.mkdir(parents=True, exist_ok=True)

def run_logged(arguments, name, extra_env=None, heartbeat_seconds=60,
               stall_seconds=None, total_seconds=None):
    environment = dict(os.environ)
    environment.setdefault('PYTHONUNBUFFERED', '1')
    if extra_env:
        environment.update(extra_env)
    logfile = REPORTS / name
    with logfile.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([str(PYTHON), *map(str, arguments)], cwd=ROOT, env=environment,
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        started = last_heartbeat = last_activity = time.monotonic()
        previous = {}
        previous_size = -1
        try:
            while process.poll() is None:
                time.sleep(5)
                now = time.monotonic()
                size = logfile.stat().st_size
                if size != previous_size:
                    previous_size = size
                    last_activity = now
                workflow_state = {}
                progress_state = {}
                build_progress = {}
                for marker, target in ((REPORTS / 'offline_final_run.json', workflow_state),
                                       (REPORTS / 'offline_ai_progress.json', progress_state),
                                       (REPORTS / 'offline_build_progress.json', build_progress)):
                    if marker.is_file():
                        try:
                            target.update(json.loads(marker.read_text(encoding='utf-8')))
                        except (OSError, json.JSONDecodeError):
                            pass
                state = dict(workflow_state)
                if workflow_state.get('stage') in {'technical_rebuild', 'extraction_quality_refresh'}:
                    state.update(build_progress)
                if workflow_state.get('stage') == 'ai_enrichment':
                    state.update(progress_state)
                if state != previous:
                    previous = state
                    last_activity = now
                if now - last_heartbeat >= heartbeat_seconds:
                    try:
                        gpu = subprocess.check_output(
                            ['nvidia-smi', '--query-gpu=index,utilization.gpu,memory.used,memory.total',
                             '--format=csv,noheader,nounits'], text=True, timeout=10).strip().replace('\\n', ' | ')
                    except Exception as exc:
                        gpu = 'unavailable:' + type(exc).__name__
                    cache = ROOT / 'artifacts/04_knowledge/ai_cache'
                    cache_count = sum(1 for _ in cache.glob('*.json')) if cache.is_dir() else 0
                    print(f"HEARTBEAT elapsed={int(now-started)}s stage={state.get('stage','starting')} "
                          f"progress={state.get('completed','?')}/{state.get('total','?')} "
                          f"ai={state.get('ai_attempted','?')}/{state.get('ai_planned','?')} "
                          f"cache={cache_count} idle={int(now-last_activity)}s gpu=[{gpu}]", flush=True)
                    last_heartbeat = now
                if (stall_seconds and state.get('stage') in {'case_ontology', 'checklists'}
                        and now - last_activity > stall_seconds):
                    raise TimeoutError('AI không tăng tiến độ trong giới hạn cho phép.')
                if total_seconds and now - started > total_seconds:
                    raise TimeoutError('OFFLINE build vượt giới hạn thời gian an toàn của notebook.')
            print(name, 'exit code:', process.returncode, flush=True)
            return process.returncode
        except BaseException:
            import signal
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
            raise

subprocess.run([str(PYTHON), 'kaggle/remote.py', 'configure'], cwd=ROOT, check=True)
# Guard the regression that previously failed only after a six-hour AI run. A
# stale code Dataset now stops here before Ollama is installed or invoked.
collision_probe = '''from vn_labor_offline.ai_requests import AIRequests,source_chunks
from vn_labor_offline.ai_preflight import probe
from vn_labor_offline.page_content import native_form_layer,validated_notes,segment_note_spans
from vn_labor_offline.integrity import require_complete_provenance
from vn_labor_offline.page_review import main as page_review_main
assert list(source_chunks('abc. tail',3500))==[(0,'abc. tail')]
from vn_labor_offline.checklists import CHECKLIST_ID_SCHEMA_VERSION,finalize_checklists
assert CHECKLIST_ID_SCHEMA_VERSION >= 2
base={'provision_id':'p','source_text':'same quote','provenance_status':'VERIFIED'}
rows=finalize_checklists([{**base,'type':'REQUIRED','generator':'heuristic'},
                          {**base,'type':'DEADLINE','generator':'structured-ai:qwen'}])
assert len(rows)==2 and len({row['checklist_id'] for row in rows})==2
'''
subprocess.run([str(PYTHON), '-c', collision_probe], cwd=ROOT, check=True)
print('Diagnostic ID collision regression: PASS', flush=True)
print('Bundle/checkpoint/environment: PASS', flush=True)
""")

    md("""## 2. Kiểm tra Aura Secrets và chuẩn bị Ollama

Ollama chỉ được cài khi bật AI. Với AI enrichment, notebook yêu cầu hai GPU để Dense dùng GPU 0 và Ollama dùng GPU 1.
""")
    code("""NEO4J_ENV = {}
if LOAD_AURA:
    from kaggle_secrets import UserSecretsClient
    client = UserSecretsClient()
    for name in ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'NEO4J_DATABASE'):
        try:
            NEO4J_ENV[name] = client.get_secret(name).strip()
        except Exception as exc:
            raise RuntimeError('Thiếu hoặc chưa cấp quyền Secret: ' + name) from exc
    if not all(NEO4J_ENV.values()) or not NEO4J_ENV['NEO4J_URI'].startswith('neo4j+s://'):
        raise RuntimeError('Aura Secrets không hợp lệ.')
    print('Aura Secrets: PRESENT (chưa xác minh kết nối); database =', NEO4J_ENV['NEO4J_DATABASE'], flush=True)

gpu_lines = subprocess.check_output(
    ['nvidia-smi', '--query-gpu=index,name', '--format=csv,noheader'], text=True).splitlines()
if not gpu_lines:
    raise RuntimeError('Chưa bật GPU trong Notebook Settings.')
if RUN_AI_ENRICHMENT and OFFLINE_AI_MAX_PROVISIONS > 0 and len(gpu_lines) < 2:
    raise RuntimeError('AI build mặc định yêu cầu GPU T4 x2; hãy tắt AI hoặc chọn T4 x2.')
print('GPU:', *gpu_lines, sep='\\n- ', flush=True)

AI_ENV = {**NEO4J_ENV,
    'VN_LABOR_OFFLINE_AI_PROVIDER': 'ollama',
    'VN_LABOR_OFFLINE_AI_URL': 'http://127.0.0.1:11434/api/chat',
    'VN_LABOR_OFFLINE_AI_MODEL': OFFLINE_AI_MODEL,
    'VN_LABOR_OFFLINE_AI_TIMEOUT_SECONDS': str(OFFLINE_AI_TIMEOUT_SECONDS),
}
if LOAD_AURA:
    # Credential/connectivity preflight is read-only, before the long build.
    result = subprocess.run(
        [str(PYTHON), 'kaggle/aura_preflight.py', '--report',
         str(REPORTS / 'aura_preflight.json')],
        cwd=ROOT, env=dict(os.environ, **NEO4J_ENV), timeout=180)
    if result.returncode:
        raise RuntimeError('Aura preflight chưa PASS. Xem reason_code ở trên hoặc aura_preflight.json. '
                           'Kiểm tra URI/Secrets; nếu muốn dựng OFFLINE trước, đặt LOAD_AURA = False.')
subprocess.run([str(PYTHON), 'kaggle/remote.py', 'preflight'], cwd=ROOT, check=True, timeout=3600)
print('Ollama will start AFTER the technical checkpoint export.', flush=True)
""")

    md("""## 3. Dựng lại OFFLINE, checkpoint, AI, Aura và export

Mốc `vn_labor_results_technical_checkpoint.zip` được tạo trước AI. Nếu cell thất bại, notebook cố xuất
`vn_labor_results_recovery.zip`; hãy giữ file đó để phiên sau tiếp tục từ AI cache.
""")
    code("""arguments = ['kaggle/offline_final_remote.py',
             '--ai-max-provisions', str(OFFLINE_AI_MAX_PROVISIONS)]
if REFRESH_EXTRACTION_QUALITY:
    arguments.append('--refresh-extraction')
if not RUN_AI_ENRICHMENT:
    arguments.append('--skip-ai')
if LOAD_AURA:
    arguments.append('--load-aura')

failure = None
try:
    result = run_logged(arguments, 'offline_final_build.log', AI_ENV,
                        heartbeat_seconds=HEARTBEAT_SECONDS,
                        stall_seconds=AI_STALL_SECONDS,
                        total_seconds=max(1, TOTAL_SECONDS - (time.monotonic() - NOTEBOOK_STARTED)))
    if result != 0:
        raise RuntimeError('OFFLINE final runner trả exit code ' + str(result))
except BaseException as exc:
    failure = exc
    marker = {'pipeline_exit_code': 1, 'stage': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}
    temporary = REPORTS / 'kaggle_run.json.tmp'
    temporary.write_text(json.dumps(marker), encoding='utf-8')
    os.replace(temporary, REPORTS / 'kaggle_run.json')
    # The runner normally exports recovery itself. This second attempt covers a
    # parent timeout that terminated the runner before its exception handler ran.
    try:
        subprocess.run([str(PYTHON), 'kaggle/remote.py', 'export',
                        '--archive-name', 'vn_labor_results_recovery.zip'], cwd=ROOT, check=False)
    except Exception:
        pass
finally:
    for key in list(NEO4J_ENV):
        NEO4J_ENV[key] = ''
    AI_ENV.clear()

if failure is not None:
    log = REPORTS / 'offline_final_build.log'
    if log.exists():
        print(log.read_text(encoding='utf-8', errors='replace')[-16000:])
    raise failure
""")

    md("""## 4. Kết quả

ZIP cuối chỉ được coi là PASS khi registry, structure, graph, Dense, BM25 và Aura cùng vượt audit.
`ONLINE-ready` vẫn có thể chưa đạt do human legal review, đây là trạng thái dữ liệu chứ không phải lỗi chạy.
""")
    code("""from IPython.display import FileLink, Markdown, display

state_path = REPORTS / 'offline_final_run.json'
if state_path.exists():
    print(state_path.read_text(encoding='utf-8'))
report = REPORTS / 'tong_hop_sau_chay.md'
if report.exists():
    display(Markdown(report.read_text(encoding='utf-8')))

outputs = []
for name in ('vn_labor_results.zip', 'vn_labor_results_technical_checkpoint.zip',
             'vn_labor_results_recovery.zip'):
    path = ROOT.parent / name
    if path.is_file():
        outputs.append(path)
        display(FileLink(str(path)))
        if Path(str(path)+'.sha256').is_file(): display(FileLink(str(path)+'.sha256'))
        print(name, round(path.stat().st_size / 1024**2, 1), 'MiB')
if not outputs:
    raise RuntimeError('Không có ZIP đầu ra.')
""")

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.13"},
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }
    for index, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), f"notebook-cell-{index}", "exec")
    return notebook
