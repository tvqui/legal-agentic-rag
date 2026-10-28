from pathlib import Path
import json

def notebook():
    cells=[]
    def markdown(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s):
        if s.startswith('from kaggle_secrets') or s.startswith('# Use GPU 1'):
            import textwrap
            fallback="OWN_OLLAMA=None;OLLAMA_LOG=None" if s.startswith('# Use GPU 1') else "print('No QA stage: Gemini secret/probe not required.',flush=True)"
            s="if {'ablation','vlsp'} & set(STAGES):\n"+textwrap.indent(s,'    ')+"\nelse:\n    "+fallback+"\n"
        cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':s.splitlines(True)})
    markdown('''# Pháp Điển AI — bộ đánh giá thống nhất

Một lần thiết lập: GPU T4 ×2, Internet bật, Add Input đúng một bộ kết quả OFFLINE,
Secrets `GEMINI_API_KEY` (và `HF_TOKEN` nếu cần). Không cần ngrok/API key của backend.
Notebook lấy code mới từ GitHub, chạy các thí nghiệm riêng và xuất bảng/ZIP.
`smoke` chọn 8 câu Gold theo nhóm và giới hạn dữ liệu ngoài; không dùng làm kết quả nghiên cứu.
Muốn đánh giá nghiên cứu, chọn `standard` và cung cấp Gold đã rà soát.
''')
    code('''from pathlib import Path
REPO_URL = "https://github.com/tvqui/legal-agentic-rag.git"
ROOT = Path('/kaggle/working/legal-agentic-rag')
WORK = Path('/kaggle/working/evaluation_work')
PROFILE = 'smoke'  # set 'standard' after smoke succeeds
RESUME_EVALUATION_ZIP = None  # e.g. '/kaggle/input/old-run/evaluation_...zip'; same code/data/settings required  # 'standard' uses settings.yaml limits and three repetitions
ARTIFACT = 'auto'  # or a precise /kaggle/input/.../artifacts path
LABOR_GOLD = 'gold_dataset/PhapDienAI_Gold_100_Labor_v0_1.zip'  # reads ZIP directly
STAGES = ['retrieval','zalo','ablation','vlsp']  # may run groups separately
GEMINI_MODEL = 'gemini-3.1-flash-lite'
EVALUATION_MODEL = GEMINI_MODEL  # records the actual AI judge model
RESEARCHER_PROVIDER = 'gemini'  # change explicitly if comparing another setup
''')
    code('''import os,sys,subprocess,shutil,json,time,urllib.request
WORK.mkdir(parents=True,exist_ok=True)
def run(args, **kw):
    print('RUN',args[0],flush=True)
    return subprocess.run(args,check=True,**kw)
run(['apt-get','update','-y'])
run(['apt-get','install','-y','git','curl','zstd'])
if not ROOT.exists():
    run(['git','clone','--branch','main','--single-branch',REPO_URL,str(ROOT)])
else:
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
    if dirty.strip():raise RuntimeError('Tracked code was edited in the notebook. Save changes before updating.')
    run(['git','fetch','--prune','origin'],cwd=ROOT)
    run(['git','checkout','--detach','origin/main'],cwd=ROOT)
run(['git','log','-1','--oneline'],cwd=ROOT)
# Keep Kaggle's CUDA-compatible Torch and isolate project dependencies.
import importlib.metadata
constraints=[]
for package in ('torch','torchvision','torchaudio'):
    try:constraints.append(package+'=='+importlib.metadata.version(package))
    except importlib.metadata.PackageNotFoundError:
        if package=='torch':raise RuntimeError('Kaggle runtime has no Torch; select a GPU image.')
constraint_file=WORK/'torch_constraints.txt'
constraint_file.write_text('\\n'.join(constraints)+'\\n',encoding='utf-8')
VENV=WORK/'.venv'
run([sys.executable,'-m','venv','--system-site-packages','--without-pip',str(VENV)])
PYTHON=str(VENV/'bin/python')
run([sys.executable,'-m','pip','--python',PYTHON,'install','--disable-pip-version-check',
    '-q','-c',str(constraint_file),'-e',str(ROOT)+'[retrieval,online]','datasets'])
run([PYTHON,'-c','import torch,FlagEmbedding,faiss,datasets; assert torch.cuda.is_available(); print("CUDA dependencies ready:",torch.cuda.device_count())'])
if not (ROOT/'benchmarks/evaluation_suite/protocol.py').exists() or 'labor-evaluation-v2-20261028' not in (ROOT/'benchmarks/evaluation_suite/protocol.py').read_text(encoding='utf-8'):
    raise RuntimeError('Push evaluation suite v2 before running this notebook.')
if not (ROOT/'benchmarks/evaluation_suite/suite.py').exists():
    raise RuntimeError('Push the evaluation_suite folder to GitHub before Run All.')
''')
    code('''from kaggle_secrets import UserSecretsClient
client=UserSecretsClient()
key=client.get_secret('GEMINI_API_KEY')
if not key:raise RuntimeError('Add and enable GEMINI_API_KEY for this notebook.')
os.environ['GEMINI_API_KEY']=key
os.environ['GEMINI_MODEL']=GEMINI_MODEL
os.environ['GEMINI_EVAL_MODEL']=EVALUATION_MODEL
os.environ['VN_LABOR_RESEARCHER_MODE']=RESEARCHER_PROVIDER
os.environ['VN_LABOR_ADJUDICATION_REVIEW_PROVIDER']='gemini'
os.environ['VN_LABOR_ADJUDICATION_REVIEW_MODEL']=GEMINI_MODEL
os.environ['VN_LABOR_GEMINI_RPM']='13'
os.environ['HF_HUB_ETAG_TIMEOUT']='30'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='60'
try:
    token=client.get_secret('HF_TOKEN')
    if token:os.environ['HF_TOKEN']=token
except Exception:
    print('HF_TOKEN optional; public downloads will be attempted.',flush=True)
print('Secrets configured; values are never displayed.',flush=True)
run([PYTHON,'-u','kaggle/check_gemini.py','--config','config/online_kaggle.yaml',
    '--model',GEMINI_MODEL],cwd=ROOT,timeout=300)
''')
    code('''# Use GPU 1 for Ollama, GPU 0 for embedding/reranker. Own only the server
# started by this notebook; never terminate another session's server.
gpu_lines=subprocess.check_output(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],text=True).splitlines()
print('GPUs:',gpu_lines,flush=True)
if len(gpu_lines)<2:raise RuntimeError('Select GPU T4 x2 in Kaggle settings for this configuration.')
if shutil.which('ollama') is None:
    run(['bash','-lc','set -o pipefail; curl -fsSL https://ollama.com/install.sh | sh'])
def ollama_json(path):
    with urllib.request.urlopen('http://127.0.0.1:11434'+path,timeout=5) as response:return json.load(response)
OWN_OLLAMA=None
OLLAMA_LOG=(WORK/'ollama.log').open('a',encoding='utf-8')
try:
    ollama_json('/api/tags')
    print('Reusing existing Ollama; verify it is not serving another workload.',flush=True)
except Exception:
    environment=dict(os.environ);environment['CUDA_VISIBLE_DEVICES']='1'
    OWN_OLLAMA=subprocess.Popen(['ollama','serve'],env=environment,stdout=OLLAMA_LOG,stderr=subprocess.STDOUT)
    for attempt in range(60):
        if OWN_OLLAMA.poll() is not None:raise RuntimeError('Ollama stopped; read '+str(WORK/'ollama.log'))
        try:ollama_json('/api/tags');break
        except Exception:time.sleep(2)
    else:raise RuntimeError('Ollama did not become ready')
models={m.get('name') for m in ollama_json('/api/tags').get('models',[])}
if 'qwen3:8b' not in models:
    for attempt in range(3):
        try:run(['ollama','pull','qwen3:8b'],timeout=900);break
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
            if attempt==2:raise
            time.sleep(10)
print('Ollama and model ready.',flush=True)
''')
    code('''import yaml
from datetime import datetime,timezone
settings=yaml.safe_load((ROOT/'benchmarks/evaluation_suite/settings.yaml').read_text(encoding='utf-8'))
settings['artifact']=ARTIFACT
settings['labor_gold']=LABOR_GOLD
settings['cache']=str(WORK/'cache')
if PROFILE=='smoke':
    settings['repeats']=1;settings['qa_repeats']=1;settings['labor_limit']=8
    settings['zalo']['limit']=10;settings['vlsp']['limit']=5
elif PROFILE!='standard':raise ValueError('Unknown profile')
settings_path=WORK/'settings.yaml'
settings_path.write_text(yaml.safe_dump(settings,allow_unicode=True),encoding='utf-8')
run([PYTHON,'-u','benchmarks/evaluation_suite/preflight_external.py','--settings',str(settings_path),
     '--output',str(WORK/'external_preflight'),'--stages',*STAGES],cwd=ROOT,timeout=900)
resume_args=[]
if RESUME_EVALUATION_ZIP:
    import importlib.util
    spec=importlib.util.spec_from_file_location('evaluation_restore',ROOT/'benchmarks/evaluation_suite/resume.py')
    restore_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(restore_module)
    OUTPUT=WORK/'restored_run'
    restore_module.restore(RESUME_EVALUATION_ZIP,OUTPUT)
    frozen=json.loads((OUTPUT/'settings_resolved.json').read_text(encoding='utf-8'))
    # Keep every score-affecting setting. Paths must resolve to the same input; suite checks hashes.
    settings=frozen
    settings_path.write_text(yaml.safe_dump(settings,allow_unicode=True),encoding='utf-8')
    resume_args=['--resume']
else:
    OUTPUT=Path('/kaggle/working')/('evaluation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
try:
    result=subprocess.run([PYTHON,'-u','benchmarks/evaluation_suite/suite.py','run',
        '--settings',str(settings_path),'--output',str(OUTPUT),'--stages',*STAGES,*resume_args],cwd=ROOT)
    print('Suite exit code:',result.returncode,flush=True)
finally:
    if OWN_OLLAMA is not None and OWN_OLLAMA.poll() is None:
        OWN_OLLAMA.terminate()
        try:OWN_OLLAMA.wait(timeout=15)
        except subprocess.TimeoutExpired:OWN_OLLAMA.kill();OWN_OLLAMA.wait(timeout=10)
    if OLLAMA_LOG is not None:OLLAMA_LOG.close()
''')
    code('''from IPython.display import display,FileLink,Markdown
table=OUTPUT/'comparison_tables.md'
if table.exists():display(Markdown(table.read_text(encoding='utf-8')))
else:print('Preparation failed before measurement. Inspect the preceding error; do not report missing scores as zero.')
for file in [OUTPUT/'comparison_tables.md',OUTPUT/'comparison_tables.csv',OUTPUT.parent/(OUTPUT.name+'.zip')]:
    if file.exists():display(FileLink(str(file)))
''')
    for index,cell in enumerate(cells):cell['id']='eval-'+str(index).zfill(3)
    return {'nbformat':4,'nbformat_minor':5,'metadata':{
      'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
      'language_info':{'name':'python'},'kaggle':{'accelerator':'gpu','isInternetEnabled':True,'language':'python','sourceType':'notebook'}},'cells':cells}

