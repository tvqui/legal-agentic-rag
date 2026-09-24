from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str, dict[str, str]]] = []
        self._anchor_stack: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag.lower() == "a" and values.get("href"):
            self._anchor_stack.append({"href": values["href"], "label": "", "attrs": values})

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._anchor_stack:
            anchor = self._anchor_stack.pop()
            self.links.append((anchor["href"], anchor["label"], anchor["attrs"]))

    def handle_data(self, data):
        if self._anchor_stack:
            self._anchor_stack[-1]["label"] = f"{self._anchor_stack[-1]['label']} {data}".strip()


def attachment_candidates(html: bytes, page_url: str, provider_id: str,
                          expected_identifier: str, source_class: str = "OFFICIAL_CANDIDATE") -> list[dict]:
    parser = _LinkParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    results = []
    seen: set[str] = set()
    for href, label, attrs in parser.links:
        absolute = urljoin(page_url, href.strip())
        path = urlparse(absolute).path.lower()
        hint = f"{label} {href}".casefold()
        binary_extension = path.endswith((".pdf", ".doc", ".docx", ".zip"))
        download_hint = any(
            token in hint for token in ("tải về", "download", "tai-ve", "attachment", "đính kèm", "xem nhanh")
        )
        if not binary_extension and not download_hint:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        parsed = urlparse(absolute)
        known_binary_endpoint = (
            parsed.hostname == "g7.cdnchinhphu.vn"
            and parsed.path == "/api/download/stream"
        )
        control = not binary_extension and not known_binary_endpoint
        selector = ""
        if control and attrs.get("data-atc") == "download":
            selector = "a[data-atc='download']"
        elif control and attrs.get("id"):
            selector = f"a#{attrs['id']}"
        results.append({
            "url": absolute, "role": "DOWNLOAD_CONTROL" if control else "BINARY", "provider_id": provider_id,
            "source_class": source_class, "discovered_from": page_url,
            "attachment_label": label or href, "expected_identifier": expected_identifier,
            "required": True, "selector": selector,
            "reason_codes": ["DOWNLOAD_CONTROL" if control else "ATTACHMENT_DISCOVERED"],
        })
    return results


@dataclass(frozen=True)
class GenericOfficialAdapter:
    provider_id: str

    def candidate_urls(self, url: str) -> list[str]:
        return [url] if url else []

    def discover_attachments(self, html: bytes, page_url: str, expected_identifier: str) -> list[dict]:
        return attachment_candidates(html, page_url, self.provider_id, expected_identifier)
