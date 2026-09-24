from __future__ import annotations

from urllib.parse import urlparse

from ..provider_registry import ProviderRegistry


def verify_authority(registry: ProviderRegistry, requested_url: str, final_url: str, role: str, source_group: str) -> tuple[bool, list[str]]:
    reasons = []
    if not final_url or urlparse(final_url).scheme.lower() != "https":
        reasons.append("HTTPS_REQUIRED")
    if not registry.is_allowed_redirect(requested_url, final_url, role, source_group):
        reasons.append("FINAL_URL_OUTSIDE_ALLOWLIST")
    return not reasons, reasons
