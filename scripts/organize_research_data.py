"""Read-only research views of an existing artifact; never a runtime replacement."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile
from vn_labor_offline.artifact_layout import resolve_member, resolve_path, runtime_name

RULE = {'SourceDocument', 'DocumentVersion', 'LegalInstrument', 'ConsolidatedDocumentVersion',
        'SupplementaryDocument', 'Annex', 'Form', 'Chapter', 'Section', 'Article', 'Clause',
        'Point', 'ProvisionIdentity', 'ProvisionVersion', 'Document', 'Provision'}
FACT = {'Case', 'Judgment', 'Precedent', 'CassationDecision', 'CaseFeature', 'Actor', 'Event', 'FactAssertion', 'Community'}
ONTOLOGY = {'LegalIssue', 'LegalConcept'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(data):
    return [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line.strip()]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n')


@contextmanager
def artifact_reader(source):
    """ZIP members are read in memory, never extracted or executed."""
    source = Path(source).resolve(strict=True)
    if source.is_file():
        with zipfile.ZipFile(source) as archive:
            names = [i.filename for i in archive.infolist() if not i.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError('Duplicate ZIP members')
            for name in names + [i.orig_filename for i in archive.infolist()]:
                p = PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
                    raise ValueError('Unsafe ZIP member')
            roots = [n[:-len(suffix)] for n in names
                     for suffix in ('06_indexes/retrieval_units.jsonl','retrieval/retrieval_units.jsonl')
                     if n.endswith(suffix)]
            if len(roots) != 1:
                raise ValueError('Expected exactly one artifact root')
            prefix = roots[0]
            inventory = [{'path': n[len(prefix):], 'bytes': archive.getinfo(n).file_size}
                         for n in names if n.startswith(prefix)]
            def read(relative):
                info = archive.getinfo(resolve_member(names, relative))
                if info.file_size > 512 * 1024**2:
                    raise ValueError('JSON input exceeds 512 MiB limit')
                return archive.read(info)
            yield read, inventory, {'path': str(source), 'sha256': file_hash(source)}
    else:
        root = source / 'artifacts' if (source / 'artifacts').is_dir() else source
        inventory = []
        for p in sorted(root.rglob('*')):
            if p.is_symlink():
                raise ValueError('Symlink in artifact')
            if p.is_file():
                inventory.append({'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size})
        def read(relative):
            p = resolve_path(root, relative)
            if p.stat().st_size > 512 * 1024**2:
                raise ValueError('JSON input exceeds 512 MiB limit')
            return p.read_bytes()
        yield read, inventory, {'path': str(root), 'sha256': None}


def partition(nodes, edges):
    ids = [n['id'] for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate node IDs')
    edge_ids = [e['id'] for e in edges if 'id' in e]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError('Duplicate edge IDs')
    membership = {}
    groups = {k: {'nodes': [], 'edges': []} for k in ('rule', 'ontology', 'fact', 'derived')}
    for node in nodes:
        kind = node.get('label', node.get('type'))
        layer = 'rule' if kind in RULE else 'ontology' if kind in ONTOLOGY else 'fact' if kind in FACT else 'derived'
        membership[node['id']] = layer
        groups[layer]['nodes'].append(node)
    cross = []
    for edge in edges:
        source, target = edge.get('source'), edge.get('target')
        if source not in membership or target not in membership:
            raise ValueError('Missing graph endpoint')
        if membership[source] == membership[target]:
            groups[membership[source]]['edges'].append(edge)
        else:
            cross.append(edge)
    return groups, cross


def stage_peer(peer, units, destination):
    """Stage definition hints only; source approval labels are observations."""
    peer = Path(peer).resolve(strict=True)
    base = peer / 'Hierargraph'
    inputs = {}
    def load(relative):
        p = base / relative
        data = p.read_bytes()
        inputs[relative] = sha(data)
        return rows(data)
    rule = load('rule_graph/nodes.jsonl')
    concepts = load('ontology_graph/nodes.jsonl')
    evidence = load('ontology_graph/evidence.jsonl')
    relations = load('ontology_graph/edges.jsonl')
    if len({n['id'] for n in rule + concepts}) != len(rule + concepts):
        raise ValueError('Duplicate peer node IDs')
    rule_by_id = {n['id']: n for n in rule if n['type'] == 'Provision'}
    unit_by_id = {u['unit_id']: u for u in units}
    evidence_by_id = {}
    for record in evidence:
        evidence_by_id.setdefault(record['graph_record_id'], []).extend(record.get('provenance', []))
    hints, rejected, mapping = [], [], []
    for node in rule_by_id.values():
        original = node['properties'].get('source_record_id')
        if original in unit_by_id:
            mapping.append({'peer_id': node['id'], 'unit_id': original})
    for concept in concepts:
        if concept.get('type') != 'LegalConcept':
            continue
        props = concept['properties']
        verified = []
        for ev in evidence_by_id.get(concept['id'], []):
            provision = rule_by_id.get(ev.get('provision_node_id'))
            if not provision:
                continue
            unit = unit_by_id.get(provision['properties'].get('source_record_id'))
            start, end, quote = ev.get('provision_char_start'), ev.get('provision_char_end'), ev.get('quote')
            text = provision['properties'].get('source_properties', {}).get('text', '')
            if (unit and isinstance(quote, str) and quote and type(start) is int and type(end) is int
                    and 0 <= start < end <= len(text) and text[start:end] == quote
                    and sha(quote.encode('utf-8')) == ev.get('quote_sha256')
                    and isinstance(unit.get('source_text'), str) and quote in unit['source_text']):
                verified.append({'unit_id': unit['unit_id'], 'quote': quote,
                                 'quote_sha256': ev['quote_sha256'], 'peer_span': [start, end],
                                 'artifact_source_text_sha256': sha(unit['source_text'].encode('utf-8')),
                                 'artifact_span': [unit['source_text'].index(quote), unit['source_text'].index(quote) + len(quote)]})
        targets = {e['target_id'] for e in relations
                   if e.get('type') == 'REGULATED_BY' and e.get('source_id') == concept['id']}
        valid_ids = {e['unit_id'] for e in verified}
        grounded = any(rule_by_id.get(t, {}).get('properties', {}).get('source_record_id') in valid_ids for t in targets)
        definition_matches = any(props.get('definition_vi') == ev['quote'] for ev in verified)
        if not verified or not grounded or not definition_matches:
            rejected.append({'id': concept['id'], 'reason': 'NO_EXACT_GROUNDING_IN_CURRENT_ARTIFACT'})
            continue
        hints.append({'id': concept['id'], 'label_vi': props.get('label_vi'),
                      'definition_vi': props['definition_vi'], 'evidence': verified,
                      'source_claims': {'verification': props.get('verification'),
                                        'independent_approval': props.get('independent_approval')},
                      'status': 'LITERAL_MATCH_ONLY_NOT_LEGAL_APPROVAL', 'enabled_online': False,
                      'temporal_verified': False, 'applicability_verified': False})
    accepted = {n['id'] for n in hints}
    taxonomy = [e for e in relations if e.get('type') == 'IS_A'
                and e.get('source_id') in accepted and e.get('target_id') in accepted]
    write_rows(destination / 'definition_hints.jsonl', hints)
    write_rows(destination / 'taxonomy_source_observations.jsonl', taxonomy)
    write_rows(destination / 'provision_id_mapping.jsonl', mapping)
    write_rows(destination / 'excluded_concepts.jsonl', rejected)
    report = {'source': str(peer), 'input_sha256': inputs, 'accepted': len(hints),
              'excluded': len(rejected), 'mapped_provisions': len(mapping),
              'enabled_online': False, 'legal_approval': False}
    write_json(destination / 'report.json', report)
    return report


def build(source, output, peer=None):
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new output directory')
    for protected in [source] + ([Path(peer).resolve(strict=True)] if peer else []):
        if output == protected or protected in output.parents or output in protected.parents:
            raise ValueError('Output overlaps input')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.research-', dir=output.parent))
    try:
        with artifact_reader(source) as (read, inventory, origin):
            inputs = {}
            def load(relative):
                data = read(relative)
                inputs[relative] = sha(data)
                return rows(data)
            nodes = load('05_graph/nodes.jsonl')
            edges = load('05_graph/edges.jsonl')
            units = load('06_indexes/retrieval_units.jsonl')
            unit_ids = [u['unit_id'] for u in units]
            if len(set(unit_ids)) != len(unit_ids) or not set(unit_ids) <= {n['id'] for n in nodes}:
                raise ValueError('Invalid retrieval IDs')
            groups, cross = partition(nodes, edges)
            write_rows(temporary / '00_catalog/artifact_files.jsonl', inventory)
            if any(x['path'] in {'00_manifest/source_catalog_resolved.jsonl',runtime_name('00_manifest/source_catalog_resolved.jsonl')} for x in inventory):
                catalog = load('00_manifest/source_catalog_resolved.jsonl')
                write_rows(temporary / '01_sources/source_catalog_resolved.jsonl', catalog)
            counts = {}
            for name, content in groups.items():
                for kind, records in content.items():
                    write_rows(temporary / f'02_graph/{name}/{kind}.jsonl', records)
                counts[name] = {k: len(v) for k, v in content.items()}
                counts[name]['node_types'] = dict(Counter(n.get('label', n.get('type')) for n in content['nodes']))
            write_rows(temporary / '02_graph/cross_layer/edges.jsonl', cross)
            write_rows(temporary / '03_retrieval/retrieval_units.jsonl', units)
            write_json(temporary / '01_sources/locations.json', {
                'artifact': origin, 'paths': [x for x in inventory if x['path'].startswith(('00_manifest/', '01_registry/', '02_extracted/', '03_structure/'))],
                'note': 'References only; source files remain in the original artifact.'})
            peer_report = stage_peer(peer, units, temporary / '04_peer_ontology') if peer else None
            manifest = {'schema': 'research-organization-v1', 'purpose': 'RESEARCH_VIEW_NOT_RUNTIME_ARTIFACT',
                        'source': origin, 'input_sha256': inputs, 'groups': counts,
                        'cross_layer_edges': len(cross), 'nodes': len(nodes), 'edges': len(edges),
                        'retrieval_units': len(units), 'peer': peer_report,
                        'script_sha256': file_hash(Path(__file__)), 'enabled_online': False}
            write_json(temporary / '00_catalog/manifest.json', manifest)
            (temporary / 'README.md').write_text(
                '# Dữ liệu nghiên cứu tách lớp\n\n'
                '00_catalog: kiểm kê, số lượng và fingerprint.\n'
                '01_sources: danh mục và vị trí nguồn gốc; không sao chép PDF.\n'
                '02_graph/rule: văn bản và quy định Điều–Khoản–Điểm.\n'
                '02_graph/ontology: khái niệm và chủ đề.\n'
                '02_graph/fact: hồ sơ vụ việc, đặc trưng và cộng đồng vụ án; không khẳng định mọi đặc trưng đã được xác minh.\n'
                '02_graph/derived: checklist và loại node chưa được phân nhóm.\n'
                '02_graph/cross_layer: cạnh liên tầng; cần nạp cùng các tầng để truy vết.\n'
                '03_retrieval: đơn vị tìm kiếm giữ nguyên ID và nội dung. BM25/FAISS vẫn nằm trong artifact gốc.\n'
                '04_peer_ontology: gợi ý định nghĩa khớp nguyên văn, CHƯA bật ONLINE.\n\n'
                'Đây là góc nhìn phục vụ nghiên cứu, không phải phê duyệt pháp lý. '
                'Không dùng thư mục này thay artifact_source. Xem docs/data/README.md để chạy lại.\n', encoding='utf-8')
            write_rows(temporary / '00_catalog/output_hashes.jsonl', [
                {'path': p.relative_to(temporary).as_posix(), 'sha256': file_hash(p)}
                for p in sorted(temporary.rglob('*')) if p.is_file()])
        temporary.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(temporary)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--peer', type=Path)
    args = parser.parse_args()
    report = build(args.artifact, args.output, args.peer)
    print(json.dumps({k: report[k] for k in ['purpose', 'nodes', 'edges', 'retrieval_units', 'peer']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
