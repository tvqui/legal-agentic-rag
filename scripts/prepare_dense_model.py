"""Download only BGE-M3 inference files, sequentially with bounded memory."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / '.cache/models/bge-m3'
REPO = 'BAAI/bge-m3'
REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
FILES = ['config.json', 'tokenizer.json', 'tokenizer_config.json',
         'special_tokens_map.json', 'sentencepiece.bpe.model',
         'colbert_linear.pt', 'sparse_linear.pt', 'pytorch_model.bin']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    MODEL.mkdir(parents=True, exist_ok=True)
    source_path = MODEL / 'source.json'
    if source_path.exists():
        previous = json.loads(source_path.read_text(encoding='utf-8'))
        entries = {entry['rfilename']: entry for entry in previous['siblings']}
        if previous.get('sha') == REVISION and all(
            (MODEL / name).is_file() and (MODEL / name).stat().st_size > 0
            and (MODEL / name).stat().st_size == entries[name].get('size', entries[name].get('lfs', {}).get('size'))
            and (not entries[name].get('lfs', {}).get('sha256') or
                 digest(MODEL / name) == entries[name]['lfs']['sha256'])
            for name in FILES
        ):
            print(f'Local model verified; no download needed: {MODEL}', flush=True)
            return
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(
        total=8, connect=8, read=8, status=8, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504])))
    response = session.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}',
                           params={'blobs': 'true'}, timeout=(20, 60))
    response.raise_for_status()
    info = response.json()
    assert info['sha'] == REVISION
    (MODEL / 'source.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    entries = {entry['rfilename']: entry for entry in info['siblings']}
    cache = ROOT / '.cache/huggingface/hub/models--BAAI--bge-m3/snapshots' / REVISION
    for name in FILES:
        entry = entries[name]
        size = entry.get('size') or entry.get('lfs', {}).get('size')
        sha = entry.get('lfs', {}).get('sha256')
        target = MODEL / name
        def valid(path):
            return path.is_file() and path.stat().st_size > 0 and (
                size is None or path.stat().st_size == size) and (sha is None or digest(path) == sha)
        if valid(target):
            print(f'Cached: {name}', flush=True)
            continue
        if valid(cache / name):
            shutil.copyfile(cache / name, target)
            print(f'Reused HF cache: {name}', flush=True)
            continue
        partial = target.with_suffix(target.suffix + '.download')
        url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
        for attempt in range(1, 7):
            try:
                offset = partial.stat().st_size if partial.exists() else 0
                if size and offset == size and (sha is None or digest(partial) == sha):
                    os.replace(partial, target)
                    break
                headers = {'Range': f'bytes={offset}-'} if offset else {}
                with session.get(url, headers=headers, stream=True, timeout=(20, 60)) as response:
                    response.raise_for_status()
                    if offset and response.status_code != 206:
                        offset = 0
                    if response.status_code == 206 and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise RuntimeError('Unexpected download range')
                    print(f'Downloading {name}, resume={offset}, attempt={attempt}', flush=True)
                    last = time.monotonic()
                    with partial.open('ab' if offset else 'wb') as stream:
                        for block in response.iter_content(chunk_size=1024 * 1024):
                            stream.write(block)
                            if time.monotonic() - last > 15:
                                print(f'{name}: {stream.tell() / 1024**2:.0f} MiB', flush=True)
                                last = time.monotonic()
                if not valid(partial):
                    raise RuntimeError(f'File size/hash validation failed: {name}')
                os.replace(partial, target)
                print(f'Verified: {name} ({target.stat().st_size} bytes)', flush=True)
                break
            except (requests.RequestException, RuntimeError) as exc:
                print(f'{name}: attempt {attempt} failed ({type(exc).__name__})', flush=True)
                if attempt == 6:
                    raise
                time.sleep(min(attempt * 2, 10))
    print(f'Model ready: {MODEL}', flush=True)


if __name__ == '__main__':
    main()
