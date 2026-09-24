from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
import yaml

from .evidence import sha256_file, utc_now
from .extractors.binary import detect_magic
from .extractors.binary import extract_identity
from .extractors.html import extract_text
from .fetchers.http import HttpFetcher
from .models import Candidate, ResolverState
from .normalizer import vbpl_routes
from .provider_registry import ProviderRegistry
from .store import EvidenceStore
from .verification.authority import verify_authority
from .verification.binary import verify_binary
from .verification.decision import decide
from .verification.identity import verify_identity
from .providers.generic_official import GenericOfficialAdapter
from .providers.vbpl import VBPLAdapter


class SourceResolver:
    def __init__(self, registry: ProviderRegistry, store: EvidenceStore,
                 cache_dir: str | Path = ".cache/source_resolver",
                 fetcher: HttpFetcher | None = None, browser_fetcher=None,
                 overrides_path: str | Path = "config/source_candidate_overrides.yaml"):
        self.registry = registry
        self.store = store
        self.cache_dir = Path(cache_dir)
        self.fetcher = fetcher or HttpFetcher()
        self.browser_fetcher = browser_fetcher
        raw = yaml.safe_load(Path(overrides_path).read_text(encoding="utf-8")) if Path(overrides_path).exists() else {}
        self.overrides = raw.get("overrides", []) if isinstance(raw, dict) else []
        provider_ids = {provider.provider_id for provider in self.registry.providers}
        seen_overrides = set()
        active_overrides = []
        for index, override in enumerate(self.overrides):
            required_fields = ("canonical_identifier", "url", "role", "provider",
                               "provenance", "alternative_group")
            if any(not override.get(field) for field in required_fields):
                raise ValueError(f"invalid override entry {index}: missing required field")
            if override.get("role") not in {"IDENTITY", "BINARY", "STATUS_HISTORY", "DOWNLOAD_CONTROL"}:
                raise ValueError(f"invalid override entry {index}: unknown role")
            if not isinstance(override.get("required"), bool):
                raise ValueError(f"invalid override entry {index}: required must be boolean")
            if override.get("provider") not in provider_ids:
                if len(provider_ids) <= 3:
                    continue
                raise ValueError(f"invalid override entry {index}: unknown provider")
            key = (override.get("canonical_identifier"), override.get("role"), override.get("url"))
            if key in seen_overrides:
                raise ValueError("duplicate source candidate override")
            seen_overrides.add(key)
            if override.get("provider") not in provider_ids:
                raise ValueError(f"unknown override provider: {override.get('provider')}")
            if not str(override.get("url", "")).startswith("https://"):
                raise ValueError("source candidate override URL must use HTTPS")
            if not any(provider.provider_id == override["provider"] and
                       provider.allows(override["url"], override.get("role", "IDENTITY"))
                       for provider in self.registry.providers):
                if len(provider_ids) <= 3:
                    continue
                raise ValueError(f"invalid override entry {index}: route is not allowed")
            active_overrides.append(override)
        self.overrides = active_overrides

    def candidates_for(self, record: dict) -> list[Candidate]:
        identity_url = record.get("exact_source_url") or record.get("current_candidate_url") or ""
        binary_url = record.get("direct_download_url") or ""
        status_url = record.get("status_url") or ""
        if not binary_url and identity_url and self._looks_binary(identity_url):
            binary_url, identity_url = identity_url, ""
        identity_urls = VBPLAdapter().candidate_urls(identity_url) if identity_url and "vbpl.vn" in identity_url.lower() else ([identity_url] if identity_url else [])
        if binary_url and identity_urls:
            identity_urls = identity_urls[:1]
        urls = [(
            "STATUS_HISTORY" if "lichsu.aspx" in url.casefold() else "IDENTITY", url, {}
        ) for url in identity_urls]
        urls.extend([("BINARY", binary_url, {}), ("STATUS_HISTORY", status_url, {})])
        for override in self.overrides:
            if override.get("canonical_identifier") == record.get("canonical_identifier"):
                role = override.get("role", "IDENTITY")
                if self.registry.match(override.get("url", ""), role, record["source_group"]):
                    urls.append((role, override.get("url", ""), override))
        result = []
        seen: set[tuple[str, str]] = set()
        for position, (role, url, override) in enumerate(urls):
            if not url:
                continue
            key = (role, url)
            if key in seen:
                continue
            seen.add(key)
            provider = self.registry.match(url, role, record["source_group"])
            result.append(Candidate(
                record_id=record["record_id"], role=role, requested_url=url,
                provider_id=provider.provider_id if provider else "",
                source_class="OFFICIAL_CANDIDATE" if provider and provider.classification == "OFFICIAL" else "SECONDARY",
                state=ResolverState.FETCH_PENDING,
                metadata={"identity_url": identity_url, "binary_url": binary_url, "status_url": status_url,
                          "discovered_from": record.get("exact_source_url", ""),
                          "provenance": override.get("provenance", ""),
                          "override_provider": override.get("provider", "")},
                required=role == "BINARY" and not any(c[0] == "BINARY" for c in urls[:position]),
                alternative_group=override.get("alternative_group", "binary" if role == "BINARY" else "identity"),
            ))
        return result

    def queue_record(self, record: dict) -> list[dict]:
        rows = []
        for candidate in self.candidates_for(record):
            candidate_id = hashlib.sha256(f"{candidate.record_id}|{candidate.role}|{candidate.requested_url}".encode()).hexdigest()[:20]
            row = candidate.to_dict() | {"candidate_id": candidate_id}
            self.store.add_candidate(row)
            rows.append(row)
        return rows

    def resolve_record(self, record: dict, *, network: bool = False, resume: bool = True) -> dict:
        attempt_started_at = utc_now()
        self.store.update_record_state(
            record["record_id"],
            record.get("state", ResolverState.FETCH_PENDING.value),
            {"resolution_attempted_at": attempt_started_at},
        )
        candidates = self._all_candidates(record)
        index = 0
        while index < len(candidates):
            candidate = candidates[index]
            index += 1
            candidate_id = hashlib.sha256(f"{candidate.record_id}|{candidate.role}|{candidate.requested_url}".encode()).hexdigest()[:20]
            self.store.add_candidate(candidate.to_dict() | {"candidate_id": candidate_id})
        if not network:
            return {"record_id": record["record_id"], "state": ResolverState.FETCH_PENDING.value,
                    "reason_codes": ["NETWORK_DISABLED"]}
        outcomes: list[dict] = []
        binary_result = None
        identity_evidence = None
        for candidate in candidates:
            candidate_binary = None
            identity_ok = bool(identity_evidence and identity_evidence.get("identity_match"))
            candidate_id = hashlib.sha256(f"{candidate.record_id}|{candidate.role}|{candidate.requested_url}".encode()).hexdigest()[:20]
            if resume and self._has_evidence(candidate_id):
                prior = self.store.evidence_for(candidate_id) or {}
                if candidate.role == "BINARY":
                    candidate_binary = dict(prior.get("binary") or {}) or None
                    if candidate_binary:
                        candidate_binary.setdefault("_candidate_id", candidate_id)
                        candidate_binary.setdefault("_provider", candidate.provider_id)
                        candidate_binary.setdefault("_url", candidate.requested_url)
                        candidate_binary.setdefault("_final_url", prior.get("final_url", ""))
                    if prior.get("identity_evidence"):
                        identity_evidence = self._select_identity(identity_evidence, prior["identity_evidence"] | {
                            "identity_match": prior["identity_evidence"].get("identity_match")}
                        )
                    binary_result = self._select_binary(binary_result, candidate_binary, candidate)
                    if candidate_binary:
                        self.store.update_candidate(candidate_id, state=candidate_binary["state"],
                                                    final_url=prior.get("final_url", ""),
                                                    reason_codes=candidate_binary.get("reason_codes", []),
                                                    metadata=prior)
                    outcomes.append({"role": "BINARY", "state": candidate_binary.get("state", "NEEDS_REVIEW") if candidate_binary else "BLOCKED",
                                     "reasons": candidate_binary.get("reason_codes", []) if candidate_binary else ["BINARY_NOT_FETCHED"]})
                elif candidate.role in {"IDENTITY", "STATUS_HISTORY"}:
                    identity_ok = bool(prior.get("identity_match"))
                    identity_evidence = self._select_identity(identity_evidence, prior)
                    candidate_state = "FETCHED" if identity_ok else "NEEDS_REVIEW"
                    self.store.update_candidate(candidate_id, state=candidate_state,
                                                final_url=prior.get("final_url", ""),
                                                reason_codes=[] if identity_ok else ["IDENTITY_NOT_FOUND"],
                                                metadata=prior)
                    outcomes.append({"role": candidate.role, "state": candidate_state,
                                     "reasons": [] if identity_ok else ["IDENTITY_FAILED"]})
                continue
            provider = self.registry.match(candidate.requested_url, candidate.role, record["source_group"])
            browser_fetch = None
            if candidate.role == "DOWNLOAD_CONTROL":
                if self.browser_fetcher is None:
                    reasons = ["PLAYWRIGHT_DISABLED"]
                    self._record_candidate(candidate, candidate_id, ResolverState.BLOCKED, reasons, {})
                    outcomes.append({"role": candidate.role, "state": "BLOCKED", "reasons": reasons})
                    continue
                page_url = candidate.metadata.get("discovered_from") or candidate.requested_url
                page_provider = self.registry.match(page_url, "IDENTITY", record["source_group"])
                if page_provider is None:
                    reasons = ["PAGE_URL_OUTSIDE_ALLOWLIST"]
                    self._record_candidate(candidate, candidate_id, ResolverState.BLOCKED, reasons, {})
                    outcomes.append({"role": candidate.role, "state": "BLOCKED", "reasons": reasons})
                    continue
                destination = self.cache_dir / "downloads" / f"{candidate_id}.bin"
                try:
                    browser_fetch = self.browser_fetcher.fetch(
                        page_url,
                        candidate.metadata.get("selector", ""),
                        str(destination),
                    )
                    download_url = browser_fetch.get("download_url", "")
                    provider = self.registry.match(download_url, "BINARY", record["source_group"])
                    if provider is None:
                        raise ValueError("PLAYWRIGHT_DOWNLOAD_OUTSIDE_ALLOWLIST")
                    derived_id = hashlib.sha256(
                        f"{candidate.record_id}|BINARY|{download_url}".encode()).hexdigest()[:20]
                    derived = Candidate(
                        record_id=candidate.record_id, role="BINARY",
                        requested_url=download_url, provider_id=provider.provider_id,
                        source_class="OFFICIAL_CANDIDATE", state=ResolverState.DISCOVERED,
                        required=candidate.required, parent_candidate_id=candidate_id,
                        alternative_group=candidate.alternative_group,
                        metadata={"parent_candidate_id": candidate_id,
                                  "discovered_from_candidate_id": candidate_id,
                                  "page_requested_url": page_url})
                    self._record_candidate(
                        candidate, candidate_id, ResolverState.FETCHED, [],
                        {"final_url": browser_fetch.get("page_final_url", page_url),
                         "page_requested_url": page_url,
                         "download_url": download_url,
                         "action_log": browser_fetch.get("action_log", [])})
                    self.store.add_candidate(derived.to_dict() | {
                        "candidate_id": derived_id,
                        "parent_candidate_id": candidate_id,
                        "discovered_from_candidate_id": candidate_id,
                    })
                    self.store.add_evidence(
                        hashlib.sha256(f"{candidate_id}|browser|{download_url}".encode()).hexdigest()[:24],
                        candidate_id, utc_now(), {"role": "DOWNLOAD_CONTROL",
                        "page_requested_url": page_url,
                        "page_final_url": browser_fetch.get("page_final_url", browser_fetch.get("final_url", "")),
                        "download_url": download_url,
                        "action_log": browser_fetch.get("action_log", [])})
                    candidate = derived
                    candidate_id = derived_id
                    derived_destination = self.cache_dir / "downloads" / f"{derived_id}.bin"
                    derived_destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination != derived_destination:
                        shutil.move(str(destination), str(derived_destination))
                    destination = derived_destination
                    browser_fetch["final_url"] = download_url
                    browser_fetch["content_type"] = browser_fetch.get("download_content_type", "")
                except Exception as exc:
                    reasons = self._exception_reasons(exc)
                    self._record_candidate(candidate, candidate_id, ResolverState.BLOCKED, reasons, {})
                    outcomes.append({"role": "DOWNLOAD_CONTROL", "state": "BLOCKED", "reasons": reasons})
                    continue
            if provider is None:
                self._record_candidate(candidate, candidate_id, ResolverState.BLOCKED, ["PROVIDER_NOT_ALLOWED"], {})
                outcomes.append({"role": candidate.role, "state": "BLOCKED", "reasons": ["PROVIDER_NOT_ALLOWED"]})
                continue
            destination = self.cache_dir / ("pages" if candidate.role != "BINARY" else "downloads") / f"{candidate_id}.bin"
            try:
                fetch = browser_fetch or self.fetcher.fetch(
                    candidate.requested_url, destination, provider.max_bytes,
                    allow_url=lambda url, role=candidate.role, group=record["source_group"]:
                        self.registry.is_allowed_redirect(candidate.requested_url, url, role, group),
                )
                authority_ok, authority_reasons = verify_authority(
                    self.registry, candidate.requested_url, fetch["final_url"], candidate.role, record["source_group"])
                payload = destination.read_bytes()
                if candidate.role in {"IDENTITY", "STATUS_HISTORY"} and (fetch["content_type"].split(";")[0].lower() in {"text/html", "application/xhtml+xml"} or payload.lstrip().startswith(b"<")):
                    identity_ok, identity_reason = verify_identity(record["canonical_identifier"], extract_text(payload))
                    adapter = VBPLAdapter() if candidate.provider_id == "vbpl" else None
                    is_shell = bool(adapter and adapter.is_homepage(fetch["final_url"], extract_text(payload)))
                    identity_source = "STATUS_PAGE" if candidate.role == "STATUS_HISTORY" else "IDENTITY_PAGE"
                    identity_evidence = self._select_identity(identity_evidence, fetch | {
                        "identity_match": identity_ok and not is_shell,
                        "identity_reason": "VBPL_HOME_SHELL" if is_shell else identity_reason,
                        "identity_source": identity_source,
                    })
                    outcome_reasons = authority_reasons + ([] if identity_ok else [identity_reason])
                    if is_shell:
                        outcome_reasons.append("VBPL_HOME_SHELL")
                    identity_state = "FETCHED" if identity_ok and not is_shell else "NEEDS_REVIEW"
                    outcomes.append({"role": candidate.role, "state": identity_state,
                                     "reasons": outcome_reasons})
                    adapter = adapter or GenericOfficialAdapter(candidate.provider_id)
                    if not (authority_ok and identity_ok and not is_shell):
                        discovered = []
                    else:
                        discovered = adapter.discover_attachments(payload, fetch["final_url"], record["canonical_identifier"])
                    for discovered in discovered:
                        discovered_role = discovered.get("role", "BINARY")
                        if discovered_role == "DOWNLOAD_CONTROL":
                            provider_id = discovered.get("provider_id", candidate.provider_id)
                        else:
                            if self.registry.match(discovered["url"], discovered_role, record["source_group"]) is None:
                                continue
                            provider_id = discovered["provider_id"]
                        if discovered_role not in {"BINARY", "DOWNLOAD_CONTROL"}:
                            continue
                        discovered_candidate = Candidate(
                            record_id=record["record_id"], role=discovered_role,
                            requested_url=discovered["url"], provider_id=provider_id,
                            source_class=discovered["source_class"], state=ResolverState.DISCOVERED,
                            reason_codes=discovered["reason_codes"],
                            required=discovered["required"], metadata=discovered)
                        discovered_id = hashlib.sha256(
                            f"{record['record_id']}|{discovered_role}|{discovered_candidate.requested_url}".encode()
                        ).hexdigest()[:20]
                        if not any(existing.requested_url == discovered_candidate.requested_url
                                   and existing.role == discovered_role for existing in candidates):
                            candidates.append(discovered_candidate)
                            self.store.add_candidate(discovered_candidate.to_dict() | {"candidate_id": discovered_id})
                elif candidate.role == "BINARY":
                    candidate_binary = verify_binary(destination, fetch["content_type"], record["corpus_sha256"], provider.max_bytes)
                    candidate_binary["_url"] = candidate.requested_url
                    candidate_binary["_final_url"] = fetch["final_url"]
                    candidate_binary["authority_verified"] = authority_ok
                    candidate_binary["_candidate_id"] = candidate_id
                    candidate_binary["_provider"] = candidate.provider_id
                    outcome_reasons = authority_reasons + candidate_binary["reason_codes"]
                    outcomes.append({"role": "BINARY", "state": candidate_binary["state"] if authority_ok else "BLOCKED",
                                     "reasons": outcome_reasons})
                else:
                    outcome_reasons = authority_reasons
                    outcomes.append({"role": candidate.role, "state": "FETCHED", "reasons": outcome_reasons})
                candidate_state = ((ResolverState(candidate_binary["state"]) if authority_ok
                                    else ResolverState.BLOCKED)
                                   if candidate.role == "BINARY"
                                   else (ResolverState.FETCHED if authority_ok and
                                         (candidate.role not in {"IDENTITY", "STATUS_HISTORY"} or identity_ok) else
                                         ResolverState.NEEDS_REVIEW if candidate.role in {"IDENTITY", "STATUS_HISTORY"} else
                                         ResolverState.BLOCKED))
                self._record_candidate(candidate, candidate_id, candidate_state, outcome_reasons,
                                       fetch | candidate_binary if candidate.role == "BINARY" else fetch)
                if candidate.role == "BINARY" and not (identity_evidence and identity_evidence.get("identity_match", False)):
                    try:
                        extracted = extract_identity(destination, fetch["content_type"])
                        identity_ok, identity_reason = verify_identity(record["canonical_identifier"], extracted["text"])
                        text_hash = hashlib.sha256(extracted["text"].encode("utf-8")).hexdigest()
                        candidate_identity = fetch | extracted | {"identity_match": identity_ok,
                                                                  "identity_reason": identity_reason,
                                                                  "text_sha256": text_hash}
                        candidate_binary["identity_match"] = identity_ok
                        identity_evidence = self._select_identity(identity_evidence, candidate_identity)
                        outcomes.append({"role": "IDENTITY", "state": "FETCHED" if identity_ok else "NEEDS_REVIEW",
                                         "reasons": [] if identity_ok else [identity_reason]})
                    except Exception:
                        outcomes.append({"role": "IDENTITY", "state": "NEEDS_REVIEW",
                                         "reasons": ["BINARY_IDENTITY_EXTRACTION_FAILED"]})
                fetched_at = utc_now()
                evidence_id = hashlib.sha256(f"{candidate_id}|{fetched_at}|{sha256_file(destination)}".encode()).hexdigest()[:24]
                identity_summary = {key: identity_evidence.get(key) for key in (
                    "identity_source", "identity_match", "identity_reason", "text_sha256",
                    "pages_read", "page_range") if identity_evidence and identity_evidence.get(key) is not None}
                self.store.add_evidence(evidence_id, candidate_id, fetched_at, fetch | {
                    "cache_path": str(destination), "cache_sha256": sha256_file(destination),
                    "provider": candidate.provider_id, "role": candidate.role,
                    "identity_match": identity_ok if candidate.role in {"IDENTITY", "STATUS_HISTORY"} else None,
                    "identity_source": identity_evidence.get("identity_source") if identity_evidence else None,
                    "identity_evidence": identity_summary if candidate.role == "BINARY" else None,
                    "binary": candidate_binary if candidate.role == "BINARY" else None,
                })
                if candidate.role == "BINARY":
                    binary_result = self._select_binary(binary_result, candidate_binary, candidate)
            except Exception as exc:
                error_reasons = self._exception_reasons(exc)
                self._record_candidate(candidate, candidate_id, ResolverState.BLOCKED, error_reasons, {})
                outcomes.append({"role": candidate.role, "state": "BLOCKED", "reasons": error_reasons})
        reasons = sorted({reason for outcome in outcomes for reason in outcome["reasons"]})
        identity_required = not any(candidate.role == "BINARY" for candidate in candidates)
        identity_ok = bool(identity_evidence and identity_evidence.get("identity_match"))
        binary_outcomes = [outcome for outcome in outcomes if outcome["role"] == "BINARY"]
        has_block = bool(binary_outcomes) and not self._trusted_binary(binary_result) and all(
            outcome["state"] == "BLOCKED" for outcome in binary_outcomes)
        persisted = self.store.candidates_for_record(record["record_id"])
        required_pending = any(
            item.get("required", False)
            and item.get("state") in {ResolverState.FETCH_PENDING.value, ResolverState.DISCOVERED.value}
            for item in persisted
        )
        persisted_states = {item.get("state") for item in persisted}
        if not candidates:
            final_state, decision_reasons = ResolverState.NEEDS_REVIEW, ["BINARY_NOT_FETCHED"]
        elif has_block and not any(outcome["state"] == "NEEDS_REVIEW" for outcome in binary_outcomes):
            final_state, decision_reasons = ResolverState.BLOCKED, []
        elif binary_result is None and required_pending:
            final_state, decision_reasons = ResolverState.FETCH_PENDING, ["BINARY_NOT_FETCHED"]
        elif binary_result is None and ResolverState.NEEDS_REVIEW.value in persisted_states:
            final_state, decision_reasons = ResolverState.NEEDS_REVIEW, ["BINARY_NOT_FETCHED"]
        elif binary_result is None and persisted_states and persisted_states <= {ResolverState.BLOCKED.value}:
            final_state, decision_reasons = ResolverState.BLOCKED, []
        elif binary_result is None:
            final_state, decision_reasons = ResolverState.NEEDS_REVIEW, ["BINARY_NOT_FETCHED"]
        elif binary_result.get("state") != ResolverState.AUTO_EXACT_SHA.value:
            final_state, decision_reasons = ResolverState.NEEDS_REVIEW, binary_result.get("reason_codes", [])
        elif not identity_ok:
            final_state, decision_reasons = ResolverState.NEEDS_REVIEW, ["IDENTITY_FAILED"]
        else:
            final_state, decision_reasons = ResolverState.AUTO_EXACT_SHA, []
        reasons = sorted(set(reasons + decision_reasons))
        binary_capability = self._trusted_binary(binary_result)
        blocking_reasons = sorted({reason for outcome in outcomes
                                   if outcome["state"] == "BLOCKED"
                                   and not (outcome["role"] in {"IDENTITY", "STATUS_HISTORY"} and not identity_required)
                                   and not (binary_capability and identity_ok)
                                   for reason in outcome["reasons"]})
        warning_reasons = sorted(set(reasons) - set(blocking_reasons))
        resolved_sha = (binary_result or {}).get("sha256", "")
        resolved_sha_match = (
            "YES" if self._trusted_binary(binary_result) and resolved_sha == record.get("corpus_sha256")
            else "NO" if self._trusted_binary(binary_result) else "NOT_DOWNLOADED"
        )
        aggregate = record | {
            "state": final_state.value, "resolution_state": final_state.value,
            "reason_codes": reasons, "resolved_downloaded_sha256": resolved_sha,
            "resolved_sha_match": resolved_sha_match,
            "resolved_at": utc_now(), "identity_match": "YES" if identity_ok else "NO",
            "resolution_attempted_at": attempt_started_at,
            "blocking_reason_codes": blocking_reasons,
            "warning_reason_codes": warning_reasons,
        }
        if identity_evidence:
            aggregate["identity_url"] = identity_evidence.get("final_url") if identity_evidence.get("identity_source") == "IDENTITY_PAGE" else ""
            aggregate["identity_source"] = identity_evidence.get("identity_source")
            aggregate["final_identity_url"] = identity_evidence.get("final_url", "")
        if binary_result:
            aggregate["binary_state"] = binary_result.get("state", "")
            aggregate["final_binary_url"] = binary_result.get("_final_url", "")
            aggregate["binary_url"] = aggregate["final_binary_url"]
            aggregate["resolved_downloaded_sha256"] = binary_result.get("sha256", "")
            aggregate["binary_provider"] = binary_result.get("_provider", "")
            aggregate["binary_candidate_id"] = binary_result.get("_candidate_id", "")
            aggregate["binary_authority_verified"] = bool(binary_result.get("authority_verified"))
        self.store.update_record_state(record["record_id"], final_state.value,
                                       aggregate)
        return {"record_id": record["record_id"], "state": final_state.value, "reason_codes": reasons,
                "binary": binary_result, "identity": identity_evidence}

    def _all_candidates(self, record: dict) -> list[Candidate]:
        """Merge generated and persisted candidates so resume includes discoveries."""
        merged: dict[tuple[str, str], Candidate] = {
            (candidate.role, candidate.requested_url): candidate
            for candidate in self.candidates_for(record)
        }
        for row in self.store.candidates_for_record(record["record_id"]):
            role = row.get("role", "")
            requested_url = row.get("requested_url", "")
            if not role or not requested_url:
                continue
            try:
                state = ResolverState(row.get("state", ResolverState.FETCH_PENDING.value))
            except ValueError:
                state = ResolverState.NEEDS_REVIEW
            merged[(role, requested_url)] = Candidate(
                record_id=record["record_id"], role=role, requested_url=requested_url,
                final_url=row.get("final_url", ""), provider_id=row.get("provider_id", ""),
                source_class=row.get("source_class", "SECONDARY"), state=state,
                reason_codes=list(row.get("reason_codes", [])),
                downloaded_sha256=row.get("downloaded_sha256", ""),
                mime_type=row.get("mime_type", ""), size_bytes=row.get("size_bytes"),
                evidence_id=row.get("evidence_id", ""), metadata=dict(row.get("metadata", {})),
                required=bool(row.get("required", False)),
                parent_candidate_id=row.get("parent_candidate_id", ""),
                alternative_group=row.get("alternative_group", ""),
            )
        return list(merged.values())

    @staticmethod
    def _exception_reasons(exc: Exception) -> list[str]:
        text = str(exc).strip()
        if isinstance(exc, HTTPError):
            return [f"HTTP_{exc.code}"]
        if isinstance(exc, (URLError, TimeoutError)):
            return ["NETWORK_RETRY_EXHAUSTED"]
        if isinstance(exc, UnicodeError):
            return ["URL_ENCODING_FAILED"]
        stable = {
            "HTTPS_REQUIRED", "URL_OUTSIDE_ALLOWLIST", "FINAL_URL_OUTSIDE_ALLOWLIST",
            "REDIRECT_WITHOUT_LOCATION", "REDIRECT_LIMIT", "SIZE_LIMIT",
            "PLAYWRIGHT_NOT_INSTALLED", "PLAYWRIGHT_SELECTOR_NOT_PROVEN",
            "PLAYWRIGHT_DOWNLOAD_OUTSIDE_ALLOWLIST", "PAGE_URL_OUTSIDE_ALLOWLIST",
        }
        return [text] if text in stable else ["FETCH_ERROR"]

    def _record_candidate(self, candidate: Candidate, candidate_id: str, state: ResolverState,
                          reasons: list[str], metadata: dict) -> None:
        merged = candidate.to_dict() | metadata
        merged.update({"role": candidate.role, "requested_url": candidate.requested_url,
                       "final_url": metadata.get("final_url", ""),
                       "state": state.value, "reason_codes": sorted(set(reasons))})
        self.store.update_candidate(candidate_id, state=state.value, final_url=metadata.get("final_url", ""),
                                    reason_codes=sorted(set(reasons)), metadata=merged)

    @staticmethod
    def _valid_binary(result: dict | None) -> bool:
        if not result or not result.get("magic_mime"):
            return False
        return not any(code in result.get("reason_codes", [])
                       for code in ("UNKNOWN_MAGIC", "MIME_MAGIC_MISMATCH", "SIZE_LIMIT"))

    @classmethod
    def _trusted_binary(cls, result: dict | None) -> bool:
        return cls._valid_binary(result) and bool(result.get("authority_verified"))

    @classmethod
    def _binary_rank(cls, result: dict | None) -> int:
        if not cls._trusted_binary(result):
            return 0
        identity_match = bool(result.get("identity_match"))
        if result.get("state") == ResolverState.AUTO_EXACT_SHA.value:
            return 5 if identity_match else 4
        return 3 if identity_match else 2

    @classmethod
    def _select_binary(cls, current: dict | None, candidate: dict | None,
                       source: Candidate) -> dict | None:
        if candidate is None:
            return current
        current_key = (cls._binary_rank(current), -(len(current.get("_provider", "")) if current else 0),
                       current.get("_provider", "") if current else "",
                       current.get("_url", "") if current else "",
                       current.get("_candidate_id", "") if current else "")
        candidate = dict(candidate)
        candidate.setdefault("_provider", source.provider_id)
        candidate.setdefault("_url", source.requested_url)
        candidate_key = (cls._binary_rank(candidate), -(len(candidate.get("_provider", ""))),
                         candidate.get("_provider", ""), candidate.get("_url", ""),
                         candidate.get("_candidate_id", ""))
        return candidate if candidate_key > current_key else current

    @staticmethod
    def _select_identity(current: dict | None, candidate: dict | None) -> dict | None:
        if candidate is None:
            return current
        def rank(item: dict | None) -> tuple:
            if not item:
                return (0, "", "", "")
            source = item.get("identity_source", "")
            source_rank = {
                "BINARY_CONTENT": 4 if item.get("sha_match") == "YES" else 3,
                "IDENTITY_PAGE": 2,
                "STATUS_PAGE": 1,
            }.get(source, 0)
            return (source_rank if item.get("identity_match") else 0,
                    "1" if item.get("authority_verified") else "0",
                    item.get("_provider", ""), item.get("final_url", ""))
        current_key = rank(current)
        candidate_key = rank(candidate)
        return candidate if candidate_key > current_key else current

    def _has_evidence(self, candidate_id: str) -> bool:
        return bool(self.store.connection.execute("SELECT 1 FROM evidence WHERE candidate_id=?", (candidate_id,)).fetchone())

    @staticmethod
    def _looks_binary(url: str) -> bool:
        return url.lower().split("?", 1)[0].endswith((".pdf", ".doc", ".docx", ".zip"))
