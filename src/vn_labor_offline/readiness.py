"""Semantic gates that are stricter than local four-output construction checks."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from .gold_evaluator import graph_fingerprint
from .util import read_jsonl


def _evidence_issues(output_dir: Path, registry: list[dict]) -> dict:
    segments={s['segment_id']:s for s in read_jsonl(output_dir/'03_structure/segments.jsonl')}
    sources={r['file_id']:r for r in read_jsonl(output_dir/'01_extracted/documents.jsonl')}
    docs={r['document_id']:r for r in registry}
    cases={r['case_id']:r for r in read_jsonl(output_dir/'03_structure/cases.jsonl')}
    counts=Counter()
    relation_file=('04_knowledge/accepted_relation_edges.jsonl' if
                   (output_dir/'04_knowledge/accepted_relation_edges.jsonl').exists() else
                   '04_knowledge/relation_edges.jsonl')
    for name,status_field in [(relation_file,'evidence_status'),
                              ('04_knowledge/diagnostic_checklists.jsonl','provenance_status'),
                              ('04_knowledge/issue_edges.jsonl','provenance_status')]:
        for row in read_jsonl(output_dir/name):
            status=row.get(status_field)
            if status not in {'RESOLVED','VERIFIED'}:
                counts['UNRESOLVED_EVIDENCE']+=1
                continue
            span=row.get('evidence_span') or {}
            evidence=row.get('evidence_text') or ''
            segment=segments.get(span.get('segment_id'))
            doc_id=segment.get('document_id') if segment else None
            if not doc_id:
                source_id=row.get('source_id') or row.get('source_provision_id')
                doc_id=cases.get(source_id,{}).get('document_id') or docs.get(source_id,{}).get('document_id')
            source=sources.get(docs.get(doc_id,{}).get('file_id'),{})
            text=source.get('text','')
            if segment:
                start,end=span.get('segment_char_start'),span.get('segment_char_end')
                if not isinstance(start,int) or not isinstance(end,int) or segment['text'][start:end]!=evidence:
                    counts['INVALID_SEGMENT_EVIDENCE']+=1
                    continue
            doc_start,doc_end=span.get('document_char_start'),span.get('document_char_end')
            if not isinstance(doc_start,int) or not isinstance(doc_end,int) or text[doc_start:doc_end]!=evidence:
                counts['INVALID_DOCUMENT_EVIDENCE']+=1
                continue
            pages=source.get('page_provenance',[])
            if pages:
                matching=[p['page'] for p in pages if p.get('text_start',0)<doc_end and p.get('text_end',0)>doc_start]
                if not matching or span.get('page_start')!=min(matching) or span.get('page_end')!=max(matching):
                    counts['INVALID_PAGE_EVIDENCE']+=1
    return dict(counts)


def semantic_readiness_gate(output_dir: Path, registry: list[dict]) -> dict:
    evidence=_evidence_issues(output_dir,registry)
    changes=list(read_jsonl(output_dir/'04_knowledge/legal_changes.jsonl'))
    temporal_changes=[r for r in changes if r.get('operation') in {'AMEND','REPEAL','REPLACE'}]
    pending_changes=[r['change_id'] for r in temporal_changes if
        not ((r.get('review_status')=='APPROVED' and r.get('effective_from') and
              r.get('target_provision_identity_id')) or
             (r.get('review_status')=='EXCLUDED' and r.get('exclusion_reason')))]
    versions=list(read_jsonl(output_dir/'03_structure/provision_versions.jsonl'))
    unreviewed_versions=sum(not r.get('provision_temporal_verified') for r in versions)
    by_identity=defaultdict(list)
    for version in versions:
        by_identity[version.get('provision_identity_id')].append(version)
    unapplied_changes=[]
    for change in temporal_changes:
        if change['change_id'] in pending_changes or change.get('review_status')=='EXCLUDED':
            continue
        identity=change['target_provision_identity_id']
        affected=by_identity.get(identity,[])
        old_ended=any(v.get('ended_by_change_id')==change['change_id'] and
                      v.get('valid_to')==change['effective_from'] for v in affected)
        new_started=any(v.get('introduced_by_change_id')==change['change_id'] and
                        v.get('valid_from')==change['effective_from'] for v in affected)
        if not old_ended or change['operation'] in {'AMEND','REPLACE'} and not new_started:
            unapplied_changes.append(change['change_id'])
    heading_nodes=[r for r in read_jsonl(output_dir/'05_graph/nodes.jsonl') if r.get('label') in {'Chapter','Section'}]
    unresolved_headings=sum(r.get('properties',{}).get('provenance_status')!='RESOLVED' for r in heading_nodes)
    report_path=output_dir/'reports/neo4j_validation.json'
    fingerprint=graph_fingerprint(output_dir)
    neo4j_current=False
    if report_path.exists() and fingerprint:
        report=json.loads(report_path.read_text(encoding='utf-8'))
        neo4j_current=report.get('passed') is True and report.get('build_id')==fingerprint
    checks={'exact_evidence':not evidence,'reviewed_temporal_changes':not pending_changes,
            'changes_applied_to_versions':not unapplied_changes,
            'reviewed_provision_intervals':bool(versions) and not unreviewed_versions,
            'hierarchy_provenance':not unresolved_headings,'current_neo4j_build':neo4j_current}
    return {'passed':all(checks.values()),'checks':checks,'evidence_issues':evidence,
            'pending_temporal_changes':len(pending_changes),
            'unapplied_temporal_changes':len(unapplied_changes),
            'unreviewed_provision_versions':unreviewed_versions,
            'unresolved_hierarchy_headings':unresolved_headings,
            'neo4j_build_id':fingerprint if neo4j_current else None}
