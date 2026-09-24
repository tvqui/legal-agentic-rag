from __future__ import annotations

from dataclasses import dataclass

from ..normalizer import vbpl_routes


@dataclass(frozen=True)
class VBPLAdapter:
    provider_id: str = "vbpl"

    def candidate_urls(self, legacy_url: str) -> list[str]:
        return vbpl_routes(legacy_url)

    def is_homepage(self, final_url: str, body_text: str) -> bool:
        head = body_text[:4000].casefold()
        return (
            final_url.rstrip("/").lower() in {"https://vbpl.vn", "https://vbpl.vn/"}
            or "trang chủ" in head
            or "loading" in head and "vbpl" in head
            or "portal-placeholder" in head
            or "không tìm thấy văn bản" in head
            or "document not found" in head
        )

    def discover_attachments(self, html: bytes, page_url: str, expected_identifier: str) -> list[dict]:
        from .generic_official import attachment_candidates
        return attachment_candidates(html, page_url, self.provider_id, expected_identifier)
