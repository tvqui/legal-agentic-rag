from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from vn_labor_offline.source_resolver.import_seed import _safe_relative_path, read_seed
from vn_labor_offline.source_resolver.models import ResolverState, canonical_identifier
from vn_labor_offline.source_resolver.normalizer import extract_item_id, vbpl_routes
from vn_labor_offline.source_resolver.provider_registry import ProviderRegistry
from vn_labor_offline.source_resolver.provider_registry import Provider
from vn_labor_offline.source_resolver.resolver import SourceResolver
from vn_labor_offline.source_resolver.verification.authority import verify_authority
from vn_labor_offline.source_resolver.verification.binary import verify_binary
from vn_labor_offline.source_resolver.verification.decision import decide


ROOT = Path(__file__).parents[2]
SEED = ROOT / "review/inputs/v8_1/source_review_return_v8_1/source_review_tracking.csv"


class SourceResolverTests(unittest.TestCase):
  def test_seed_distribution_and_real_statuses(self):
    rows = read_seed(SEED)
    assert len(rows) == 95
    assert {group: sum(row.source_group == group for row in rows) for group in ("LEGAL_DOCUMENT", "JUDICIAL", "SUPPLEMENTARY", "CONSOLIDATED")} == {
        "LEGAL_DOCUMENT": 57, "JUDICIAL": 24, "SUPPLEMENTARY": 10, "CONSOLIDATED": 4
    }
    assert sum(row.official_source == "YES" for row in rows) == 84
    assert sum(row.collection_result == "ACCESS_BLOCKED" for row in rows) == 84
    assert sum(row.collection_result == "SOURCE_NOT_FOUND" for row in rows) == 10
    assert sum(row.collection_result == "MULTIPLE_CANDIDATES" for row in rows) == 1


  def test_identifier_rules_and_vbpl_item_id(self):
    assert canonical_identifier("LEGAL_DOCUMENT", "21/2021/TT-BLĐTBXH", "") == "21/2021/TT-BLĐTBXH"
    assert canonical_identifier("JUDICIAL", "", "01/2022/LĐ-GĐT") == "01/2022/LĐ-GĐT"
    url = "https://vbpl.vn/bolaodong/Pages/ivbpq-thuoctinh.aspx?ItemID=162453"
    assert extract_item_id(url) == "162453"
    assert vbpl_routes(url)[0].endswith("vbpq-van-ban-goc.aspx?ItemID=162453")


  def test_binary_magic_and_exact_sha(self):
    target = Path(__file__).parent / "_resolver_fixture.pdf"
    target.write_bytes(b"%PDF-1.7\nfixture")
    try:
      digest = hashlib.sha256(target.read_bytes()).hexdigest()
      result = verify_binary(target, "application/pdf", digest)
      self.assertEqual(result["state"], ResolverState.AUTO_EXACT_SHA)
      self.assertEqual(verify_binary(target, "text/html", digest)["state"], ResolverState.NEEDS_REVIEW)
    finally:
      target.unlink()

  def test_unfetched_cannot_be_exact_and_redirect_is_blocked(self):
    state, reasons = decide(authority_ok=True, identity_ok=True, binary=None, evidence_complete=True)
    self.assertEqual(state, ResolverState.FETCH_PENDING)
    registry = ProviderRegistry.load(ROOT / "config/source_provider_registry.yaml")
    allowed, reasons = verify_authority(
        registry,
        "https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID=162453",
        "https://example.invalid/",
        "IDENTITY",
        "LEGAL_DOCUMENT",
    )
    self.assertFalse(allowed)
    self.assertIn("FINAL_URL_OUTSIDE_ALLOWLIST", reasons)

  def test_path_traversal_rejected(self):
    with self.assertRaisesRegex(ValueError, "unsafe relative_path"):
        _safe_relative_path("../escape.pdf")

  def test_catalog_missing_record_is_rejected(self):
    from vn_labor_offline.source_resolver.import_seed import validate_against_catalog
    from vn_labor_offline.source_resolver.models import SeedRecord
    row = SeedRecord("missing.pdf", "LEGAL_DOCUMENT", "a", "missing.pdf")
    with tempfile.TemporaryDirectory() as directory:
      catalog = Path(directory) / "catalog.yaml"
      catalog.write_text("sources: {}\n", encoding="utf-8")
      with self.assertRaisesRegex(ValueError, "catalog missing seed records"):
        validate_against_catalog([row], catalog)

  def test_sha_mismatch_never_content_match(self):
    target = Path(__file__).parent / "_resolver_fixture.pdf"
    target.write_bytes(b"%PDF-1.7\nother")
    try:
      result = verify_binary(target, "application/pdf", "0" * 64)
      self.assertEqual(result["state"], ResolverState.NEEDS_REVIEW)
      self.assertIn("SHA_MISMATCH", result["reason_codes"])
    finally:
      target.unlink()

  def test_import_twice_is_idempotent_and_evidence_export_is_stable(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      row = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
             "corpus_sha256": "a", "canonical_identifier": "1", "state": "FETCH_PENDING"}
      self.assertEqual(store.upsert_records([row]), 1)
      self.assertEqual(store.upsert_records([row]), 1)
      self.assertEqual(len(store.export_records()), 1)
      store.add_candidate({"candidate_id": "c", "record_id": "r", "role": "BINARY",
                           "requested_url": "https://fixture.test/x", "state": "FETCH_PENDING"})
      store.add_evidence("e", "c", "2026-01-01T00:00:00+00:00", {"status": 200})
      self.assertEqual(store.export_evidence(), [{"status": 200, "evidence_id": "e", "candidate_id": "c"}])
      store.close()

  def test_http_redirect_size_limit_and_cleanup(self):
    class Handler(BaseHTTPRequestHandler):
      def do_GET(self):
        if self.path == "/redirect":
          self.send_response(302); self.send_header("Location", "/pdf"); self.end_headers()
        elif self.path == "/pdf":
          body = b"%PDF-1.7\nfixture"
          self.send_response(200); self.send_header("Content-Type", "application/pdf")
          self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
          body = b"x" * 64
          self.send_response(200); self.end_headers(); self.wfile.write(body)
      def log_message(self, *args):
        pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
      from vn_labor_offline.source_resolver.fetchers.http import HttpFetcher
      with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "download.bin"
        fetch = HttpFetcher(allow_http=True, max_redirects=2, retries=0).fetch(
            f"http://127.0.0.1:{server.server_port}/redirect", target, 1024, allow_url=lambda _: True)
        self.assertEqual(fetch["status"], 200)
        self.assertEqual(target.read_bytes(), b"%PDF-1.7\nfixture")
        with self.assertRaises(ValueError):
          HttpFetcher(allow_http=True, retries=0).fetch(
              f"http://127.0.0.1:{server.server_port}/large", target, 8, allow_url=lambda _: True)
        self.assertFalse(list(Path(directory).glob(".resolver-*")))
    finally:
      server.shutdown(); server.server_close(); thread.join()

  def test_vbpl_identity_and_direct_binary_are_separate(self):
    registry = ProviderRegistry([Provider("vbpl", "VBPL", ("vbpl.vn",), ("/TW/Pages/*.aspx",),
                                           ("IDENTITY",), ("LEGAL_DOCUMENT",), "OFFICIAL")])
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(registry, store)
      record = {"record_id": "r", "source_group": "LEGAL_DOCUMENT",
                "exact_source_url": "https://vbpl.vn/old/Pages/view.aspx?ItemID=162453",
                "direct_download_url": "https://datafiles.chinhphu.vn/attachment.pdf",
                "current_candidate_url": ""}
      candidates = resolver.candidates_for(record)
      self.assertEqual([c.role for c in candidates], ["IDENTITY", "BINARY"])
      self.assertEqual(candidates[1].requested_url, record["direct_download_url"])
      store.close()

  def test_playwright_optional_action_log(self):
    from vn_labor_offline.source_resolver.fetchers.playwright import PlaywrightFetcher
    fetcher = PlaywrightFetcher()
    action = fetcher.plan_download("https://fixture.test/page", "a.download")
    self.assertEqual(action["selector"], "a.download")
    self.assertEqual(fetcher.action_log, [action])

  def test_mocked_resolve_flow_reaches_exact_sha_and_evidence(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    pdf = b"%PDF-1.7\nfixture"
    class FakeFetcher:
      def fetch(self, url, target, max_bytes, allow_url):
        body = b"<html><body>21/2021/TT-BLDTBXH</body></html>" if "identity" in url else pdf
        Path(target).parent.mkdir(parents=True, exist_ok=True); Path(target).write_bytes(body)
        return {"requested_url": url, "final_url": url, "redirect_chain": [],
                "status": 200, "content_type": "text/html" if "identity" in url else "application/pdf",
                "size_bytes": len(body)}
    registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",), ("/identity", "/*.pdf"),
                                           ("IDENTITY", "BINARY"), ("LEGAL_DOCUMENT",), "OFFICIAL")])
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(registry, store, Path(directory) / "cache", FakeFetcher())
      digest = hashlib.sha256(pdf).hexdigest()
      record = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
                "corpus_sha256": digest, "canonical_identifier": "21/2021/TT-BLDTBXH",
                "exact_source_url": "https://fixture.test/identity",
                "direct_download_url": "https://fixture.test/attachment.pdf",
                "current_candidate_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      try:
        result = resolver.resolve_record(record, network=True)
        self.assertEqual(result["state"], ResolverState.AUTO_EXACT_SHA.value)
        self.assertTrue(store.export_evidence())
        self.assertEqual(store.export_records()[0]["state"], ResolverState.AUTO_EXACT_SHA.value)
      finally:
        store.close()

  def test_optional_identity_failure_does_not_block_exact_binary(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    import pymupdf
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "01/2022/LĐ-GĐT")
    pdf = document.tobytes()
    document.close()
    class FakeFetcher:
      def fetch(self, url, target, max_bytes, allow_url):
        if "identity" in url:
          raise OSError("HTTP 403")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(pdf)
        return {"requested_url": url, "final_url": url, "redirect_chain": [],
                "status": 200, "content_type": "application/pdf", "size_bytes": len(pdf)}
    registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",),
                                           ("/identity", "/*.pdf"),
                                           ("IDENTITY", "BINARY"), ("JUDICIAL",), "OFFICIAL")])
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(registry, store, Path(directory) / "cache", FakeFetcher())
      digest = hashlib.sha256(pdf).hexdigest()
      record = {"record_id": "r", "relative_path": "x.pdf", "source_group": "JUDICIAL",
                "corpus_sha256": digest, "canonical_identifier": "01/2022/LĐ-GĐT",
                "exact_source_url": "https://fixture.test/identity",
                "direct_download_url": "https://fixture.test/attachment.pdf",
                "current_candidate_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      result = resolver.resolve_record(record, network=True)
      self.assertEqual(result["state"], ResolverState.AUTO_EXACT_SHA.value)
      self.assertEqual(result["identity"]["identity_source"], "BINARY_CONTENT")
      exported = store.export_records()[0]
      self.assertEqual(exported["seed_sha_match"], "")
      self.assertEqual(exported["resolved_sha_match"], "YES")
      store.close()

  def test_attachment_links_are_canonical_and_deduplicated(self):
    from vn_labor_offline.source_resolver.providers.generic_official import attachment_candidates
    html = b'''<a href="/files/a.pdf">T\xc3\xa0i v\xe1\xbb\x81</a>
               <a href="https://fixture.test/files/a.pdf">duplicate</a>
               <a href="/detail">View</a>'''
    candidates = attachment_candidates(html, "https://fixture.test/detail", "fixture",
                                        "21/2021/TT-BL\xc4\x90TBXH")
    self.assertEqual([item["url"] for item in candidates],
                     ["https://fixture.test/files/a.pdf"])
    self.assertTrue(candidates[0]["required"])

  def test_role_specific_registry_rejects_congbao_identity_as_binary(self):
    registry = ProviderRegistry.load(ROOT / "config/source_provider_registry.yaml")
    self.assertIsNotNone(registry.match(
        "https://congbao.chinhphu.vn/van-ban/thong-tu.htm", "IDENTITY", "LEGAL_DOCUMENT"))
    self.assertIsNone(registry.match(
        "https://congbao.chinhphu.vn/van-ban/thong-tu.htm", "BINARY", "LEGAL_DOCUMENT"))

  def test_congbao_fixture_discovers_cdn_binary_links(self):
    from vn_labor_offline.source_resolver.providers.generic_official import attachment_candidates
    html = b'''<a href="https://g7.cdnchinhphu.vn/api/download/stream?Url=abc&file_name=06.pdf"
                    data-atc="download">06.pdf</a>
                <a href="/van-ban/thong-tu.htm">T\xc3\xa0i li\xe1\xbb\x87u</a>'''
    candidates = attachment_candidates(
        html, "https://congbao.chinhphu.vn/van-ban/thong-tu.htm",
        "congbao", "06/2020/TT-BL\xc4\x90TBXH")
    self.assertEqual([item["role"] for item in candidates], ["BINARY"])
    self.assertTrue(candidates[0]["url"].startswith("https://g7.cdnchinhphu.vn/api/download/stream"))

  def test_generic_download_label_html_remains_control(self):
    from vn_labor_offline.source_resolver.providers.generic_official import attachment_candidates
    candidates = attachment_candidates(
        b'<a href="/van-ban/thong-tu.htm">T\xe1\xba\xa3i v\xe1\xbb\x81</a>',
        "https://congbao.chinhphu.vn/", "congbao", "06/2020/TT-BL\xc4\x90TBXH")
    self.assertEqual(candidates[0]["role"], "DOWNLOAD_CONTROL")

  def test_javascript_download_control_is_not_binary(self):
    from vn_labor_offline.source_resolver.providers.generic_official import attachment_candidates
    candidates = attachment_candidates(
        b'<a href="javascript:downloadFile(1)">T\xe1\xba\xa3i v\xe1\xbb\x81</a>',
        "https://fixture.test/detail", "fixture", "21/2021/TT-BL\xc4\x90TBXH")
    self.assertEqual(candidates[0]["role"], "DOWNLOAD_CONTROL")

  def test_exact_binary_is_not_overwritten_by_later_mismatch(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    from vn_labor_offline.source_resolver.providers.generic_official import attachment_candidates
    good = b"%PDF-1.7\nexact"
    bad = b"%PDF-1.7\nother"
    class FakeFetcher:
      def fetch(self, url, target, max_bytes, allow_url):
        if url.endswith("/identity"):
          body = b'<html>21/2021/TT-BLDTBXH <a href="/good.pdf">PDF</a><a href="/bad.pdf">PDF</a></html>'
          content_type = "text/html"
        else:
          body = good if url.endswith("good.pdf") else bad
          content_type = "application/pdf"
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(body)
        return {"requested_url": url, "final_url": url, "redirect_chain": [], "status": 200,
                "content_type": content_type, "size_bytes": len(body)}
    registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",),
                                           ("/identity", "/*.pdf"), ("IDENTITY", "BINARY"),
                                           ("LEGAL_DOCUMENT",), "OFFICIAL")])
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(registry, store, Path(directory) / "cache", FakeFetcher())
      digest = hashlib.sha256(good).hexdigest()
      record = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
                "corpus_sha256": digest, "canonical_identifier": "21/2021/TT-BLDTBXH",
                "exact_source_url": "https://fixture.test/identity", "direct_download_url": "",
                "current_candidate_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      result = resolver.resolve_record(record, network=True)
      self.assertEqual(result["state"], ResolverState.AUTO_EXACT_SHA.value)
      self.assertTrue(result["binary"]["sha256"] == digest)
      store.close()

  def test_export_uses_not_downloaded_for_html_or_fetch_error(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      row = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
             "corpus_sha256": "a", "canonical_identifier": "1", "state": "NEEDS_REVIEW",
             "collection_result": "ACCESS_BLOCKED", "sha_match": "NOT_DOWNLOADED",
             "downloaded_sha256": ""}
      store.upsert_records([row])
      exported = store.export_records()[0]
      self.assertEqual(exported["seed_sha_match"], "NOT_DOWNLOADED")
      self.assertEqual(exported["resolved_sha_match"], "")
      self.assertNotIn("sha_match", exported)
      store.close()

  def test_playwright_missing_dependency_is_explicit(self):
    from vn_labor_offline.source_resolver.fetchers.playwright import PlaywrightFetcher
    fetcher = PlaywrightFetcher()
    if not fetcher._available:
      with self.assertRaisesRegex(RuntimeError, "PLAYWRIGHT_NOT_INSTALLED"):
        fetcher.fetch("https://fixture.test/detail", "a.download", str(ROOT / "tests" / "_unused.bin"))

  def test_identity_mismatch_is_persisted_as_needs_review(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    class FakeFetcher:
      def fetch(self, url, target, max_bytes, allow_url):
        payload = b"<html><title>Trang chu</title>not this instrument</html>"
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(payload)
        return {"requested_url": url, "final_url": url, "status": 200,
                "content_type": "text/html", "size_bytes": len(payload)}
    registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",),
                                           ("/identity",), ("IDENTITY",),
                                           ("LEGAL_DOCUMENT",), "OFFICIAL")])
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(registry, store, Path(directory) / "cache", FakeFetcher())
      record = {"record_id": "mismatch", "relative_path": "x.pdf",
                "source_group": "LEGAL_DOCUMENT", "corpus_sha256": "a",
                "canonical_identifier": "21/2021/TT-BLDTBXH",
                "exact_source_url": "https://fixture.test/identity",
                "direct_download_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      resolver.resolve_record(record, network=True)
      row = store.connection.execute(
          "SELECT state, metadata_json FROM candidates WHERE record_id='mismatch'").fetchone()
      self.assertEqual(row["state"], "NEEDS_REVIEW")
      self.assertEqual(json.loads(row["metadata_json"])["state"], "NEEDS_REVIEW")
      store.close()

  def test_vbpl_candidate_routes_include_history_without_direct_binary(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(ProviderRegistry.load(ROOT / "config/source_provider_registry.yaml"), store)
      record = {"record_id": "vbpl-r", "source_group": "LEGAL_DOCUMENT",
                "canonical_identifier": "10/2020/TT-BLĐTBXH",
                "exact_source_url": "https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID=146696",
                "direct_download_url": "", "current_candidate_url": ""}
      roles = [(candidate.role, candidate.requested_url) for candidate in resolver.candidates_for(record)]
      self.assertTrue(any(role == "STATUS_HISTORY" and "lichsu.aspx" in url for role, url in roles))
      self.assertTrue(any("vbpq-toanvan.aspx" in url for _, url in roles))
      store.close()

  def test_browser_control_creates_derived_binary_candidate(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    good = b"%PDF-1.7\nbrowser-exact"
    class HttpFixture:
      def fetch(self, url, target, max_bytes, allow_url):
        payload = '<html>21/2021/TT-BLDTBXH <a href="javascript:download()">Tải về</a></html>'.encode()
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(payload)
        return {"requested_url": url, "final_url": url, "status": 200,
                "content_type": "text/html", "size_bytes": len(payload)}
    class BrowserFixture:
      def fetch(self, page_url, selector, target):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(good)
        return {"page_requested_url": page_url, "page_final_url": page_url,
                "download_url": "https://fixture.test/files/browser.pdf",
                "download_content_type": "application/pdf",
                "action_log": [{"action": "click", "selector": selector}]}
    registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",),
                                           ("/identity", "/*.pdf"), ("IDENTITY", "BINARY"),
                                           ("LEGAL_DOCUMENT",), "OFFICIAL")])
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      resolver = SourceResolver(registry, store, Path(directory) / "cache",
                                HttpFixture(), BrowserFixture())
      record = {"record_id": "browser-r", "relative_path": "x.pdf",
                "source_group": "LEGAL_DOCUMENT", "corpus_sha256": hashlib.sha256(good).hexdigest(),
                "canonical_identifier": "21/2021/TT-BLDTBXH",
                "exact_source_url": "https://fixture.test/identity",
                "direct_download_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      result = resolver.resolve_record(record, network=True)
      self.assertEqual(result["state"], ResolverState.AUTO_EXACT_SHA.value)
      rows = store.connection.execute(
          "SELECT role, requested_url, parent_candidate_id FROM candidates WHERE record_id='browser-r'").fetchall()
      self.assertTrue(any(row["role"] == "DOWNLOAD_CONTROL" for row in rows))
      self.assertTrue(any(row["role"] == "BINARY" and row["requested_url"].endswith("browser.pdf")
                          and row["parent_candidate_id"] for row in rows))
      store.close()

  def test_http_fetcher_percent_encodes_unicode_url_without_double_encoding(self):
    from vn_labor_offline.source_resolver.fetchers.http import _iri_to_uri
    url = "https://example.test/tệp/[FINAL] bản án%20số 1.pdf?q=lao động&x=%2F"
    encoded = _iri_to_uri(url)
    self.assertNotIn("tệp", encoded)
    self.assertNotIn("bản án", encoded)
    self.assertIn("%20", encoded)
    self.assertIn("x=%2F", encoded)
    self.assertNotIn("%252F", encoded)

  def test_ensure_records_preserves_existing_resolution_metadata(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      seed = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
              "corpus_sha256": "a", "canonical_identifier": "1", "state": "FETCH_PENDING"}
      store.upsert_records([seed])
      store.update_record_state("r", "NEEDS_REVIEW", {"resolution_attempted_at": "now",
                                                        "reason_codes": ["IDENTITY_FAILED"]})
      store.ensure_records([seed])
      row = store.record_for_id("r")
      self.assertEqual(row["state"], "NEEDS_REVIEW")
      self.assertEqual(row["resolution_attempted_at"], "now")
      self.assertEqual(row["relative_path"], "x.pdf")
      store.close()

  def test_resume_uses_persisted_discovered_exact_binary(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      record = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
                "corpus_sha256": "abc", "canonical_identifier": "1/2024/TT-X",
                "exact_source_url": "", "direct_download_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      candidate_id = hashlib.sha256(
          "r|BINARY|https://fixture.test/file.pdf".encode()).hexdigest()[:20]
      candidate = {"candidate_id": candidate_id, "record_id": "r", "role": "BINARY",
                   "requested_url": "https://fixture.test/file.pdf", "final_url": "https://fixture.test/file.pdf",
                   "provider_id": "fixture", "source_class": "OFFICIAL", "state": "AUTO_EXACT_SHA",
                   "reason_codes": [], "required": True, "alternative_group": "binary"}
      store.add_candidate(candidate)
      binary = {"state": "AUTO_EXACT_SHA", "sha256": "abc", "magic_mime": "application/pdf",
                "reason_codes": [], "authority_verified": True, "identity_match": True}
      store.add_evidence("e", candidate_id, "2026-01-01T00:00:00Z", {
          "final_url": "https://fixture.test/file.pdf", "binary": binary,
          "identity_evidence": {"identity_source": "BINARY_CONTENT", "identity_match": True,
                                "authority_verified": True, "final_url": "https://fixture.test/file.pdf"}})
      registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",), ("/*.pdf",),
                                           ("BINARY",), ("LEGAL_DOCUMENT",), "OFFICIAL")])
      resolver = SourceResolver(registry, store, Path(directory) / "cache")
      result = resolver.resolve_record(record, network=True, resume=True)
      self.assertEqual(result["state"], "AUTO_EXACT_SHA")
      self.assertEqual(store.export_records()[0]["state"], "AUTO_EXACT_SHA")
      store.close()

  def test_exception_reason_codes_are_stable(self):
    from urllib.error import HTTPError
    self.assertEqual(SourceResolver._exception_reasons(UnicodeEncodeError(
        "ascii", "đ", 0, 1, "bad")), ["URL_ENCODING_FAILED"])
    self.assertEqual(SourceResolver._exception_reasons(RuntimeError("unexpected details")),
                     ["FETCH_ERROR"])
    self.assertEqual(SourceResolver._exception_reasons(HTTPError(
        "https://fixture.test", 403, "Forbidden", {}, None)), ["HTTP_403"])
    from urllib.error import URLError
    self.assertEqual(SourceResolver._exception_reasons(URLError("offline")),
                     ["NETWORK_RETRY_EXHAUSTED"])

  def test_resume_closes_status_history_candidate(self):
    from vn_labor_offline.source_resolver.store import EvidenceStore
    with tempfile.TemporaryDirectory() as directory:
      store = EvidenceStore(Path(directory) / "state.sqlite")
      record = {"record_id": "r", "relative_path": "x.pdf", "source_group": "LEGAL_DOCUMENT",
                "corpus_sha256": "abc", "canonical_identifier": "1/2024/TT-X",
                "exact_source_url": "", "direct_download_url": "", "state": "FETCH_PENDING"}
      store.upsert_records([record])
      url = "https://fixture.test/status"
      candidate_id = hashlib.sha256(f"r|STATUS_HISTORY|{url}".encode()).hexdigest()[:20]
      store.add_candidate({"candidate_id": candidate_id, "record_id": "r", "role": "STATUS_HISTORY",
                           "requested_url": url, "provider_id": "fixture", "source_class": "OFFICIAL",
                           "state": "FETCH_PENDING", "reason_codes": [], "required": False})
      store.add_evidence("e", candidate_id, "2026-01-01T00:00:00Z", {
          "final_url": url, "identity_match": True, "identity_source": "STATUS_PAGE"})
      registry = ProviderRegistry([Provider("fixture", "Fixture", ("fixture.test",), ("/status",),
                                           ("STATUS_HISTORY",), ("LEGAL_DOCUMENT",), "OFFICIAL")])
      resolver = SourceResolver(registry, store, Path(directory) / "cache")
      resolver.resolve_record(record, network=True, resume=True)
      candidate_state = store.connection.execute(
          "SELECT state FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()[0]
      self.assertEqual(candidate_state, "FETCHED")
      store.close()


if __name__ == "__main__":
  unittest.main()

