from __future__ import annotations
import hashlib,json,os,re
from collections import defaultdict
from pathlib import Path
from .util import read_jsonl

LABELS={'LegalInstrument','AbstractLaw','PolicySeries','DocumentVersion','ConsolidatedDocumentVersion','SourceDocument','SupplementaryDocument','Chapter','Section','Article','Clause','Point','Provision','ProvisionIdentity','Annex','Form','AttachedRegulation','Judgment','CassationDecision','Precedent','Case','CaseFeature','LegalIssue','DiagnosticItem','Community'}

def neo4j_properties(properties):
    result={}
    for key,value in properties.items():
        if isinstance(value,dict) or (isinstance(value,list) and (any(type(v) not in (str,bool,int,float) for v in value) or len({type(v) for v in value})>1)):
            result[key]=json.dumps(value,ensure_ascii=False)
        else: result[key]=value
    return result

def validate_export(nodes,edges):
    node_ids={n['id'] for n in nodes}
    if not nodes or not edges: raise ValueError('Graph export missing/empty')
    if len(node_ids)!=len(nodes) or len({e['id'] for e in edges})!=len(edges): raise ValueError('Duplicate graph IDs')
    if any(n['label'] not in LABELS for n in nodes): raise ValueError('Unsupported semantic label')
    if any(e['source'] not in node_ids or e['target'] not in node_ids or not re.fullmatch('[A-Z_]+',e['type']) for e in edges): raise ValueError('Invalid graph edge')

def replace_transaction(tx,nodes,edges,dataset,build_id,batch_size,replace_legacy=False):
    # All deletion/import/verification is in one transaction; failures roll back.
    crossing=tx.run('MATCH (n:Entity {dataset_id:$dataset})-[r]-(other) WHERE other.dataset_id IS NULL OR other.dataset_id <> $dataset RETURN count(r) AS count',dataset=dataset).single()['count']
    if crossing: raise RuntimeError('Dataset has external relationships; refusing to delete shared graph links.')
    conflicts=tx.run('MATCH (n:Entity) WHERE n.id IN $ids AND (n.dataset_id IS NULL OR n.dataset_id <> $dataset) RETURN count(n) AS count',ids=[n['id'] for n in nodes],dataset=dataset).single()['count']
    if conflicts and not replace_legacy: raise RuntimeError('Existing unowned/conflicting Entity IDs. Explicit --replace-legacy is required for migration in a dedicated database.')
    if replace_legacy:
        foreign=tx.run('MATCH (n:Entity) WHERE n.dataset_id IS NOT NULL AND n.dataset_id <> $dataset RETURN count(n) AS count',dataset=dataset).single()['count']
        if foreign: raise RuntimeError('Legacy migration requires a dedicated database without other datasets.')
        tx.run('MATCH (n:Entity) WHERE n.dataset_id IS NULL DETACH DELETE n').consume()
    tx.run('MATCH (n:Entity {dataset_id:$dataset}) DETACH DELETE n',dataset=dataset).consume()
    groups=defaultdict(list)
    for n in nodes: groups[n['label']].append(n)
    for label,group in groups.items():
        for i in range(0,len(group),batch_size):
            tx.run(f'UNWIND $rows AS row CREATE (n:Entity:{label}) SET n = row.properties SET n.id=row.id, n.type=row.label, n.dataset_id=$dataset, n.build_id=$build',rows=group[i:i+batch_size],dataset=dataset,build=build_id).consume()
    for i in range(0,len(edges),batch_size):
        tx.run('UNWIND $rows AS row MATCH (s:Entity {id:row.source, dataset_id:$dataset}), (t:Entity {id:row.target, dataset_id:$dataset}) CALL apoc.merge.relationship(s,row.type,{id:row.id},row.properties,t,{}) YIELD rel SET rel.dataset_id=$dataset, rel.build_id=$build RETURN count(rel) AS loaded',rows=edges[i:i+batch_size],dataset=dataset,build=build_id).consume()
    actual_nodes=list(tx.run('MATCH (n:Entity {dataset_id:$dataset}) RETURN n.id AS id, n.type AS type',dataset=dataset))
    actual_edges=list(tx.run('MATCH (s:Entity)-[r {dataset_id:$dataset}]->(t:Entity) RETURN r.id AS id, s.id AS source, t.id AS target, type(r) AS type',dataset=dataset))
    if len(actual_nodes)!=len(nodes) or len(actual_edges)!=len(edges):
        raise RuntimeError('Neo4j exact graph verification failed: counts differ')
    if {(n['id'],n['type']) for n in actual_nodes}!={(n['id'],n['label']) for n in nodes} or {(e['id'],e['source'],e['target'],e['type']) for e in actual_edges}!={(e['id'],e['source'],e['target'],e['type']) for e in edges}:
        raise RuntimeError('Neo4j exact graph verification failed')

def load_neo4j(output_dir: Path,batch_size=500,dataset='vn-labor-offline',replace_legacy=False):
    from neo4j import GraphDatabase
    from dotenv import load_dotenv
    if batch_size<1: raise ValueError('batch_size must be positive')
    load_dotenv()
    nodes=list(read_jsonl(output_dir/'05_graph/nodes.jsonl')); edges=list(read_jsonl(output_dir/'05_graph/edges.jsonl'))
    validate_export(nodes,edges)
    build_id=hashlib.sha256(json.dumps([nodes,edges],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    nodes=[{**n,'properties':neo4j_properties(n['properties'])} for n in nodes]
    edges=[{**e,'properties':neo4j_properties(e['properties'])} for e in edges]
    database=os.getenv('NEO4J_DATABASE','neo4j')
    with GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:7687'),auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','change_me'))) as driver:
        driver.verify_connectivity()
        driver.execute_query('CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE',database_=database)
        with driver.session(database=database) as session:
            session.execute_write(replace_transaction,nodes,edges,dataset,build_id,batch_size,replace_legacy)
    report={'passed':True,'dataset_id':dataset,'build_id':build_id,'nodes':len(nodes),'edges':len(edges),'mode':'transactional_replace'}
    (output_dir/'reports').mkdir(parents=True,exist_ok=True)
    (output_dir/'reports/neo4j_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
