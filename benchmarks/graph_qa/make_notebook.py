"""Build the standalone paired Graph-QA Kaggle notebook; no API calls here."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def markdown(text):
    return {'cell_type':'markdown','metadata':{},'source':text.strip().splitlines(keepends=True)}

def code(text):
    return {'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],
            'source':text.strip().splitlines(keepends=True)}

def notebook():
    cells=[markdown("""
# Pháp Điển AI — Graph QA đối chứng trên Kaggle

Mục tiêu: kiểm tra **khi nào mở rộng Graph giúp tìm đủ căn cứ và trả lời tốt hơn**.
Bản v3 dùng Auditor hybrid theo nhóm và warmup riêng và ghim ngân sách 360 giây/câu, 120 giây/lần gọi; không gộp với run v1 có ngân sách cũ. Hai nhánh chỉ khác `graph.enabled`; không gộp kết quả với phép đo BM25 hoặc replay cũ.
Artifact hiện chốt đến **15/09/2026**; giữ đúng query_date đã ghim, không tự đổi thành ngày chạy. Bộ nhãn được đóng băng trước khi suy luận. Nhãn kiểm bằng artifact vẫn là **DRAFT**, không tự coi là đã duyệt pháp lý.

**Trước Run All:** bật Internet, chọn GPU T4 ×2; Add Input một artifact OFFLINE cuối. Mặc định lấy code từ GitHub, không cần ZIP code; ZIP chỉ dùng khi chọn attached_zip.
Bật Secret `GEMINI_API_KEY` nếu giữ semantic review hoặc AI-judge; `HF_TOKEN` tùy chọn. Không cần Groq/coding-team key, frontend, ngrok hay Neo4j.
Dừng backend và workload khác dùng GPU hoặc quota trước khi đo.
Mặc định lấy code GitHub. Bắt đầu `PROFILE='smoke'`. Sau smoke, đặt `PROFILE='standard'` và giữ thư mục output riêng.
"""),code(r"""
from pathlib import Path
SOURCE = 'github'       # attached_zip | github
CODE_ZIP = 'auto'            # hoặc đường dẫn ZIP / thư mục chứa package_manifest.json
REPO_URL = 'https://github.com/tvqui/legal-agentic-rag.git'
CODE_ROOT = Path('/kaggle/working/graph_qa_code')
WORK = Path('/kaggle/working/graph_qa_evaluation')
PROFILE = 'smoke'            # smoke | standard
RUN_NAME = 'graph_qa_v3'
ARTIFACT = 'auto'            # hoặc đường dẫn ZIP / thư mục artifacts trong /kaggle/input
RESUME = False               # True chỉ khi code/data/settings/model vẫn y nguyên
RETRY_ERRORS = False         # không tự đo lại câu từ chối/partial
LLM_MODEL = 'qwen3:8b'
REVIEW_MODEL = 'gemini-3.1-flash-lite'
SEMANTIC_REVIEW = True
JUDGE_ENABLED = False        # generation không chấm AI trong latency trả lời
RUN_AI_JUDGE = True          # chấm riêng sau generation; cùng model reviewer, không độc lập về mô hình
REPETITIONS = 1
ALLOW_EXISTING_OLLAMA = False
REQUEST_TIMEOUT_SECONDS = 360  # tổng mỗi câu, giống nhau ở cả hai nhánh
PROVIDER_TIMEOUT_SECONDS = 120 # gọi model; ngân sách thành phần được chốt trong manifest
STARTUP_TIMEOUT_SECONDS = 300  # chỉ nạp/warmup, không tính vào latency QA
if SOURCE not in {'attached_zip','github'}: raise ValueError('SOURCE không hợp lệ')
if PROFILE not in {'smoke','standard'}: raise ValueError('PROFILE không hợp lệ')
if not RUN_NAME or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in RUN_NAME):
    raise ValueError('RUN_NAME chỉ chứa chữ, số, gạch dưới hoặc gạch ngang')
