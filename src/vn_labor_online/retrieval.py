from __future__ import annotations
import re,threading,unicodedata
from functools import wraps
from copy import deepcopy
from pathlib import Path
from collections import defaultdict
from datetime import date
from .artifact_store import ArtifactStore
from .config import OnlineConfig
from .errors import IndexUnavailable
from .taxonomy import locator_matches
from .issue_mapping import graph_issue_keys
from .legal_metadata import document_type
from .models import Evidence,ExplicitReference
from .runtime import measured

def _norm(value): return re.sub(r'[^0-9A-Z]','',str(value or '').upper().replace('Đ','D'))
def _terms(value):
    normalized=unicodedata.normalize('NFD',str(value).lower()).replace('đ','d')
    folded=''.join(char for char in normalized if unicodedata.category(char)!='Mn')
    return {term for term in re.findall(r'\w+',folded) if len(term)>2}


def request_cached_retrieval(fn):
    """Reuse raw channel results within one budget; never cache legal verdicts.

    ArtifactStore and configuration are immutable during an inference request.
    Collection identity/length also protects the append-only test-store contract.
    No cache is used by retrieval benchmarks outside request_budget().
    """
    @wraps(fn)
    def wrapped(self,query,k=None):
        from .runtime import _current
        budget=_current.get()
        if budget is None or not self.cfg.retrieval.request_cache_enabled:
            return fn(self,query,k)
        budget.remaining()
        collections_key=tuple((id(value),len(value)) for value in (
            self.store.units,getattr(self.store,'nodes',()),getattr(self.store,'edges',())))
        effective_k=k or getattr(self.cfg.retrieval,fn.__name__+'_top_k')
        key=(id(self),fn.__name__,query,effective_k,collections_key)
        if key in budget.retrieval_cache:
            budget.retrieval_cache_hits+=1
            return deepcopy(budget.retrieval_cache[key])
        result=fn(self,query,k)
        budget.remaining()
        budget.retrieval_cache_misses+=1
        if len(result)<=64:
            if len(budget.retrieval_cache)>=16:
                budget.retrieval_cache.pop(next(iter(budget.retrieval_cache)))
            budget.retrieval_cache[key]=deepcopy(result)
        return result
    return wrapped
def as_evidence(unit:dict,score:float,method:str,rank:int,components=None)->Evidence:
    keys={'ancestor_context','unit_id','document_id','instrument_id','provision_identity_id','provision_version_id','document_number','document_title','article_number','clause_number','point_number','source_url','breadcrumb','text','source_text','valid_from','valid_to','authority_rank','binding','temporal_verified','provision_temporal_verified','provenance','provenance_span','kind','level','issuer','official_source','source_catalog_status'}
    data={k:unit.get(k) for k in keys}; data.update(score=float(score),retrieval_method=method,rank=rank,component_scores=components or {})
    data['ancestor_context']=str(data.get('ancestor_context') or '')
    data['authority_rank']=int(data.get('authority_rank') or 0)
    for key in ('binding','temporal_verified','provision_temporal_verified','official_source'): data[key]=bool(data.get(key))
    for key in ('source_url','valid_from','valid_to'): data[key]=data.get(key) or None
    data['provenance']=data.get('provenance') or {}
    data['provenance_span']=data.get('provenance_span') or {}
    data['document_type']=document_type(data.get('document_number'),data.get('document_title'),unit.get('document_type'))
    return Evidence.model_validate(data)

