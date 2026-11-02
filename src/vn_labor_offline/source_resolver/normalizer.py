from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .models import canonical_identifier as _canonical_identifier, normalize_identifier

ITEM_ID_RE = re.compile(r"(?:itemid|item_id)\s*=\s*(\d+)", re.I)


def extract_item_id(url: str) -> str | None:
    match = ITEM_ID_RE.search(url or "")
    if match:
        return match.group(1)
    query_value = parse_qs(urlparse(url or "").query).get("ItemID")
    if query_value:return query_value[0]
    parsed=urlparse(url or '')
    if (parsed.hostname or '').lower() in {'vbpl.vn','www.vbpl.vn'} and parsed.path.startswith('/van-ban/chi-tiet/'):
        slug=re.search(r'--(\d+)/?$',parsed.path)
        if slug:return slug.group(1)
    return None


def normalize_url(url: str) -> str:
    return (url or "").strip()


def vbpl_routes(url: str) -> list[str]:
    item_id = extract_item_id(url)
    if not item_id:
        return [normalize_url(url)] if url else []
    legacy=[
        f"https://vbpl.vn/TW/Pages/vbpq-van-ban-goc.aspx?ItemID={item_id}",
        f"https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID={item_id}",
        f"https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID={item_id}",
        f"https://vbpl.vn/TW/Pages/vbpq-lichsu.aspx?ItemID={item_id}",
    ]
    # Preserve an explicitly supplied modern detail URL. Do not replace it
    # with legacy ASPX routes that may redirect to the portal home page.
    modern=urlparse(url or '').path.startswith('/van-ban/chi-tiet/')
    return [normalize_url(url),*legacy] if modern else legacy


def canonical_identifier(source_group: str, instrument_number: str = "", document_number: str = "") -> str:
    return _canonical_identifier(source_group, instrument_number, document_number)