if type(REPETITIONS) is not int or REPETITIONS < 1: raise ValueError('REPETITIONS phải là số nguyên dương')
OUT = WORK / RUN_NAME / PROFILE
LOGS = WORK / 'notebook_logs' / RUN_NAME / PROFILE
SETTINGS = WORK / 'settings' / RUN_NAME / (PROFILE+'.json')
RESULT_ZIP = WORK / (RUN_NAME+'_'+PROFILE+'_results.zip')
"""),markdown("""
## 1. Công cụ chạy và log

Mỗi bước có log riêng và heartbeat khi chạy lâu. Helper chỉ dừng tiến trình do chính bước đó tạo.
Không in giá trị Secrets. Lỗi API trong kết quả phải được xem cùng trạng thái, không xóa lỗi để tăng điểm.
"""),code(r"""
import os, sys, subprocess, shutil, json, time, threading, queue, re, hashlib
import zipfile, stat, urllib.request
from pathlib import PurePosixPath
WORK.mkdir(parents=True,exist_ok=True)
LOGS.mkdir(parents=True,exist_ok=True)

def safe_line(value):
    for key in ('GEMINI_API_KEY','HF_TOKEN'):
        secret=os.environ.get(key)
        if secret: value=value.replace(secret,'[REDACTED]')
    return re.sub(r'(?:AIza[A-Za-z0-9_-]{25,}|hf_[A-Za-z0-9]{15,})','[REDACTED]',value)

