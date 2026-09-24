from __future__ import annotations
import re,threading
from pathlib import Path
from collections import defaultdict
from datetime import date
from .artifact_store import ArtifactStore
from .config import OnlineConfig
from .errors import IndexUnavailable
from .models import Evidence,ExplicitReference

def _norm(value): return re.sub(r'[^0-9A-Z]','',str(value or '').upper().replace('Đ','D'))
def as_evidence(unit:dict,score:float,method:str,rank:int,components=None)->Evidence:
    keys={'unit_id','document_id','instrument_id','provision_identity_id','provision_version_id','document_number','document_title','article_number','clause_number','point_number','source_url','breadcrumb','text','source_text','valid_from','valid_to','authority_rank','binding','temporal_verified','provision_temporal_verified','provenance','provenance_span','kind','level','issuer','official_source','source_catalog_status'}
    data={k:unit.get(k) for k in keys}; data.update(score=float(score),retrieval_method=method,rank=rank,component_scores=components or {})
    data['authority_rank']=int(data.get('authority_rank') or 0)
    for key in ('binding','temporal_verified','provision_temporal_verified'): data[key]=bool(data.get(key))
    for key in ('source_url','valid_from','valid_to'): data[key]=data.get(key) or None
    data['provenance']=data.get('provenance') or {}
    return Evidence.model_validate(data)

