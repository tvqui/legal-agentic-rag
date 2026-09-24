from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
import yaml
from .temporal import instrument_id
from .util import stable_id, write_jsonl


def materialize_provision_versions(registry: list[dict], provisions: list[dict], output_dir: Path,
                                   project_root: Path | None = None) -> tuple[list[dict], list[dict]]:
    docs = {d["document_id"]: d for d in registry}
    config_root = Path(project_root) if project_root is not None else Path(output_dir).parent
    review_path=config_root/'config/provision_version_reviews.yaml'
    reviews=(yaml.safe_load(review_path.read_text(encoding='utf-8')) or {}).get('versions',{}) if review_path.exists() else {}
    coverage_path=config_root/'config/temporal_coverage_reviews.yaml'
    coverages=(yaml.safe_load(coverage_path.read_text(encoding='utf-8')) or {}).get('instruments',{}) if coverage_path.exists() else {}
    identities = {}
    versions = []
    for provision in provisions:
        doc = docs.get(provision["document_id"], {})
        instrument = doc.get("instrument_id") or instrument_id(doc)
        path = "/".join(str(provision.get(k, "")) for k in ("article_number", "clause_number", "point_number"))
        identity_id = stable_id(instrument, path, prefix="provision_identity")
        review=reviews.get(provision['provision_id']) or {}
        coverage=coverages.get(instrument) or {}
        if coverage:
            if coverage.get('review_status')!='APPROVED' or not all(coverage.get(k) for k in
                    ('reviewer','reviewed_at','evidence','coverage_as_of','source_shas')):
                raise ValueError(f"Incomplete instrument temporal coverage review: {instrument}")
            try:
                date.fromisoformat(str(coverage['reviewed_at']))
                date.fromisoformat(str(coverage['coverage_as_of']))
            except (TypeError,ValueError) as exc:
                raise ValueError(f"Invalid instrument temporal coverage date: {instrument}") from exc
            if doc.get('sha256') not in coverage['source_shas']:
                raise ValueError(f"Instrument temporal coverage source SHA mismatch: {instrument}")
        if review:
            if review.get('review_status')!='APPROVED' or not all(review.get(k) for k in
                    ('reviewer','reviewed_at','source_sha256','evidence','valid_from')):
                raise ValueError(f"Incomplete provision version review: {provision['provision_id']}")
            if review['source_sha256']!=doc.get('sha256'):
                raise ValueError(f"Provision review source SHA mismatch: {provision['provision_id']}")
            try:
                date.fromisoformat(str(review['reviewed_at']))
                start=date.fromisoformat(str(review['valid_from']))
                end=date.fromisoformat(str(review['valid_to'])) if review.get('valid_to') else None
            except (TypeError,ValueError) as exc:
                raise ValueError(f"Invalid provision review date: {provision['provision_id']}") from exc
            if end and end<=start:
                raise ValueError(f"Contradictory provision review interval: {provision['provision_id']}")
            identity_id=review.get('provision_identity_id') or identity_id
        identities.setdefault(identity_id, {
            "provision_identity_id": identity_id, "instrument_id": instrument,
            "canonical_path": path, "temporal_status": "UNKNOWN",
        })
        covered=bool(coverage and doc.get('temporal_verified') and doc.get('effective_from') and
            doc.get('legal_status') in {'EFFECTIVE','EXPIRED'} and
            (doc.get('legal_status')!='EXPIRED' or doc.get('effective_to')))
        status = ("REVIEWED_PROVISION" if review else "REVIEWED_INSTRUMENT_COVERAGE" if covered else
                  "INHERITED_DOCUMENT" if doc.get("effective_from") else "UNKNOWN")
        valid_from=review.get('valid_from') if review else provision.get('valid_from') or None
        valid_to=review.get('valid_to') if review else provision.get('valid_to') or None
        provision.update({
            "provision_identity_id": identity_id,
            "provision_version_id": provision["provision_id"],
            "source_document_version_id": provision["document_id"],
            "temporal_status": status,
            "temporal_evidence": {"source": "provision_version_review", "reviewer":review['reviewer'],
                                  "reviewed_at":review['reviewed_at'], "evidence":review['evidence']} if review else
                                 {"source":"instrument_temporal_coverage_review","reviewer":coverage['reviewer'],
                                  "reviewed_at":coverage['reviewed_at'],"evidence":coverage['evidence']} if covered else
                                 {"source": "document.effective_from"} if status != "UNKNOWN" else {},
            "introduced_by_change_id": review.get('introduced_by_change_id'),
            "ended_by_change_id": review.get('ended_by_change_id'),
            "provision_temporal_verified":bool(review or covered),
            "temporal_coverage_as_of":coverage.get('coverage_as_of') if covered and not review else None,
            "valid_from":valid_from or '', "valid_to":valid_to or '',
        })
        versions.append({
            "provision_version_id": provision["provision_id"], "provision_identity_id": identity_id,
            "source_document_version_id": provision["document_id"], "valid_from": valid_from,
            "valid_to": valid_to, "temporal_status": status,
            "temporal_evidence": provision["temporal_evidence"],
            "introduced_by_change_id":provision['introduced_by_change_id'],
            "ended_by_change_id":provision['ended_by_change_id'],
            "provision_temporal_verified":bool(review or covered),
            "temporal_coverage_as_of":provision['temporal_coverage_as_of'],
        })
    by_identity=defaultdict(list)
    for version in versions:
        if version['temporal_status']=='REVIEWED_PROVISION':
            by_identity[version['provision_identity_id']].append(version)
    for identity_id,rows in by_identity.items():
        ordered=sorted(rows,key=lambda row:row['valid_from'])
        for left,right in zip(ordered,ordered[1:]):
            if not left['valid_to'] or left['valid_to']>right['valid_from']:
                raise ValueError(f"Overlapping reviewed provision versions: {identity_id}")
    write_jsonl(output_dir / "03_structure" / "provision_identities.jsonl", identities.values())
    write_jsonl(output_dir / "03_structure" / "provision_versions.jsonl", versions)
    # The parser writes its initial rows before provenance/version enrichment.
    # Audit and resume paths reload this file, so persist the final rows here.
    write_jsonl(output_dir / "03_structure" / "provisions.jsonl", provisions)
    return list(identities.values()), versions