def run_step(arguments,name,timeout=1200,cwd=None,check=True,env=None):
    path=LOGS/(name+'.log')
    print('BẮT ĐẦU:',name,'log:',path,flush=True)
    started=time.monotonic(); heartbeat=started
    process=subprocess.Popen(list(map(str,arguments)),cwd=cwd,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    messages=queue.Queue()
    def reader():
        try:
            for line in process.stdout: messages.put(line)
        finally: messages.put(None)
    thread=threading.Thread(target=reader,daemon=True); thread.start()
    ended=False
    try:
        with path.open('a',encoding='utf-8') as log:
            log.write('\nSTEP '+name+'\n')
            while not ended or process.poll() is None:
                try:
                    line=messages.get(timeout=1)
                    if line is None: ended=True
                    else:
                        clean=safe_line(line); log.write(clean);log.flush();print(clean,end='',flush=True)
                except queue.Empty: pass
                now=time.monotonic()
                if now-heartbeat>=30:
                    text='HEARTBEAT '+name+' elapsed='+str(round(now-started))+'s\n'
                    print(text,end='',flush=True);log.write(text);log.flush();heartbeat=now
                if timeout is not None and now-started>timeout:
                    raise TimeoutError(name+' vượt thời gian, xem '+str(path))
            result=process.wait()
        if check and result:
            show_diagnostics(name)
            tail=path.read_text(encoding='utf-8',errors='replace').splitlines()
            reason=next((line for line in reversed(tail) if 'Evaluation stopped:' in line), 'Xem chẩn đoán ngay phía trên')
            raise RuntimeError(name+' thất bại, exit='+str(result)+'; '+safe_line(reason)+'; log: '+str(path))
        print('KẾT THÚC:',name,'exit=',result,'seconds=',round(time.monotonic()-started,1),flush=True)
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        if process.stdout is not None: process.stdout.close()
        thread.join(timeout=1)


def show_diagnostics(stage):
    print('\nCHẨN ĐOÁN BƯỚC: '+str(stage),flush=True)
    for path in (OUT/'preflight_error.json',OUT/'inflight.json',OUT/'worker.log',LOGS/'ollama.log'):
        if path.is_file():
            print('\n--- '+path.name+' (đuôi log, có thể chứa lần chạy trước) ---',flush=True)
            print(safe_line(path.read_text(encoding='utf-8',errors='replace')[-6000:]),flush=True)
    response_path=OUT/'responses.jsonl'
    if response_path.is_file():
        from collections import deque
        with response_path.open(encoding='utf-8') as handle:recent=deque(handle,maxlen=1)
        if recent:
            try:
                record=json.loads(recent[0]);response=record.get('response') or {}
                trace=response.get('trace') or {}
                errors=[e for e in trace.get('execution_steps',[]) if e.get('status') in ('ERROR','CANCELLED')]
                print(safe_line(json.dumps({'last_question':record.get('id'),'arm':record.get('arm'),
                    'transport_status':record.get('status'),'answer_status':response.get('status'),
                    'error':record.get('error'),'failed_steps':errors},ensure_ascii=False)),flush=True)
            except (ValueError,TypeError):print('Không đọc được record cuối; giữ file để kiểm tra.',flush=True)

def snapshot_logs():
    if not OUT.exists():return
    destination=OUT/'notebook_logs';destination.mkdir(exist_ok=True)
    for path in LOGS.glob('*.log'):
        (destination/(path.name+'.tail.txt')).write_text(safe_line(path.read_text(encoding='utf-8',errors='replace')[-64000:]),encoding='utf-8')
"""),markdown("""
## 2. Nạp code đã chuẩn bị

Mặc định dùng ZIP nguồn đã đóng gói hoặc thư mục được Kaggle tự giải nén: không cần push lên GitHub. Gói chứa source cần thiết và 24 câu/nhãn dự kiến; corpus luật vẫn lấy từ artifact riêng.
Kiểm SHA-256 của từng file, từ chối đường dẫn không an toàn và không ghi đè source khác nội dung.
Nếu chọn GitHub, phải push bộ đo mới trước; notebook lấy `origin/main` và ghi phiên bản khi chạy.
"""),code(r"""
if SOURCE == 'attached_zip':
    if CODE_ZIP=='auto':
        inputs=Path('/kaggle/input')
        candidates=sorted(inputs.rglob('PhapDienAI_GraphQA_Code.zip'))+sorted(p.parent for p in inputs.rglob('package_manifest.json'))
    else:candidates=[Path(CODE_ZIP)]
    if len(candidates)!=1:raise RuntimeError('Cần đúng một ZIP/thư mục code; tìm thấy '+str(len(candidates))+'. Đặt CODE_ZIP cụ thể nếu cần.')
    source=candidates[0]; contents={}
    def safe_member(name):
        part=Path(name)
        if part.is_absolute() or '..' in part.parts or PurePosixPath(name).as_posix()!=name or '\\' in name or ':' in name:
            raise ValueError('Code có đường dẫn không hợp lệ')
    if source.is_dir():
        if source.is_symlink():raise ValueError('Không dùng thư mục code symlink')
        entries=list(source.rglob('*'))
        if any(p.is_symlink() for p in entries):raise ValueError('Thư mục code chứa symlink')
        files=[p for p in entries if p.is_file()]
        if len(files)>5000 or sum(p.stat().st_size for p in files)>100*1024*1024:raise ValueError('Code vượt giới hạn')
        for path in files:
            name=path.relative_to(source).as_posix();safe_member(name)
            if not path.resolve().is_relative_to(source.resolve()):raise ValueError('Code nằm ngoài thư mục nguồn')
            contents[name]=path.read_bytes()
        source_hash=hashlib.sha256(contents.get('package_manifest.json',b'')).hexdigest()
    else:
        if source.is_symlink():raise ValueError('Không dùng ZIP code symlink')
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        with zipfile.ZipFile(source) as z:
            entries=z.infolist();names=[i.filename for i in entries]
            if len(entries)>5000 or len(names)!=len(set(names)) or sum(i.file_size for i in entries)>100*1024*1024:
                raise ValueError('ZIP code vượt giới hạn hoặc có tên trùng')
            for info in entries:
                safe_member(info.filename)
                if stat.S_ISLNK(info.external_attr>>16) or info.is_dir():raise ValueError('ZIP code chỉ được chứa file thường')
                contents[info.filename]=z.read(info.filename)
    manifest=json.loads(contents['package_manifest.json'])
    if type(manifest.get('schema_version')) is not int or manifest['schema_version']!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Manifest code không hợp lệ')
    if set(contents)!=set(manifest['files'])|{'package_manifest.json'}:raise ValueError('File nguồn khác manifest')
    ROOT=CODE_ROOT/source_hash[:12]
    if not ROOT.resolve().is_relative_to(Path('/kaggle/working').resolve()):raise ValueError('ROOT ngoài working')
    for name,expected in manifest['files'].items():
        safe_member(name);content=contents[name]
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('SHA-256 code không khớp: '+name)
        target=ROOT/name
        if not target.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Đường dẫn ngoài ROOT')
        if target.exists() and target.read_bytes()!=content:raise RuntimeError('Source local đã thay đổi: '+name+'. Dùng CODE_ROOT mới, không ghi đè.')
    for name in contents:
        target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(contents[name])
    print('Code input:',source.name,'SHA-256:',source_hash,'ROOT:',ROOT,flush=True)
else:
    ROOT=CODE_ROOT/'github'
    ROOT.parent.mkdir(parents=True,exist_ok=True)
    if not ROOT.exists():
        run_step(['git','clone','--branch','main','--single-branch',REPO_URL,ROOT],'clone',timeout=300)
    else:
        if not (ROOT/'.git').is_dir():raise RuntimeError('ROOT tồn tại nhưng không phải Git repo')
        dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
        if dirty.strip():raise RuntimeError('Source tracked đã sửa. Giữ lại thay đổi trước khi cập nhật; notebook không tự xóa.')
        run_step(['git','fetch','--prune','origin'],'fetch',timeout=300,cwd=ROOT)
        run_step(['git','checkout','--detach','origin/main'],'checkout',timeout=300,cwd=ROOT)
    run_step(['git','log','-1','--oneline'],'git_version',cwd=ROOT)
if not (ROOT/'benchmarks/graph_qa/run.py').is_file():raise RuntimeError('Code chưa có bộ đo Graph QA mới')
"""),markdown("""
## 3. Cài dependency, giữ Torch/CUDA của Kaggle
"""),code(r"""
missing=[name for name in ('git','curl','zstd') if shutil.which(name) is None]
if missing:
    run_step(['apt-get','update','-y'],'apt_update',timeout=1200)
    run_step(['apt-get','install','-y',*missing],'apt_install',timeout=600)
import importlib.metadata
constraints=[]
for name in ('torch','torchvision','torchaudio'):
    try:constraints.append(name+'=='+importlib.metadata.version(name))
    except importlib.metadata.PackageNotFoundError:
        if name=='torch':raise RuntimeError('Chọn Kaggle GPU image có Torch trước khi chạy')
constraint_file=WORK/'torch_constraints.txt'
constraint_file.write_text('\n'.join(constraints)+'\n',encoding='utf-8')
VENV=WORK/'.venv'
if not (VENV/'bin/python').exists():
    run_step([sys.executable,'-m','venv','--system-site-packages','--without-pip',VENV],'venv',timeout=120)
PYTHON=str(VENV/'bin/python')
run_step([sys.executable,'-m','pip','--python',PYTHON,'install','--disable-pip-version-check','-q',
    '-c',constraint_file,'-e',str(ROOT)+'[retrieval,online]'],'dependencies',timeout=2400)
run_step([PYTHON,'-c','import torch,FlagEmbedding,faiss; assert torch.cuda.is_available(); print("CUDA devices:",torch.cuda.device_count())'],
    'cuda_check',timeout=120,cwd=ROOT)
"""),markdown("""
## 4. Secrets và cấu hình hai nhánh

Chỉ dùng Secrets phục vụ QA; không nạp key coding-team/Groq. Giá trị key không được in.
Nếu thay code/artifact/model/settings, dùng `RUN_NAME` mới; không trộn vào run đang đo.
"""),code(r"""
from kaggle_secrets import UserSecretsClient
secrets=UserSecretsClient()
try:
    token=secrets.get_secret('HF_TOKEN')
    if token:os.environ['HF_TOKEN']=token
    print('HF_TOKEN đã nạp' if token else 'HF_TOKEN tùy chọn, tải công khai',flush=True)
except Exception:print('HF_TOKEN tùy chọn, tải công khai',flush=True)
if SEMANTIC_REVIEW or RUN_AI_JUDGE:
    try:key=secrets.get_secret('GEMINI_API_KEY')
    except Exception:raise RuntimeError('Bật Secret GEMINI_API_KEY cho semantic review/judge') from None
    if not key:raise RuntimeError('GEMINI_API_KEY trống')
    os.environ['GEMINI_API_KEY']=key
    print('GEMINI_API_KEY đã nạp; không hiển thị giá trị',flush=True)
os.environ['VN_LABOR_GEMINI_RPM']='13'
settings={'device':'cuda:0','cache':str(WORK/'cache'),'llm_model':LLM_MODEL,
    'ollama_url':'http://127.0.0.1:11434/api/chat','review_model':REVIEW_MODEL,
    'semantic_review':SEMANTIC_REVIEW,'request_timeout_seconds':REQUEST_TIMEOUT_SECONDS,
    'provider_timeout_seconds':PROVIDER_TIMEOUT_SECONDS,'repetitions':REPETITIONS,'seed':42,'k':10,
    'reranker_revision':'953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e','judge_enabled':JUDGE_ENABLED,
    'judge_model':REVIEW_MODEL,'judge_timeout_seconds':60}
SETTINGS.parent.mkdir(parents=True,exist_ok=True)
if SETTINGS.exists() and json.loads(SETTINGS.read_text(encoding='utf-8'))!=settings:
    raise RuntimeError('Settings đổi: đặt RUN_NAME mới, không ghi đè settings run cũ')
SETTINGS.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
print('Settings:',SETTINGS,flush=True)
"""),markdown("""
## 5. Ollama: GPU 1 cho LLM, GPU 0 cho embedding/reranker

Không tự dừng dịch vụ của notebook khác. Nếu có Ollama ngoài quyền sở hữu, mặc định dừng chuẩn bị để tránh đo trong môi trường không kiểm soát.
"""),code(r"""
models=subprocess.check_output(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],text=True).splitlines()
if len(models)<2:raise RuntimeError('Chọn GPU T4 x2 cho cấu hình này')
print('GPUs:',models,flush=True)
if shutil.which('ollama') is None:
    run_step(['bash','-lc','set -o pipefail; curl -fsSL https://ollama.com/install.sh | sh'],'install_ollama',timeout=900)
