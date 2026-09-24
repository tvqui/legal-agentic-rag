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


def detect_artifact(explicit: str | None) -> Path:
    if explicit:
        result = Path(explicit)
    else:
        matches = list(Path("/kaggle/input").rglob("vn_labor_results_v8.1(aura).zip"))
        if len(matches) != 1:
            matches = list(Path("/kaggle/input").rglob("vn_labor_results_v8_1_aura.zip"))
        if len(matches) != 1:
            raise RuntimeError(f"Add exactly one V8.1 Aura result ZIP as Kaggle Input; found {len(matches)}")
        result = matches[0]
    if not result.is_file():
        raise FileNotFoundError(result)
    return result.resolve()


def gpu_count() -> int:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], text=True
        )
        return len([line for line in output.splitlines() if line.strip()])
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact")
    parser.add_argument("--config", default="config/online_kaggle.yaml")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-pull", action="store_true")
    args = parser.parse_args()

    if not shutil.which("ollama"):
        raise RuntimeError("Ollama is missing. Run: curl -fsSL https://ollama.com/install.sh | sh")
    api_key = secret("VN_LABOR_API_KEY")
    secret("NGROK_AUTHTOKEN")
    hf_token = secret("HF_TOKEN", required=False)
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
        if not args.skip_pull:
            subprocess.run(["ollama", "pull", args.model], env=ollama_env, check=True)
        backend = subprocess.Popen(
            [sys.executable, "scripts/serve_online.py", "--config", args.config,
             "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=ROOT, env=backend_env, stdout=backend_log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        wait_json(f"http://127.0.0.1:{args.port}/health", None, backend, 300)
        readiness = wait_json(f"http://127.0.0.1:{args.port}/ready", api_key, backend, 120)
        adjudicator = readiness.get("components", {}).get("adjudicator", {})
        if not readiness.get("ready") or adjudicator.get("status") != "READY":
            raise RuntimeError(f"ONLINE backend is not fully ready: {readiness}")
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