class Retriever:
    def __init__(self,store:ArtifactStore,cfg:OnlineConfig):
        self.store=store; self.cfg=cfg; self._bm25=None; self._faiss=None; self._model=None; self._lock=threading.Lock()
    def exact(self,refs:list[ExplicitReference])->list[Evidence]:
        result=[]
        for ref in refs:
            candidates=[]
            desired_level='POINT' if ref.point else 'CLAUSE' if ref.clause else 'ARTICLE' if ref.article else None
            for u in self.store.units:
                number=u.get('instrument_number') or u.get('document_number')
                if ref.instrument_number and _norm(number)!=_norm(ref.instrument_number): continue
                if ref.article and _norm(u.get('article_number'))!=_norm(ref.article): continue
                if ref.clause and _norm(u.get('clause_number'))!=_norm(ref.clause): continue
                if ref.point and _norm(u.get('point_number'))!=_norm(ref.point): continue
                if desired_level and u.get('level')!=desired_level: continue
                candidates.append(u)
            candidates.sort(key=lambda u:(-int(u.get('authority_rank') or 0),u['unit_id']))
            result.extend(as_evidence(u,1.0,'exact',len(result)+1,{'exact':1.0}) for u in candidates[:5])
        return list({e.unit_id:e for e in result}.values())
    def hierarchy_descendants(self,seeds:list[Evidence],limit:int)->list[Evidence]:
        """Return the legal children of an exact Article/Clause in source order.

        Legal parsing stores an Article's introductory text separately from its
        Clause/Point children.  An exact lookup therefore has to follow incoming
        ``PART_OF`` edges or it can return a sentence ending in a colon while
        silently omitting the actual enumerated rule.  This traversal is kept
        deterministic and bounded; it does not open the broader adaptive graph.
        """
        if limit<=0 or not seeds: return []
        children=defaultdict(list)
        for edge in self.store.edges:
            if edge.get('type')!='PART_OF': continue
            child=edge.get('source'); parent=edge.get('target')
            if child in self.store.units_by_id and parent in self.store.units_by_id:
                children[parent].append((edge,child))
        def source_order(row):
            edge,uid=row; unit=self.store.units_by_id[uid]; span=unit.get('provenance_span') or {}
            position=span.get('document_char_start')
            if position is None: position=span.get('char_start')
            if position is None: position=10**18
            return (position,uid,edge.get('id') or '')
        for values in children.values(): values.sort(key=source_order)
        out=[]; seen={item.unit_id for item in seeds}
        def visit(parent_id:str,path:list[str],depth:int):
            for edge,uid in children.get(parent_id,[]):
                if len(out)>=limit: return
                if uid in seen: continue
                seen.add(uid); edge_id=edge.get('id') or ''
                evidence=as_evidence(self.store.units_by_id[uid],max(.8,.95-depth*.04-len(out)*.001),
                  'exact_hierarchy',len(out)+1,{'exact_hierarchy':1/(depth+1)})
                evidence=evidence.model_copy(update={'graph_path':path+[edge_id],
                  'graph_relations':['PART_OF']*(depth+1),'graph_directions':['IN']*(depth+1)})
                out.append(evidence); visit(uid,path+[edge_id],depth+1)
                if len(out)>=limit: return
        for seed in seeds:
            visit(seed.unit_id,list(seed.graph_path),0)
            if len(out)>=limit: break
        return out
    def bm25(self,query:str,k:int|None=None)->list[Evidence]:
        import bm25s
        if self._bm25 is None: self._bm25=self.store.load_bm25()
        tokens=bm25s.tokenize([query.lower()],stopwords=None,stemmer=None)
        docs,scores=self._bm25.retrieve(tokens,k=min(k or self.cfg.retrieval.bm25_top_k,len(self.store.units)))
        out=[]
        for i,(doc,score) in enumerate(zip(docs[0],scores[0]),1):
            uid=doc.get('id') if isinstance(doc,dict) else str(doc)
            if uid in self.store.units_by_id: out.append(as_evidence(self.store.units_by_id[uid],float(score),'bm25',i,{'bm25':float(score)}))
        return out
    def dense(self,query:str,k:int|None=None)->list[Evidence]:
        try:
            import numpy as np,faiss
            if self._faiss is None: self._faiss=self.store.load_faiss()
            if self._model is None:
                with self._lock:
                    if self._model is None:
                        from FlagEmbedding import BGEM3FlagModel
                        configured_path=self.cfg.embedding_model_path
                        model=str(Path(configured_path).expanduser()) if configured_path and Path(configured_path).expanduser().exists() else self.cfg.embedding_model
                        import torch
                        device=self.cfg.embedding_device
                        if device=='auto': device='cuda:0' if torch.cuda.is_available() else 'cpu'
                        self._model=BGEM3FlagModel(model,use_fp16=self.cfg.embedding_use_fp16 and device!='cpu',devices=device)
            vector=np.asarray(self._model.encode([query],batch_size=1,max_length=1024,return_dense=True,return_sparse=False,return_colbert_vecs=False)['dense_vecs'],dtype='float32')
            faiss.normalize_L2(vector); scores,positions=self._faiss.search(vector,min(k or self.cfg.retrieval.dense_top_k,len(self.store.units)))
            return [as_evidence(self.store.units[int(pos)],float(score),'dense',i,{'dense':float(score)}) for i,(pos,score) in enumerate(zip(positions[0],scores[0]),1) if pos>=0]
        except IndexUnavailable:
            raise
        except Exception as exc:
            raise IndexUnavailable(f'Dense retrieval unavailable: {type(exc).__name__}') from exc
    def issue_anchor(self,issues:list[str],k:int|None=None)->list[Evidence]:
        issue_keys={'TERMINATION':'Termination','CONTRACT':'LaborContract','WAGE':'Wage','LEAVE':'WorkingTime',
          'SOCIAL_INSURANCE':'SocialInsurance','SAFETY':'OccupationalSafety','DISPUTE':'DisputeResolution',
          'DISCIPLINE':'Discipline','MATERNITY':'FemaleWorker','WORKING_TIME':'WorkingTime','UNION':'TradeUnion',
          'FOREIGN_WORKER':'ForeignWorker','UNEMPLOYMENT_INSURANCE':'UnemploymentInsurance'}
        wanted={issue_keys[x] for x in issues if x in issue_keys}
        if not wanted: return []
        anchors={n['id'] for n in self.store.nodes if n.get('label')=='LegalIssue' and (n.get('properties') or {}).get('issue_key') in wanted}
        unit_ids=[]
        for edge in self.store.edges:
            if edge.get('type')!='RELATES_TO_ISSUE': continue
            if edge.get('source') in anchors and edge.get('target') in self.store.units_by_id: unit_ids.append(edge['target'])
            elif edge.get('target') in anchors and edge.get('source') in self.store.units_by_id: unit_ids.append(edge['source'])
        unique=list(dict.fromkeys(unit_ids))
        unique.sort(key=lambda uid:(-int(self.store.units_by_id[uid].get('authority_rank') or 0),uid))
        limit=k or self.cfg.retrieval.issue_anchor_top_k
        return [as_evidence(self.store.units_by_id[uid],.5,'issue',i,{'issue':.5}) for i,uid in enumerate(unique[:limit],1)]
    def policy_anchor(self,issues:list[str],facts:dict)->list[Evidence]:
        """Deterministic anchors for mandatory rule chains identified at intake.

        Semantic retrieval is still used, but it must not omit the governing
        employee-termination rule or its statutory consequences merely because
        employer-side provisions share more words with the query.
        """
        if 'TERMINATION' not in issues or facts.get('actor')!='EMPLOYEE': return []
        allowed_documents={'45/2019/QH14','18/VBHN-VPQH'}
        matched=[]
        for unit in self.store.units:
            if unit.get('kind')!='PROVISION' or unit.get('document_number') not in allowed_documents: continue
            article=str(unit.get('article_number') or ''); clause=str(unit.get('clause_number') or ''); point=str(unit.get('point_number') or '').lower()
            text=' '.join(' '.join(str(unit.get(field) or '').split()) for field in ('breadcrumb','text','source_text')).lower()
            required=False
            if facts.get('contract_type')=='INDEFINITE' and article=='35' and clause=='1' and point=='a':
                required='45 ngày' in text and 'không xác định thời hạn' in text
            elif article=='35' and clause=='2' and not point:
                required='không cần báo trước' in text
            elif article=='39' and not clause:
                required='trái pháp luật' in text and 'điều 35' in text
            elif article=='40' and clause in {'1','2','3'}:
                required=any(term in text for term in ('không được trợ cấp thôi việc','nửa tháng tiền lương','chi phí đào tạo'))
            if required: matched.append(unit)
        # Prefer the clean consolidated text for each structural location, while
        # retaining the original act as a fallback when no consolidated unit exists.
        by_location={}
        for unit in sorted(matched,key=lambda value:(value.get('document_number')!='18/VBHN-VPQH',-int(value.get('authority_rank') or 0),value['unit_id'])):
            location=(unit.get('article_number'),unit.get('clause_number'),unit.get('point_number'))
            by_location.setdefault(location,unit)
        return [as_evidence(unit,1.0-index*.01,'policy',index,{'policy':1.0})
          for index,unit in enumerate(by_location.values(),1)]
    def case_law(self,query:str,k:int|None=None)->list[Evidence]:
        """Dedicated judicial channel so case questions do not depend on a global top-k."""
        terms={term for term in re.findall(r'\w+',query.lower()) if len(term)>2}
        scored=[]
        for unit in self.store.units:
            if unit.get('kind')!='CASE': continue
            text=' '.join(str(unit.get(field) or '') for field in ('document_number','document_title','breadcrumb','text','source_text')).lower()
            tokens=set(re.findall(r'\w+',text)); overlap=len(terms&tokens)/max(1,len(terms))
            identifier_bonus=.5 if unit.get('document_number') and _norm(unit['document_number']) in _norm(query) else 0
            scored.append((overlap+identifier_bonus,unit['unit_id'],unit))
        scored.sort(key=lambda row:(-row[0],row[1]))
        limit=k or self.cfg.retrieval.case_law_top_k
        return [as_evidence(unit,score,'case_law',rank,{'case_law':score})
          for rank,(score,_,unit) in enumerate(scored[:limit],1) if score>0]
    def fusion(self,lists:list[list[Evidence]])->list[Evidence]:
        scores=defaultdict(float); by_id={}; components=defaultdict(dict); rrf=self.cfg.retrieval.rrf_k
        for values in lists:
            for rank,item in enumerate(values,1):
                scores[item.unit_id]+=1/(rrf+rank); by_id[item.unit_id]=item
                components[item.unit_id][item.retrieval_method]=item.score
        ordered=sorted(scores,key=lambda uid:(-scores[uid],uid))[:self.cfg.retrieval.fusion_top_k]
        return [by_id[uid].model_copy(update={'score':scores[uid],'rank':i,'retrieval_method':'hybrid','component_scores':components[uid]}) for i,uid in enumerate(ordered,1)]