def ollama_json(path):
    with urllib.request.urlopen('http://127.0.0.1:11434'+path,timeout=5) as response:return json.load(response)
old_owned=globals().get('OWN_OLLAMA')
server_up=False
try:ollama_json('/api/tags');server_up=True
except Exception:pass
if server_up and not (old_owned is not None and old_owned.poll() is None) and not ALLOW_EXISTING_OLLAMA:
    raise RuntimeError('Ollama đang chạy ngoài notebook này. Dùng phiên sạch hoặc chỉ cho phép tái sử dụng khi chắc chắn không có workload khác.')
if not server_up:
    OLLAMA_LOG=(LOGS/'ollama.log').open('a',encoding='utf-8')
    environment=dict(os.environ);environment.update(CUDA_VISIBLE_DEVICES='1',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_KEEP_ALIVE='30m')
    OWN_OLLAMA=subprocess.Popen(['ollama','serve'],env=environment,stdout=OLLAMA_LOG,stderr=subprocess.STDOUT)
    for attempt in range(60):
        if OWN_OLLAMA.poll() is not None:raise RuntimeError('Ollama dừng; xem '+str(LOGS/'ollama.log'))
        try:ollama_json('/api/tags');break
        except Exception:time.sleep(2)
    else:raise RuntimeError('Ollama chưa sẵn sàng sau 120 giây')
