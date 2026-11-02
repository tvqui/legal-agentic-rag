"""Check that an artifact carries the configured citation URLs, not stale ones.

Missing sources stay pending. Alignment with config is not identity, content,
availability or legal review, and never creates a human approval.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,yaml


def check_source_links(catalog,registry,units=None,nodes=None,source_records=None):
    expected={};missing=[];issues=[];counts={'registry':0,'retrieval_units':0,'graph_documents':0,'source_catalog':0}
    if not registry:issues.append({'stage':'registry','reason':'REGISTRY_EMPTY'})
    for d in registry:
        relative=d.get('relative_path','')
        entry=catalog.get(relative) or catalog.get(Path(relative).name) or {}
        link=entry.get('source_url') or ''
        if not link:
            missing.append({'document_id':d.get('document_id'),'relative_path':relative,'reason':'NO_CONFIGURED_SOURCE_URL'})
            continue
        if entry.get('sha256') and entry['sha256']!=d.get('sha256'):
            issues.append({'stage':'registry','document_id':d.get('document_id'),'relative_path':relative,'reason':'CONFIG_SOURCE_SHA_MISMATCH'})
        expected[d['document_id']]={'url':link,'file_id':d.get('file_id'),'relative_path':relative,'sha256':d.get('sha256')}
        counts['registry']+=1
        if (d.get('source_url') or '')!=link:
            issues.append({'stage':'registry','document_id':d['document_id'],'reason':'SOURCE_URL_MISMATCH','expected_url':link,'actual_url':d.get('source_url')})
    def compare(stage,doc_id,actual,identifier):
        counts[stage]+=1;want=expected[doc_id]['url']
        if (actual or '')!=want:
            issues.append({'stage':stage,'document_id':doc_id,'record_id':identifier,'reason':'SOURCE_URL_MISMATCH','expected_url':want,'actual_url':actual})
    if units is not None:
        for u in units:
            if u.get('document_id') in expected:compare('retrieval_units',u['document_id'],u.get('source_url'),u.get('unit_id'))
    if nodes is not None:
        by_id={n.get('id'):n for n in nodes}
        for doc_id in expected:
            if doc_id not in by_id:issues.append({'stage':'graph_documents','document_id':doc_id,'reason':'DOCUMENT_NODE_MISSING'})
            else:compare('graph_documents',doc_id,by_id[doc_id].get('properties',{}).get('source_url'),doc_id)
    if source_records is not None:
        by_file={r.get('file_id'):r for r in source_records}
        for doc_id,value in expected.items():
            r=by_file.get(value['file_id'])
            if r is None:issues.append({'stage':'source_catalog','document_id':doc_id,'reason':'RESOLVED_CATALOG_RECORD_MISSING'})
            else:compare('source_catalog',doc_id,r.get('source_url'),value['file_id'])
    return {'schema_version':1,'scope':'CONFIG_ALIGNMENT_NOT_LEGAL_APPROVAL','passed':not issues,
        'documents':len(registry),'configured_documents':len(expected),'matched_configured_documents':len(expected)-len({i.get('document_id') for i in issues if i.get('document_id') in expected}),
        'missing_source_count':len(missing),'all_documents_have_configured_links':bool(registry) and not missing,
        'missing_sources':missing,'records_checked':counts,'issues':issues,
        'configured_links':[{'document_id':doc_id,**value} for doc_id,value in expected.items()],
        'human_legal_approvals_created':0}


def audit_source_links(project_root,output,registry,units=None,nodes=None,source_records=None):
    root=Path(project_root);output=Path(output);path=root/'config/source_catalog.yaml'
    raw=path.read_bytes() if path.exists() else b''
    catalog=(yaml.safe_load(raw) or {}).get('sources',{})
    report=check_source_links(catalog,registry,units,nodes,source_records)
    report.update(checked_at=datetime.now(timezone.utc).isoformat(),config_sha256=hashlib.sha256(raw).hexdigest())
    (output/'reports').mkdir(parents=True,exist_ok=True)
    (output/'00_manifest').mkdir(parents=True,exist_ok=True)
    (output/'reports/source_links_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'00_manifest/source_links_snapshot.json').write_text(json.dumps({
        'schema_version':1,'config_sha256':report['config_sha256'],'checked_at':report['checked_at'],
        'configured_links':report['configured_links'],'missing_sources':report['missing_sources']},ensure_ascii=False,indent=2),encoding='utf-8')
    print('SOURCE_LINKS_VALIDATION '+json.dumps({key:report[key] for key in
        ('passed','configured_documents','matched_configured_documents','missing_source_count')},ensure_ascii=False),flush=True)
    return report
