"""Bounded reference-aware ordering, proposed by coding-team and reviewed locally.

Only reorders the already source/date-filtered pool. Graph connectivity never
turns a candidate into verified evidence or supplies a missing legal premise.
"""
import re
import unicodedata
from collections.abc import Mapping, Sequence

from .models import Evidence

_REFUSAL = re.compile(
    r"\b(?:khong|dung)\s+(?:ban|noi|hoi|de\s+cap|xet)"
    r"(?:\s+(?:ve|den|toi))?\s+(?:ngoai\s+le|dan\s+chieu)\b"
    r"|\b(?:do\s+not|don't)\s+discuss\s+exceptions?\b"
)
_POSITIVE = re.compile(
    r"\b(?:ngoai\s+le|ngoai\s+tru|dan\s+chieu|duoc\s+vien\s+dan|duoc\s+dan"
    r"|exceptions?|cross[\s-]references?|referred\s+to)\b"
)


def reference_intent(query: str) -> bool:
    text = unicodedata.normalize('NFD', (query or '').casefold())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    text = ' '.join(text.split())
    return bool(_POSITIVE.search(text) and not _REFUSAL.search(text))


def post_select_references(candidates: Sequence[Evidence], references: Mapping[str, Sequence[str]],
                           query: str, k: int, max_promotions: int | None = None) -> list[Evidence]:
    if type(k) is not int or k < 0:
        raise ValueError('k must be a nonnegative integer')
    if max_promotions is not None and (type(max_promotions) is not int or max_promotions < 0):
        raise ValueError('max_promotions must be a nonnegative integer')
    seen, pool = set(), []
    for candidate in candidates:
        if candidate.unit_id not in seen:
            seen.add(candidate.unit_id)
            pool.append(candidate)
    budget = max(0, min(k - 1, k // 2 if max_promotions is None else max_promotions))
    if pool and budget and reference_intent(query):
        seed, tail = pool[0], pool[1:]
        targets = set(references.get(seed.unit_id, ()))
        promoted = [candidate for candidate in tail if candidate.unit_id in targets][:budget]
        promoted_ids = {candidate.unit_id for candidate in promoted}
        pool = [seed] + promoted + [candidate for candidate in tail if candidate.unit_id not in promoted_ids]
    return [candidate.model_copy(update={'rank': rank}) for rank, candidate in enumerate(pool, 1)]