else:
    OWN_OLLAMA=old_owned if old_owned is not None and old_owned.poll() is None else None
    if 'OLLAMA_LOG' not in globals():OLLAMA_LOG=None
names={m.get('name') for m in ollama_json('/api/tags').get('models',[])}
if LLM_MODEL not in names:
    for attempt in range(2):
        try:run_step(['ollama','pull',LLM_MODEL],'pull_model',timeout=1200);break
        except (RuntimeError,TimeoutError):
            if attempt==1:raise
            time.sleep(5)
# Warm a neutral request outside measured QA; prevent the first 45s probe from paying cold-load cost.
warm_code=r'''import json,sys,time,urllib.request
model=sys.argv[1];timeout=float(sys.argv[2]);base='http://127.0.0.1:11434'
payload={'model':model,'prompt':'Return exactly OK.','stream':False,'think':False,'keep_alive':'30m',
         'options':{'temperature':0,'seed':0,'num_predict':8,'num_ctx':16384}}
request=urllib.request.Request(base+'/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=timeout) as response:result=json.load(response)
if result.get('done') is not True:raise RuntimeError('Ollama warmup chưa hoàn tất')
with urllib.request.urlopen(base+'/api/ps',timeout=10) as response:running=json.load(response)
models=[m for m in running.get('models',[]) if m.get('name')==model or m.get('model')==model]
if len(models)!=1:raise RuntimeError('Không xác nhận được model đã nạp')
m=models[0];size=m.get('size',0);vram=m.get('size_vram',0)
print(json.dumps({'model':model,'load_seconds':result.get('load_duration',0)/1e9,
    'total_seconds':result.get('total_duration',0)/1e9,'size':size,'size_vram':vram}),flush=True)
if not size or vram<=0:raise RuntimeError('Qwen không dùng GPU; kiểm tra ollama.log/GPU trước khi đo')
if vram<size*.9:print('WARNING: VRAM thấp hơn tổng size; kiểm tra ollama ps. Tỷ lệ này không phải phần trăm layer GPU.',flush=True)
'''
run_step([PYTHON,'-u','-c',warm_code,LLM_MODEL,str(STARTUP_TIMEOUT_SECONDS)],
         'ollama_warmup',timeout=STARTUP_TIMEOUT_SECONDS+30,cwd=ROOT)