class Retriever:
    def __init__(self,store:ArtifactStore,cfg:OnlineConfig):
        self.store=store; self.cfg=cfg; self._bm25=None; self._faiss=None; self._model=None; self._reranker=None; self._lock=threading.Lock()
        self._profile_units=defaultdict(list); self._units_by_article=defaultdict(list)
        self._units_by_instrument=defaultdict(list); self._part_of_children=defaultdict(list)
        self._case_units=[]
        self._issue_nodes_by_key=defaultdict(set); self._issue_node_ids=set()
        self._issue_units_by_node=defaultdict(list)
        self._units_by_id=getattr(store,'units_by_id',None) or {}
        self._indexed_unit_count=0;self._indexed_node_count=0;self._indexed_edge_count=0
        self._refresh_indexes()

    def _refresh_indexes(self):
        new_units=self.store.units[self._indexed_unit_count:]
        for unit in new_units:
            self._profile_units[(unit.get('document_number'),str(unit.get('article_number') or ''))].append(unit)
            if unit.get('unit_id'):self._units_by_id[unit['unit_id']]=unit
            article=_norm(unit.get('article_number'))
            instrument=_norm(unit.get('instrument_number') or unit.get('document_number'))
            if article:self._units_by_article[article].append(unit)
            if instrument:self._units_by_instrument[instrument].append(unit)
            if unit.get('kind')=='CASE':self._case_units.append(unit)
        self._indexed_unit_count=len(self.store.units)
        new_nodes=getattr(self.store,'nodes',[])[self._indexed_node_count:]
        for node in new_nodes:
            if node.get('label')=='LegalIssue':
                key=(node.get('properties') or {}).get('issue_key')
                if key:
                    self._issue_nodes_by_key[key].add(node['id'])
                    self._issue_node_ids.add(node['id'])
        self._indexed_node_count=len(getattr(self.store,'nodes',[]))
        new_edges=getattr(self.store,'edges',[])[self._indexed_edge_count:]
        touched_parents=set()
        for edge in new_edges:
            if (edge.get('type')=='PART_OF' and edge.get('source') in self._units_by_id
              and edge.get('target') in self._units_by_id):
                self._part_of_children[edge['target']].append((edge,edge['source']))
                touched_parents.add(edge['target'])
            if edge.get('type')=='RELATES_TO_ISSUE':
                source=edge.get('source');target=edge.get('target')
                if source in self._issue_node_ids and target in self._units_by_id:
                    self._issue_units_by_node[source].append(target)
                elif target in self._issue_node_ids and source in self._units_by_id:
                    self._issue_units_by_node[target].append(source)
        self._indexed_edge_count=len(getattr(self.store,'edges',[]))
        for parent in touched_parents:
            self._part_of_children[parent].sort(key=self._child_source_order)

    def _child_source_order(self,row):
        edge,unit_id=row; unit=self._units_by_id[unit_id]
        span=unit.get('provenance_span') or {}
        position=span.get('document_char_start')
        if position is None:position=span.get('char_start')
        if position is None:position=10**18
        return position,unit_id,edge.get('id') or ''
    def exception_context(self,items:list[Evidence],limit:int)->tuple[list[Evidence],dict]:
        """Append explicitly referenced exception units before audit, not to RRF.

        Same document edition and article only; dates/authority/provenance and
        applicability still require their normal checks. This is not a sweep
        over all sibling provisions or unrestricted NEXT edges.
        """
        from .exception_references import exception_locators
        seen={x.unit_id for x in items};added=[];references=0
        for seed in items:
            if not seed.document_id: continue
            for locator in exception_locators(seed):
                references+=1
                if len(added)>=limit: continue
                candidates=self._profile_units.get((seed.document_number,str(seed.article_number)),[])
                for unit in candidates:
                    if len(added)>=limit: break
                    if unit.get('document_id')!=seed.document_id or unit.get('kind')!='PROVISION': continue
                    if str(unit.get('clause_number') or '')!=locator.clause: continue
                    uid=unit['unit_id']
                    if uid in seen: continue
                    seen.add(uid)
                    added.append(as_evidence(unit,seed.score*.95,'exception_context',len(items)+len(added)+1,
                      {'exception_context':1.0}))
        return added,{'explicit_exception_references':references,'added':len(added),'limit':limit}

    def exact(self,refs:list[ExplicitReference])->list[Evidence]:
        self._refresh_indexes()
        result=[]
        for ref in refs:
            candidates=[]
            desired_level='POINT' if ref.point else 'CLAUSE' if ref.clause else 'ARTICLE' if ref.article else None
            if ref.instrument_number:
                units=self._units_by_instrument.get(_norm(ref.instrument_number),[])
            elif ref.article:
                units=self._units_by_article.get(_norm(ref.article),[])
            else:
                units=self.store.units
            for u in units:
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
        self._refresh_indexes()
        out=[]; seen={item.unit_id for item in seeds}
        def visit(parent_id:str,path:list[str],depth:int):
            for edge,uid in self._part_of_children.get(parent_id,[]):
                if len(out)>=limit: return
                if uid in seen: continue
                seen.add(uid); edge_id=edge.get('id') or ''
                evidence=as_evidence(self._units_by_id[uid],max(.8,.95-depth*.04-len(out)*.001),
                  'exact_hierarchy',len(out)+1,{'exact_hierarchy':1/(depth+1)})
                evidence=evidence.model_copy(update={'graph_path':path+[edge_id],
                  'graph_relations':['PART_OF']*(depth+1),'graph_directions':['IN']*(depth+1)})
                out.append(evidence); visit(uid,path+[edge_id],depth+1)
                if len(out)>=limit: return
        for seed in seeds:
            visit(seed.unit_id,list(seed.graph_path),0)
            if len(out)>=limit: break
        return out
    @request_cached_retrieval
    def bm25(self,query:str,k:int|None=None)->list[Evidence]:
        with measured('bm25.dependencies_import'):
            import bm25s
        if self._bm25 is None:
            with measured('bm25.index_load'): self._bm25=self.store.load_bm25()
        with measured('bm25.tokenize'):
            tokens=bm25s.tokenize([query.lower()],stopwords=None,stemmer=None)
        with measured('bm25.search'):
            docs,scores=self._bm25.retrieve(tokens,k=min(k or self.cfg.retrieval.bm25_top_k,len(self.store.units)))
        out=[]
        for i,(doc,score) in enumerate(zip(docs[0],scores[0]),1):
            uid=doc.get('id') if isinstance(doc,dict) else str(doc)
            if uid in self.store.units_by_id: out.append(as_evidence(self.store.units_by_id[uid],float(score),'bm25',i,{'bm25':float(score)}))
        return out
    @request_cached_retrieval
    def dense(self,query:str,k:int|None=None)->list[Evidence]:
        try:
            with measured('dense.dependencies_import'):
                import numpy as np,faiss
            if self._faiss is None:
                with measured('dense.index_load'): self._faiss=self.store.load_faiss()
            if self._model is None:
                with self._lock:
                    if self._model is None:
                        with measured('dense.model_init'):
                            from FlagEmbedding import BGEM3FlagModel
                            configured_path=self.cfg.embedding_model_path
                            model=str(Path(configured_path).expanduser()) if configured_path and Path(configured_path).expanduser().exists() else self.cfg.embedding_model
                            import torch
                            device=self.cfg.embedding_device
                            if device=='auto': device='cuda:0' if torch.cuda.is_available() else 'cpu'
                            self._model=BGEM3FlagModel(model,use_fp16=self.cfg.embedding_use_fp16 and device!='cpu',devices=device)
            with measured('dense.encode'):
                vector=np.asarray(self._model.encode([query],batch_size=1,max_length=1024,return_dense=True,return_sparse=False,return_colbert_vecs=False)['dense_vecs'],dtype='float32')
            with measured('dense.search'):
                faiss.normalize_L2(vector); scores,positions=self._faiss.search(vector,min(k or self.cfg.retrieval.dense_top_k,len(self.store.units)))
            return [as_evidence(self.store.units[int(pos)],float(score),'dense',i,{'dense':float(score)}) for i,(pos,score) in enumerate(zip(positions[0],scores[0]),1) if pos>=0]
        except IndexUnavailable:
            raise
        except Exception as exc:
            raise IndexUnavailable(f'Dense retrieval unavailable: {type(exc).__name__}') from exc
    def neural_rerank(self,items:list[Evidence],query:str)->list[Evidence]:
        settings=self.cfg.reranker
        if not settings.enabled or not items: return items
        candidates=items[:settings.top_n]
        try:
            if self._reranker is None:
                with self._lock:
                    if self._reranker is None:
                        with measured('reranker.model_init'):
                            from FlagEmbedding import FlagReranker
                            import torch
                            configured=settings.model_path
                            model=str(Path(configured).expanduser()) if configured and Path(configured).expanduser().exists() else settings.model
                            device=settings.device
                            if device=='auto': device='cuda:0' if torch.cuda.is_available() else 'cpu'
                            self._reranker=FlagReranker(model,use_fp16=settings.use_fp16 and device!='cpu',devices=device)
            pairs=[[query,item.source_text or item.text] for item in candidates]
            with measured('reranker.score'):
                raw=self._reranker.compute_score(pairs,normalize=True)
            scores=[float(raw)] if len(candidates)==1 and isinstance(raw,(int,float)) else [float(x) for x in raw]
            if len(scores)!=len(candidates): raise ValueError('reranker score count mismatch')
            rescored=[item.model_copy(update={'score':score,'component_scores':{**item.component_scores,'cross_encoder':score}})
              for item,score in zip(candidates,scores)]
            return sorted(rescored,key=lambda x:(-x.score,x.unit_id))+items[len(candidates):]
        except Exception as exc:
            raise IndexUnavailable(f'Neural reranker unavailable: {type(exc).__name__}') from exc

    def issue_anchor(self,issues:list[str],k:int|None=None)->list[Evidence]:
        wanted=graph_issue_keys(issues)
        if not wanted: return []
        self._refresh_indexes()
        anchors=set().union(*(self._issue_nodes_by_key.get(key,set()) for key in wanted))
        unit_ids=[unit_id for anchor in anchors for unit_id in self._issue_units_by_node.get(anchor,[])]
        unique=list(dict.fromkeys(unit_ids))
        unique.sort(key=lambda uid:(-int(self.store.units_by_id[uid].get('authority_rank') or 0),uid))
        limit=k or self.cfg.retrieval.issue_anchor_top_k
        return [as_evidence(self.store.units_by_id[uid],.5,'issue',i,{'issue':.5}) for i,uid in enumerate(unique[:limit],1)]
    def policy_anchor(self,issues:list[str],facts:dict,plan=None)->list[Evidence]:
        """Deterministic anchors for mandatory rule chains identified at intake.

        Semantic retrieval is still used, but it must not omit the governing
        employee-termination rule or its statutory consequences merely because
        employer-side provisions share more words with the query.
        """
        allowed_documents={'45/2019/QH14','18/VBHN-VPQH','145/2020/NĐ-CP'}
        intent=facts.get('query_intent'); basis=facts.get('termination_basis'); locations=set()
        if 'TERMINATION' in issues and (facts.get('actor')=='EMPLOYEE' or intent in {'WITHDRAW_TERMINATION','UNLAWFUL_DEFINITION_CONSEQUENCES','MUTUAL_TERMINATION'}):
            if basis=='LATE_WAGE': locations|={('35','2','b'),('97','4','')}
            elif basis=='EMPLOYER_MISINFORMATION': locations|={('35','2','g'),('16','1','')}
            elif basis=='SEXUAL_HARASSMENT': locations.add(('35','2','d'))
            if intent=='WITHDRAW_TERMINATION': locations.add(('38','',''))
            if intent=='UNLAWFUL_DEFINITION_CONSEQUENCES': locations|={('39','',''),('40','1',''),('40','2',''),('40','3','')}
            if intent=='MUTUAL_TERMINATION': locations.add(('34','3',''))
            if not basis and intent not in {'WITHDRAW_TERMINATION','UNLAWFUL_DEFINITION_CONSEQUENCES','MUTUAL_TERMINATION'}:
                if facts.get('contract_type')=='INDEFINITE': locations.add(('35','1','a'))
                if facts.get('special_occupation') is True:
                    locations|={('35','1','d'),('7','2','a')}
                threshold=120 if facts.get('special_occupation') is True else 45
                if facts.get('notice_exception') is False and isinstance(facts.get('notice_days'),int) and facts['notice_days']<threshold:
                    locations|={('39','',''),('40','1',''),('40','2',''),('40','3','')}
        if 'LEAVE' in issues:
            if intent=='TRAVEL_TIME': locations.add(('113','6',''))
            elif intent in {'ANNUAL_LEAVE_CALC','ANNUAL_LEAVE_OVERVIEW'}:
                category=facts.get('work_category')
                if intent=='ANNUAL_LEAVE_OVERVIEW': locations|={('113','1','a'),('113','1','b'),('113','1','c')}
                elif category=='SPECIAL_HEAVY': locations.add(('113','1','c'))
                elif category=='NORMAL' and not facts.get('minor') and not facts.get('disabled'): locations.add(('113','1','a'))
                else: locations.add(('113','1','b'))
                if int(facts.get('service_years') or 0)>=5: locations.add(('114','',''))
                if isinstance(facts.get('worked_months'),int) and facts['worked_months']<12:
                    locations|={('113','2',''),('66','1','')}
        if plan is not None and plan.slot_requirements:
            # Structured profiles carry code-family/date-aware locators. Do not
            # mix legacy 2019 anchors into a historical or alternate mechanism.
            return self.profile_anchors(plan)
        if not locations: return []
        matched=[]
        self._refresh_indexes()
        for article,clause,point in locations:
            for document in allowed_documents:
                for unit in self._profile_units.get((document,article),[]):
                    if unit.get('kind')!='PROVISION':continue
                    if str(unit.get('clause_number') or '')!=clause or str(unit.get('point_number') or '').lower()!=point:continue
                    # Article 66 is the implementing rule only in Decree 145;
                    # Article 7 belongs there while other anchors use the Code.
                    if article in {'66','7'} and document!='145/2020/NĐ-CP':continue
                    if article not in {'66','7'} and document=='145/2020/NĐ-CP':continue
                    matched.append(unit)
        # Prefer the clean consolidated text for each structural location, while
        # retaining the original act as a fallback when no consolidated unit exists.
        by_location={}
        for unit in sorted(matched,key=lambda value:(value.get('document_number')!='18/VBHN-VPQH',-int(value.get('authority_rank') or 0),value['unit_id'])):
            location=(unit.get('article_number'),unit.get('clause_number'),unit.get('point_number'))
            by_location.setdefault(location,unit)
        return [as_evidence(unit,1.0-index*.01,'policy',index,{'policy':1.0})
          for index,unit in enumerate(by_location.values(),1)]
    def profile_anchors(self,plan)->list[Evidence]:
        self._refresh_indexes()
        chosen={}
        for groups in plan.slot_requirements.values():
            for alternatives in groups:
                pool={unit['unit_id']:unit for locator in alternatives for doc in locator.documents
                  for unit in self._profile_units.get((doc,locator.article),[])}
                matches=[unit for unit in pool.values() if any(locator_matches(unit,locator) for locator in alternatives)]
                # Keep versions from each instrument; temporal filtering chooses
                # the applicable one later. Prefer exact locator granularity.
                matches.sort(key=lambda unit:(sum(bool(unit.get(field)) for field in ('clause_number','point_number')),
                  -int(unit.get('authority_rank') or 0),unit['unit_id']))
                counts={}
                for unit in matches:
                    # Prefer the requested article/clause container, retaining
                    # each instrument/version without flooding the seed list.
                    key=(unit.get('document_number'),unit.get('valid_from') or unit.get('effective_from'),unit.get('valid_to') or unit.get('effective_to'))
                    if key in counts: continue
                    counts[key]=True; chosen.setdefault(unit['unit_id'],unit)
        # One seed per structural location first, then the alternate documents.
        ordered=sorted(chosen.values(),key=lambda unit:(unit.get('document_number')!='18/VBHN-VPQH',
          int(unit.get('article_number')) if str(unit.get('article_number')).isdigit() else 1000,
          str(unit.get('clause_number') or ''),str(unit.get('point_number') or ''),unit['unit_id']))
        return [as_evidence(unit,1.0,'policy',index,{'policy':1.0}) for index,unit in enumerate(ordered,1)]

    def resolve_article_plan(self,plan,query_date=None,query_date_end=None):
        from .article_content import resolve_article_requirements
        return resolve_article_requirements(plan,self._profile_units,query_date,query_date_end)

    def case_law(self,query:str,k:int|None=None)->list[Evidence]:
        """Dedicated judicial channel so case questions do not depend on a global top-k."""
        self._refresh_indexes()
        terms={term for term in re.findall(r'\w+',query.lower()) if len(term)>2}
        scored=[]
        for unit in self._case_units:
            text=' '.join(str(unit.get(field) or '') for field in ('document_number','document_title','breadcrumb','text','source_text')).lower()
            tokens=set(re.findall(r'\w+',text)); overlap=len(terms&tokens)/max(1,len(terms))
            identifier_bonus=.5 if unit.get('document_number') and _norm(unit['document_number']) in _norm(query) else 0
            scored.append((overlap+identifier_bonus,unit['unit_id'],unit))
        scored.sort(key=lambda row:(-row[0],row[1]))
        limit=k or self.cfg.retrieval.case_law_top_k
        return [as_evidence(unit,score,'case_law',rank,{'case_law':score})
          for rank,(score,_,unit) in enumerate(scored[:limit],1) if score>0]
    def community_cases(self,query:str)->list[Evidence]:
        """Rank OFFLINE communities, then return their original CASE units."""
        query_terms=_terms(query)
        if not query_terms: return []
        communities={node['id']:node for node in self.store.nodes if node.get('label')=='Community'}
        memberships=defaultdict(list)
        for edge in self.store.edges:
            if edge.get('type')!='BELONGS_TO' or edge.get('target') not in communities: continue
            unit=self.store.units_by_id.get(edge.get('source'))
            if unit and unit.get('kind')=='CASE': memberships[edge['target']].append((edge,edge['source']))
        ranked=[]
        for community_id,node in communities.items():
            properties=node.get('properties') or {}; members=memberships.get(community_id,[])
            member_text=' '.join(' '.join(str(self.store.units_by_id[uid].get(field) or '') for field in ('document_title','breadcrumb','text','source_text')) for _,uid in members)
            community_text=' '.join(str(properties.get(field) or '') for field in ('summary','keywords'))+' '+member_text
            overlap=len(query_terms&_terms(community_text))/max(1,len(query_terms))
            if overlap>0: ranked.append((overlap,community_id,members))
        ranked.sort(key=lambda row:(-row[0],row[1])); ranked=ranked[:self.cfg.retrieval.community_top_k]
        cases=[]
        for community_score,community_id,members in ranked:
            for edge,uid in members:
                unit=self.store.units_by_id[uid]
                case_terms=_terms(' '.join(str(unit.get(field) or '') for field in ('document_number','document_title','breadcrumb','text','source_text')))
                direct=len(query_terms&case_terms)/max(1,len(query_terms)); score=.65*community_score+.35*direct
                evidence=as_evidence(unit,score,'community_case',0,{'community':community_score,'community_case':direct})
                cases.append(evidence.model_copy(update={'graph_path':[edge.get('id') or ''],
                  'graph_relations':['BELONGS_TO'],'graph_directions':['IN']}))
        best={}
        for item in cases:
            if item.unit_id not in best or item.score>best[item.unit_id].score: best[item.unit_id]=item
        ordered=sorted(best.values(),key=lambda item:(-item.score,item.unit_id))[:self.cfg.retrieval.community_case_top_k]
        return [item.model_copy(update={'rank':rank}) for rank,item in enumerate(ordered,1)]
    def fusion(self,lists:list[list[Evidence]])->list[Evidence]:
        scores=defaultdict(float); by_id={}; components=defaultdict(dict); rrf=self.cfg.retrieval.rrf_k
        for values in lists:
            for rank,item in enumerate(values,1):
                scores[item.unit_id]+=1/(rrf+rank); by_id[item.unit_id]=item
                components[item.unit_id][item.retrieval_method]=item.score
        ordered=sorted(scores,key=lambda uid:(-scores[uid],uid))[:self.cfg.retrieval.fusion_top_k]
        return [by_id[uid].model_copy(update={'score':scores[uid],'rank':i,'retrieval_method':'hybrid','component_scores':components[uid]}) for i,uid in enumerate(ordered,1)]

