from __future__ import annotations

import re
from ..models import normalize_identifier


def _comparison_identifier(value: str) -> str:
    return normalize_identifier(value).replace("Đ", "D").replace("đ", "d").replace("·", "D")


def verify_identity(expected_identifier: str, page_text: str) -> tuple[bool, str]:
    if not expected_identifier:
        return False, "IDENTIFIER_MISSING"
    expected = _comparison_identifier(expected_identifier).casefold()
    actual = _comparison_identifier(page_text).casefold()
    if expected not in actual:
        compact_expected = re.sub(r"[\s\-_]+", "", expected)
        compact_actual = re.sub(r"[\s\-_]+", "", actual)
        if not compact_expected or compact_expected not in compact_actual:
            return False, "IDENTITY_NOT_FOUND"
    return True, "IDENTITY_MATCH"
