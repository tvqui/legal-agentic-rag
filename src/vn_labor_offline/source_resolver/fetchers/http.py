from __future__ import annotations

import os
import random
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import BaseHandler, Request, build_opener


class _NoRedirect(BaseHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp
    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


class HttpFetcher:
    def __init__(self, timeout: float = 20, max_redirects: int = 5,
                 retries: int = 2, backoff: float = 0.2, rate_limit: float = 0,
                 user_agent: str = "vn-labor-source-resolver/1.0",
                 allow_http: bool = False):
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.retries = retries
        self.backoff = backoff
        self.rate_limit = rate_limit
        self.user_agent = user_agent
        self.allow_http = allow_http
        self._last_request = 0.0
        self._opener = build_opener(_NoRedirect())

    def fetch(self, url: str, target: str | Path, max_bytes: int = 25 * 1024 * 1024,
              allow_url=None) -> dict:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" and not self.allow_http:
            raise ValueError("HTTPS_REQUIRED")
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        current = url
        chain = []
        response = None
        try:
            for redirect_count in range(self.max_redirects + 1):
                if allow_url and not allow_url(current):
                    raise ValueError("URL_OUTSIDE_ALLOWLIST")
                response = self._request_with_retry(current)
                chain.append({"url": current, "status": response.status,
                              "location": response.headers.get("Location", "")})
                if response.status not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("REDIRECT_WITHOUT_LOCATION")
                if redirect_count >= self.max_redirects:
                    raise ValueError("REDIRECT_LIMIT")
                current = urljoin(current, location)
            else:
                raise ValueError("REDIRECT_LIMIT")
            if allow_url and not allow_url(current):
                raise ValueError("FINAL_URL_OUTSIDE_ALLOWLIST")
            fd, temp_name = tempfile.mkstemp(prefix=".resolver-", dir=destination.parent)
            os.close(fd)
            temp = Path(temp_name)
            total = 0
            try:
                with temp.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("SIZE_LIMIT")
                        handle.write(chunk)
                os.replace(temp, destination)
            finally:
                if temp.exists():
                    temp.unlink()
            return {
                "requested_url": url, "final_url": current, "redirect_chain": chain,
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "content_length": response.headers.get("Content-Length", ""),
                "size_bytes": total,
            }
        finally:
            if response is not None:
                response.close()

    def _request_with_retry(self, url: str):
        last_error = None
        for attempt in range(self.retries + 1):
            wait = self.rate_limit - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                request = Request(_iri_to_uri(url), headers={"User-Agent": self.user_agent, "Accept": "*/*"})
                return self._opener.open(request, timeout=self.timeout)
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                time.sleep(self.backoff * (2 ** attempt) + random.random() * self.backoff)
        raise last_error


def _iri_to_uri(url: str) -> str:
    """Encode Unicode URL components without double-encoding existing escapes."""
    parts = urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    userinfo = ""
    if parts.username is not None:
        userinfo = quote(parts.username, safe="%")
        if parts.password is not None:
            userinfo += ":" + quote(parts.password, safe="%")
        userinfo += "@"
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{userinfo}{host}{port}"
    path = quote(parts.path, safe="/%:@-._~!$&'()*+,;=%[]")
    query = quote(parts.query, safe="=&?/:;+,%@[]-._~!$'()*")
    fragment = quote(parts.fragment, safe="=&?/:;+,%@[]-._~!$'()*")
    return urlunsplit((parts.scheme, netloc, path, query, fragment))