def retain_required_anchors(items,anchors,plan,limit):
    """Reserve recall for required groups within the existing candidate budget.

    Anchors must pass the same date/authority filters as semantic candidates
    before this function. A protected source is still unverified until audited.
    """
    groups=[group for slot,values in plan.slot_requirements.items() if slot in plan.mandatory_slots for group in values]
    existing={item.unit_id:item for item in items}; chosen={}
    for group in groups:
        if any(any(locator_matches(item,loc) for loc in group) for item in chosen.values()): continue
        candidates=[item for item in anchors if any(locator_matches(item,loc) for loc in group)]
        if not candidates or len(chosen)>=limit: continue
        anchor=candidates[0]; item=existing.get(anchor.unit_id,anchor)
        chosen[item.unit_id]=item.model_copy(update={'component_scores':{**item.component_scores,'policy':1.0}})
    protected=list(chosen)
    for item in items:
        if len(chosen)>=limit: break
        chosen.setdefault(item.unit_id,item)
    result=list(chosen.values())
    missing=[i for i,group in enumerate(groups) if not any(any(locator_matches(item,loc) for loc in group) for item in result)]
    return result,{'required_groups':len(groups),'protected_ids':protected,
        'restored_ids':[uid for uid in protected if uid not in existing],
        'unrepresented_group_indexes':missing,'candidate_limit':limit}


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
