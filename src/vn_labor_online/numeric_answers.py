"""Deterministic arithmetic for explicitly stated wage bases."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re


_SALARY_BASE = re.compile(
    r'\b(?:mức\s+)?lương(?:\s+của)?\s+(?:vị\s+trí|công\s+việc)(?:\s+đó)?'
    r'\s*(?:là|:|=)?\s*'
    r'(?P<number>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d{1,2})?)'
    r'\s*(?P<scale>triệu|nghìn)?\s*(?:đồng|đ|vnd)?\s*'
    r'(?:/\s*|mỗi\s+)(?P<unit>tháng|ngày|giờ)\b',
    re.I,
)


@dataclass(frozen=True)
class SalaryBase:
    amount: int
    unit: str
    source_quote: str
    char_start: int
    char_end: int


def requests_probation_amount(query: str) -> bool:
    """Require an explicit monetary-result request before adding arithmetic."""
    q=' '.join(query.lower().split())
    if 'thử việc' not in q:
        return False
    # A mixed rate-and-amount question still requests a monetary result.
    if re.search(r'bao nhiêu\s+(?:tiền|đồng)|số tiền|mức tiền thấp nhất|tính tiền thử việc', q):
        return True
    return bool(re.search(r'bao nhiêu', q)) and not re.search(r'phần trăm|tỷ lệ|bao nhiêu\s*%', q)


def parse_salary_base(query: str) -> SalaryBase | None:
    """Parse only a clearly labeled job/position wage, not probation pay."""
    matches = list(_SALARY_BASE.finditer(query))
    if not matches:
        return None
    bases = [_parse_match(match) for match in matches]
    if any(base is None for base in bases) or len({(base.amount, base.unit) for base in bases if base}) != 1:
        # Never choose the first of several different wages silently.
        return None
    return bases[-1]


def conflicting_salary_bases(query: str) -> bool:
    matches=list(_SALARY_BASE.finditer(query))
    return len(matches)>1 and parse_salary_base(query) is None


def _parse_match(match) -> SalaryBase | None:
    number = match.group('number')
    if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', number):
        amount_value=Decimal(number.replace('.', '').replace(',', ''))
    else:
        amount_value=Decimal(number.replace(',', '.'))
    scale = (match.group('scale') or '').lower()
    amount_value *= {'triệu': 1_000_000, 'nghìn': 1_000}.get(scale, 1)
    if amount_value != amount_value.to_integral_value():
        return None
    amount=int(amount_value)
    if amount <= 0:
        return None
    return SalaryBase(
        amount=amount,
        unit=match.group('unit').lower(),
        source_quote=match.group(),
        char_start=match.start(),
        char_end=match.end(),
    )


def probation_minimum_amount(
    query: str,
    percent: int = 85,
    salary_base_amount: int | None = None,
    salary_base_unit: str | None = None,
) -> tuple[str, str] | None:
    """Return exact integer-dong arithmetic only when both operands are explicit."""
    base = parse_salary_base(query)
    if base is None and _SALARY_BASE.search(query):
        return None
    if base is not None:
        amount_value, unit = base.amount, base.unit
    elif (
        isinstance(salary_base_amount, int)
        and not isinstance(salary_base_amount, bool)
        and salary_base_amount > 0
        and salary_base_unit in {'tháng', 'ngày', 'giờ'}
    ):
        amount_value, unit = salary_base_amount, salary_base_unit
    else:
        return None
    result = Decimal(amount_value) * Decimal(percent) / Decimal(100)
    if result != result.to_integral_value():
        return None
    amount = f'{int(result):,}'.replace(',', '.')
    return amount, unit
