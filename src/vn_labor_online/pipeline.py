from __future__ import annotations
import hashlib,json,time
from datetime import date
from .analysis import intake,analyze,plan_evidence
from .applicability import LegalApplicabilityAuditor
from .artifact_store import ArtifactStore
from .audit import deterministic_audit,citations,reference_audit
from .config import OnlineConfig,AdjudicationConfig
from .evidence import state_for,build_verified_pack,detect_authoritative_conflicts,select_for_plan,extend_plan_for_evidence
from .generation import LegalAdjudicator
from .errors import IndexUnavailable
from .graph import GraphExplorer
from .models import QueryRequest,AnswerResponse,Trace,Stop,Route,SlotStatus,AdjudicationDraft
from .retrieval import Retriever,authority_filter,temporal_filter,rerank
from .researcher import LegalResearcher
from .trace import persist
from .taxonomy import TAXONOMY_VERSION

def _actionable_gaps(gaps,items,provisional):
    result=[]
    for gap in gaps:
        if provisional and gap=='applicable_version' and any(x.temporal_verified for x in items): continue
        if provisional and gap=='official_source' and any(x.source_url for x in items): continue
        result.append(gap)
    return result

def _repair_references(selected,claims):
    """Build one deterministic, reduced draft from claims already tied to verified IDs."""
    valid_ids={item.unit_id for item in selected if item.verified}
    repaired_claims=[claim for claim in claims if claim.evidence_ids and set(claim.evidence_ids)<=valid_ids]
    used_ids=list(dict.fromkeys(evidence_id for claim in repaired_claims for evidence_id in claim.evidence_ids))
    by_id={item.unit_id:item for item in selected}
    repaired_items=[by_id[evidence_id] for evidence_id in used_ids]
    lines=['Kết quả tra cứu dựa trên các căn cứ sau:']
    for claim in repaired_claims:
        markers=' '.join(f'[{evidence_id}]' for evidence_id in claim.evidence_ids)
        lines.append(f'- {claim.text} {markers}')
    return '\n'.join(lines),repaired_items,repaired_claims

