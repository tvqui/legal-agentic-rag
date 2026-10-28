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
from .errors import IndexUnavailable,ProviderRateLimited
from .graph import GraphExplorer
from .models import QueryRequest,AnswerResponse,Trace,Stop,Route,SlotStatus,AdjudicationDraft
from .retrieval import Retriever,authority_filter,temporal_filter,rerank,retain_required_anchors
from .researcher import LegalResearcher
from .trace import persist
from .taxonomy import TAXONOMY_VERSION
from .demo_progress import call as observed,Step,skip as skip_step,skip_after_gate,evidence_summary,audit_summary,graph_summary,execution_snapshot

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
        reviewer=getattr(self.adjudicator,'review_provider',None)
        if reviewer is not None and reviewer is not self.adjudicator.provider: reviewer.close()

    def ask(self,request:QueryRequest)->AnswerResponse:
        from .conversation import resolve_context
        from .runtime import request_budget,checkpoint
        with request_budget(self.cfg.request_timeout_seconds):
            resolved=observed('context',resolve_context,request,summary=lambda r:{'luot_ngu_canh':len(r.used_turns),'can_hoi_lai':bool(r.clarification),'truong_du_kien':sorted(r.facts)})
            checkpoint('understanding')
            if resolved.clarification:
                Step('scope_gate').finish({'ket_qua':'NEED_MORE_FACTS','ly_do':'Chưa rõ chủ đề hỏi nối tiếp'},'WARNING')
                skip_after_gate('Chưa rõ chủ đề nối tiếp; cần người dùng làm rõ trước')
                env=intake(request.question,request.conversation_context,request.query_date,request.facts)
                trace=Trace(trace_id='trace_'+hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16],
                  query_id=env.query_id,build_id=self.store.report.build_id or '',route=Route.STANDARD,
                  route_reason='ambiguous follow-up',stop_reason=Stop.NEED_MORE_FACTS,
                  events=[{'event':'context_clarification','model_calls':0}])
                snapshot=execution_snapshot(); trace.execution_steps=snapshot['steps']; trace.execution_steps_dropped=snapshot['dropped']
                persist(trace,self.cfg.trace_dir)
                return AnswerResponse(query_id=env.query_id,status=Stop.NEED_MORE_FACTS,
                  answer='Cần xác định chủ đề của câu hỏi nối tiếp trước khi tra cứu.',
                  questions=[resolved.clarification],evidence_status='NOT_RETRIEVED',
                  warnings=['CONVERSATION_CONTEXT_AMBIGUOUS'],build_id=self.store.report.build_id or '',
                  trace_id=trace.trace_id,trace=trace)
            effective=request.model_copy(update={'question':resolved.query,
              'facts':{**resolved.facts,**request.facts},
              'conversation_context':[turn.content for turn in request.conversation_turns] if request.conversation_turns else request.conversation_context,
              'query_date':request.query_date or resolved.query_date})
            response=self._ask(effective)
            checkpoint('completed')
            from .runtime import measured_timings
            if response.trace:
                response.trace.timings_ms.update(measured_timings())
                snapshot=execution_snapshot(); response.trace.execution_steps=snapshot['steps']; response.trace.execution_steps_dropped=snapshot['dropped']
                persist(response.trace,self.cfg.trace_dir)
            response.legal_status=getattr(self.store.report,'legal_status','PROVISIONAL')
            if response.legal_status=='PROVISIONAL':
                response.warnings=list(dict.fromkeys(response.warnings+['CORPUS_LEGAL_REVIEW_INCOMPLETE']))
            if resolved.used_turns:
                response.warnings=list(dict.fromkeys(response.warnings+['CONVERSATION_CONTEXT_USED']))
                if response.trace:
                    response.trace.events.insert(0,{'event':'conversation_context',
                      'turn_ids':resolved.used_turns,'fact_provenance':resolved.provenance,
                      'original_question':request.question,'resolved_question':resolved.query})
                    persist(response.trace,self.cfg.trace_dir)
            return response

    def _ask(self,request:QueryRequest)->AnswerResponse:
        from .runtime import checkpoint
        checkpoint('analysis')
        start=time.perf_counter(); stage=time.perf_counter()
        env=intake(request.question,request.conversation_context,request.query_date,request.facts)
        analysis=observed('analysis',analyze,env,request.query_date,request.facts,summary=lambda a:{'van_de':a.legal_issues,'van_de_con':a.legal_subissues,'truong_du_kien':sorted(a.facts),'so_y_can_tra_loi':len(a.answer_tasks),'thieu_du_kien':len(a.missing_facts),'tuyen':a.route.value})
        snapshot=self.cfg.corpus_snapshot_as_of
        defaulted_query_date=False
        if analysis.query_date is None and snapshot:
            default_date=min(snapshot,date.today().isoformat())
            analysis=analysis.model_copy(update={'query_date':default_date,'query_date_end':default_date,
              'query_date_precision':'DAY','temporal_intent':'CURRENT'})
            defaulted_query_date=True
        analysis_ms=round((time.perf_counter()-stage)*1000,2)
        checkpoint('understanding')
        researcher_started=time.perf_counter()
        researcher_path=self.researcher.execution_path(analysis)
        analysis,research_warnings=observed('researcher',self.researcher.enrich,analysis,env.normalized_query,env.conversation_context,
          technology='Python · quy tắc / taxonomy' if researcher_path!='MODEL_REQUESTED' else 'Researcher · yêu cầu model (xem lượt provider)',
          summary=lambda r:{'nhanh':researcher_path,'so_query':len(r[0].retrieval_queries),'so_task':len(r[0].answer_tasks),'so_canh_bao':len(r[1])},
          status=lambda r:'SKIPPED' if researcher_path!='MODEL_REQUESTED' else 'WARNING' if r[1] else 'DONE')
        if ('RESEARCHER_PROVIDER_ERROR:GEMINI_HTTP_429' in research_warnings
          and self.cfg.adjudication.review_provider=='gemini' and self.cfg.adjudication.semantic_review
          and self.cfg.adjudication.mode!='deterministic'):
            # Compatibility guard for providers returning warning codes. Gemini
            # now paces and retries transient limits before surfacing an error;
            # exhausted limits must not be mislabeled as missing legal evidence.
            raise ProviderRateLimited('GEMINI_HTTP_429')
        checkpoint('planning')
        plan=observed('planning',plan_evidence,analysis,summary=lambda v:{'o_bat_buoc':v.mandatory_slots,'o_co_dieu_kien':v.conditional_slots,'so_nhom_can_cu':sum(len(g) for g in v.slot_requirements.values()),'ngay_tra_cuu':analysis.query_date})
        plan,container_notes=self.retriever.resolve_article_plan(plan,analysis.query_date,analysis.query_date_end)
        analysis=analysis.model_copy(update={'resolved_rule_requirements':plan.slot_requirements})
        trace=Trace(trace_id='trace_'+hashlib.sha256((env.query_id+str(time.time_ns())).encode()).hexdigest()[:16],query_id=env.query_id,
          build_id=self.store.report.build_id or '',route=analysis.route,route_reason=analysis.route_reason,
          config_fingerprint=hashlib.sha256(json.dumps(self.cfg.model_dump(mode='json'),sort_keys=True).encode()).hexdigest())
        trace.timings_ms['analysis']=analysis_ms
        trace.timings_ms['researcher']=round((time.perf_counter()-researcher_started)*1000,2)
        if container_notes: trace.events.append({'event':'article_content_plan','resolved':container_notes})
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
        trace.events.append({'event':'analysis','issues':analysis.legal_issues,'subissues':analysis.legal_subissues,'routing_topics':analysis.routing_topics,
          'answer_task_count':len(analysis.answer_tasks),'taxonomy_version':TAXONOMY_VERSION,'fact_fields':sorted(analysis.facts),'temporal_intent':analysis.temporal_intent,
          'query_date_precision':analysis.query_date_precision,'query_date':analysis.query_date,'query_date_end':analysis.query_date_end,
          'fact_candidates':[candidate.model_dump(mode='json') for candidate in analysis.fact_candidates]})
        trace.events.append({'event':'researcher','mode':self.cfg.researcher.mode,'execution':researcher_path,'issues':analysis.legal_issues,
          'retrieval_queries':analysis.retrieval_queries,'ontology':analysis.ontology_features.model_dump(mode='json'),
          'verified_fact_candidates':sum(candidate.verified for candidate in analysis.fact_candidates),'fallback':bool(research_warnings)})
        trace.events.append({'event':'freshness','corpus_snapshot_as_of':snapshot,'warning':freshness_relevant and 'CORPUS_MAY_BE_STALE' in warnings})
        trace.events.append({'event':'evidence_plan','mandatory_slots':plan.mandatory_slots,'conditional_slots':plan.conditional_slots,'slot_requirements':{slot:[[locator.model_dump(mode='json') for locator in group] for group in groups] for slot,groups in plan.slot_requirements.items()}})
        if not analysis.in_scope:
            Step('scope_gate').finish({'ket_qua':'ABSTAIN','ly_do':'Ngoài phạm vi pháp luật lao động'},'WARNING')
            skip_after_gate('Câu hỏi ngoài phạm vi; không truy xuất hoặc tạo kết luận lao động')
            trace.stop_reason=Stop.ABSTAIN; trace.reference_audit='PASS'; trace.timings_ms['total']=round((time.perf_counter()-start)*1000,2)
            trace.events.append({'event':'scope_gate','status':'ABSTAIN','reason':'OUT_OF_LABOR_LAW_SCOPE'}); persist(trace,self.cfg.trace_dir)
            return AnswerResponse(query_id=env.query_id,status=Stop.ABSTAIN,
              answer='Câu hỏi nằm ngoài phạm vi pháp luật lao động của hệ thống.',evidence_status='OUT_OF_SCOPE',
              applicable_date=analysis.query_date,query_date=analysis.query_date,assumptions=assumptions,
              limitations=['out_of_scope'],warnings=warnings+['OUT_OF_LABOR_LAW_SCOPE'],facts=analysis.facts,
              build_id=trace.build_id,trace_id=trace.trace_id,trace=trace)
        # Explain general rules while clarifying, but do not decide a concrete
        # case when the analyzer says a material prerequisite is unknown.
        # Warnings appended after an unconditional verdict cannot repair it.
        clarify_during_answer=bool(analysis.missing_facts and self.cfg.answer_while_clarifying
          and analysis.route!=Route.DIRECT and analysis.requested_outcome!='ASSESS_LEGALITY')
        if clarify_during_answer:
            warnings.append('CONDITIONAL_EXPLANATION_PENDING_FACTS')
            assumptions.append('Chỉ giải thích có điều kiện đối với phần còn thiếu dữ kiện; không xác nhận điều kiện đó đã xảy ra.')
        if analysis.missing_facts and not clarify_during_answer:
            Step('scope_gate').finish({'ket_qua':'NEED_MORE_FACTS','so_thong_tin_can_bo_sung':len(analysis.missing_facts)},'WARNING')
            skip_after_gate('Thiếu dữ kiện quyết định; cần hỏi lại trước khi tìm sâu')
            trace.stop_reason=Stop.NEED_MORE_FACTS; trace.reference_audit='NOT_RUN'; trace.timings_ms['total']=round((time.perf_counter()-start)*1000,2)
            trace.events.append({'event':'fact_gate','status':'NEED_MORE_FACTS','missing':analysis.missing_facts}); persist(trace,self.cfg.trace_dir)
            return AnswerResponse(query_id=env.query_id,status=Stop.NEED_MORE_FACTS,answer='Cần bổ sung dữ kiện trước khi tra cứu chuyên sâu.',questions=analysis.missing_facts,
              evidence_status='NOT_RETRIEVED',applicable_date=analysis.query_date,query_date=analysis.query_date,assumptions=assumptions,
              warnings=warnings,facts=analysis.facts,build_id=trace.build_id,trace_id=trace.trace_id,trace=trace)
        Step('scope_gate').finish({'ket_qua':'Tiếp tục tra cứu','giai_thich_co_dieu_kien':clarify_during_answer},'WARNING' if clarify_during_answer else 'DONE')
        checkpoint('retrieval')
        audit_outcome='EXPLAIN' if clarify_during_answer else analysis.requested_outcome
        stage=time.perf_counter(); lists=[]
        allow_fallback=self.cfg.provisional_mode and self.cfg.allow_document_temporal_fallback
        lookup_scope_complete=False
        if analysis.explicit_references and self.cfg.retrieval.exact_lookup:
            exact=observed('exact',self.retriever.exact,analysis.explicit_references,summary=lambda v:evidence_summary(v,self.store))
            descendant_limit=max(0,self.cfg.max_verified_units-len(exact))
            descendants=self.retriever.hierarchy_descendants(exact,descendant_limit)
            lookup_scope_complete=bool(descendant_limit and len(descendants)<descendant_limit)
            lists.append(exact+descendants)
        exact_only=bool(analysis.route==Route.DIRECT and lists and lists[0])
        profile_only=False
        if not analysis.explicit_references or not self.cfg.retrieval.exact_lookup:
            skip_step('exact','Không có định vị Điều/Khoản/Điểm hoặc exact lookup đã tắt')
        policy=[]
        if not exact_only and self.cfg.retrieval.profile_fast_path and plan.slot_requirements:
            profile_step=Step('profile')
            probe_started=time.perf_counter()
            policy=self.retriever.policy_anchor(analysis.legal_issues,analysis.facts,plan)
            probe,_=temporal_filter(policy,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end)
            probe,_=authority_filter(probe,strict=not self.cfg.provisional_mode)
            probe=deterministic_audit(self.store,probe,analysis.query_date,allow_fallback,analysis.query_date_end)
            proved,probe_decisions,_=self.applicability._deterministic([item for item in probe if item.verified],
              env.normalized_query,analysis.legal_issues,analysis.facts,audit_outcome)
            probe_plan=extend_plan_for_evidence(plan,proved,analysis.facts,analysis.query_date)
            probe_state=state_for(proved,probe_plan,analysis.query_date,allow_fallback)
            recognized={'DETERMINISTIC_PROFILE_RULE','DETERMINISTIC_RULE_MATCH','DETERMINISTIC_LEAVE_RULE_CHAIN',
              'DETERMINISTIC_PRO_RATA_BASE_PARAMETER',
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
            profile_step.finish({'du_chuoi':profile_only,'so_nguon_PASS':len(proved),'o_con_thieu':probe_state.gaps},'DONE' if profile_only else 'WARNING')
            if profile_only:
                lists.append(proved); plan=probe_plan
        if exact_only or not self.cfg.retrieval.profile_fast_path or not plan.slot_requirements:
            skip_step('profile','Exact lookup đã dùng, hoặc profile fast path không áp dụng')
        if not exact_only:
            policy=policy or observed('policy',self.retriever.policy_anchor,analysis.legal_issues,analysis.facts,plan,summary=lambda v:evidence_summary(v,self.store))
        if not exact_only and not profile_only:
            if policy: lists.append(policy)
            retrieval_queries=[env.normalized_query]+analysis.retrieval_queries
            if self.cfg.retrieval.bm25_enabled:
                channel_started=time.perf_counter()
                for retrieval_query in retrieval_queries: lists.append(observed('bm25',self.retriever.bm25,retrieval_query,summary=lambda v:evidence_summary(v,self.store)))
                from .query_support import task_bm25_channels
                task_channels,task_report=observed('bm25',task_bm25_channels,self.retriever,analysis.answer_tasks,retrieval_queries,technology='BM25S · bổ sung theo task',summary=lambda r:{'so_kenh_bo_sung':len(r[0]),'so_nguon':sum(len(c) for c in r[0])})
                lists.extend(task_channels)
                trace.events.append({'event':'task_scoped_retrieval',**task_report})
                trace.timings_ms['bm25']=round((time.perf_counter()-channel_started)*1000,2)
            if self.cfg.retrieval.dense_enabled:
                channel_started=time.perf_counter()
                for retrieval_query in retrieval_queries:
                    try:
                        lists.append(observed('dense',self.retriever.dense,retrieval_query,technology=self.cfg.embedding_model+' · FAISS',summary=lambda v:evidence_summary(v,self.store)))
                    except IndexUnavailable as exc:
                        warnings.append('DENSE_RETRIEVAL_UNAVAILABLE')
                        trace.events.append({'event':'dense_retrieval','status':'DEGRADED',
                          'error':type(exc.__cause__ or exc).__name__})
                        break
                trace.timings_ms['dense']=round((time.perf_counter()-channel_started)*1000,2)
            if self.cfg.retrieval.issue_anchor_enabled: lists.append(observed('issue',self.retriever.issue_anchor,analysis.legal_issues,summary=lambda v:evidence_summary(v,self.store)))
            case_query=analysis.requested_outcome=='FIND_CASE' or 'DISPUTE' in analysis.legal_issues
            if self.cfg.retrieval.case_law_enabled and case_query: lists.append(observed('cases',self.retriever.case_law,env.normalized_query,summary=lambda v:evidence_summary(v,self.store)))
            else: skip_step('cases','Không cần kênh vụ án hoặc kênh đã tắt')
            if self.cfg.retrieval.community_enabled and case_query: lists.append(observed('community',self.retriever.community_cases,env.normalized_query,summary=lambda v:evidence_summary(v,self.store)))
            else: skip_step('community','Không cần cộng đồng vụ án hoặc kênh đã tắt')
        if exact_only or profile_only:
            for key in ('bm25','dense','issue','cases','community'):
                skip_step(key,'Exact/profile đã đủ căn cứ; không yêu cầu kênh này')
        else:
            if not self.cfg.retrieval.bm25_enabled: skip_step('bm25','BM25 đã tắt trong cấu hình')
            if not self.cfg.retrieval.dense_enabled: skip_step('dense','Dense đã tắt trong cấu hình')
            if not self.cfg.retrieval.issue_anchor_enabled: skip_step('issue','Kênh issue đã tắt trong cấu hình')
        fusion_started=time.perf_counter()
        nonempty=[x for x in lists if x]
        items=observed('fusion',lambda:nonempty[0] if len(nonempty)==1 else self.retriever.fusion(nonempty) if nonempty else [],
          technology='RRF' if len(nonempty)>1 else 'Python · một kênh hoặc không có nguồn',
          summary=lambda v:{**evidence_summary(v,self.store),'so_kenh':len(nonempty)})
        trace.timings_ms['fusion']=round((time.perf_counter()-fusion_started)*1000,2)
        trace.seed_results=sum(len(x) for x in lists)
        items,removed=observed('temporal',temporal_filter,items,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end,summary=lambda r:{'giu_lai':len(r[0]),'loai':len(r[1]),'ngay_tra_cuu':analysis.query_date,'cho_fallback_cap_van_ban':allow_fallback})
        items,authority_removed=observed('authority',authority_filter,items,strict=not self.cfg.provisional_mode,summary=lambda r:{'giu_lai':len(r[0]),'loai':len(r[1]),'provisional':self.cfg.provisional_mode})
        if policy and not (exact_only or profile_only):
            anchors,_=temporal_filter(policy,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end)
            anchors,_=authority_filter(anchors,strict=not self.cfg.provisional_mode)
            items,retention=retain_required_anchors(items,anchors,plan,self.cfg.retrieval.fusion_top_k)
            trace.events.append({'event':'required_anchor_retention',**retention})
        reranker_started=time.perf_counter()
        if self.cfg.reranker.enabled and not exact_only and not profile_only:
            try: items=observed('reranker',self.retriever.neural_rerank,items,env.normalized_query,technology=self.cfg.reranker.model,summary=lambda v:evidence_summary(v,self.store))
            except IndexUnavailable as exc:
                warnings.append('NEURAL_RERANKER_UNAVAILABLE')
                trace.events.append({'event':'neural_reranker','status':'DEGRADED','error':type(exc.__cause__ or exc).__name__})
        if not self.cfg.reranker.enabled or exact_only or profile_only:
            skip_step('reranker','Exact/profile đã dùng hoặc reranker đã tắt')
        trace.timings_ms['neural_reranker']=round((time.perf_counter()-reranker_started)*1000,2)
        trace.events.append({'event':'retrieval_execution','path':'EXACT' if exact_only else 'PROFILE' if profile_only else 'HYBRID',
          'bm25_requested':self.cfg.retrieval.bm25_enabled and not (exact_only or profile_only),
          'dense_requested':self.cfg.retrieval.dense_enabled and not (exact_only or profile_only),
          'reranker_requested':self.cfg.reranker.enabled and not (exact_only or profile_only)})
        items=rerank(items,self.cfg)
        if self.cfg.retrieval.exception_context_top_k:
            context,context_report=observed('exact',self.retriever.exception_context,items,self.cfg.retrieval.exception_context_top_k,
              technology='Python · định vị ngoại lệ được nguồn dẫn chiếu',summary=lambda r:r[1])
            context,context_removed=temporal_filter(context,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end)
            context,context_authority_removed=authority_filter(context,strict=not self.cfg.provisional_mode)
            items+=context; removed+=context_removed; authority_removed+=context_authority_removed
            trace.events.append({'event':'explicit_exception_context',**context_report,'retained':len(context)})
        trace.timings_ms['seed_retrieval']=round((time.perf_counter()-stage)*1000,2)
        audit_started=time.perf_counter()
        audited=observed('source_audit',deterministic_audit,self.store,items,analysis.query_date,allow_fallback,analysis.query_date_end,summary=lambda v:{'vuot_kiem_tra_may':sum(x.verified for x in v),'co_loi_cung':sum(not x.verified for x in v),'so_nguon_co_canh_bao':sum(bool(x.audit_warnings) for x in v)},status=lambda v:'WARNING' if any(x.audit_warnings or not x.verified for x in v) else 'DONE')
        trace.timings_ms['deterministic_audit']=round((time.perf_counter()-audit_started)*1000,2)
        applicability_started=time.perf_counter()
        checkpoint('applicability')
        verified,decisions,app_warnings=observed('auditor',self.applicability.audit,[x for x in audited if x.verified],env.normalized_query,analysis.legal_issues,analysis.facts,audit_outcome,technology='Python · '+self.cfg.applicability.mode+'; xem lượt model nếu có',summary=audit_summary,status=lambda r:'WARNING' if r[2] or any(d.audit_status=='UNRESOLVED' for d in r[1]) else 'DONE')
        checkpoint()
        trace.timings_ms['applicability_audit']=round((time.perf_counter()-applicability_started)*1000,2)
        warnings+=app_warnings
        extended_plan=extend_plan_for_evidence(plan,verified,analysis.facts,analysis.query_date)
        if extended_plan!=plan:
            plan=extended_plan
            plan,context_notes=self.retriever.resolve_article_plan(plan,analysis.query_date,analysis.query_date_end)
            analysis=analysis.model_copy(update={'resolved_rule_requirements':plan.slot_requirements})
            trace.events.append({'event':'evidence_plan_extended','mandatory_slots':plan.mandatory_slots})
        state=observed('coverage',state_for,verified,plan,analysis.query_date,allow_fallback,summary=lambda v:{'coverage':v.coverage,'o_con_thieu':v.gaps},status=lambda v:'WARNING' if v.gaps else 'DONE')
        trace.timings_ms['seed_retrieval_and_audit']=round((time.perf_counter()-stage)*1000,2)
        trace.retrieval_candidates=[{'unit_id':x.unit_id,'method':x.retrieval_method,'score':round(x.score,8),
          'authority_verified':x.authority_verified} for x in items[:50]]
        trace.evidence_gaps.append({'round':0,'missing':state.gaps,'coverage':state.coverage})
        hierarchy_edges={edge for item in verified for edge in item.graph_path}
        hierarchy_relations=list(dict.fromkeys(relation for item in verified for relation in item.graph_relations))
        graph_stats={'nodes_visited':len(verified),'edges_visited':len(hierarchy_edges),'rounds':0,
          'critical_edges_followed':hierarchy_relations}
        budget_reason=None; stage=time.perf_counter()
        graph_step=Step('graph')
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
                expanded,frontier,round_stats=observed('graph_round',self.graph.expand_round,frontier,gaps,env.normalized_query,visited,paths,
                  self.cfg.graph.max_nodes-len(visited),self.cfg.graph.max_edges-graph_stats['edges_visited'],relation_paths,direction_paths,remaining_ms,
                  summary=lambda r:graph_summary(r,self.store,round_no))
                graph_stats['edges_visited']+=round_stats['edges_visited']; graph_stats['rounds']=round_no
                graph_stats['critical_edges_followed']+=round_stats['critical_edges_followed']
                if expanded:
                    expanded,removed_more=temporal_filter(expanded,analysis.query_date,strict=not allow_fallback,query_date_end=analysis.query_date_end); removed+=removed_more
                    expanded,authority_removed_more=authority_filter(expanded,strict=not self.cfg.provisional_mode); authority_removed+=authority_removed_more
                    expanded=observed('source_audit',deterministic_audit,self.store,expanded,analysis.query_date,allow_fallback,analysis.query_date_end,summary=lambda v:{'nguon_graph_vuot_kiem_tra':sum(x.verified for x in v),'co_loi_cung':sum(not x.verified for x in v)})
                    expanded,round_decisions,round_warnings=observed('auditor',self.applicability.audit,[x for x in expanded if x.verified],env.normalized_query,analysis.legal_issues,analysis.facts,audit_outcome,summary=audit_summary)
                    decisions+=round_decisions; warnings+=round_warnings
                    verified=rerank(list({x.unit_id:x for x in verified+expanded}.values()),self.cfg)
                    next_plan=extend_plan_for_evidence(plan,verified,analysis.facts,analysis.query_date)
                    if next_plan!=plan:
                        plan,_=self.retriever.resolve_article_plan(next_plan,analysis.query_date,analysis.query_date_end)
                        analysis=analysis.model_copy(update={'resolved_rule_requirements':plan.slot_requirements})
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
        graph_step.finish({'so_vong':graph_stats['rounds'],'node_da_xet':graph_stats['nodes_visited'] if graph_stats['rounds'] else 0,'canh_da_xet':graph_stats['edges_visited'] if graph_stats['rounds'] else 0,'ly_do_dung':budget_reason or ('GRAPH_DISABLED' if not self.cfg.graph.enabled else 'EXACT_LOOKUP'),'o_con_thieu':state.gaps},'SKIPPED' if not graph_stats['rounds'] else 'WARNING' if _actionable_gaps(state.gaps,verified,self.cfg.provisional_mode) else 'DONE')
        trace.timings_ms['graph_retrieval']=round((time.perf_counter()-stage)*1000,2)
        route_limit=self.cfg.max_verified_units if analysis.route==Route.DIRECT and any(x.retrieval_method=='exact_hierarchy' for x in verified) else 1 if analysis.route==Route.DIRECT else min(self.cfg.max_verified_units,6) if analysis.route==Route.STANDARD else self.cfg.max_verified_units
        if plan.slot_requirements:
            route_limit=self.cfg.max_verified_units
        selection_started=time.perf_counter()
        selected,state=observed('selection',select_for_plan,verified,plan,analysis.query_date,allow_fallback,route_limit,summary=lambda r:{**evidence_summary(r[0],self.store),'coverage':r[1].coverage,'o_con_thieu':r[1].gaps})
        conflicts=detect_authoritative_conflicts(verified,analysis.query_date,analysis.query_date_end)
        required_missing=_actionable_gaps(state.gaps,selected,self.cfg.provisional_mode)
        if required_missing:
            warnings+=['MISSING_REQUIRED_RULE:'+slot for slot in required_missing if slot in plan.slot_requirements]
        trace.timings_ms['selection']=round((time.perf_counter()-selection_started)*1000,2)
        if conflicts:
            conflict_ids={uid for pair in conflicts for uid in pair}
            selected=list({item.unit_id:item for item in selected+[x for x in verified if x.unit_id in conflict_ids]}.values())
            state=state_for(selected,plan,analysis.query_date,allow_fallback)
        imprecise_boundary_ids=[x.unit_id for x in selected if 'IMPRECISE_QUERY_DATE_OVERLAPS_VERSION_BOUNDARY' in x.audit_warnings]
        followup_questions=list(analysis.missing_facts) if clarify_during_answer else []
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
        status=Stop.CONFLICTING_EVIDENCE if conflicts else Stop.NEED_MORE_FACTS if imprecise_boundary_ids else Stop.SUFFICIENT if sufficient else Stop.PARTIAL_ALLOWED if partial else Stop.INSUFFICIENT_EVIDENCE
        partial_task_plan=None
        if status==Stop.INSUFFICIENT_EVIDENCE and self.cfg.allow_partial and not conflicts:
            from .tasks import independent_partial_plan
            partial_task_plan,partial_ids=independent_partial_plan(analysis,selected,allow_fallback)
            if partial_task_plan:
                selected=[item for item in selected if item.unit_id in partial_ids]
                state=state_for(selected,plan,analysis.query_date,allow_fallback)
                status=Stop.PARTIAL_ALLOWED; partial=True
                warnings.append('INDEPENDENT_TASK_RULES_ONLY')
        selected_decisions=[x for x in decisions if x.evidence_id in {item.unit_id for item in selected}]
        pack=observed('pack',build_verified_pack,env.normalized_query,analysis.query_date,analysis.facts,state,selected,selected_decisions,analysis.requested_outcome,summary=lambda v:{'so_nguon':len(v.evidence),'so_ky_tu':sum(len(x.text) for x in v.evidence),'trang_thai_du_kien':status.value})
        pack=pack.model_copy(update={'answer_tasks':analysis.answer_tasks,'resolved_rule_requirements':plan.slot_requirements})
        if (exact_only and lookup_scope_complete and len(analysis.explicit_references)==1
          and not conflicts and not analysis.facts and not analysis.legal_subissues
          and len(pack.evidence)==len(items)==len(selected)):
            pack=pack.model_copy(update={'lookup_reference':analysis.explicit_references[0]})
        adjudication_started=time.perf_counter()
        if status in {Stop.INSUFFICIENT_EVIDENCE,Stop.NEED_MORE_FACTS}:
            for key in ('adjudicator','answer_quality','semantic_review'): skip_step(key,'Chưa đủ căn cứ hoặc cần làm rõ ngày; không tạo kết luận')
            summary='Cần ngày chính xác để xác định phiên bản pháp luật áp dụng.' if status==Stop.NEED_MORE_FACTS else 'Không đủ bằng chứng đã xác minh để kết luận.'
            draft=AdjudicationDraft(answer_summary=summary,claims=[],applicable_law_versions=[],assumptions=assumptions,limitations=state.gaps)
            generation_warnings=[]; answer=draft.answer_summary; refs=[]
        else:
            checkpoint('generation')
            draft,generation_warnings=observed('adjudicator',self.adjudicator.generate,pack,partial,assumptions,summary=lambda r:{'so_claim':len(r[0].claims),'so_canh_bao':len(r[1]),'semantic_review':r[0].semantic_review.get('status','NOT_RUN')},status=lambda r:'WARNING' if r[1] else 'DONE')
            if draft.semantic_review.get('error_code')=='GEMINI_HTTP_429':
                raise ProviderRateLimited('GEMINI_HTTP_429')
            checkpoint()
            # Retrieval completeness does not establish answer completeness.
            # The public claims must actually cite every mandatory locator group.
            def missing_answer_slots(candidate):
                cited={uid for claim in candidate.claims for uid in claim.evidence_ids}
                output_state=state_for([item for item in selected if item.unit_id in cited],partial_task_plan or plan,analysis.query_date,allow_fallback)
                return _actionable_gaps(output_state.gaps,[item for item in selected if item.unit_id in cited],self.cfg.provisional_mode)
            missing_claims=missing_answer_slots(draft)
            if missing_claims and draft.semantic_review and 'ANSWER_QUALITY_BLOCKED' not in generation_warnings:
                generation_warnings.append('ANSWER_SEMANTIC_REVIEW_INCOMPLETE')
                # Structural repair cannot bypass the semantic checker. Keep
                # only independently checked parts and disclose incompleteness.
                draft=draft.model_copy(update={'limitations':list(dict.fromkeys(draft.limitations+['answer_coverage']))})
            if missing_claims and not draft.semantic_review and 'ANSWER_QUALITY_BLOCKED' not in generation_warnings:
                # One bounded deterministic repair, with the same vetted pack;
                # never fabricate a source or issue another inference request.
                repaired,repair_warnings=LegalAdjudicator(AdjudicationConfig()).generate(pack,partial,assumptions)
                if not missing_answer_slots(repaired) and 'ANSWER_QUALITY_BLOCKED' not in repair_warnings:
                    draft=repaired; generation_warnings+=repair_warnings+['ANSWER_REQUIRED_EVIDENCE_REPAIRED']
                else:
                    generation_warnings+=['ANSWER_REQUIRED_EVIDENCE_MISSING:'+','.join(missing_claims),'ANSWER_QUALITY_BLOCKED']
            if draft.semantic_review:
                trace.events.append({'event':'literal_source_audit' if draft.semantic_review.get('status')=='LITERAL_SOURCE_MATCH' else 'semantic_answer_audit',**draft.semantic_review})
            if 'ANSWER_SEMANTIC_REVIEW_INCOMPLETE' in generation_warnings:
                status=Stop.PARTIAL_ALLOWED
                state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+['answer_coverage']))})
            if clarify_during_answer and status==Stop.SUFFICIENT:
                status=Stop.PARTIAL_ALLOWED
                state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+['pending_facts']))})
            answer=draft.answer_summary
            if 'ANSWER_QUALITY_BLOCKED' in generation_warnings:
                status=Stop.INSUFFICIENT_EVIDENCE
                if any(warning.startswith('ANSWER_REQUIRED_EVIDENCE_MISSING:') for warning in generation_warnings):
                    quality_gap='answer_completeness'
                    answer='Câu trả lời còn thiếu nội dung pháp lý bắt buộc của câu hỏi. Cần bổ sung chuỗi căn cứ trước khi kết luận.'
                elif any(warning.startswith('ANSWER_SEMANTIC_REVIEW_ERROR:') for warning in generation_warnings):
                    from .answer_review import review_service_unavailable
                    if review_service_unavailable(draft.semantic_review):
                        quality_gap='review_service_unavailable'
                        answer='Dịch vụ kiểm tra câu trả lời tạm thời không phản hồi hoặc gặp lỗi. Chưa thể trả kết luận đã xác minh; vui lòng thử lại sau.'
                    else:
                        quality_gap='semantic_verification'
                        answer='Chưa xác minh được ý nghĩa pháp lý của câu trả lời. Không thể coi việc có trích dẫn là đủ để kết luận.'
                elif any(warning.startswith('SOURCE_TEXT_QUALITY:') for warning in generation_warnings):
                    quality_gap='source_text_quality'
                    answer='Nội dung nguồn có lỗi đọc chữ đáng ngờ. Cần đối chiếu bản gốc trước khi kết luận.'
                elif draft.semantic_review.get('status')=='FAIL':
                    quality_gap='semantic_support'
                    answer='Bước kiểm tra nội dung chưa xác nhận được kết luận từ các nguồn đã chọn. Chưa thể trả một câu trả lời pháp lý đáng tin cậy.'
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
        ok,problems=observed('reference_audit',reference_audit,answer,reference_items,refs,draft.claims,context_query=env.normalized_query,summary=lambda r:{'ket_qua':'PASS' if r[0] else 'FAIL','so_van_de':len(r[1])},status=lambda r:'DONE' if r[0] else 'WARNING')
        if not ok and draft.claims:
            repaired_answer,repaired_items,repaired_claims=_repair_references(selected,draft.claims)
            repaired_refs=citations(repaired_items)
            repaired_ok,repaired_problems=reference_audit(repaired_answer,repaired_items,repaired_refs,repaired_claims,context_query=env.normalized_query)
            if repaired_ok:
                answer=repaired_answer; selected=repaired_items; refs=repaired_refs; ok=True; problems=[]
                draft=draft.model_copy(update={'claims':repaired_claims}); warnings.append('REFERENCE_AUDIT_REPAIRED')
                preserved_gaps=[gap for gap in state.gaps if gap in {'answer_coverage','pending_facts'}]
                selected,state=select_for_plan(selected,plan,analysis.query_date,allow_fallback,len(selected))
                state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+preserved_gaps))})
                pack=build_verified_pack(env.normalized_query,analysis.query_date,analysis.facts,state,selected,
                  [x for x in decisions if x.evidence_id in {item.unit_id for item in selected}],analysis.requested_outcome)
                pack=pack.model_copy(update={'answer_tasks':analysis.answer_tasks,'resolved_rule_requirements':plan.slot_requirements})
                sufficient=bool(selected) and not state.gaps
                actionable_final=_actionable_gaps(state.gaps,selected,self.cfg.provisional_mode)
                partial=bool(selected) and not sufficient and not actionable_final and state.coverage>=self.cfg.minimum_coverage and self.cfg.allow_partial
                status=Stop.SUFFICIENT if sufficient else Stop.PARTIAL_ALLOWED if partial else Stop.INSUFFICIENT_EVIDENCE
                if partial_task_plan and selected:
                    subset=state_for(selected,partial_task_plan,analysis.query_date,allow_fallback)
                    if not _actionable_gaps(subset.gaps,selected,self.cfg.provisional_mode): status=Stop.PARTIAL_ALLOWED
                if selected and preserved_gaps and not _actionable_gaps([g for g in state.gaps if g not in preserved_gaps],selected,self.cfg.provisional_mode):
                    status=Stop.PARTIAL_ALLOWED
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
        from .tasks import assess_parts
        parts=observed('tasks',assess_parts,analysis,selected,draft.claims,draft.semantic_review,allow_fallback,getattr(self.store.report,'legal_ready',False),summary=lambda v:{'so_y':len(v),'trang_thai_tung_y':[p.answer_status for p in v]},status=lambda v:'WARNING' if any(p.answer_status!='ANSWERED' for p in v) else 'DONE')
        if parts and any(part.answer_status!='ANSWERED' for part in parts) and status==Stop.SUFFICIENT:
            status=Stop.PARTIAL_ALLOWED
            state=state.model_copy(update={'gaps':list(dict.fromkeys(state.gaps+['per_task_answer_completeness']))})
        trace.events.append({'event':'task_completeness','parts':[part.model_dump(mode='json') for part in parts]})
        trace.stop_reason=status
        trace.timings_ms['total']=round((time.perf_counter()-start)*1000,2); persist(trace,self.cfg.trace_dir)
        evidence_status='CONFLICTING' if status==Stop.CONFLICTING_EVIDENCE else 'NEED_MORE_FACTS' if status==Stop.NEED_MORE_FACTS else 'SUFFICIENT' if status==Stop.SUFFICIENT else 'PARTIAL' if status==Stop.PARTIAL_ALLOWED else 'INSUFFICIENT'
        if status in {Stop.SUFFICIENT,Stop.PARTIAL_ALLOWED} and 'CONTRACT.PROBATION_DURATION' in analysis.legal_subissues:
            import re
            if not analysis.facts.get('probation_work_group') and re.search(r'(?:thử việc[^.]{0,50}\b(?:\d+|một|hai|ba)\s*(?:ngày|tháng)\b|\b(?:\d+|một|hai|ba)\s*(?:ngày|tháng)\s+thử việc)',env.normalized_query.lower()):
                followup_questions.append('Công việc thuộc nhóm quản lý doanh nghiệp, cần trình độ từ cao đẳng, trung cấp/công nhân kỹ thuật/nhân viên nghiệp vụ, hay công việc khác?')
        return AnswerResponse(query_id=env.query_id,status=status,answer=answer,citations=refs,evidence_status=evidence_status,
          applicable_date=analysis.query_date,query_date=analysis.query_date,applicable_law_versions=draft.applicable_law_versions,
          claims=draft.claims,assumptions=draft.assumptions,limitations=state.gaps,questions=followup_questions,warnings=list(dict.fromkeys(warnings)),
          facts=analysis.facts,parts=parts,legal_status=getattr(self.store.report,'legal_status','PROVISIONAL'),
          build_id=trace.build_id,trace_id=trace.trace_id,trace=trace)