print('Ollama đã warmup trên GPU; thời gian này không tính vào phép đo QA.',flush=True)
"""),markdown("""
## 6. Chuẩn bị artifact, đóng băng nhãn và kiểm tra readiness
"""),code(r"""
PREPARED=False
if ARTIFACT=='auto':
    inputs=Path('/kaggle/input')
    candidates=sorted(inputs.rglob('vn_labor_results.zip'))+sorted(p.parent.parent for p in inputs.rglob('reports/final_outputs_validation.json'))
    if len(candidates)!=1:raise RuntimeError('Cần đúng một artifact cuối; tìm thấy '+str(len(candidates))+'. Đặt ARTIFACT cụ thể nếu có nhiều input.')
    artifact=candidates[0]
else:artifact=Path(ARTIFACT)
if not artifact.exists():raise FileNotFoundError('Không tìm thấy artifact đã chọn')
ENTRY=ROOT/'benchmarks/graph_qa/run.py'
if OUT.exists():
    if not RESUME:raise RuntimeError('OUT đã tồn tại: chọn RUN_NAME mới hoặc RESUME=True khi cùng code/data/settings/model')
    print('Giữ kết quả cũ; runner sẽ kiểm hash/settings trước khi resume.',flush=True)
else:
    run_step([PYTHON,'-X','utf8',ENTRY,'prepare','--artifact',artifact,'--output',OUT,'--cache',WORK/'cache'],
        'prepare',timeout=1800,cwd=ROOT)
try:
    run_step([PYTHON,'-X','utf8',ENTRY,'preflight','--run',OUT,'--settings',SETTINGS],
        'preflight',timeout=1800,cwd=ROOT)
except Exception:
    snapshot_logs()
    run_step([PYTHON,'-X','utf8',ENTRY,'export','--run',OUT,'--output',RESULT_ZIP],
        'export_preflight_failure',timeout=300,cwd=ROOT,check=False)
    raise
PREPARED=True
print('Chuẩn bị đạt. OUT:',OUT,flush=True)
"""),markdown("""
## 7. Đo hai nhánh — báo cáo và ZIP kể cả khi dừng/lỗi

