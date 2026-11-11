"""Bounded, source-dated subrequests for general rule explanations over a range.

Every slice runs the existing retrieval, agents and checks. Aggregation adds
only date labels and preserves per-slice failures; it infers no new legal claim.
Concrete multi-event cases still need event/fact disambiguation.
"""
from dataclasses import dataclass
from datetime import date,timedelta
import hashlib
import re
import time
from .date_mentions import date_mentions
from .models import AnswerResponse,Trace,Route,Stop

@dataclass(frozen=True)
class RulePeriod:
    start: str
    end: str
    question: str


def rule_periods(request,store,max_periods=4,*,retriever=None):
    if request.query_date or request.facts or request.conversation_turns or request.conversation_context:return []
    query=request.question
    from .analysis import analyze,intake
    analysis=analyze(intake(query,[]))
    if not analysis.in_scope or analysis.requested_outcome=='ASSESS_LEGALITY':return []
    concrete={'actor','notice_days','notice_date','termination_date','probation_duration_value','salary_base_amount'}
    if concrete.intersection(analysis.facts):return []
    # Do not flatten dated events/parties or turn a factual assessment into a
    # generic rule explanation. Such requests use the existing clarification.
    if re.search(r'\b(?:tôi|của tôi|đã|bị|khởi kiện|khiếu nại)\b',query,re.I):return []
    mentions=date_mentions(query)
    if len(mentions)!=2 or any(not m.valid or m.precision!='DAY' for m in mentions):return []
    first,last=mentions
    prefix=re.search(r'\b(?:trong\s+khoảng\s+)?từ\s*(?:ngày\s*)?$',query[:first.char_start],re.I)
    if not prefix or not re.fullmatch(r'\s*(?:đến|tới|[-–])\s*(?:ngày\s*)?',query[first.char_end:last.char_start],re.I):return []
    start,end=date.fromisoformat(first.start),date.fromisoformat(last.start)
    if start>=end:return []
    bounds={start,end+timedelta(days=1)}
    units=getattr(store,'units',[])
    if retriever is not None:
        from .analysis import plan_evidence
        from .taxonomy import profile_covers_issues
        # Scoped, closed request plans can use the existing indexed statutory
        # anchors at both regimes. Unknown requests retain the conservative
        # corpus-wide fallback rather than guessing their relevant instruments.
        probes=[];closed=True
        undated=query[:prefix.start()]+query[last.char_end:]
        for point in (start.isoformat(),end.isoformat()):
            probe=analyze(intake(undated,[],point),point)
            if not profile_covers_issues(probe):closed=False;break
            anchors=retriever.policy_anchor(probe.legal_issues,probe.facts,plan_evidence(probe))
            if not anchors:closed=False;break
            probes.extend(anchors)
        if closed:
            ids={item.unit_id for item in probes}
            units=[store.units_by_id[uid] for uid in ids if uid in store.units_by_id]
    for unit in units:
        for key in ('valid_from','valid_to','promulgated_date','consolidation_as_of'):
            value=unit.get(key)
            if not value:continue
            try:boundary=date.fromisoformat(value)
            except (ValueError,TypeError):continue
            if start<boundary<=end:bounds.add(boundary)
    snapshot=getattr(getattr(store,'cfg',None),'corpus_snapshot_as_of',None)
    if snapshot:
        try:boundary=date.fromisoformat(snapshot)+timedelta(days=1)
        except (ValueError,TypeError):boundary=None
        if boundary and start<boundary<=end:bounds.add(boundary)
    ordered=sorted(bounds)
    if len(ordered)-1>max_periods:return []
    periods=[]
    scoped_query=query[:prefix.start()]+query[last.char_end:]
    # A comparison instruction belongs to the aggregate response, not every
    # dated subrequest. Keeping it in each slice makes a later period ask for
    # statutes from earlier regimes that are correctly excluded by date.
    scoped_query=re.sub(
        r'\s*(?:[.?!]\s*)?(?:nếu|trường hợp)\s+(?:quy định|pháp luật|văn bản|điều luật)\b[^.?!]{0,120}'
        r'\b(?:thay đổi|khác nhau)\b[^.?!]{0,80}\b(?:hãy|cần)\s+(?:phân biệt|so sánh|nêu rõ)\b[^.?!]*[.?!]?\s*$',
        '',scoped_query,flags=re.I)
    for left,right in zip(ordered,ordered[1:]):
        # Replace only the exact range header. Preserve all substantive user
        # words; no legal answer, citation or asserted fact is added here.
        scoped=scoped_query[:prefix.start()]+f'Tại ngày {left.isoformat()}'+scoped_query[prefix.start():]
        if len(scoped)>10000:return []
        periods.append(RulePeriod(left.isoformat(),(right-timedelta(days=1)).isoformat(),scoped))
    return periods