def temporal_filter(items:list[Evidence],query_date:str|None,strict:bool=True,query_date_end:str|None=None)->tuple[list[Evidence],list[str]]:
    if not query_date: return items,[]
    range_start=date.fromisoformat(query_date); range_end=date.fromisoformat(query_date_end or query_date); out=[]; removed=[]
    if range_end<range_start: raise ValueError('query_date_end must not precede query_date')
    for e in items:
        if e.provision_version_id and not e.provision_temporal_verified:
            # Strict mode requires provision-level human review. Provisional mode may
            # fall back only to a verified document-level interval.
            if strict or not e.temporal_verified: removed.append(e.unit_id); continue
        try:
            start=date.fromisoformat(e.valid_from) if e.valid_from else None; end=date.fromisoformat(e.valid_to) if e.valid_to else None
        except ValueError: removed.append(e.unit_id); continue
        # Legal intervals are [valid_from, valid_to). A month/year-only query is
        # treated as an interval so a version beginning during that period is not
        # silently discarded as if the event occurred on its first day.
        if not start or start>range_end or end and end<=range_start: removed.append(e.unit_id); continue
        warnings=list(e.audit_warnings)
        if range_start!=range_end and (start>range_start or end and end<=range_end):
            warnings.append('IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY')
        out.append(e.model_copy(update={'audit_warnings':list(dict.fromkeys(warnings))}))
    return out,removed
