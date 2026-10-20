"""Run the complete ONLINE backend on a Kaggle GPU and expose it securely."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def secret(name: str, required: bool = True) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        try:
            from kaggle_secrets import UserSecretsClient
            value = UserSecretsClient().get_secret(name).strip()
        except Exception:
            value = ""
    if required and not value:
        raise RuntimeError(f"Missing Kaggle Secret: {name}")
    if value:
        os.environ[name] = value
    return value


def get_json(url: str, token: str | None = None, timeout: int = 10) -> dict:
    headers = {"Accept": "application/json", "ngrok-skip-browser-warning": "true"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        return json.loads(response.read())


def wait_json(url: str, token: str | None, process: subprocess.Popen, timeout: int = 300) -> dict:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited early with code {process.returncode}")
        try:
            return get_json(url, token)
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def readiness_diagnostics(snapshot):
    """Allowlisted startup diagnostics, never raw SDK errors or configuration."""
    values={}
    for name in ('researcher','auditor','adjudicator','answer_reviewer'):
        component=snapshot.get('components',{}).get(name,{})
        values[name]={key:component[key] for key in ('status','provider','error_code','quota_kind','retry_after_seconds') if key in component}
    return values


def wait_ready(url, token, process, timeout=180):
    deadline=time.monotonic()+timeout
    last={}
    last_error=None
    last_print=-float('inf')
    permanent={'GEMINI_API_KEY_MISSING','GEMINI_MODEL_MISSING','GEMINI_SDK_MISSING',
               'GEMINI_HTTP_400','GEMINI_HTTP_401','GEMINI_HTTP_403','GEMINI_HTTP_404'}
    while time.monotonic()<deadline:
        exit_code=process.poll()
        if exit_code is not None:
            raise RuntimeError(f'Backend exited during readiness with code {exit_code}; see logs/backend.log')
        try:
            # /ready may perform two sequential inference probes, each <=20s.
            last=get_json(url,token,timeout=min(45,max(.1,deadline-time.monotonic())))
            if not isinstance(last,dict): raise ValueError('Invalid readiness response')
            components=last.get('components',{})
            required=('researcher','auditor','adjudicator','answer_reviewer')
            if last.get('ready') is True and all(components.get(name,{}).get('status')=='READY' for name in required):
                return last
            diagnostic=readiness_diagnostics(last)
            if time.monotonic()-last_print>=10:
                print('ONLINE_READY_WAIT '+json.dumps(diagnostic),flush=True)
                last_print=time.monotonic()
            if any(value.get('error_code') in permanent or value.get('quota_kind') in {'DAILY','QUOTA_DISABLED'} for value in diagnostic.values()):
                raise RuntimeError('ONLINE dependency configuration/quota needs attention: '+json.dumps(diagnostic))
            last_error='dependencies not ready'
        except RuntimeError:
            raise
        except Exception as exc:
            # Exception messages/URLs can contain credentials; types suffice.
            last_error=type(exc).__name__
        remaining=deadline-time.monotonic()
        if remaining>0: time.sleep(min(2,remaining))
    raise RuntimeError('ONLINE readiness timed out; last_error='+str(last_error)+
                       '; components='+json.dumps(readiness_diagnostics(last))+'; see logs/backend.log')


def _artifact_directory_roots(input_root: Path) -> list[Path]:
    """Find Kaggle datasets after Kaggle has automatically unpacked the ZIP."""
    roots = set()
    for marker in input_root.rglob("reports/final_outputs_validation.json"):
        artifact_dir = marker.parent.parent
        required = (
            artifact_dir / "06_indexes/retrieval_units.jsonl",
            artifact_dir / "05_graph/nodes.jsonl",
            artifact_dir / "reports/dense_validation.json",
            artifact_dir / "reports/neo4j_validation.json",
        )
        if all(item.is_file() for item in required):
            roots.add(artifact_dir.parent if artifact_dir.name == "artifacts" else artifact_dir)
    return sorted(roots)


def detect_artifact(explicit: str | None, *, input_root: Path | None = None) -> Path:
    if explicit:
        result = Path(explicit)
        if not result.exists():
            raise FileNotFoundError(result)
        return result.resolve()

    input_root = input_root or Path("/kaggle/input")
    names=('vn_labor_results.zip','vn_labor_results_20261014.zip',
           'vn_labor_results_v8.1(aura).zip','vn_labor_results_v8_1_aura.zip')
    zip_matches=sorted({path.resolve() for name in names for path in input_root.rglob(name)})
    directory_matches = _artifact_directory_roots(input_root)
    matches=zip_matches+directory_matches
    if len(matches) != 1:
        raise RuntimeError(
            "Add exactly one OFFLINE result ZIP or unpacked artifacts/ directory, "
            f"or pass --artifact explicitly; found {len(matches)} candidates: "+', '.join(str(path) for path in matches)
        )
    return matches[0].resolve()


def gpu_count() -> int:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], text=True
        )
        return len([line for line in output.splitlines() if line.strip()])
    except Exception:
        return 0


def ensure_ollama_model(model: str, env: dict, *, skip_pull: bool = False,
                        attempts: int = 3, total_seconds: float = 600) -> str:
    """Reuse the exact local model; bound downloading by time and attempts.

    A local manifest check is not an inference or model-quality certification.
    Backend readiness and the subsequent request checks still run normally.
    """
    if attempts < 1 or total_seconds <= 0:
        raise ValueError('Model download limits must be positive')
    def available():
        result = subprocess.run(['ollama', 'show', model], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=15, check=False)
        return result.returncode == 0
    if available():
        print(f'Ollama model cached: {model}; skipping registry download.', flush=True)
        return 'CACHED'
    if skip_pull:
        raise RuntimeError(f'--skip-pull requested but model is not available locally: {model}. '
                           'Retry without --skip-pull when the Ollama registry is reachable.')
    deadline = time.monotonic() + total_seconds
    last_error = 'not started'
    for attempt in range(1, attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        print(f'Ollama download {attempt}/{attempts}: {model}; remaining budget {remaining:.0f}s.', flush=True)
        try:
            result = subprocess.run(['ollama', 'pull', model], env=env,
                                    timeout=remaining, check=False)
            if result.returncode == 0:
                if not available():
                    raise RuntimeError(f'Ollama pull finished but the exact model is unavailable: {model}')
                return 'PULLED'
            last_error = f'exit code {result.returncode}'
        except subprocess.TimeoutExpired:
            last_error = 'download timeout'
            break
        if attempt < attempts:
            delay = min(5 * attempt, max(0, deadline - time.monotonic()))
            if delay <= 0: break
            print(f'Ollama download failed ({last_error}); retry in {delay:.0f}s.', flush=True)
            time.sleep(delay)
    raise RuntimeError(f'Ollama model download failed after bounded attempts: {model} ({last_error}). '
                       'Backend has not started. Keep the current model cache and retry later; '
                       'no OFFLINE rebuild or artifact upload is required.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact")
    parser.add_argument("--config", default="config/online_kaggle.yaml")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-pull", action="store_true")
    parser.add_argument("--ready-timeout",type=int,default=180)
    args = parser.parse_args()
    if not 1<=args.ready_timeout<=1800: parser.error("--ready-timeout must be between 1 and 1800 seconds")

    if not shutil.which("ollama"):
        raise RuntimeError("Ollama is missing. Run: curl -fsSL https://ollama.com/install.sh | sh")
    api_key = secret("VN_LABOR_API_KEY")
    secret("NGROK_AUTHTOKEN")
    hf_token = secret("HF_TOKEN", required=False)
    # Optional, backend-only. The selected config/environment controls whether it is used.
    secret("GEMINI_API_KEY", required=False)
    artifact = detect_artifact(args.artifact)
    count = gpu_count()
    if count < 1:
        raise RuntimeError("Enable a Kaggle GPU accelerator before starting ONLINE")

    working = Path("/kaggle/working/vn_labor_online")
    working.mkdir(parents=True, exist_ok=True)
    logs = working / "logs"
    logs.mkdir(exist_ok=True)
    ollama_env = os.environ.copy()
    ollama_env.update({
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(working / "ollama_models"),
        "CUDA_VISIBLE_DEVICES": "1" if count > 1 else "0",
    })
    backend_env = os.environ.copy()
    backend_env.update({
        "VN_LABOR_API_KEY": api_key,
        "VN_LABOR_ARTIFACT_SOURCE": str(artifact),
        "VN_LABOR_ONLINE_CACHE": str(working / "artifact_cache"),
        "VN_LABOR_ONLINE_CONFIG": args.config,
        "HF_HOME": str(working / "huggingface"),
        "CUDA_VISIBLE_DEVICES": "0",
        "PYTHONUNBUFFERED": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
    if hf_token:
        backend_env["HF_TOKEN"] = hf_token

    ollama_log = (logs / "ollama.log").open("w", encoding="utf-8")
    backend_log = (logs / "backend.log").open("w", encoding="utf-8")
    ollama = subprocess.Popen(["ollama", "serve"], env=ollama_env,
                              stdout=ollama_log, stderr=subprocess.STDOUT, start_new_session=True)
    backend = None
    listener = None
    try:
        wait_json("http://127.0.0.1:11434/api/tags", None, ollama, 60)
        ensure_ollama_model(args.model, ollama_env, skip_pull=args.skip_pull)
        subprocess.run([sys.executable, "scripts/prepare_online_models.py", "--config", args.config],
                       cwd=ROOT, env=backend_env, check=True)
        backend = subprocess.Popen(
            [sys.executable, "scripts/serve_online.py", "--config", args.config,
             "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=ROOT, env=backend_env, stdout=backend_log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        wait_json(f"http://127.0.0.1:{args.port}/health", None, backend, 300)
        readiness = wait_ready(f"http://127.0.0.1:{args.port}/ready",api_key,backend,args.ready_timeout)
        import ngrok
        listener = ngrok.forward(f"localhost:{args.port}", authtoken_from_env=True, compression=True)
        print("REMOTE_BACKEND_URL=" + listener.url(), flush=True)
        print("Use this URL only as VITE_BACKEND_TARGET; keep VN_LABOR_API_KEY secret.", flush=True)
        while backend.poll() is None and ollama.poll() is None:
            time.sleep(5)
        raise RuntimeError(f"A service stopped: backend={backend.poll()} ollama={ollama.poll()}")
    except KeyboardInterrupt:
        return 0
    finally:
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass
        for process in (backend, ollama):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        ollama_log.close()
        backend_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
