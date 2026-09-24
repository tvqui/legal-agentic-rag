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
    return query_value[0] if query_value else None


def normalize_url(url: str) -> str:
    return (url or "").strip()


def vbpl_routes(url: str) -> list[str]:
    item_id = extract_item_id(url)
    if not item_id:
        return [normalize_url(url)] if url else []
    return [
        f"https://vbpl.vn/TW/Pages/vbpq-van-ban-goc.aspx?ItemID={item_id}",
        f"https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID={item_id}",
        f"https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID={item_id}",
        f"https://vbpl.vn/TW/Pages/vbpq-lichsu.aspx?ItemID={item_id}",
    ]


def canonical_identifier(source_group: str, instrument_number: str = "", document_number: str = "") -> str:
    return _canonical_identifier(source_group, instrument_number, document_number)