def authority_score(item:Evidence)->float:
    rank=max(0,min(100,item.authority_rank))/100
    source_type={"PROVISION":1.0,"CASE":.65,"DIAGNOSTIC":.25}.get(str(item.kind or '').upper(),.4)
    catalog_verified=float(item.source_catalog_status=='VERIFIED')
    return .4*rank+.18*float(item.binding)+.12*source_type+.1*float(bool(item.source_url))+.1*float(item.official_source)+.1*catalog_verified
def authority_filter(items:list[Evidence],strict:bool=False)->tuple[list[Evidence],list[str]]:
    """Remove candidates without traceable legal authority before graph expansion."""
    accepted=[]; removed=[]
    for item in items:
        traceable=bool(item.source_url and item.authority_rank>0 and item.document_id)
        reviewed=bool(item.official_source and item.source_catalog_status=='VERIFIED')
        if not traceable or strict and not reviewed:
            removed.append(item.unit_id); continue
        accepted.append(item.model_copy(update={'authority_verified':reviewed}))
    return accepted,removed
def rerank(items:list[Evidence],cfg:OnlineConfig|None=None)->list[Evidence]:
    if not items: return []
    weights=cfg.retrieval if cfg else None; maximum=max(abs(e.score) for e in items) or 1
    values=[]
    for e in items:
        auth=authority_score(e); relevance=e.score/maximum; temporal=float(e.provision_temporal_verified or e.temporal_verified)
        score=(weights.relevance_weight if weights else .75)*relevance+(weights.authority_weight if weights else .2)*auth+(weights.temporal_weight if weights else .05)*temporal
        values.append(e.model_copy(update={'score':score,'component_scores':{**e.component_scores,'normalized_relevance':relevance,'authority':auth,'temporal':temporal}}))
    return [e.model_copy(update={'rank':i}) for i,e in enumerate(sorted(values,key=lambda x:(-x.score,x.unit_id)),1)]
