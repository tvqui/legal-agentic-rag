"""Bounded Ollama lifecycle; models stay outside saved Kaggle Output."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import urllib.request

def stop(process):
    if process is None or process.poll() is not None: return
    try:
        os.killpg(process.pid,signal.SIGTERM); process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL); process.wait(timeout=15)
    except ProcessLookupError: pass

def bounded_command(arguments,environment,log_path,timeout):
    with Path(log_path).open('w',encoding='utf-8') as log:
        process=subprocess.Popen(arguments,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        started=last=time.monotonic()
        try:
            while process.poll() is None:
                time.sleep(2); now=time.monotonic()
                if now-last>=30:
                    print('OLLAMA_SETUP elapsed='+str(int(now-started))+'s log='+Path(log_path).name,flush=True); last=now
                if now-started>=timeout: raise TimeoutError('Ollama setup deadline exceeded: '+Path(log_path).name)
            if process.returncode: raise RuntimeError('Ollama setup failed; see '+str(log_path))
        finally: stop(process)

@contextmanager
def session(reports,model):
    reports=Path(reports); reports.mkdir(parents=True,exist_ok=True)
    environment=dict(os.environ,OLLAMA_HOST='127.0.0.1:11434',OLLAMA_MODELS='/tmp/vn_labor_ollama_models',
        CUDA_VISIBLE_DEVICES='1',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1')
    if not shutil.which('ollama'):
        installer=Path('/tmp/vn_install_ollama.sh')
        with urllib.request.urlopen('https://ollama.com/install.sh',timeout=60) as response:
            data=response.read(1024*1024+1)
        if len(data)>1024*1024: raise RuntimeError('Ollama installer exceeds size limit')
        installer.write_bytes(data)
        bounded_command(['bash',str(installer)],environment,reports/'ollama_install.log',900)
    if not shutil.which('ollama'): raise RuntimeError('Ollama installation is incomplete')
    # A foreign process may have the wrong GPU/model location. Fail visibly.
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2): pass
    except Exception: pass
    else: raise RuntimeError('Ollama already runs on 11434. Start a fresh Kaggle session before this notebook.')
    process=None
    with (reports/'ollama_serve.log').open('w',encoding='utf-8') as log:
        try:
            process=subprocess.Popen(['ollama','serve'],env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            deadline=time.monotonic()+180
            while True:
                if process.poll() is not None: raise RuntimeError('Ollama exited; see ollama_serve.log')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2): pass
                    break
                except Exception:
                    if time.monotonic()>deadline: raise TimeoutError('Ollama startup timed out')
                    time.sleep(2)
            bounded_command(['ollama','pull',model],environment,reports/'ollama_pull.log',2400)
            with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=10) as response:
                models=json.load(response).get('models',[])
            if model not in {row.get('name') for row in models}: raise RuntimeError('Ollama model was not confirmed')
            print('OLLAMA_READY model='+model+' GPU=1',flush=True)
            yield
        finally: stop(process)
