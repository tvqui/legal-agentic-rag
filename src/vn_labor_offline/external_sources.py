"""Version-pinned, bounded staging of supplementary legal corpora.

Never writes production catalog, graph, temporal changes, indexes or approvals.
Run with ``python -m vn_labor_offline.external_sources --help``.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

SOURCES = {
    'cases': {
        'repo': 'tmquan/anle-toaan-gov-vn',
        'revision': 'd6124923ddcba618811644f433de7c748a291e22',
        'files': {'documents': 'documents-00000-of-00001.parquet'},
        'license': 'cc-by-4.0', 'attribution': 'TMQuan / Vietnamese Án lệ + Bản án Corpus',
    },
    'legal': {
        'repo': 'th1nhng0/vietnamese-legal-documents',
        'revision': '8977887f17be2defae4c5171d55562e1cde7d695',
        'files': {'metadata': 'data/metadata.parquet', 'content': 'data/content.parquet',
                  'relationships': 'data/relationships.parquet'},
        'license': 'cc-by-4.0', 'attribution': 'Thịnh Ngô / Vietnamese Legal Documents',
    },
}
MAX_ROW_BYTES = 24_000_000  # source HTML can exceed 15 MB; still one bounded row


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def fold(value):
    text = unicodedata.normalize('NFD', str(value or '').casefold()).replace('đ', 'd')
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


def key(value):
    # UUID/portal-prefixed IDs are strings; never cast them to integer.
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ValueError('MISSING_OR_INVALID_ID')
    return str(value).strip()


def identifier(source, external_id):
    return 'ext_' + digest(SOURCES[source]['repo'] + ':' + external_id)[:24]


def parse_date(value):
    if value is None or value == '':
        return None
    for pattern in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value).strip(), pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError('INVALID_DATE')


def official_case_url(value):
    try:
        parsed = urlsplit(value or '')
        return (parsed.scheme == 'https' and parsed.hostname in {'anle.toaan.gov.vn', 'www.anle.toaan.gov.vn'}
                and not parsed.username and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        return False


def labour_scope(row, source):
    if source == 'cases':
        # A label is only a selection hint. Code disagreement remains a review issue.
        return (fold(row.get('category')) in {'labor', 'labour', 'lao dong'}
                or bool(re.search(r'(?:^|/)LĐ(?:-|$)', str(row.get('code') or row.get('official_document_id') or '').upper())))
    # Do not match incidental mentions of labour in a full HTML body, signatory,
    # or ministry name. Occupational/social-insurance documents are in scope.
    text = ' '.join(fold(row.get(k)) for k in ('title', 'nganh', 'linh_vuc'))
    return any(term in text for term in ('lao dong', 'tien luong', 'cong doan',
        'bao hiem xa hoi', 'bao hiem that nghiep', 'an toan ve sinh lao dong',
        'viec lam', 'thoi gio lam viec', 'nghi hang nam'))


def html_text(raw):
    soup = BeautifulSoup(raw, 'html.parser')
    for element in soup(['script', 'style', 'noscript', 'template', 'head']):
        element.decompose()
    body = soup.body or soup
    return '\n'.join(line.strip() for line in body.get_text('\n').splitlines() if line.strip())


def source_rows(source, table):
    """Only pinned Parquet. No remote dataset Python or supplied embeddings."""
    from datasets import load_dataset
    spec = SOURCES[source]
    url = f"https://huggingface.co/datasets/{spec['repo']}/resolve/{spec['revision']}/{spec['files'][table]}"
    print(dump({'event': 'EXTERNAL_SOURCE_READ', 'dataset': spec['repo'],
                'revision': spec['revision'], 'table': table}), flush=True)
    # Lazy initialization keeps download/configuration failures inside stage's
    # transaction and FAILED manifest, including a missing optional dependency.
    yield from load_dataset('parquet', data_files={'train': url}, split='train', streaming=True)


def jsonl_rows(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        for line in stream:
            if len(line.encode('utf-8')) > MAX_ROW_BYTES:
                raise ValueError('ROW_TOO_LARGE')
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError('JSONL_ROW_MUST_BE_OBJECT')
                yield value


class Scan:
    def __init__(self, rows, limit):
        self.rows, self.limit = rows, limit
        self.count = 0
        self.exhausted = False

    def __iter__(self):
        iterator = iter(self.rows)
        while not self.limit or self.count < self.limit:
            try:
                row = next(iterator)
            except StopIteration:
                self.exhausted = True
                return
            self.count += 1
            yield row
        # Do not read an extra (potentially huge) row to claim completeness.

    def report(self):
        return {'rows_scanned': self.count, 'source_exhausted': self.exhausted,
                'limit': self.limit, 'coverage': 'FULL_SCAN' if self.exhausted else 'BOUNDED_SCAN'}


def citation_spans(citation, text):
    spans = citation.get('span')
    if not isinstance(spans, list) or not spans:
        return [], 'MISSING_SPANS'
    found = []
    for span in spans:
        if (not isinstance(span, list) or len(span) != 2
                or any(type(v) is not int for v in span)
                or not 0 <= span[0] < span[1] <= len(text)):
            return [], 'INVALID_SPANS'
        found.append({'start': span[0], 'end': span[1], 'quote': text[span[0]:span[1]],
                      'coordinate_space': 'EXTERNAL_RAW_MARKDOWN', 'source_sha256': digest(text)})
    # Exact slice existence is not semantic verification of the cited law.
    return found, 'SPAN_BOUNDS_CHECKED_NOT_LEGAL_VERIFICATION'


def stage(source, rows, output, *, max_scan=2000, max_records=100, provenance=None):
    if source not in SOURCES or max_scan < 0 or max_records < 1:
        raise ValueError('Invalid source or limits')
    expected = {'documents'} if source == 'cases' else {'metadata', 'content', 'relationships'}
    if set(rows) != expected:
        raise ValueError(f'Expected tables: {sorted(expected)}')
    output = Path(output)
    # Exclusive output prevents overwriting any canonical file or previous run.
    output.mkdir(parents=True, exist_ok=False)
    database = output / 'external_sources.sqlite'
    connection = sqlite3.connect(database)
    connection.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE metadata(id TEXT PRIMARY KEY, external_id TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL, identity_key TEXT, payload_json TEXT NOT NULL);
        CREATE TABLE content(id TEXT PRIMARY KEY REFERENCES metadata(id),
            text TEXT NOT NULL, raw_sha256 TEXT NOT NULL, text_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL);
        CREATE TABLE relationships(id TEXT PRIMARY KEY, doc_id TEXT REFERENCES metadata(id),
            other_doc_id TEXT, relation TEXT NOT NULL, payload_json TEXT NOT NULL);
        CREATE TABLE rejected(table_name TEXT, row_number INTEGER, reason TEXT, external_id TEXT);
    ''')
    scans = {table: Scan(values, max_scan) for table, values in rows.items()}
    counters = Counter()
    issues = Counter()
    spec = SOURCES[source]
    manifest = {'schema_version': 1, 'status': 'RUNNING', 'source': source,
        'dataset': spec['repo'], 'dataset_revision': spec['revision'],
        'license': spec['license'], 'attribution': spec['attribution'],
        'origin': provenance or {'kind': 'LOCAL_ROWS_UNVERIFIED_ORIGIN'},
        'started_at': datetime.now(timezone.utc).isoformat(),
        'review_state': 'REVIEW_REQUIRED', 'authority_verified': False,
        'approved_for_online': False, 'production_changes': 0,
        'foreign_embeddings_imported': 0, 'max_records': max_records}
    pinned_source = manifest['origin'].get('kind') == 'PINNED_HUGGING_FACE_PARQUET'
    manifest['coverage_scope'] = 'PINNED_SOURCE' if pinned_source else 'SUPPLIED_INPUT_ONLY'

    def reject(table, index, reason, external_id=''):
        counters['rejected_rows'] += 1
        issues[reason] += 1
        # Only compact diagnostics; never echo untrusted HTML into a review UI.
        if counters['rejected_rows'] <= 500:
            connection.execute('INSERT INTO rejected VALUES (?,?,?,?)', (table, index, reason, external_id))

    def insert_meta(raw, table):
        encoded = dump(raw)
        if len(encoded.encode('utf-8')) > MAX_ROW_BYTES:
            raise ValueError('ROW_TOO_LARGE')
        required = {'doc_name', 'category', 'is_precedent', 'markdown'} if source == 'cases' else {'id', 'title', 'so_ky_hieu'}
        if not required <= raw.keys():
            raise ValueError('UNSUPPORTED_SCHEMA')
        external_id = key(raw['doc_name' if source == 'cases' else 'id'])
        if not labour_scope(raw, source):
            counters['outside_labour_scope'] += 1
            return
        counters['in_scope_rows_seen'] += 1
        nid = identifier(source, external_id)
        if connection.execute('SELECT 1 FROM metadata WHERE id=?', (nid,)).fetchone():
            raise ValueError('DUPLICATE_METADATA_ID')
        if counters['metadata'] >= max_records:
            counters['selection_limit_rows'] += 1
            return
        warnings = ['EXTERNAL_SOURCE_UNVERIFIED']
        if source == 'cases':
            if type(raw['is_precedent']) is not bool:
                raise ValueError('IS_PRECEDENT_MUST_BE_BOOLEAN')
            if not isinstance(raw['markdown'], str):
                raise ValueError('MARKDOWN_MUST_BE_STRING')
            kind = ('PRECEDENT_CANDIDATE' if raw['is_precedent'] else
                    'CASSATION_CANDIDATE' if raw.get('instance_level') == 'Cassation' else 'JUDGMENT_CANDIDATE')
            number = str(raw.get('official_document_id_normalized') or raw.get('official_document_id') or '')
            if not official_case_url(raw.get('web_url')) or not official_case_url(raw.get('pdf_url')):
                warnings.append('OFFICIAL_URL_MISSING_OR_NOT_ALLOWED')
            if raw['is_precedent'] and not raw.get('precedent_number'):
                warnings.append('PRECEDENT_RECOGNITION_NOT_PROVEN')
            if fold(raw.get('category')) not in {'labor', 'labour', 'lao dong'}:
                warnings.append('CATEGORY_CODE_DISAGREEMENT')
            issued = parse_date(raw.get('issued_date'))
            dates = {'issued_at': issued}
            authority = raw.get('court') or ''
        else:
            kind = 'LEGAL_DOCUMENT_CANDIDATE'
            number = str(raw.get('so_ky_hieu') or '')
            dates = {dst: parse_date(raw.get(src)) for src, dst in (
                ('ngay_ban_hanh', 'issued_at'), ('ngay_co_hieu_luc', 'effective_from'),
                ('ngay_het_hieu_luc', 'effective_to'))}
            if dates['effective_from'] and dates['effective_to'] and dates['effective_to'] < dates['effective_from']:
                warnings.append('INVALID_EFFECTIVE_INTERVAL')
            # Current schema has no official URL. An external ID is not sufficient
            # to invent an ItemID route, particularly for UUID/prefixed records.
            warnings.extend(['OFFICIAL_URL_REQUIRES_RESOLUTION', 'DOCUMENT_DATES_NOT_PROVISION_INTERVALS'])
            authority = raw.get('co_quan_ban_hanh') or ''
        if not number:
            warnings.append('MISSING_DOCUMENT_NUMBER')
        identity = '|'.join((fold(number), fold(authority), str(dates.get('issued_at') or '')))
        payload = {'raw': raw, 'raw_row_sha256': digest(encoded), 'dataset': spec['repo'],
            'revision': spec['revision'], 'review_state': 'REVIEW_REQUIRED',
            'authority_verified': False, 'date_claims': dates, 'review_issues': warnings,
            'source_config': table, 'external_id': external_id}
        connection.execute('INSERT INTO metadata VALUES (?,?,?,?,?)',
                           (nid, external_id, kind, identity, dump(payload)))
        counters['metadata'] += 1
        issues.update(warnings)
        if source == 'cases':
            text = raw['markdown']
            if not isinstance(text, str) or not text.strip():
                issues['EMPTY_CONTENT'] += 1
                return
            insert_content(nid, text, text, 'EXTERNAL_RAW_MARKDOWN')
            for family in ('citations_law', 'citations_case'):
                citations = raw.get(family) or []
                if not isinstance(citations, list):
                    issues['INVALID_CITATION_SCHEMA'] += 1
                    continue
                for position, citation in enumerate(citations):
                    if not isinstance(citation, dict):
                        issues['INVALID_CITATION_SCHEMA'] += 1
                        continue
                    spans, status = citation_spans(citation, text)
                    relation_payload = {'raw': citation, 'citation_family': family,
                        'extractor': raw.get('citations_source'), 'spans': spans, 'span_status': status,
                        'review_state': 'REVIEW_REQUIRED', 'semantic_verified': False,
                        'target_status': 'UNRESOLVED', 'direction': 'CASE_CITES_TARGET'}
                    rid = 'extrel_' + digest(nid + ':' + family + ':' + str(position))[:24]
                    connection.execute('INSERT INTO relationships VALUES (?,?,?,?,?)',
                        (rid, nid, None, 'CITES_CANDIDATE', dump(relation_payload)))
                    counters['relationships'] += 1
                    issues[status] += 1

    def insert_content(nid, raw, text, coordinate_space):
        if connection.execute('SELECT 1 FROM content WHERE id=?', (nid,)).fetchone():
            raise ValueError('DUPLICATE_CONTENT_ID')
        payload = {'raw': raw, 'coordinate_space': coordinate_space,
            'text_transform': 'NONE' if coordinate_space == 'EXTERNAL_RAW_MARKDOWN' else 'HTML_VISIBLE_TEXT',
            'review_state': 'REVIEW_REQUIRED', 'exact_pdf_bytes_verified': False}
        connection.execute('INSERT INTO content VALUES (?,?,?,?,?)',
            (nid, text, digest(raw), digest(text), dump(payload)))
        counters['content'] += 1
        if not text.strip():
            issues['EMPTY_CONTENT'] += 1

    try:
        table = 'documents' if source == 'cases' else 'metadata'
        for raw in scans[table]:
            try:
                insert_meta(raw, table)
            except (ValueError, TypeError) as exc:
                reject(table, scans[table].count, str(exc) if isinstance(exc, ValueError) else 'INVALID_ROW_TYPE')
        if source == 'legal':
            selected = {r[0]: r[1] for r in connection.execute('SELECT external_id,id FROM metadata')}
            for raw in scans['content']:
                try:
                    eid = key(raw.get('id'))
                    if eid not in selected:
                        continue
                    content = raw.get('content_html')
                    if not isinstance(content, str):
                        raise ValueError('CONTENT_HTML_MUST_BE_STRING')
                    if len(content.encode('utf-8')) > MAX_ROW_BYTES:
                        raise ValueError('ROW_TOO_LARGE')
                    insert_content(selected[eid], content, html_text(content), 'EXTERNAL_HTML_VISIBLE_TEXT')
                except (ValueError, TypeError) as exc:
                    reject('content', scans['content'].count, str(exc))
            seen = set()
            for raw in scans['relationships']:
                try:
                    eid = key(raw.get('doc_id'))
                    target = key(raw.get('other_doc_id'))
                    relation = raw.get('relationship')
                    if not isinstance(relation, str) or not relation.strip():
                        raise ValueError('MISSING_RELATIONSHIP_LABEL')
                    if eid not in selected:
                        continue
                    signature = (eid, target, relation)
                    if signature in seen:
                        issues['DUPLICATE_RELATIONSHIP'] += 1
                        continue
                    seen.add(signature)
                    payload = {'raw': raw, 'direction': 'PORTAL_DOC_ID_TO_OTHER_DOC_ID_UNINTERPRETED',
                        'target_status': 'SELECTED' if target in selected else 'NOT_IN_SELECTED_METADATA',
                        'review_state': 'REVIEW_REQUIRED', 'semantic_verified': False,
                        'effective_change_applied': False}
                    rid = 'extrel_' + digest(dump(signature))[:24]
                    connection.execute('INSERT INTO relationships VALUES (?,?,?,?,?)',
                        (rid, selected[eid], selected.get(target), relation, dump(payload)))
                    counters['relationships'] += 1
                except (ValueError, TypeError) as exc:
                    reject('relationships', scans['relationships'].count, str(exc))
        missing = connection.execute('SELECT COUNT(*) FROM metadata m LEFT JOIN content c ON c.id=m.id WHERE c.id IS NULL').fetchone()[0]
        if missing:
            reason = ('CONTENT_NOT_OBSERVED_IN_SCAN' if source == 'legal' and not scans['content'].exhausted
                      else 'CONTENT_MISSING' if pinned_source else 'CONTENT_NOT_OBSERVED_IN_INPUT')
            issues[reason] += missing
        duplicate_identity = connection.execute('SELECT COUNT(*) FROM (SELECT identity_key FROM metadata GROUP BY identity_key HAVING COUNT(*)>1)').fetchone()[0]
        duplicate_content = connection.execute('SELECT COUNT(*) FROM (SELECT text_sha256 FROM content GROUP BY text_sha256 HAVING COUNT(*)>1)').fetchone()[0]
        manifest.update(status='STAGED_REVIEW_REQUIRED', duplicate_identity_groups=duplicate_identity,
                        duplicate_content_groups=duplicate_content)
        connection.commit()
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('STAGING_SQLITE_INTEGRITY_FAILED')
        # Small review manifest, no legal approvals or arbitrary HTML rendering.
        with (output / 'source_review_queue.jsonl').open('w', encoding='utf-8') as stream:
            for nid, eid, kind, raw in connection.execute('SELECT id,external_id,kind,payload_json FROM metadata ORDER BY id'):
                payload = json.loads(raw)
                stream.write(dump({'id': nid, 'external_id': eid, 'kind': kind,
                    'review_state': 'REVIEW_REQUIRED', 'reviewer': None,
                    'dataset': spec['repo'], 'revision': spec['revision'],
                    'review_issues': payload['review_issues'],
                    'required_checks': ['IDENTITY', 'OFFICIAL_SOURCE_BYTES', 'TEXT_COMPLETENESS',
                        'PRECEDENT_RECOGNITION' if source == 'cases' else 'TEMPORAL_AND_RELATION_DIRECTION']}) + '\n')
    except BaseException as exc:
        connection.rollback()
        manifest.update(status='FAILED', error_type=type(exc).__name__)
        raise
    finally:
        connection.close()
        manifest['counts'] = dict(sorted(counters.items()))
        manifest['issues'] = dict(sorted(issues.items()))
        manifest['scans'] = {k: v.report() for k, v in scans.items()}
        manifest['dataset_scan_complete'] = pinned_source and all(v.exhausted for v in scans.values())
        manifest['selection_complete_within_scan'] = counters['selection_limit_rows'] == 0
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'manifest.json').write_text(dump(manifest) + '\n', encoding='utf-8')
    manifest['database_sha256'] = _file_sha256(database)
    (output / 'manifest.json').write_text(dump(manifest) + '\n', encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('fetch', 'stage'):
        p = sub.add_parser(command)
        p.add_argument('--source', choices=tuple(SOURCES), required=True)
        p.add_argument('--output', type=Path, required=True)
        p.add_argument('--max-scan', type=int, default=2000,
                       help='Per-table scan bound; 0 explicitly scans the entire source')
        p.add_argument('--max-records', type=int, default=100)
        if command == 'stage':
            for table in ('documents', 'metadata', 'content', 'relationships'):
                p.add_argument('--' + table, type=Path)
    p = sub.add_parser('ontology-audit')
    p.add_argument('--ontology', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'ontology-audit':
        from .ontology_vocabulary import read_vocabulary
        _, report = read_vocabulary(args.ontology)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(dump(report) + '\n')
        print(dump(report))
        return 1 if report['undefined_references'] else 0
    names = ('documents',) if args.source == 'cases' else ('metadata', 'content', 'relationships')
    if args.command == 'fetch':
        rows = {name: source_rows(args.source, name) for name in names}
        origin = {'kind': 'PINNED_HUGGING_FACE_PARQUET'}
    else:
        if any(getattr(args, name) is None for name in names):
            parser.error('stage requires local JSONL for each source table')
        rows = {name: jsonl_rows(getattr(args, name)) for name in names}
        origin = {'kind': 'LOCAL_JSONL_UNVERIFIED_ORIGIN', 'files': {
            name: {'name': getattr(args, name).name,
                   'sha256': _file_sha256(getattr(args, name))} for name in names}}
    result = stage(args.source, rows, args.output, max_scan=args.max_scan,
                   max_records=args.max_records, provenance=origin)
    print(dump(result))
    return 2 if result['counts'].get('rejected_rows') else 0


def _file_sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


if __name__ == '__main__':
    raise SystemExit(main())
