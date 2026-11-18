"""Versioned runtime layout. Fixed aliases only; no configurable path remapping."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

SCHEMA = 'phapdien-runtime-2'
ALIASES = {'00_manifest/source_catalog_resolved.jsonl': 'shared/source_catalog_resolved.jsonl',
           '05_graph': 'graph', '06_indexes': 'retrieval'}
CHECKS = ('final_outputs_validation.json', 'dense_validation.json', 'neo4j_validation.json')


def runtime_name(relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or ':' in relative:
        raise ValueError('Unsafe artifact path')
    if relative.startswith('reports/') and relative.split('/', 1)[1] in CHECKS:
        return 'checks/' + relative.split('/', 1)[1]
    for old, new in ALIASES.items():
        if relative == old or relative.startswith(old + '/'):
            return new + relative[len(old):]
    return relative


def resolve_path(root, relative):
    root = Path(root)
    translated = runtime_name(relative)
    old, new = root / relative, root / translated
    if old != new and old.exists() and new.exists():
        raise ValueError('Mixed artifact layouts: ' + relative)
    return new if new.exists() else old


def resolve_member(names, relative):
    """Find one physical ZIP/relative file for a stable logical name."""
    translated = runtime_name(relative)
    suffixes = {relative, translated}
    found = [n for n in names if any(n == suffix or n.endswith('/' + suffix) for suffix in suffixes)]
    if len(found) != 1:
        raise ValueError(f'Expected one {relative}; found {len(found)}')
    return found[0]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_layout(root):
    root = Path(root)
    marker = root / 'runtime_manifest.json'
    if not marker.exists():
        if any((root / p).exists() for p in ('shared', 'graph', 'retrieval', 'checks')):
            raise ValueError('Runtime v2 manifest missing')
        return None
    manifest = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(manifest,dict):
        raise ValueError('Invalid runtime manifest object')
    if any((root / name).exists() for name in ('05_graph','06_indexes','00_manifest','reports')):
        raise ValueError('Mixed artifact layouts')
    if manifest.get('schema') != SCHEMA or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unknown runtime manifest')
    files = manifest['files']
    required = [runtime_name(n) for n in ('05_graph/nodes.jsonl', '05_graph/edges.jsonl',
        '06_indexes/retrieval_units.jsonl', '06_indexes/dense/metadata.jsonl',
        '06_indexes/dense/faiss.index', '06_indexes/bm25/corpus.jsonl',
        '00_manifest/source_catalog_resolved.jsonl', *('reports/' + n for n in CHECKS))]
    if not set(required) <= set(files):
        raise ValueError('Runtime manifest missing required files')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root / '.complete'}
    if actual != set(files) | {'runtime_manifest.json'}:
        raise ValueError('Runtime file inventory mismatch')
    for name, expected in files.items():
        runtime_name(name)  # reject absolute/traversal paths before opening
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError('Unsafe runtime file')
        if digest(p) != expected:
            raise ValueError('Runtime SHA256 mismatch: ' + name)
    return manifest


def package_outputs(artifact, destination):
    """Publish a fresh release directory; never modify source or fabricate checks."""
    artifact = Path(artifact).resolve(strict=True)
    if (artifact / 'artifacts').is_dir():
        artifact = artifact / 'artifacts'
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Release already exists; choose a new directory')
    if artifact == destination or artifact in destination.parents or destination in artifact.parents:
        raise ValueError('Release overlaps artifact')
    from vn_labor_online.artifact_store import ArtifactStore
    from vn_labor_online.config import OnlineConfig
    store = ArtifactStore(OnlineConfig(artifact_source=str(artifact)))
    # Gate on the same compatibility checks as the real reader, not legal approval.
    if not store.report.compatible:
        raise ValueError('Artifact is not technically compatible')
    if (artifact / 'runtime_manifest.json').exists():
        raise ValueError('Packaging needs the full OFFLINE working artifact, not a runtime-only release')
    store.load_bm25()
    store.load_faiss()
    source_files = [p for p in sorted(artifact.rglob('*')) if p.is_file()]
    if any(p.is_symlink() for p in artifact.rglob('*')):
        raise ValueError('Symlinks not allowed in release source')
    runtime = {}
    for p in source_files:
        rel = p.relative_to(artifact).as_posix()
        if (rel in {'00_manifest/source_catalog_resolved.jsonl', '05_graph/nodes.jsonl',
                    '05_graph/edges.jsonl', '06_indexes/retrieval_units.jsonl',
                    '06_indexes/dense/metadata.jsonl', '06_indexes/dense/faiss.index'}
                or rel.startswith('06_indexes/bm25/') and p.suffix in {'.json','.jsonl','.npy'}
                or rel in {'reports/' + n for n in CHECKS}):
            runtime[runtime_name(rel)] = p
    if not runtime:
        raise ValueError('Package expects legacy OFFLINE working layout')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.release-', dir=destination.parent))
    try:
        hashes = {name: digest(p) for name, p in runtime.items()}
        readme = ('# Artifact dành cho ONLINE\n\n'
                  'shared/: danh mục nguồn dùng chung.\n'
                  'graph/: node và cạnh nguyên bản; type/label phân biệt Rule, Ontology và Fact, không nhân bản liên kết.\n'
                  'retrieval/: retrieval_units dùng chung; bm25/ và dense/ chứa chỉ mục tương ứng.\n'
                  'checks/: ba báo cáo tối thiểu để ONLINE kiểm tương thích.\n'
                  'runtime_manifest.json: phiên bản cấu trúc và SHA-256 từng tệp.\n\n'
                  'Chọn ZIP này hoặc thư mục artifacts làm artifact_source. '
                  'Đạt kiểm tra kỹ thuật không phải phê duyệt pháp lý.\n').encode('utf-8')
        hashes['README.md'] = hashlib.sha256(readme).hexdigest()
        manifest = {'schema': SCHEMA, 'purpose': 'ONLINE_RUNTIME', 'files': hashes,
                    'build_id': store.report.build_id,
                    'retrieval_unit_fingerprint': store.report.retrieval_unit_fingerprint,
                    'dense_fingerprint': store.report.dense_fingerprint,
                    'legal_status': store.report.legal_status,
                    'provisional_reasons': store.report.provisional_reasons}
        with zipfile.ZipFile(temporary / 'vn_labor_online.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for name, p in runtime.items():
                z.write(p, 'artifacts/' + name)
            z.writestr('artifacts/README.md', readme)
            z.writestr('artifacts/runtime_manifest.json', json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        with zipfile.ZipFile(temporary / 'vn_labor_online.zip') as check:
            for name, expected in hashes.items():
                with check.open('artifacts/' + name) as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest() != expected:
                        raise ValueError('Source changed while packaging: ' + name)
        runtime_sources = set(runtime.values())
        # Complementary audit/intermediate package: no duplicated runtime data.
        with zipfile.ZipFile(temporary / 'vn_labor_offline_review.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for p in source_files:
                if p not in runtime_sources and not p.name.endswith('.tmp'):
                    z.write(p, 'offline_review/' + p.relative_to(artifact).as_posix())
            z.writestr('README.md', 'Hồ sơ kiểm tra và dữ liệu trung gian OFFLINE. Không dùng làm artifact_source. '
                       'Dùng cùng vn_labor_online.zip để đối chiếu toàn bộ đầu ra. Không chứa corpus PDF bên ngoài artifact.\n')
        release = {'schema': SCHEMA, 'build_id': store.report.build_id,
                   'archives': {n: digest(temporary / n) for n in ('vn_labor_online.zip', 'vn_labor_offline_review.zip')}}
        (temporary / 'release.json').write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding='utf-8')
        (temporary / 'README.md').write_text(
            '# Đầu ra OFFLINE\n\n- vn_labor_online.zip: đưa vào Backend/Kaggle ONLINE.\n'
            '- vn_labor_offline_review.zip: báo cáo chi tiết và dữ liệu trung gian.\n'
            '- release.json: SHA-256 hai gói và build ID.\n\n'
            'Artifact làm việc và checkpoint đầy đủ vẫn giữ riêng để tiếp tục OFFLINE.\n', encoding='utf-8')
        os.rename(temporary, destination)
        return release
    except BaseException:
        import shutil
        shutil.rmtree(temporary)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package_outputs(args.artifact, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
