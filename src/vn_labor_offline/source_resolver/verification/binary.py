from __future__ import annotations

import hashlib
from pathlib import Path


MAGIC = {b"%PDF-": "application/pdf", b"PK\x03\x04": "application/zip", b"\xd0\xcf\x11\xe0": "application/msword"}


def verify_binary(path: str | Path, content_type: str, expected_sha: str, max_bytes: int = 25 * 1024 * 1024) -> dict:
    target = Path(path)
    size = target.stat().st_size
    with target.open("rb") as handle:
        prefix = handle.read(8)
    magic_type = next((mime for magic, mime in MAGIC.items() if prefix.startswith(magic)), None)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    reasons = []
    if size > max_bytes:
        reasons.append("SIZE_LIMIT")
    if magic_type is None:
        reasons.append("UNKNOWN_MAGIC")
    if content_type and magic_type and content_type.split(";")[0].lower() not in {magic_type, "application/octet-stream"}:
        reasons.append("MIME_MAGIC_MISMATCH")
    state = "AUTO_EXACT_SHA" if not reasons and actual == expected_sha else "NEEDS_REVIEW"
    if actual != expected_sha:
        reasons.append("SHA_MISMATCH")
    return {"sha256": actual, "size_bytes": size, "magic_mime": magic_type, "state": state, "reason_codes": reasons}