if __name__=='__main__':
    path=Path(__file__).with_name('Kaggle_Evaluation.ipynb')
    path.write_text(json.dumps(notebook(),ensure_ascii=False,indent=1),encoding='utf-8')
    import copy,hashlib
    standard=copy.deepcopy(notebook())
    standard['cells'][0]['source'].insert(0,'# STANDARD — chạy sau khi smoke đã đạt\n\n')
    for cell in standard['cells']:
        if cell['cell_type']=='code':
            code=''.join(cell['source']).replace("PROFILE = 'smoke'","PROFILE = 'standard'")
            compile(code,'standard-notebook','exec');cell['source']=code.splitlines(True)
    standard_path=path.with_name('Kaggle_Evaluation_Standard.ipynb')
    standard_path.write_text(json.dumps(standard,ensure_ascii=False,indent=1),encoding='utf-8')
    for candidate in (path,standard_path):
        for cell in json.loads(candidate.read_text(encoding='utf-8'))['cells']:
            if cell['cell_type']=='code':compile(''.join(cell['source']),'evaluation-cell','exec')
        Path(str(candidate)+'.sha256').write_text(hashlib.sha256(candidate.read_bytes()).hexdigest()+'  '+candidate.name+'\n',encoding='ascii')
    print(path);print(standard_path)
