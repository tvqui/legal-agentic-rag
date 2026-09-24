from __future__ import annotations
import re, unicodedata
from collections import Counter
from .util import normalize_unicode, collapse_spaces

NOISE_PATTERNS = [
    r"^\s*Trang\s+\d+(?:\s*/\s*\d+)?\s*$",
    r"^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*$",
    r"^\s*\d+\s*$",
]


def remove_repeated_page_lines(pages: list[str], ratio: float=.55, max_chars: int=120) -> list[str]:
    if len(pages) < 3:
        return pages
    per_page = []
    counts = Counter()
    for page in pages:
        lines = [collapse_spaces(x) for x in normalize_unicode(page).splitlines() if collapse_spaces(x)]
        uniq = set(x for x in lines if len(x) <= max_chars)
        counts.update(uniq)
        per_page.append(lines)
    cutoff = max(2, int(len(pages) * ratio + .999))
    repeated = {x for x, c in counts.items() if c >= cutoff and not re.match(r'^(?:Điều|Chương|Mục|PHỤ LỤC|MẪU|\d+[.)]|[a-zđ][.)])',x,re.I)}
    return ["\n".join(x for x in lines if x not in repeated) for lines in per_page]


def clean_text(text: str, unicode_form: str='NFC') -> str:
    text = unicodedata.normalize(unicode_form,normalize_unicode(text))
    lines = []
    for line in text.splitlines():
        line = collapse_spaces(line)
        if not line:
            lines.append("")
            continue
        if any(re.match(p, line, flags=re.I) for p in NOISE_PATTERNS):
            continue
        lines.append(line)
    text = "\n".join(lines)
    # Keep line boundaries. Unicode ranges such as à-ỹ include uppercase Đ and
    # previously glued Article headings onto chapter titles or preceding text.
    return collapse_spaces(text)