def combine_period_answers(request,periods,responses):
    if len(periods)!=len(responses) or not responses:raise ValueError('period answer accounting mismatch')
    if len({response.build_id for response in responses})!=1:raise ValueError('period artifact mismatch')
    query_id='query_'+hashlib.sha256(request.model_dump_json().encode()).hexdigest()[:16]
    trace=Trace(trace_id='trace_'+hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16],
        query_id=query_id,build_id=responses[0].build_id,route=Route.COMPLEX,route_reason='independently audited dated periods')
    lines=[];claims=[];citations={};parts=[];warnings=[];limitations=[];questions=[];assumptions=[];versions={}
    has_content=False
    for index,(period,response) in enumerate(zip(periods,responses),1):
        checked=response.trace.reference_audit=='PASS'
        public=response.status in {Stop.SUFFICIENT,Stop.PARTIAL_ALLOWED} and bool(response.claims) and checked
        has_content=has_content or public
        lines.append(f'Giai đoạn {index}: {period.start} đến {period.end}')
        lines.append(response.answer if not response.claims or checked else 'Chưa xác minh được trích dẫn của phần trả lời này.')
        prefix=f'period_{index}_'
        if checked:
            for citation in response.citations:citations[citation.evidence_id]=citation
        if public:
            claims.extend(claim.model_copy(update={'claim_id':prefix+claim.claim_id}) for claim in response.claims)
            for version in response.applicable_law_versions:versions[version.model_dump_json()]=version
        for part in response.parts:
            parts.append(part.model_copy(update={'task_id':prefix+part.task_id,
                'description':f'{period.start} – {period.end}: {part.description}',
                'claim_ids':[prefix+uid for uid in part.claim_ids] if public else [],
                'answer_status':part.answer_status if public else 'MISSING'}))
        if not response.parts:
            from .models import AnswerPart
            parts.append(AnswerPart(task_id=prefix+'question',question=request.question,
                description=f'Quy định trong khoảng {period.start} – {period.end}',
                answer_status='PARTIAL' if public else 'MISSING',
                evidence_status='PARTIAL' if public else 'MISSING',
                evidence_ids=[citation.evidence_id for citation in response.citations] if public else [],
                claim_ids=[prefix+claim.claim_id for claim in response.claims] if public else [],
                missing_requirements=response.questions or response.limitations or ['period_completeness_not_checked']))
        warnings+=response.warnings;limitations+=response.limitations;assumptions+=response.assumptions
        questions.extend(f'{period.start} – {period.end}: {question}' for question in response.questions)
        trace.events.append({'event':'dated_period','start':period.start,'end':period.end,
            'status':response.status.value,'trace':response.trace.model_dump(mode='json')})
        trace.retrieval_rounds+=response.trace.retrieval_rounds
        trace.nodes_visited+=response.trace.nodes_visited;trace.edges_visited+=response.trace.edges_visited
        trace.verified_evidence_count+=response.trace.verified_evidence_count
        for name,milliseconds in response.trace.timings_ms.items():
            trace.timings_ms[name]=round(trace.timings_ms.get(name,0)+milliseconds,3)
    # Separate checked rule explanations are useful; they are not an
    # independently verified cross-period synthesis or legal-change history.
    status=Stop.PARTIAL_ALLOWED if has_content else (
        Stop.ABSTAIN if all(r.status==Stop.ABSTAIN for r in responses) else
        Stop.CONFLICTING_EVIDENCE if any(r.status==Stop.CONFLICTING_EVIDENCE for r in responses) else
        Stop.NEED_MORE_FACTS if all(r.status==Stop.NEED_MORE_FACTS for r in responses) else Stop.INSUFFICIENT_EVIDENCE)
    limitations.append('cross_period_synthesis_not_verified')
    trace.reference_audit='PASS' if claims and all(r.trace.reference_audit=='PASS' for r in responses if r.claims) else 'NOT_RUN'
    trace.stop_reason=status
    return AnswerResponse(query_id=query_id,status=status,answer='\n\n'.join(lines),
        citations=list(citations.values()),claims=claims,evidence_status='PARTIAL' if has_content else 'INSUFFICIENT',
        applicable_law_versions=list(versions.values()),parts=parts,
        assumptions=list(dict.fromkeys(assumptions)),limitations=list(dict.fromkeys(limitations)),
        questions=list(dict.fromkeys(questions)),warnings=list(dict.fromkeys(warnings+['DATED_PERIODS_SEPARATELY_AUDITED'])),
        legal_status='REVIEWED' if all(r.legal_status=='REVIEWED' for r in responses) else 'PROVISIONAL',
        build_id=responses[0].build_id,trace_id=trace.trace_id,trace=trace)