class OnlinePipeline:
    def __init__(self,cfg:OnlineConfig):
        self.cfg=cfg; self.store=ArtifactStore(cfg); self.retriever=Retriever(self.store,cfg)
        self.graph=GraphExplorer(self.store,cfg.graph); self.researcher=LegalResearcher(cfg.researcher)
        self.applicability=LegalApplicabilityAuditor(cfg.applicability,self.store)
        self.adjudicator=LegalAdjudicator(cfg.adjudication)
    def close(self):
        for component in (self.researcher,self.applicability,self.adjudicator):
            if component.provider is not None: component.provider.close()

    def ask(self,request:QueryRequest)->AnswerResponse:
        start=time.perf_counter(); stage=time.perf_counter()
        env=intake(request.question,request.conversation_context,request.query_date,request.facts)
        analysis=analyze(env,request.query_date,request.facts)
        snapshot=self.cfg.corpus_snapshot_as_of
        defaulted_query_date=False
        if analysis.query_date is None and snapshot:
            default_date=min(snapshot,date.today().isoformat())
            analysis=analysis.model_copy(update={'query_date':default_date,'query_date_end':default_date,
              'query_date_precision':'DAY','temporal_intent':'CURRENT'})
            defaulted_query_date=True
        analysis_ms=round((time.perf_counter()-stage)*1000,2)
        researcher_started=time.perf_counter()
        researcher_path=self.researcher.execution_path(analysis)
        analysis,research_warnings=self.researcher.enrich(analysis,env.normalized_query,env.conversation_context)
        plan=plan_evidence(analysis)
        trace=Trace(trace_id='trace_'+hashlib.sha256((env.query_id+str(time.time_ns())).encode()).hexdigest()[:16],query_id=env.query_id,
          build_id=self.store.report.build_id or '',route=analysis.route,route_reason=analysis.route_reason,
          config_fingerprint=hashlib.sha256(json.dumps(self.cfg.model_dump(mode='json'),sort_keys=True).encode()).hexdigest())
        trace.timings_ms['analysis']=analysis_ms
        trace.timings_ms['researcher']=round((time.perf_counter()-researcher_started)*1000,2)
        warnings=list(research_warnings); assumptions=[]
        if self.cfg.provisional_mode: warnings+=['Dữ liệu chưa hoàn tất human legal review.']+self.store.report.provisional_reasons
        if defaulted_query_date:
            warnings.append('QUERY_DATE_DEFAULTED_TO_CORPUS_SNAPSHOT')
            assumptions.append(f'Không có ngày tra cứu; hệ thống dùng ngày chốt corpus {analysis.query_date}.')
        current_stale=analysis.temporal_intent=='CURRENT' and (not snapshot or snapshot<date.today().isoformat())
        requested_beyond_snapshot=bool(analysis.query_date and (not snapshot or analysis.query_date>snapshot))
        freshness_relevant=current_stale or requested_beyond_snapshot
        if freshness_relevant: warnings.append('CORPUS_MAY_BE_STALE')
        if analysis.query_date_precision in {'MONTH','YEAR'}:
            assumptions.append(f'Mốc thời gian chỉ chính xác theo {"tháng" if analysis.query_date_precision=="MONTH" else "năm"}; kiểm tra các phiên bản giao với khoảng {analysis.query_date} đến {analysis.query_date_end}.')
        trace.events.append({'event':'query_intake','raw_preserved':env.raw_query==request.question,'conversation_turns':len(env.conversation_context),'evidence_treated_as_data':True})
        trace.events.append({'event':'analysis','issues':analysis.legal_issues,'subissues':analysis.legal_subissues,'taxonomy_version':TAXONOMY_VERSION,'fact_fields':sorted(analysis.facts),'temporal_intent':analysis.temporal_intent,
          'query_date_precision':analysis.query_date_precision,'query_date':analysis.query_date,'query_date_end':analysis.query_date_end,
          'fact_candidates':[candidate.model_dump(mode='json') for candidate in analysis.fact_candidates]})
        trace.events.append({'event':'researcher','mode':self.cfg.researcher.mode,'execution':researcher_path,'issues':analysis.legal_issues,
          'retrieval_queries':analysis.retrieval_queries,'ontology':analysis.ontology_features.model_dump(mode='json'),
          'verified_fact_candidates':sum(candidate.verified for candidate in analysis.fact_candidates),'fallback':bool(research_warnings)})
        trace.events.append({'event':'freshness','corpus_snapshot_as_of':snapshot,'warning':freshness_relevant and 'CORPUS_MAY_BE_STALE' in warnings})
        trace.events.append({'event':'evidence_plan','mandatory_slots':plan.mandatory_slots,'conditional_slots':plan.conditional_slots,'slot_requirements':{slot:[[locator.model_dump(mode='json') for locator in group] for group in groups] for slot,groups in plan.slot_requirements.items()}})
        if not analysis.in_scope:
            trace.stop_reason=Stop.ABSTAIN; trace.reference_audit='PASS'; trace.timings_ms['total']=round((time.perf_counter()-start)*1000,2)
            trace.events.append({'event':'scope_gate','status':'ABSTAIN','reason':'OUT_OF_LABOR_LAW_SCOPE'}); persist(trace,self.cfg.trace_dir)
            return AnswerResponse(query_id=env.query_id,status=Stop.ABSTAIN,
              answer='Câu hỏi nằm ngoài phạm vi pháp luật lao động của hệ thống.',evidence_status='OUT_OF_SCOPE',
              applicable_date=analysis.query_date,query_date=analysis.query_date,assumptions=assumptions,
              limitations=['out_of_scope'],warnings=warnings+['OUT_OF_LABOR_LAW_SCOPE'],facts=analysis.facts,
              build_id=trace.build_id,trace_id=trace.trace_id,trace=trace)
        if analysis.missing_facts:
            trace.stop_reason=Stop.NEED_MORE_FACTS; trace.reference_audit='NOT_RUN'; trace.timings_ms['total']=round((time.perf_counter()-start)*1000,2)
            trace.events.append({'event':'fact_gate','status':'NEED_MORE_FACTS','missing':analysis.missing_facts}); persist(trace,self.cfg.trace_dir)
            return AnswerResponse(query_id=env.query_id,status=Stop.NEED_MORE_FACTS,answer='Cần bổ sung dữ kiện trước khi tra cứu chuyên sâu.',questions=analysis.missing_facts,
              evidence_status='NOT_RETRIEVED',applicable_date=analysis.query_date,query_date=analysis.query_date,assumptions=assumptions,
              warnings=warnings,facts=analysis.facts,build_id=trace.build_id,trace_id=trace.trace_id,trace=trace)
        stage=time.perf_counter(); lists=[]
        allow_fallback=self.cfg.provisional_mode and self.cfg.allow_document_temporal_fallback
        if analysis.explicit_references and self.cfg.retrieval.exact_lookup:
            exact=self.retriever.exact(analysis.explicit_references)
            descendants=self.retriever.hierarchy_descendants(exact,max(0,self.cfg.max_verified_units-len(exact)))
            lists.append(exact+descendants)
        exact_only=bool(analysis.route==Route.DIRECT and lists and lists[0])
        profile_only=False
        policy=[]
        if not exact_only and self.cfg.retrieval.profile_fast_path and plan.slot_requirements:
            probe_started=time.perf_counter()
            policy=self.retriever.policy_anchor(analysis.legal_issues,analysis.facts,plan)
            probe,_=temporal_filter(policy,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end)
            probe,_=authority_filter(probe,strict=not self.cfg.provisional_mode)
            probe=deterministic_audit(self.store,probe,analysis.query_date,allow_fallback,analysis.query_date_end)
            proved,probe_decisions,_=self.applicability._deterministic([item for item in probe if item.verified],
              env.normalized_query,analysis.legal_issues,analysis.facts,analysis.requested_outcome)
            probe_plan=extend_plan_for_evidence(plan,proved,analysis.facts,analysis.query_date)
            probe_state=state_for(proved,probe_plan,analysis.query_date,allow_fallback)
            recognized={'DETERMINISTIC_PROFILE_RULE','DETERMINISTIC_RULE_MATCH','DETERMINISTIC_LEAVE_RULE_CHAIN',
              'DETERMINISTIC_SPECIAL_OCCUPATION_RULE_MATCH','DETERMINISTIC_SPECIAL_OCCUPATION_DELEGATION_MATCH',
              'DETERMINISTIC_LATE_WAGE_CHAIN','DETERMINISTIC_MISINFORMATION_CHAIN','DETERMINISTIC_HARASSMENT_EXCEPTION',
              'DETERMINISTIC_WITHDRAWAL_RULE','DETERMINISTIC_DEFINITION_CONSEQUENCE_CHAIN','DETERMINISTIC_MUTUAL_AGREEMENT_RULE',
              'DETERMINISTIC_HISTORICAL_NOTICE_CHAIN'}
            proved_ids={item.unit_id for item in proved}
            known=bool(proved) and all(recognized.intersection(d.reasons) for d in probe_decisions if d.evidence_id in proved_ids)
            profile_only=known and not _actionable_gaps(probe_state.gaps,proved,self.cfg.provisional_mode)
            trace.timings_ms['profile_probe']=round((time.perf_counter()-probe_started)*1000,2)
            trace.events.append({'event':'profile_fast_path','used':profile_only,'missing':probe_state.gaps,
              'proved_ids':sorted(proved_ids),'reason':'KNOWN_RULE_CHAIN_COMPLETE' if profile_only else 'FULL_RETRIEVAL_REQUIRED'})
            if profile_only:
                lists.append(proved); plan=probe_plan
        if not exact_only:
            policy=policy or self.retriever.policy_anchor(analysis.legal_issues,analysis.facts,plan)
        if not exact_only and not profile_only:
            if policy: lists.append(policy)
            retrieval_queries=[env.normalized_query]+analysis.retrieval_queries
            if self.cfg.retrieval.bm25_enabled:
                channel_started=time.perf_counter()
                for retrieval_query in retrieval_queries: lists.append(self.retriever.bm25(retrieval_query))
                trace.timings_ms['bm25']=round((time.perf_counter()-channel_started)*1000,2)
            if self.cfg.retrieval.dense_enabled:
                channel_started=time.perf_counter()
                for retrieval_query in retrieval_queries:
                    try:
                        lists.append(self.retriever.dense(retrieval_query))
                    except IndexUnavailable as exc:
                        warnings.append('DENSE_RETRIEVAL_UNAVAILABLE')
                        trace.events.append({'event':'dense_retrieval','status':'DEGRADED',
                          'error':type(exc.__cause__ or exc).__name__})
                        break
                trace.timings_ms['dense']=round((time.perf_counter()-channel_started)*1000,2)
            if self.cfg.retrieval.issue_anchor_enabled: lists.append(self.retriever.issue_anchor(analysis.legal_issues))
            case_query=analysis.requested_outcome=='FIND_CASE' or 'DISPUTE' in analysis.legal_issues
            if self.cfg.retrieval.case_law_enabled and case_query: lists.append(self.retriever.case_law(env.normalized_query))
            if self.cfg.retrieval.community_enabled and case_query: lists.append(self.retriever.community_cases(env.normalized_query))
        fusion_started=time.perf_counter()
        nonempty=[x for x in lists if x]; items=nonempty[0] if len(nonempty)==1 else self.retriever.fusion(nonempty) if nonempty else []
        trace.timings_ms['fusion']=round((time.perf_counter()-fusion_started)*1000,2)
        trace.seed_results=sum(len(x) for x in lists)
        items,removed=temporal_filter(items,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end)
        items,authority_removed=authority_filter(items,strict=not self.cfg.provisional_mode)
        reranker_started=time.perf_counter()
        if self.cfg.reranker.enabled and not exact_only and not profile_only:
            try: items=self.retriever.neural_rerank(items,env.normalized_query)
            except IndexUnavailable as exc:
                warnings.append('NEURAL_RERANKER_UNAVAILABLE')
                trace.events.append({'event':'neural_reranker','status':'DEGRADED','error':type(exc.__cause__ or exc).__name__})
        trace.timings_ms['neural_reranker']=round((time.perf_counter()-reranker_started)*1000,2)
        trace.events.append({'event':'retrieval_execution','path':'EXACT' if exact_only else 'PROFILE' if profile_only else 'HYBRID',
          'bm25_requested':self.cfg.retrieval.bm25_enabled and not (exact_only or profile_only),
          'dense_requested':self.cfg.retrieval.dense_enabled and not (exact_only or profile_only),
          'reranker_requested':self.cfg.reranker.enabled and not (exact_only or profile_only)})
        items=rerank(items,self.cfg)
        trace.timings_ms['seed_retrieval']=round((time.perf_counter()-stage)*1000,2)
        audit_started=time.perf_counter()
        audited=deterministic_audit(self.store,items,analysis.query_date,allow_fallback,analysis.query_date_end)
        trace.timings_ms['deterministic_audit']=round((time.perf_counter()-audit_started)*1000,2)
        applicability_started=time.perf_counter()
        verified,decisions,app_warnings=self.applicability.audit([x for x in audited if x.verified],env.normalized_query,analysis.legal_issues,analysis.facts,analysis.requested_outcome)
        trace.timings_ms['applicability_audit']=round((time.perf_counter()-applicability_started)*1000,2)
        warnings+=app_warnings
        extended_plan=extend_plan_for_evidence(plan,verified,analysis.facts,analysis.query_date)
        if extended_plan.mandatory_slots!=plan.mandatory_slots:
            plan=extended_plan
            trace.events.append({'event':'evidence_plan_extended','mandatory_slots':plan.mandatory_slots})
        state=state_for(verified,plan,analysis.query_date,allow_fallback)
        trace.timings_ms['seed_retrieval_and_audit']=round((time.perf_counter()-stage)*1000,2)
        trace.retrieval_candidates=[{'unit_id':x.unit_id,'method':x.retrieval_method,'score':round(x.score,8),
          'authority_verified':x.authority_verified} for x in items[:50]]
        trace.evidence_gaps.append({'round':0,'missing':state.gaps,'coverage':state.coverage})
        hierarchy_edges={edge for item in verified for edge in item.graph_path}
        hierarchy_relations=list(dict.fromkeys(relation for item in verified for relation in item.graph_relations))
        graph_stats={'nodes_visited':len(verified),'edges_visited':len(hierarchy_edges),'rounds':0,
          'critical_edges_followed':hierarchy_relations}
        budget_reason=None; stage=time.perf_counter()
        if self.cfg.graph.enabled and not exact_only:
            graph_seeds=verified[:self.cfg.graph.max_nodes]
            visited={x.unit_id for x in graph_seeds}; paths={x.unit_id:list(x.graph_path) for x in graph_seeds}
            relation_paths={x.unit_id:list(x.graph_relations) for x in graph_seeds}; direction_paths={x.unit_id:list(x.graph_directions) for x in graph_seeds}
            frontier=list(visited)
            max_rounds=1 if analysis.route==Route.STANDARD and self.cfg.graph.mode=='adaptive' else min(self.cfg.graph.max_rounds,self.cfg.graph.max_hops)
            graph_started=time.monotonic()
            for round_no in range(1,max_rounds+1):
                gaps=_actionable_gaps(state.gaps,verified,self.cfg.provisional_mode)
                if self.cfg.graph.mode=='fixed': gaps=['__fixed__']
                if not gaps: budget_reason='EVIDENCE_SUFFICIENT'; break
                if not frontier: budget_reason='FRONTIER_EXHAUSTED'; break
                if len(visited)>=self.cfg.graph.max_nodes: budget_reason='NODE_BUDGET'; break
                if graph_stats['edges_visited']>=self.cfg.graph.max_edges: budget_reason='EDGE_BUDGET'; break
                if (time.monotonic()-graph_started)*1000>=self.cfg.graph.wall_clock_ms: budget_reason='TIME_BUDGET'; break
                remaining_ms=self.cfg.graph.wall_clock_ms-(time.monotonic()-graph_started)*1000
                expanded,frontier,round_stats=self.graph.expand_round(frontier,gaps,env.normalized_query,visited,paths,
                  self.cfg.graph.max_nodes-len(visited),self.cfg.graph.max_edges-graph_stats['edges_visited'],relation_paths,direction_paths,remaining_ms)
                graph_stats['edges_visited']+=round_stats['edges_visited']; graph_stats['rounds']=round_no
                graph_stats['critical_edges_followed']+=round_stats['critical_edges_followed']
                if expanded:
                    expanded,removed_more=temporal_filter(expanded,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end); removed+=removed_more
                    expanded,authority_removed_more=authority_filter(expanded,strict=not self.cfg.provisional_mode); authority_removed+=authority_removed_more
                    expanded=deterministic_audit(self.store,expanded,analysis.query_date,allow_fallback,analysis.query_date_end)
                    expanded,round_decisions,round_warnings=self.applicability.audit([x for x in expanded if x.verified],env.normalized_query,analysis.legal_issues,analysis.facts,analysis.requested_outcome)
                    decisions+=round_decisions; warnings+=round_warnings
                    verified=rerank(list({x.unit_id:x for x in verified+expanded}.values()),self.cfg)
                    state=state_for(verified,plan,analysis.query_date,allow_fallback)
                trace.evidence_gaps.append({'round':round_no,'missing':state.gaps,'coverage':state.coverage})
                trace.graph_round_details.append({'round':round_no,'frontier':len(frontier),'added':round_stats['nodes_added'],
                  'edges_visited':round_stats['edges_visited'],'relations':round_stats['critical_edges_followed'],'gaps':state.gaps,
                  'budget_stop_reason':round_stats['stop_reason']})
                if round_stats['stop_reason'] in {'TIME_BUDGET','NODE_BUDGET','EDGE_BUDGET'}:
                    budget_reason=round_stats['stop_reason']; break
                if not frontier: budget_reason='FRONTIER_EXHAUSTED'; break
            else:
                budget_reason='ROUND_BUDGET' if max_rounds else 'GRAPH_DISABLED_BY_ZERO_ROUNDS'
            graph_stats['nodes_visited']=len(visited); graph_stats['critical_edges_followed']=list(dict.fromkeys(graph_stats['critical_edges_followed']))
        trace.timings_ms['graph_retrieval']=round((time.perf_counter()-stage)*1000,2)
        route_limit=self.cfg.max_verified_units if analysis.route==Route.DIRECT and any(x.retrieval_method=='exact_hierarchy' for x in verified) else 1 if analysis.route==Route.DIRECT else min(self.cfg.max_verified_units,6) if analysis.route==Route.STANDARD else self.cfg.max_verified_units
        if plan.slot_requirements:
            route_limit=self.cfg.max_verified_units
        selection_started=time.perf_counter()
        selected,state=select_for_plan(verified,plan,analysis.query_date,allow_fallback,route_limit)
        conflicts=detect_authoritative_conflicts(verified,analysis.query_date,analysis.query_date_end)
        trace.timings_ms['selection']=round((time.perf_counter()-selection_started)*1000,2)
        if conflicts:
            conflict_ids={uid for pair in conflicts for uid in pair}
            selected=list({item.unit_id:item for item in selected+[x for x in verified if x.unit_id in conflict_ids]}.values())
            state=state_for(selected,plan,analysis.query_date,allow_fallback)
        imprecise_boundary_ids=[x.unit_id for x in selected if 'IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY' in x.audit_warnings]
        followup_questions=[]
        if imprecise_boundary_ids:
            state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+['imprecise_query_date']))})
            followup_questions=['Quy định thay đổi trong khoảng thời gian đã nêu. Vui lòng cung cấp ngày chính xác (YYYY-MM-DD) để xác định đúng phiên bản pháp luật.']
        if conflicts:
            for slot in state.mandatory_slots:
                if state.slots[slot].evidence_ids: state.slots[slot]=state.slots[slot].model_copy(update={'status':SlotStatus.CONFLICT})
            state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+['authoritative_conflict']))})
        actionable_final=_actionable_gaps(state.gaps,selected,self.cfg.provisional_mode)
        sufficient=bool(selected) and not state.gaps
        partial=bool(selected) and not sufficient and not actionable_final and state.coverage>=self.cfg.minimum_coverage and self.cfg.allow_partial
        status=Stop.CONFLICTING_EVIDENCE if conflicts else Stop.NEED_MORE_FACTS if followup_questions else Stop.SUFFICIENT if sufficient else Stop.PARTIAL_ALLOWED if partial else Stop.INSUFFICIENT_EVIDENCE
        selected_decisions=[x for x in decisions if x.evidence_id in {item.unit_id for item in selected}]
        pack=build_verified_pack(env.normalized_query,analysis.query_date,analysis.facts,state,selected,selected_decisions,analysis.requested_outcome)
        adjudication_started=time.perf_counter()
        if status in {Stop.INSUFFICIENT_EVIDENCE,Stop.NEED_MORE_FACTS}:
            summary='Cần ngày chính xác để xác định phiên bản pháp luật áp dụng.' if status==Stop.NEED_MORE_FACTS else 'Không đủ bằng chứng đã xác minh để kết luận.'
            draft=AdjudicationDraft(answer_summary=summary,claims=[],applicable_law_versions=[],assumptions=assumptions,limitations=state.gaps)
            generation_warnings=[]; answer=draft.answer_summary; refs=[]
        else:
            draft,generation_warnings=self.adjudicator.generate(pack,partial,assumptions)
            # Retrieval completeness does not establish answer completeness.
            # The public claims must actually cite every mandatory locator group.
            def missing_answer_slots(candidate):
                cited={uid for claim in candidate.claims for uid in claim.evidence_ids}
                output_state=state_for([item for item in selected if item.unit_id in cited],plan,analysis.query_date,allow_fallback)
                return _actionable_gaps(output_state.gaps,[item for item in selected if item.unit_id in cited],self.cfg.provisional_mode)
            missing_claims=missing_answer_slots(draft)
            if missing_claims and 'ANSWER_QUALITY_BLOCKED' not in generation_warnings:
                # One bounded deterministic repair, with the same vetted pack;
                # never fabricate a source or issue another inference request.
                repaired,repair_warnings=LegalAdjudicator(AdjudicationConfig()).generate(pack,partial,assumptions)
                if not missing_answer_slots(repaired) and 'ANSWER_QUALITY_BLOCKED' not in repair_warnings:
                    draft=repaired; generation_warnings+=repair_warnings+['ANSWER_REQUIRED_EVIDENCE_REPAIRED']
                else:
                    generation_warnings+=['ANSWER_REQUIRED_EVIDENCE_MISSING:'+','.join(missing_claims),'ANSWER_QUALITY_BLOCKED']
            answer=draft.answer_summary
            if 'ANSWER_QUALITY_BLOCKED' in generation_warnings:
                status=Stop.INSUFFICIENT_EVIDENCE
                if any(warning.startswith('ANSWER_REQUIRED_EVIDENCE_MISSING:') for warning in generation_warnings):
                    quality_gap='answer_completeness'
                    answer='Câu trả lời còn thiếu nội dung pháp lý bắt buộc của câu hỏi. Cần bổ sung chuỗi căn cứ trước khi kết luận.'
                elif any(warning.startswith('SOURCE_TEXT_QUALITY:') for warning in generation_warnings):
                    quality_gap='source_text_quality'
                    answer='Nội dung nguồn có lỗi đọc chữ đáng ngờ. Cần đối chiếu bản gốc trước khi kết luận.'
                else:
                    quality_gap='answer_text_quality'
                    answer='Câu trả lời chưa đạt kiểm tra câu chữ. Chưa thể đưa ra kết luận đáng tin cậy.'
                state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+[quality_gap]))})
                draft=AdjudicationDraft(answer_summary=answer,claims=[],applicable_law_versions=[],assumptions=assumptions,limitations=state.gaps)
            used_ids=list(dict.fromkeys(evidence_id for claim in draft.claims for evidence_id in claim.evidence_ids))
            selected_by_id={item.unit_id:item for item in selected}
            reference_items=[selected_by_id[evidence_id] for evidence_id in used_ids if evidence_id in selected_by_id] if used_ids else selected
            refs=[] if status==Stop.INSUFFICIENT_EVIDENCE else citations(reference_items)
        trace.timings_ms['adjudication']=round((time.perf_counter()-adjudication_started)*1000,2)
        warnings+=generation_warnings
        if conflicts:
            conflict_ids=list(dict.fromkeys(uid for pair in conflicts for uid in pair)); conflict_items=[x for x in selected if x.unit_id in conflict_ids]
            answer='Các nguồn có thẩm quyền đang cho kết quả xung đột; hệ thống chưa thể kết luận. '+ ' '.join(f'[{x}]' for x in conflict_ids)
            refs=citations(conflict_items); warnings.append('AUTHORITATIVE_EVIDENCE_CONFLICT'); draft=draft.model_copy(update={'claims':[]})
        # An abstention deliberately exposes no evidence or citation.  Audit the
        # public answer surface, while retaining selected evidence in the trace.
        reference_items=[] if status in {Stop.INSUFFICIENT_EVIDENCE,Stop.NEED_MORE_FACTS} else (
          [item for item in selected if item.unit_id in {citation.evidence_id for citation in refs}] if refs else selected)
        reference_audit_started=time.perf_counter()
        ok,problems=reference_audit(answer,reference_items,refs,draft.claims)
        if not ok and draft.claims:
            repaired_answer,repaired_items,repaired_claims=_repair_references(selected,draft.claims)
            repaired_refs=citations(repaired_items)
            repaired_ok,repaired_problems=reference_audit(repaired_answer,repaired_items,repaired_refs,repaired_claims)
            if repaired_ok:
                answer=repaired_answer; selected=repaired_items; refs=repaired_refs; ok=True; problems=[]
                draft=draft.model_copy(update={'claims':repaired_claims}); warnings.append('REFERENCE_AUDIT_REPAIRED')
                selected,state=select_for_plan(selected,plan,analysis.query_date,allow_fallback,len(selected))
                pack=build_verified_pack(env.normalized_query,analysis.query_date,analysis.facts,state,selected,
                  [x for x in decisions if x.evidence_id in {item.unit_id for item in selected}],analysis.requested_outcome)
                sufficient=bool(selected) and not state.gaps
                actionable_final=_actionable_gaps(state.gaps,selected,self.cfg.provisional_mode)
                partial=bool(selected) and not sufficient and not actionable_final and state.coverage>=self.cfg.minimum_coverage and self.cfg.allow_partial
                status=Stop.SUFFICIENT if sufficient else Stop.PARTIAL_ALLOWED if partial else Stop.INSUFFICIENT_EVIDENCE
                if status==Stop.INSUFFICIENT_EVIDENCE:
                    answer='Không đủ bằng chứng đã xác minh để kết luận.'; refs=[]
                    draft=AdjudicationDraft(answer_summary=answer,claims=[],applicable_law_versions=[],assumptions=assumptions,limitations=state.gaps)
            else:
                problems=list(dict.fromkeys(problems+repaired_problems))
        if not ok:
            answer='Không thể tạo câu trả lời có trích dẫn được xác minh.'; refs=[]; status=Stop.INSUFFICIENT_EVIDENCE; warnings+=problems
            state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+['reference_audit']))})
            draft=draft.model_copy(update={'claims':[],'applicable_law_versions':[],'limitations':state.gaps})
        trace.timings_ms['reference_audit']=round((time.perf_counter()-reference_audit_started)*1000,2)
        public_evidence_ids={citation.evidence_id for citation in refs}
        temporal_fallback_ids=[
          x.unit_id for x in selected
          if x.unit_id in public_evidence_ids and 'DOCUMENT_LEVEL_TEMPORAL_FALLBACK' in x.audit_warnings
        ]
        if temporal_fallback_ids: warnings.append(f'DOCUMENT_LEVEL_TEMPORAL_FALLBACK_USED:{len(temporal_fallback_ids)}')
        if imprecise_boundary_ids: warnings.append(f'IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY:{len(imprecise_boundary_ids)}')
        warnings=[
          warning for warning in warnings
          if not warning.startswith('APPLICABILITY_UNRESOLVED:')
          or warning.split(':',1)[1] in public_evidence_ids
        ]
        trace.retrieval_rounds=graph_stats['rounds']; trace.nodes_visited=graph_stats['nodes_visited']; trace.edges_visited=graph_stats['edges_visited']
        trace.critical_edges_followed=graph_stats['critical_edges_followed']; trace.verified_evidence_count=len(selected)
        trace.reference_audit='PASS' if ok else 'FAIL'; trace.stop_reason=status; trace.budget_stop_reason=budget_reason
        trace.events+=[{'event':'retrieval','candidates':trace.seed_results,'temporal_removed':len(set(removed)),
          'authority_removed':len(set(authority_removed)),'temporal_fallback':len(temporal_fallback_ids)},
          {'event':'applicability_audit','mode':self.cfg.applicability.mode,'passed':sum(x.audit_status=='PASS' for x in decisions),'total':len(decisions),
           'decisions':[{'evidence_id':x.evidence_id,'audit_status':x.audit_status,'relevant':x.relevant,
             'supports_claim':x.supports_claim,'reasons':x.reasons} for x in decisions]},
          {'event':'selection','selected':len(selected),'deduplicated':max(0,len(verified)-len(selected)),
            'evidence_ids':[item.unit_id for item in selected]},
          {'event':'evidence_state','coverage':state.coverage,'gaps':state.gaps},
          {'event':'verified_evidence_pack','count':len(pack.evidence),'characters':sum(len(x.text) for x in pack.evidence),
           'estimated_tokens':sum(len(x.text) for x in pack.evidence)/4},
          {'event':'adjudication','mode':self.cfg.adjudication.mode,'claims':len(draft.claims),'fallback':bool(generation_warnings)},
          {'event':'reference_audit','passed':ok,'issues':problems}]
        trace.timings_ms['total']=round((time.perf_counter()-start)*1000,2); persist(trace,self.cfg.trace_dir)
        evidence_status='CONFLICTING' if status==Stop.CONFLICTING_EVIDENCE else 'NEED_MORE_FACTS' if status==Stop.NEED_MORE_FACTS else 'SUFFICIENT' if status==Stop.SUFFICIENT else 'PARTIAL' if status==Stop.PARTIAL_ALLOWED else 'INSUFFICIENT'
        return AnswerResponse(query_id=env.query_id,status=status,answer=answer,citations=refs,evidence_status=evidence_status,
          applicable_date=analysis.query_date,query_date=analysis.query_date,applicable_law_versions=draft.applicable_law_versions,
          claims=draft.claims,assumptions=draft.assumptions,limitations=state.gaps,questions=followup_questions,warnings=list(dict.fromkeys(warnings)),
          facts=analysis.facts,build_id=trace.build_id,trace_id=trace.trace_id,trace=trace)
