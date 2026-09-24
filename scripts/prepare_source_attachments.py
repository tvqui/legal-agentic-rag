"""Fetch the full-text PDFs linked by the three saved official landing pages."""
from pathlib import Path
import hashlib
import json
from urllib.parse import urlsplit
import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'congbaocdn.chinhphu.vn', 'datafiles.chinhphu.vn'}


def main():
    target = ROOT / 'review/attachments'
    target.mkdir(parents=True, exist_ok=True)
    records = {}
    session = requests.Session()
    for html in sorted((ROOT / 'data').rglob('*OFFICIAL_HTML.html')):
        soup = BeautifulSoup(html.read_text(encoding='utf-8'), 'html.parser')
        urls = list(dict.fromkeys(value for el in soup.find_all(True) for value in el.attrs.values()
                   if isinstance(value, str) and value.lower().endswith('.pdf')
                   and urlsplit(value).hostname in ALLOWED))
        if len(urls) != 1:
            raise ValueError(f'Expected one official full-text PDF: {html.name}')
        canonical = soup.select_one('link[rel=canonical]')
        og = soup.select_one('meta[property="og:url"]')
        page_url = canonical['href'] if canonical else og['content']
        dest = target / (html.stem.replace('_OFFICIAL_HTML', '') + '.pdf')
        if not dest.exists():
            response = session.get(urls[0], timeout=(20, 120))
            response.raise_for_status()
            if not response.content.startswith(b'%PDF-'):
                raise ValueError(f'Not a PDF: {urls[0]}')
            dest.write_bytes(response.content)
        import pymupdf
        with pymupdf.open(dest) as pdf:
            if len(pdf) == 0: raise ValueError('Empty PDF')
            print(dest.name, len(pdf), 'pages', flush=True)
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        records[html.relative_to(ROOT / 'data').as_posix()] = {
            'html_sha256': sha(html), 'path': dest.relative_to(ROOT).as_posix(),
            'sha256': sha(dest), 'source_url': page_url, 'download_url': urls[0],
        }
    (ROOT / 'config/source_attachments.yaml').write_text(yaml.safe_dump({'attachments': records}, allow_unicode=True, sort_keys=False), encoding='utf-8')


if __name__ == '__main__': main()
