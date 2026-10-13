"""Read-only Aura connectivity check with bounded retries and safe diagnostics."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import time
from urllib.parse import urlsplit


def settings(environment):
    values = {name: environment.get(name, '').strip() for name in
              ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'NEO4J_DATABASE')}
    if not all(values.values()):
        raise ValueError('MISSING_SECRET')
    try:
        parsed = urlsplit(values['NEO4J_URI'])
        host = parsed.hostname
        port = parsed.port or 7687
        if (parsed.scheme != 'neo4j+s' or not host or parsed.username is not None
                or parsed.password is not None or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or not 1 <= port <= 65535
                or not re.fullmatch(r'[a-zA-Z0-9.-]+', host)
                or any(char.isspace() for char in values['NEO4J_URI'])):
            raise ValueError('INVALID_URI')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError('INVALID_URI')
    except (ValueError, TypeError):
        raise ValueError('INVALID_URI') from None
    return values, host, port


def reason(error):
    # Never include raw exception text: drivers can echo connection/auth data.
    current, seen = error, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return 'DNS_UNRESOLVED'
        current = current.__cause__ or current.__context__
    code = getattr(error, 'code', '') or ''
    if type(error).__name__ == 'AuthError' or code.startswith('Neo.ClientError.Security.'):
        return 'AUTH_FAILED'
    if code == 'Neo.ClientError.Database.DatabaseNotFound':
        return 'DATABASE_NOT_FOUND'
    if type(error).__name__ in ('ServiceUnavailable', 'SessionExpired') or isinstance(error, OSError):
        return 'CONNECTION_UNAVAILABLE'
    return 'PREFLIGHT_FAILED'


HINTS = {
    'MISSING_SECRET': 'Cap quyen du 4 Kaggle Secrets cho notebook.',
    'INVALID_URI': 'Copy dung Connection URI neo4j+s:// tu Aura Console; khong dung IP hay URL trang web.',
    'DNS_UNRESOLVED': 'Kiem tra URI/instance trong Aura Console va Internet Kaggle; DNS chua tim thay hostname.',
    'AUTH_FAILED': 'Kiem tra NEO4J_USER/NEO4J_PASSWORD trong Kaggle Secrets.',
    'DATABASE_NOT_FOUND': 'NEO4J_DATABASE la ten database, khong mac dinh la ID instance. Doi chieu Aura Console.',
    'CONNECTION_UNAVAILABLE': 'Kiem tra instance dang Running, Internet va ket noi TLS/Bolt.',
    'PREFLIGHT_FAILED': 'Kiem tra driver Neo4j va cau hinh ket noi; khong nap graph khi preflight chua PASS.',
}


def check(environment=None, *, attempts=3, delay=5, driver_factory=None,
          resolve=None, sleep=None, emit=None):
    if not 1 <= attempts <= 3 or not 0 <= delay <= 10:
        raise ValueError('Preflight retry budget exceeded')
    environment = os.environ if environment is None else environment
    resolve = socket.getaddrinfo if resolve is None else resolve
    sleep = time.sleep if sleep is None else sleep
    emit = (lambda value: print(value, flush=True)) if emit is None else emit
    report = {'schema_version': 1, 'passed': False, 'attempts': [],
              'checked_at': datetime.now(timezone.utc).isoformat(), 'read_only': True}
    try:
        values, host, port = settings(environment)
    except ValueError as error:
        report['reason_code'] = str(error)
    else:
        report['endpoint'] = f'{host}:{port}'
        for index in range(1, attempts + 1):
            emit(f'Aura preflight attempt {index}/{attempts}: {host}:{port}')
            try:
                resolve(host, port, type=socket.SOCK_STREAM)
                if driver_factory is None:
                    from neo4j import GraphDatabase
                    driver_factory = GraphDatabase.driver
                with driver_factory(values['NEO4J_URI'],
                                    auth=(values['NEO4J_USER'], values['NEO4J_PASSWORD']),
                                    connection_timeout=10, connection_acquisition_timeout=15,
                                    max_transaction_retry_time=0) as driver:
                    driver.verify_connectivity()
                    with driver.session(database=values['NEO4J_DATABASE'], default_access_mode='READ') as session:
                        row = session.run('RETURN 1 AS ok').single()
                        if row is None or row['ok'] != 1:
                            raise RuntimeError('Unexpected preflight result')
            except Exception as error:
                failure = reason(error)
                report['attempts'].append({'attempt': index, 'passed': False, 'reason_code': failure})
                report['reason_code'] = failure
                emit(f'Aura preflight: {failure}')
                if failure not in ('DNS_UNRESOLVED', 'CONNECTION_UNAVAILABLE') or index == attempts:
                    break
                sleep(delay)
            else:
                report['attempts'].append({'attempt': index, 'passed': True})
                report.update(passed=True, reason_code='PASS')
                emit('Aura connectivity/database preflight: PASS (read-only)')
                break
    if not report['passed']:
        report['hint'] = HINTS[report['reason_code']]
        emit(report['hint'])
        emit('Muon dung OFFLINE local truoc: dat LOAD_AURA = False; Aura se chua duoc nap/xac minh.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = check()
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(args.report.suffix + '.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, args.report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
