"""Record the runtime relevant to numerical reproducibility, never credentials."""
import sys,platform,importlib.metadata,subprocess,shutil,json,urllib.request

def snapshot():
    versions={}
    for name in ('numpy','torch','transformers','FlagEmbedding','bm25s','faiss-cpu','faiss-gpu','google-genai','datasets','huggingface-hub'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    gpus=[]
    if shutil.which('nvidia-smi'):
        try:
            r=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
            if r.returncode==0:gpus=r.stdout.strip().splitlines()
        except (OSError,subprocess.TimeoutExpired):pass
    ollama=[]
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as response:
            data=json.load(response)
        ollama=sorted([{'name':m.get('name'),'digest':m.get('digest')} for m in data.get('models',[])],key=lambda m:m['name'] or '')
    except Exception:pass  # metadata only; the inference preflight checks availability
    return {'python':platform.python_version(),'system':platform.system(),'packages':versions,'gpus':gpus,'ollama_models':ollama}