Không tự gọi lại câu trả lời từ chối/partial để tìm đáp án đẹp hơn.
RETRY_ERRORS chỉ là lựa chọn rõ ràng cho lỗi thực thi; giữ lịch sử attempt.
"""),code(r"""
if not PREPARED:raise RuntimeError('Chạy cell chuẩn bị đạt trước khi đo')
args=[PYTHON,'-X','utf8',ENTRY,'run','--run',OUT,'--settings',SETTINGS,'--profile',PROFILE]
if RETRY_ERRORS:args.append('--retry-errors')
failure=None
try:
    run_step(args,'paired_graph_qa',timeout=None,cwd=ROOT)
    if RUN_AI_JUDGE:
        run_step([PYTHON,'-X','utf8',ENTRY,'judge','--run',OUT,'--settings',SETTINGS],
            'posthoc_ai_judge',timeout=None,cwd=ROOT)
except Exception as exc:
    failure=exc
finally:
    snapshot_logs()
    for command,name in [([PYTHON,'-X','utf8',ENTRY,'report','--run',OUT],'report'),
                         ([PYTHON,'-X','utf8',ENTRY,'export','--run',OUT,'--output',RESULT_ZIP],'export')]:
        try:run_step(command,name,timeout=300,cwd=ROOT)
        except Exception as exc:print(name+' chưa hoàn tất: '+type(exc).__name__+'; chạy cell tải checkpoint riêng.',flush=True)
if failure is not None:raise failure
"""),markdown("""
## 8. Tải kết quả/checkpoint — cell này chạy riêng được sau lỗi

Không gộp các run khác fingerprint hoặc settings. Điểm nhãn DRAFT và AI-judge không phải chứng nhận pháp lý.
"""),code(r"""
from IPython.display import FileLink, display, Markdown
if not OUT.exists():raise RuntimeError('Chưa có OUT để xuất')
for command,name in [([PYTHON,'-X','utf8',ENTRY,'report','--run',OUT],'report_manual'),
                     ([PYTHON,'-X','utf8',ENTRY,'export','--run',OUT,'--output',RESULT_ZIP],'export_manual')]:
    run_step(command,name,timeout=300,cwd=ROOT,check=False)
for path in (OUT/'comparison.md',):
    if path.is_file():display(Markdown(path.read_text(encoding='utf-8')));break
if RESULT_ZIP.is_file():display(FileLink(str(RESULT_ZIP)))
else:raise RuntimeError('Chưa xuất được ZIP; xem log export')
print('Tải ZIP để kiểm từng câu, trace, căn cứ, trích dẫn, thời gian và lỗi. Cache/model/venv nằm ngoài OUT.',flush=True)
"""),markdown("""
## 9. Dọn dịch vụ do notebook tạo

Chạy khi đã kết thúc hoặc muốn giải phóng GPU; không dừng dịch vụ được tái sử dụng.
"""),code(r"""
owned=globals().get('OWN_OLLAMA')
if owned is not None and owned.poll() is None:
    owned.terminate()
    try:owned.wait(timeout=10)
    except subprocess.TimeoutExpired:owned.kill();owned.wait(timeout=10)
handle=globals().get('OLLAMA_LOG')
if handle is not None:handle.close()
print('Đã dọn dịch vụ do notebook này sở hữu.',flush=True)
""")]
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
            'language_info':{'name':'python'},'graph_qa_notebook_protocol':'paired-graph-qa-v1'},'nbformat':4,'nbformat_minor':5}

def validate(nb):
    if nb['nbformat']!=4:raise ValueError('Unexpected notebook format')
    for i,cell in enumerate(nb['cells']):
        if cell['cell_type']=='code':
            if cell.get('outputs') or cell.get('execution_count') is not None:raise ValueError('Notebook must contain no cached execution')
            ast.parse(''.join(cell['source']),filename=f'notebook_cell_{i}')
    code_text='\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code')
    for token in ['package_manifest.json','sha256','SOURCE','RETRY_ERRORS','finally:','GEMINI_API_KEY','preflight']:
        if token not in code_text:raise ValueError('Required notebook control missing: '+token)
    return sum(c['cell_type']=='code' for c in nb['cells'])

def main():
    nb=notebook();count=validate(nb)
    path=HERE/'Kaggle_Graph_QA.ipynb'
    path.write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
    print(json.dumps({'notebook':str(path),'code_cells_ast_ok':count,'api_calls':0,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))

if __name__=='__main__':main()
