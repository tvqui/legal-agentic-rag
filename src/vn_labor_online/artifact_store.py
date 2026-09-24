from __future__ import annotations
import hashlib,json,os,shutil,stat,uuid,zipfile
from pathlib import Path
from .config import OnlineConfig
from .errors import OfflineArtifactMismatch,IndexUnavailable
from .models import CompatibilityReport

def _hash_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def _jsonl(path:Path):
    with path.open(encoding='utf-8-sig') as f: return [json.loads(x) for x in f if x.strip()]
def _fingerprint(value)->str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

class ArtifactStore:
    """Materializes a trusted OFFLINE archive and exposes immutable build data."""
    def __init__(self,cfg:OnlineConfig):
        self.cfg=cfg; source=Path(cfg.artifact_source).expanduser()
        if not source.exists(): raise OfflineArtifactMismatch(f'Artifact source missing: {source}')
        self.archive_sha256=None
        if source.is_file():
            self.archive_sha256=_hash_file(source)
            if cfg.expected_archive_sha256 and self.archive_sha256!=cfg.expected_archive_sha256:
                raise OfflineArtifactMismatch('OFFLINE archive SHA-256 mismatch')
            cache_root=Path(cfg.cache_dir); cache_root.mkdir(parents=True,exist_ok=True)
            target=cache_root/('build_'+self.archive_sha256[:16]); marker=target/'.complete'
            if marker.exists() and marker.read_text(encoding='ascii').strip()!=self.archive_sha256:
                raise OfflineArtifactMismatch('Cached OFFLINE archive marker mismatch')
            if not marker.exists():
                temporary=cache_root/(target.name+'.tmp_'+str(os.getpid())+'_'+uuid.uuid4().hex)
                try:
                    temporary.mkdir(parents=False,exist_ok=False); base=temporary.resolve(); total_size=0
                    with zipfile.ZipFile(source) as z:
                        if z.testzip(): raise OfflineArtifactMismatch('OFFLINE ZIP CRC failure')
                        destinations=set()
                        for info in z.infolist():
                            mode=(info.external_attr>>16)&0o170000
                            if mode==stat.S_IFLNK: raise OfflineArtifactMismatch('OFFLINE ZIP contains a symbolic link')
                            total_size+=info.file_size
                            if info.file_size>8*1024**3 or total_size>20*1024**3: raise OfflineArtifactMismatch('OFFLINE ZIP expanded size exceeds safety limit')
                            dest=(temporary/info.filename).resolve()
                            if base not in dest.parents and dest!=base: raise OfflineArtifactMismatch('ZIP path traversal')
                            normalized=os.path.normcase(str(dest))
                            if normalized in destinations: raise OfflineArtifactMismatch('OFFLINE ZIP contains duplicate paths')
                            destinations.add(normalized)
                            if info.is_dir(): dest.mkdir(parents=True,exist_ok=True); continue
                            dest.parent.mkdir(parents=True,exist_ok=True)
                            with z.open(info) as src,dest.open('wb') as dst: shutil.copyfileobj(src,dst,1024*1024)
                    (temporary/'.complete').write_text(self.archive_sha256,encoding='ascii')
                    concurrent_marker=target/'.complete'
                    if concurrent_marker.exists() and concurrent_marker.read_text(encoding='ascii').strip()==self.archive_sha256:
                        pass
                    else:
                        if target.exists(): shutil.rmtree(target)
                        os.replace(temporary,target)
                finally:
                    if temporary.exists(): shutil.rmtree(temporary,ignore_errors=True)
            self.root=target
        else: self.root=source
        self.artifacts=self.root/'artifacts' if (self.root/'artifacts').exists() else self.root
        self.units=_jsonl(self.path('06_indexes/retrieval_units.jsonl'))
        self.nodes=_jsonl(self.path('05_graph/nodes.jsonl')); self.edges=_jsonl(self.path('05_graph/edges.jsonl'))
        self.units_by_id={x['unit_id']:x for x in self.units}; self.nodes_by_id={x['id']:x for x in self.nodes}
        catalog_path=self.path('00_manifest/source_catalog_resolved.jsonl')
        self.source_catalog=_jsonl(catalog_path) if catalog_path.exists() else []
        self.catalog_by_file_id={x.get('file_id'):x for x in self.source_catalog if x.get('file_id')}
        self.final=json.loads(self.path('reports/final_outputs_validation.json').read_text(encoding='utf-8-sig'))
        self.dense_report=json.loads(self.path('reports/dense_validation.json').read_text(encoding='utf-8-sig'))
        self.neo=json.loads(self.path('reports/neo4j_validation.json').read_text(encoding='utf-8-sig'))
        self.report=self._validate()
        if not self.report.compatible: raise OfflineArtifactMismatch('; '.join(self.report.issues))
    def path(self,relative:str)->Path: return self.artifacts/relative
    def _validate(self)->CompatibilityReport:
        issues=[]; graph=_fingerprint([self.nodes,self.edges]); units=_fingerprint(self.units)
        stages=self.final.get('stages',{})
        if not all(stages.get(x) is True for x in ('registry','structure','graph','indexes')): issues.append('OFFLINE_STAGES_NOT_PASS')
        if self.neo.get('passed') is not True: issues.append('NEO4J_VALIDATION_FAILED')
        if graph!=self.neo.get('build_id'): issues.append('GRAPH_NEO4J_BUILD_MISMATCH')
        if self.neo.get('nodes')!=len(self.nodes) or self.neo.get('edges')!=len(self.edges): issues.append('GRAPH_NEO4J_COUNT_MISMATCH')
        if self.cfg.expected_build_id and graph!=self.cfg.expected_build_id: issues.append('EXPECTED_BUILD_MISMATCH')
        if self.cfg.expected_retrieval_unit_fingerprint and units!=self.cfg.expected_retrieval_unit_fingerprint: issues.append('RETRIEVAL_UNIT_FINGERPRINT_MISMATCH')
        node_ids={x.get('id') for x in self.nodes}
        if len(node_ids)!=len(self.nodes) or None in node_ids: issues.append('GRAPH_NODE_ID_INVALID')
        if any(x.get('source') not in node_ids or x.get('target') not in node_ids for x in self.edges): issues.append('GRAPH_EDGE_ENDPOINT_MISSING')
        if any(x.get('unit_id') not in node_ids for x in self.units): issues.append('RETRIEVAL_UNIT_NOT_IN_GRAPH')
        catalog_ids=set(self.catalog_by_file_id)
        if not self.source_catalog: issues.append('SOURCE_CATALOG_MISSING')
        elif len(catalog_ids)!=len(self.source_catalog): issues.append('SOURCE_CATALOG_ID_INVALID')
        if any((x.get('provenance') or {}).get('file_id') not in catalog_ids for x in self.units): issues.append('RETRIEVAL_UNIT_SOURCE_NOT_IN_CATALOG')
        dense_meta=_jsonl(self.path('06_indexes/dense/metadata.jsonl'))
        bm25=_jsonl(self.path('06_indexes/bm25/corpus.jsonl'))
        ids=[x['unit_id'] for x in self.units]
        if [x.get('unit_id') for x in dense_meta]!=ids: issues.append('DENSE_UNIT_ORDER_MISMATCH')
        if [x.get('id') for x in bm25]!=ids: issues.append('BM25_UNIT_ORDER_MISMATCH')
        if self.dense_report.get('dense_passed') is not True or self.dense_report.get('units')!=len(ids): issues.append('DENSE_VALIDATION_FAILED')
        if self.cfg.expected_dense_fingerprint and self.dense_report.get('fingerprint')!=self.cfg.expected_dense_fingerprint: issues.append('DENSE_FINGERPRINT_MISMATCH')
        provisional=[]
        if self.final.get('source_catalog_quality',{}).get('passed') is not True: provisional.append('SOURCE_CATALOG_HUMAN_REVIEW_INCOMPLETE')
        if self.final.get('semantic_quality',{}).get('passed') is not True: provisional.append('PROVISION_TEMPORAL_REVIEW_INCOMPLETE')
        if self.final.get('gold_evaluation',{}).get('passed') is not True: provisional.append('GOLD_NOT_APPROVED')
        return CompatibilityReport(compatible=not issues,build_id=graph,graph_fingerprint=graph,
          retrieval_unit_fingerprint=units,dense_fingerprint=self.dense_report.get('fingerprint'),
          gold_build_id=self.final.get('gold_build_id'),issues=issues,provisional_reasons=provisional,
          source_catalog_records=len(self.source_catalog),corpus_snapshot_as_of=self.cfg.corpus_snapshot_as_of)
    def load_bm25(self):
        try:
            import bm25s
            return bm25s.BM25.load(str(self.path('06_indexes/bm25')),load_corpus=True)
        except Exception as exc: raise IndexUnavailable(f'BM25 unavailable: {exc}') from exc
    def load_faiss(self):
        try:
            import faiss,numpy as np
            return faiss.deserialize_index(np.frombuffer(self.path('06_indexes/dense/faiss.index').read_bytes(),dtype='uint8').copy())
        except Exception as exc: raise IndexUnavailable(f'Dense unavailable: {exc}') from exc
