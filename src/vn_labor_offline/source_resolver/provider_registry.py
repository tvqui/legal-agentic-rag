from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import yaml


@dataclass(frozen=True)
class Provider:
    provider_id: str
    name: str
    domains: tuple[str, ...]
    routes: tuple[str, ...]
    roles: tuple[str, ...]
    groups: tuple[str, ...]
    classification: str
    role_routes: dict[str, tuple[str, ...]] | None = None
    redirect_policy: str = "same_provider"
    max_bytes: int = 25 * 1024 * 1024
    retries: int = 2
    allowed_redirect_domains: tuple[str, ...] = ()

    def allows(self, url: str, role: str | None = None, source_group: str | None = None) -> bool:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        host = (parsed.hostname or "").lower()
        domain_ok = any(host == d or host.endswith("." + d) for d in self.domains)
        routes = (self.role_routes or {}).get(role or "", self.routes)
        route_ok = not routes or any(fnmatch(parsed.path, route) for route in routes)
        role_ok = role is None or role in self.roles
        group_ok = source_group is None or source_group in self.groups
        return domain_ok and route_ok and role_ok and group_ok

    def allows_redirect(self, url: str, role: str | None = None,
                        source_group: str | None = None) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        redirect_domains = self.allowed_redirect_domains or self.domains
        redirect_ok = any(host == d or host.endswith("." + d)
                          for d in redirect_domains)
        return redirect_ok and self.allows(url, role, source_group)


class ProviderRegistry:
    def __init__(self, providers: list[Provider]):
        self.providers = providers

    @classmethod
    def load(cls, path: str | Path) -> "ProviderRegistry":
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        providers = []
        for item in raw.get("providers", []):
            providers.append(Provider(
                provider_id=item["id"], name=item.get("name", item["id"]),
                domains=tuple(item.get("allowed_domains", [])),
                routes=tuple(item.get("allowed_routes", [])),
                roles=tuple(item.get("roles", [])), groups=tuple(item.get("document_groups", [])),
                classification=item.get("classification", "SECONDARY"),
                redirect_policy=item.get("redirect_policy", "same_provider"),
                max_bytes=int(item.get("max_bytes", 25 * 1024 * 1024)),
                retries=int(item.get("retries", 2)),
                allowed_redirect_domains=tuple(item.get("allowed_redirect_domains", item.get("allowed_domains", []))),
                role_routes={role: tuple(routes) for role, routes in item.get("role_routes", {}).items()},
            ))
        return cls(providers)

    def match(self, url: str, role: str | None = None, source_group: str | None = None) -> Provider | None:
        return next((p for p in self.providers if p.allows(url, role, source_group)), None)

    def is_allowed_redirect(self, requested: str, final: str, role: str | None = None, source_group: str | None = None) -> bool:
        provider = self.match(requested, role, source_group)
        return provider is not None and provider.allows_redirect(final, role, source_group)
