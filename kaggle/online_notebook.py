"""Generate the manual Kaggle ONLINE notebook. Does not install or start services."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from textwrap import dedent


def make_notebook():
    cells=[]
    def add(kind,name,value):
        cell={'cell_type':kind,'id':'online-'+str(len(cells)).zfill(2),
              'metadata':{'name':name},'source':dedent(value).strip().splitlines(keepends=True)}
        if kind=='code': cell.update(execution_count=None,outputs=[])
        cells.append(cell)

    add('markdown','instructions',r'''
    # Pháp Điển AI — ONLINE backend trên Kaggle

    Trước khi Run All, kiểm tra trong Kaggle:
    - **Internet ON**, **GPU T4 x2**. Notebook không tự cấp GPU hay thêm Input/Secrets.
    - **Add Input** một dataset kết quả cuối `result_14-10` (`vn-labor-results-14-10`),
      dạng `vn_labor_results.zip` hoặc thư mục `artifacts/` đã giải nén.
      Không cần package OFFLINE, technical checkpoint hoặc PDF thô.
    - Bật quyền dùng Secrets **GEMINI_API_KEY**, **VN_LABOR_API_KEY**, **NGROK_AUTHTOKEN**;
      **HF_TOKEN** là tùy chọn. Không dán key vào code.

    Chạy Run All ở phiên tương tác. Cell cuối **tiếp tục chạy là bình thường**:
    nó giữ backend và tunnel sống, hiện `VITE_BACKEND_TARGET=https://...` khi sẵn sàng.
    Dừng cell sẽ dừng server. Không coi Run All & Save đã hoàn tất là server còn chạy.
    Sau khi có URL, cập nhật `frontend/.env` ở máy local nếu URL đổi rồi khởi động Vite.
    Mã và model giữ cache khi chạy lại cùng phiên; không xóa thư mục repo/cache.
    ''')
    add('code','settings',r'''
    from pathlib import Path
    ROOT = Path('/kaggle/working/legal-agentic-rag')
    REPO_URL = 'https://github.com/tvqui/legal-agentic-rag.git'
    BRANCH = 'main'
    INPUT_ROOT = Path('/kaggle/input')
    # Để trống nếu chỉ gắn một kết quả cuối; nếu có nhiều Input, điền đúng path.
    ARTIFACT = ''
    GEMINI_MODEL = 'gemini-3.5-flash-lite'  # model bạn đang sử dụng
    OLLAMA_MODEL = 'qwen3:8b'
    GEMINI_RPM = 13
    READY_TIMEOUT_SECONDS = 180
    CONFIG = Path('/kaggle/working/online_pinned.yaml')
    WORKING = Path('/kaggle/working/vn_labor_online')
    PYTHON = Path('/tmp/vn_labor_online_env/bin/python')
    NOTEBOOK_VALIDATED = False
    ''')
    add('code','helpers',r'''
    import importlib.metadata
    import json
    import os
    import queue
    import re
    import shutil
    import signal
    import socket
    import subprocess
    import sys
    import threading
    import time
    import urllib.request

    def redact(value):
        text = str(value)
        for name in ('GEMINI_API_KEY','VN_LABOR_RESEARCHER_API_KEY','VN_LABOR_API_KEY',
                     'NGROK_AUTHTOKEN','HF_TOKEN'):
            secret = os.getenv(name,'')
            if secret: text = text.replace(secret,'[REDACTED]')
        return text

    def stop_owned(process):
        if process.poll() is not None: return
        try:
            os.killpg(process.pid,signal.SIGINT)
            process.wait(timeout=30)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)

    def log_tail(path,limit=12000):
        if not path.is_file(): return '(chưa tạo log)'
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-limit))
            return redact(stream.read(limit).decode('utf-8',errors='replace'))

    def run_step(arguments,name,timeout=300,cwd=None,on_line=None):
        logs=WORKING/'notebook_logs'; logs.mkdir(parents=True,exist_ok=True)
        path=logs/(name+'.log')
        print(f'BẮT ĐẦU: {name}; log: {path}',flush=True)
        process=subprocess.Popen(list(map(str,arguments)),cwd=cwd,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
            bufsize=1,start_new_session=True)
        events=queue.Queue()
        def read_output():
            try:
                for line in process.stdout: events.put(line)
            finally: events.put(None)
        reader=threading.Thread(target=read_output,daemon=True); reader.start()
        started=heartbeat=time.monotonic(); eof=False
        try:
            with path.open('a',encoding='utf-8') as log:
                while not eof or process.poll() is None:
                    now=time.monotonic()
                    if timeout is not None and now-started>timeout:
                        raise TimeoutError(f'{name} vượt {timeout} giây; xem {path}')
                    try:
                        line=events.get(timeout=1)
                        if line is None: eof=True
                        else:
                            safe=redact(line); print(safe,end='',flush=True); log.write(safe); log.flush()
                            if on_line: on_line(line.strip())
                    except queue.Empty: pass
                    if now-heartbeat>=30:
                        print(f'{name}: tiến trình còn chạy, đã {int(now-started)} giây.',flush=True)
                        heartbeat=now
                if process.returncode:
                    raise RuntimeError(f'{name} thất bại, exit={process.returncode}; xem {path}')
        finally:
            stop_owned(process)
            reader.join(timeout=2)
            process.stdout.close()

    def assert_ports_free(ports=(8000,11434)):
        busy=[]
        for port in ports:
            with socket.socket() as connection:
                connection.settimeout(.3)
                if connection.connect_ex(('127.0.0.1',port))==0: busy.append(port)
        if busy:
            raise RuntimeError('Đang có service cũ ở cổng '+str(busy)+
                '. Dừng cell backend cũ hoặc Restart Session; không tự kill process không rõ chủ.')

    def select_artifact(input_root,explicit=''):
        root=Path(input_root).resolve()
        if explicit:
            target=Path(explicit).expanduser().resolve()
            if not target.exists() or not target.is_relative_to(root):
                raise RuntimeError('ARTIFACT phải là path tồn tại trong Kaggle Input.')
            return target
        archives={p.resolve() for name in ('vn_labor_results.zip','vn_labor_results_20261014.zip',
            'vn_labor_results_v8.1(aura).zip','vn_labor_results_v8_1_aura.zip') for p in root.rglob(name)}
        directories=set()
        required=('05_graph/nodes.jsonl','05_graph/edges.jsonl','06_indexes/retrieval_units.jsonl',
                  'reports/dense_validation.json','reports/neo4j_validation.json')
        for marker in root.rglob('reports/final_outputs_validation.json'):
            parent=marker.parent.parent
            try: report=json.loads(marker.read_text(encoding='utf-8-sig'))
            except (OSError,ValueError): continue
            if (all(report.get('stages',{}).get(k) is True for k in ('registry','structure','graph','indexes'))
                    and all((parent/name).is_file() for name in required)):
                directories.add(parent.resolve())
        candidates=sorted(archives|directories)
        if len(candidates)!=1:
            raise RuntimeError('Cần đúng một kết quả cuối; tìm thấy '+str(len(candidates))+
                '. Chỉ giữ Input result_14-10 hoặc đặt ARTIFACT rõ ràng: '+str(candidates))
        return candidates[0]

    def assert_release(pin,effective):
        pairs=(('build_id','expected_build_id'),('retrieval_unit_fingerprint','expected_retrieval_unit_fingerprint'),
               ('dense_fingerprint','expected_dense_fingerprint'))
        for found,expected in pairs:
            if not effective.get(expected):
                raise RuntimeError('Config release thiếu fingerprint bắt buộc: '+expected)
            if pin.get(found)!=effective[expected]:
                raise RuntimeError('Input không khớp release trong config/online_kaggle.yaml: '+found+
                    '. Kiểm tra đã gắn đúng result_14-10; không bỏ kiểm fingerprint.')
        if pin.get('compatible') is not True: raise RuntimeError('Artifact không tương thích kỹ thuật.')

    def backend_line(line):
        prefix='REMOTE_BACKEND_URL='
        if line.startswith(prefix):
            url=line[len(prefix):].strip()
            if not url.startswith('https://'): raise RuntimeError('Tunnel không trả URL HTTPS.')
            (WORKING/'remote_backend_url.txt').write_text(url+'\n',encoding='utf-8')
            print('\nDán dòng sau vào frontend/.env ở máy local:\nVITE_BACKEND_TARGET='+url,flush=True)
            print('Giữ BACKEND_PROXY_TOKEN khớp VN_LABOR_API_KEY; không đưa token vào VITE_*.',flush=True)
    ''')
    add('markdown','prerequisites',r'''
    ## 1. Kiểm GPU, Internet, Input và Secrets trước khi cài model
    Nếu dừng ở đây, sửa Settings/Add Input/Secrets rồi chạy lại. Không cần OCR hay chạy OFFLINE.
    ''')
    add('code','preflight',r'''
    NOTEBOOK_VALIDATED=False
    if not ((3,12)<=sys.version_info[:2]<(3,14)):
        raise RuntimeError('Dự án hỗ trợ Python 3.12 hoặc 3.13.')
    if sys.platform!='linux' or not INPUT_ROOT.is_dir():
        raise RuntimeError('Notebook này cần chạy trong Kaggle Linux.')
    if not shutil.which('nvidia-smi'):
        raise RuntimeError('Chưa bật GPU. Chọn Settings → Accelerator → GPU T4 x2.')
    gpu=subprocess.run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],
        capture_output=True,text=True,check=True,timeout=20)
    gpus=[line.strip() for line in gpu.stdout.splitlines() if line.strip()]
    if not gpus: raise RuntimeError('Không có GPU được cấp cho phiên này.')
    print('GPU:',gpus,flush=True)
    if len(gpus)<2: print('Chỉ có một GPU: Dense/reranker và Ollama sẽ dùng chung GPU.',flush=True)
    assert_ports_free()
    try:
        with urllib.request.urlopen('https://github.com/tvqui/legal-agentic-rag',timeout=20) as response:
            if response.status!=200: raise RuntimeError('GitHub unavailable')
    except Exception as exc:
        raise RuntimeError('Không truy cập được GitHub. Kiểm tra Internet ON; lỗi: '+type(exc).__name__) from None
    ARTIFACT_PATH=select_artifact(INPUT_ROOT,ARTIFACT)
    print('Input đã chọn:',ARTIFACT_PATH,flush=True)
    from kaggle_secrets import UserSecretsClient
    client=UserSecretsClient(); missing=[]
    for name in ('GEMINI_API_KEY','VN_LABOR_API_KEY','NGROK_AUTHTOKEN','HF_TOKEN'):
        try: value=client.get_secret(name).strip()
        except Exception: value=''
        if not value and name!='HF_TOKEN': missing.append(name)
        if value: os.environ[name]=value
        elif name in os.environ: os.environ.pop(name)
        print(name+(': OK' if value else ': chưa cấu hình'),flush=True)
    value=''
    if missing: raise RuntimeError('Thiếu/quên cấp quyền Secrets: '+', '.join(missing))
    if len(os.environ['VN_LABOR_API_KEY'])<32:
        raise RuntimeError('VN_LABOR_API_KEY cần có ít nhất 32 ký tự ngẫu nhiên.')
    os.environ.update({
        'GEMINI_MODEL':GEMINI_MODEL,'VN_LABOR_RESEARCHER_MODE':'gemini',
        'VN_LABOR_RESEARCHER_API_KEY':os.environ['GEMINI_API_KEY'],
        'VN_LABOR_ADJUDICATION_REVIEW_PROVIDER':'gemini',
        'VN_LABOR_ADJUDICATION_REVIEW_MODEL':GEMINI_MODEL,
        'VN_LABOR_GEMINI_RPM':str(GEMINI_RPM),'VN_LABOR_GEMINI_RATE_RETRIES':'2',
        'VN_LABOR_GEMINI_RATE_MAX_WAIT_SECONDS':'70',
        'VN_LABOR_APPLICABILITY_MODE':'hybrid','VN_LABOR_APPLICABILITY_PROVIDER':'ollama',
        'VN_LABOR_ADJUDICATION_MODE':'ollama','VN_LABOR_REQUEST_TIMEOUT_SECONDS':'180',
        'VN_LABOR_MAX_CONCURRENT_ANSWERS':'1','TOKENIZERS_PARALLELISM':'false',
    })
    for role in ('APPLICABILITY','ADJUDICATION'):
        os.environ['VN_LABOR_'+role+'_MODEL']=OLLAMA_MODEL
        os.environ['VN_LABOR_'+role+'_URL']='http://127.0.0.1:11434/api/chat'
        os.environ['VN_LABOR_'+role+'_HEALTH_URL']='http://127.0.0.1:11434/api/tags'
    print('Preflight GPU/Internet/Input/Secrets: PASS',flush=True)
    ''')
    add('markdown','setup_description',r'''
    ## 2. Cập nhật main và cài môi trường riêng
    Cài `zstd` một lần. Môi trường Python riêng tái sử dụng Torch/CUDA có sẵn của Kaggle,
    ràng buộc đúng phiên bản Torch để tránh pip tự đổi sang bản khác. Nếu repo có sửa
    tracked file chưa lưu, notebook dừng; không reset/xóa code hoặc model cache.
    ''')
    add('code','setup',r'''
    NOTEBOOK_VALIDATED=False
    # Tương đương: !apt-get update -y ; !apt-get install -y git curl zstd
    run_step(['apt-get','update','-y'],'apt_update',timeout=300)
    run_step(['apt-get','install','-y','git','curl','zstd'],'apt_install',timeout=300)
    if not ROOT.exists():
        run_step(['git','clone','--branch',BRANCH,'--single-branch',REPO_URL,ROOT],
                 'git_clone',timeout=300)
    elif not (ROOT/'.git').exists():
        raise RuntimeError('ROOT tồn tại nhưng không phải repository; kiểm tra path trước khi chạy lại.')
    origin=subprocess.check_output(['git','remote','get-url','origin'],cwd=ROOT,text=True,timeout=20).strip()
    if origin.rstrip('/').removesuffix('.git')!=REPO_URL.rstrip('/').removesuffix('.git'):
        raise RuntimeError('origin của ROOT không đúng repo dự án; không cập nhật nhầm repo.')
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True,timeout=20)
    if dirty.strip(): raise RuntimeError('Repo có tracked file đã sửa; lưu thay đổi trước khi cập nhật.')
    run_step(['git','fetch','--prune','origin','+refs/heads/'+BRANCH+':refs/remotes/origin/'+BRANCH],
             'git_fetch',timeout=300,cwd=ROOT)
    run_step(['git','checkout','--detach','origin/'+BRANCH],'git_checkout',cwd=ROOT)
    COMMIT_USED=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,timeout=20).strip()
    print('Commit đang dùng:',COMMIT_USED,flush=True)
    api_source=(ROOT/'src/vn_labor_online/api.py').read_text(encoding='utf-8')
    if 'diagnostic-probe-v2' not in api_source or not (ROOT/'kaggle/check_gemini.py').is_file():
        raise RuntimeError('main chưa có bản sửa Gemini readiness. Push code local rồi chạy lại cell này.')
    constraints=[]
    for package in ('torch','torchvision','torchaudio'):
        try: constraints.append(package+'=='+importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:
            if package=='torch': raise RuntimeError('Kaggle image chưa có Torch; kiểm tra GPU runtime.')
    WORKING.mkdir(parents=True,exist_ok=True)
    constraint_file=WORKING/'torch_constraints.txt'
    constraint_file.write_text('\n'.join(constraints)+'\n',encoding='utf-8')
    run_step([sys.executable,'-m','venv','--system-site-packages','--without-pip',PYTHON.parent.parent],
             'python_env',timeout=120)
    run_step([sys.executable,'-m','pip','--python',PYTHON,'install','--disable-pip-version-check',
              '-c',constraint_file,'-e',str(ROOT)+'[retrieval,online]','ngrok'],
             'python_dependencies',timeout=1800,cwd=ROOT)
    if shutil.which('ollama') is None:
        installer=WORKING/'ollama-install.sh'
        run_step(['curl','-fsSL','--retry','2','--connect-timeout','20',
                  'https://ollama.com/install.sh','-o',installer],'ollama_installer',timeout=180)
        run_step(['sh',installer],'ollama_install',timeout=900)
    if not shutil.which('ollama'): raise RuntimeError('Chưa cài được Ollama.')
    check=('import torch,FlagEmbedding,faiss,fastapi,google.genai,jsonschema,ngrok; '
           'assert torch.cuda.is_available(), "Torch không thấy CUDA"; '
           'print("Python dependencies/CUDA: PASS; GPU count:",torch.cuda.device_count())')
    run_step([PYTHON,'-c',check],'dependency_check',timeout=120,cwd=ROOT)
    ''')
    add('markdown','pin_description',r'''
    ## 3. Pin và kiểm đúng release dữ liệu
    Tiến trình pin chạy riêng để trả RAM sau khi kiểm. Build, retrieval fingerprint và dense
    fingerprint phải khớp release trong config; không chỉ dựa vào tên ZIP. Các mục human review
    chưa duyệt vẫn là PROVISIONAL, không bị đổi thành đã duyệt.
    ''')
    add('code','pin_config',r'''
    NOTEBOOK_VALIDATED=False
    pin_lines=[]
    run_step([PYTHON,'scripts/pin_online_artifact.py','--artifact',ARTIFACT_PATH,
              '--base-config','config/online_kaggle.yaml','--output',CONFIG,'--force'],
             'pin_artifact',timeout=300,cwd=ROOT,on_line=pin_lines.append)
    pin_report=json.loads('\n'.join(pin_lines))
    inspect=r"""
    import json,sys
    from pathlib import Path
    from vn_labor_online.config import load_config
    base=load_config(Path('config/online_kaggle.yaml')); selected=load_config(Path(sys.argv[1]))
    print(json.dumps({'base':{'expected_build_id':base.expected_build_id,
      'expected_retrieval_unit_fingerprint':base.expected_retrieval_unit_fingerprint,
      'expected_dense_fingerprint':base.expected_dense_fingerprint},
      'selected':{'expected_build_id':selected.expected_build_id,
      'expected_retrieval_unit_fingerprint':selected.expected_retrieval_unit_fingerprint,
      'expected_dense_fingerprint':selected.expected_dense_fingerprint},
      'profile':{'researcher':selected.researcher.mode,'reviewer':selected.adjudication.review_provider,
      'semantic_review':selected.adjudication.semantic_review,'applicability':selected.applicability.mode,
      'adjudication':selected.adjudication.mode,'dense':selected.retrieval.dense_enabled,
      'bm25':selected.retrieval.bm25_enabled,'reranker':selected.reranker.enabled,'graph':selected.graph.enabled,
      'researcher_model':selected.researcher.model,'reviewer_model':selected.adjudication.review_model}}))
    """
    from textwrap import dedent
    raw=subprocess.check_output([str(PYTHON),'-c',dedent(inspect),str(CONFIG)],cwd=ROOT,text=True,timeout=30)
    effective=json.loads(raw)
    assert_release(pin_report,effective['base'])
    assert_release(pin_report,effective['selected'])
    profile=effective['profile']
    if not (profile['researcher']=='gemini' and profile['reviewer']=='gemini' and profile['semantic_review']
            and profile['applicability']=='hybrid' and profile['adjudication']=='ollama'
            and all(profile[name] for name in ('dense','bm25','reranker','graph'))):
        raise RuntimeError('Profile thực tế không đúng cấu hình đầy đủ của notebook.')
    print('Effective ONLINE profile:',json.dumps(profile,ensure_ascii=False),flush=True)
    print('Pinned build:',pin_report['build_id'],flush=True)
    ''')
    add('markdown','gemini_description',r'''
    ## 4. Kiểm Gemini trước khi tải BGE/Qwen
    Đây là probe kết nối nhỏ, không chứng nhận câu trả lời pháp lý đúng. Nếu lỗi, mã lỗi
    được in an toàn; sửa Secrets/model/quota rồi chạy lại từ cell cần thiết.
    Không chạy notebook/benchmark khác dùng cùng quota trong lúc kiểm.
    ''')
    add('code','gemini_check',r'''
    NOTEBOOK_VALIDATED=False
    run_step([PYTHON,'-u','kaggle/check_gemini.py','--config',CONFIG,'--model',GEMINI_MODEL],
             'gemini_check',timeout=120,cwd=ROOT)
    NOTEBOOK_VALIDATED=True
    print('Các bước chuẩn bị đã đạt. Cell tiếp theo sẽ giữ backend chạy.',flush=True)
    ''')
    add('markdown','serve_description',r'''
    ## 5. Khởi động backend — giữ cell này chạy
    Chờ `VITE_BACKEND_TARGET=https://...`. Log setup nằm ở
    `/kaggle/working/vn_labor_online/notebook_logs/`; log dịch vụ ở `logs/backend.log`
    và `logs/ollama.log`. Khi lỗi/dừng, notebook tự hiện phần log cuối đã che key.
    Không có cell chẩn đoán bắt buộc ở sau cell chạy liên tục này.
    ''')
    add('code','backend',r'''
    if not NOTEBOOK_VALIDATED: raise RuntimeError('Chưa chạy thành công các cell chuẩn bị và kiểm Gemini.')
    assert_ports_free()
    try:
        run_step([PYTHON,'-u','kaggle/online_remote.py','--artifact',ARTIFACT_PATH,
                  '--config',CONFIG,'--model',OLLAMA_MODEL,'--ready-timeout',READY_TIMEOUT_SECONDS],
                 'backend',timeout=None,cwd=ROOT,on_line=backend_line)
    finally:
        for name in ('backend.log','ollama.log'):
            print('\nLOG '+name+' (đã che key):\n'+log_tail(WORKING/'logs'/name),flush=True)
    ''')
    notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
        'language_info':{'name':'python'},'vn_labor':{'workflow':'ONLINE_KAGGLE_GEMINI_PACED_V1',
        'required_settings':{'internet':True,'recommended_gpu':'T4 x2','dataset':'vn-labor-results-14-10'}}},
        'nbformat':4,'nbformat_minor':5}
    for cell in cells:
        if cell['cell_type']=='code': compile(''.join(cell['source']),cell['metadata']['name'],'exec')
    return notebook


def write_notebook(path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(make_notebook(),ensure_ascii=False,indent=2)+'\n'
    data=payload.encode('utf-8')
    path.write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    Path(str(path)+'.sha256').write_text(sha+'  '+path.name+'\n',encoding='ascii')
    return {'notebook':str(path),'sha256':sha,'code_syntax':'PASS','secrets_included':False,
            'remote_execution_tested':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('ONLINE_Backend.ipynb'))
    print(json.dumps(write_notebook(parser.parse_args().output),ensure_ascii=False))
