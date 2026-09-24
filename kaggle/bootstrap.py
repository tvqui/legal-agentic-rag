"""Prepare the uploaded bundle on Kaggle; stdlib only until dependencies exist."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile


def safe_relative(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError(f'Unsafe bundle path: {name}')
    return p


def verify_bundle(source):
    manifest = json.loads((source / 'bundle_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1:
        raise ValueError('Unsupported bundle schema')
    for row in manifest['files']:
        p = source / safe_relative(row['path'])
        if not p.is_file() or p.stat().st_size != row['bytes']:
            raise ValueError(f'Incomplete upload: {row["path"]}')
        with p.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if digest != row['sha256']:
            raise ValueError(f'Upload checksum mismatch: {row["path"]}')
    return manifest


def restore_artifacts(archive, root):
    """Restore only an export produced by this notebook, into an empty output dir."""
    out = root / 'artifacts'
    if out.exists() and any(out.iterdir()):
        raise ValueError('Artifacts already exist. Use the current checkpoints or a fresh session.')
    if archive.is_dir():
        source = archive if archive.name == 'artifacts' else archive / 'artifacts'
        if not source.is_dir() or source.is_symlink():
            raise ValueError('Select the exported artifacts directory in Kaggle Input.')
        for item in source.rglob('*'):
            safe_relative(item.relative_to(source).as_posix())
            if item.is_symlink():
                raise ValueError('Symlinks are not allowed in checkpoint directories')
        shutil.copytree(source, out, dirs_exist_ok=True)
        return
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            p = safe_relative(member.filename)
            if not p.parts or p.parts[0] != 'artifacts':
                raise ValueError('Checkpoint archive must contain only artifacts/')
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symlinks are not allowed in a checkpoint archive')
        z.extractall(root)


def prepare(source, working=Path('/kaggle/working'), restore=''):
    manifest = verify_bundle(source)
    root = working / 'vn_labor_project'
    root.mkdir(parents=True, exist_ok=True)
    # Copy code/config only. Inputs remain in Kaggle's read-only dataset mount.
    for row in manifest['files']:
        rel = safe_relative(row['path'])
        if rel.parts[0] in {'data', 'seed_converted'}:
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, target)
    (root / 'bundle_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    data_link = root / 'data'
    if not data_link.exists():
        data_link.symlink_to(source / 'data', target_is_directory=True)
    elif data_link.resolve() != (source / 'data').resolve():
        raise ValueError('Existing project points to another dataset. Start a fresh session.')
    if restore:
        restore_artifacts(Path(restore), root)
    converted = root / 'artifacts/01_extracted/converted_docx'
    converted.mkdir(parents=True, exist_ok=True)
    for row in manifest['converted_docs']:
        # Raw source SHA is included in the same verified manifest.
        shutil.copy2(source / row['seed'], converted / row['output_name'])
    # Models and Python environment are not saved as Notebook output.
    cache = Path('/tmp/vn_labor_cache')
    cache.mkdir(parents=True, exist_ok=True)
    link = root / '.cache'
    if not link.exists():
        link.symlink_to(cache, target_is_directory=True)
    os.environ.update({
        'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1', 'CUDA_VISIBLE_DEVICES': '0',
        'HF_HOME': str(cache / 'huggingface'), 'EASYOCR_MODULE_PATH': str(cache / 'easyocr'),
        'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4', 'TOKENIZERS_PARALLELISM': 'false',
        'USE_TF': '0', 'USE_FLAX': '0',
    })
    print(f'Bundle verified: {manifest["corpus_files"]} corpus files. Project: {root}')
    return root


def install(root):
    from importlib.metadata import version, PackageNotFoundError
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('This bundle targets the verified Kaggle Python 3.12 environment.')
    constraints = (root / 'kaggle/constraints.txt').read_text(encoding='utf-8')
    for name in ('torch', 'torchvision', 'torchaudio'):
        try:
            constraints += f'\n{name}=={version(name)}'
        except PackageNotFoundError:
            if name == 'torch':
                raise RuntimeError('Enable a Kaggle GPU environment before setup.')
    constraint_path = root / 'kaggle/runtime_constraints.txt'
    constraint_path.write_text(constraints + '\n', encoding='utf-8')
    env_dir = Path('/tmp/vn_labor_env')
    python = env_dir / 'bin/python'
    # Kaggle's system Python may not provide a working ensurepip. Recreate the
    # venv metadata even after a partial setup; preserve already installed files.
    subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages',
                    '--without-pip', str(env_dir)], check=True)
    # Host pip manages the target interpreter without bootstrapping pip there.
    # This also avoids treating an existing bin/python as proof of a complete env.
    subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
                    'install', '--disable-pip-version-check',
                    '-c', str(constraint_path), '-e', str(root) + '[ocr,retrieval,graph,community]',
                    'setuptools==81.0.0'], check=True)
    return python
