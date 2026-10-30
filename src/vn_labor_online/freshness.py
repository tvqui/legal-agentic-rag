"""Expose the actual temporal coverage; a warning never certifies new law."""
from .models import Stop
from datetime import date

def _reviewed_until(unit):
    value=unit.get('temporal_coverage_as_of')
    if unit.get('provision_temporal_verified') is not True or not isinstance(value,str):return None
    try:return value if date.fromisoformat(value).isoformat()==value else None
    except ValueError:return None

def qualify_freshness(response,store,snapshot,allow_partial=True):
    if not response.citations:return response
    requested=response.query_date or response.applicable_date
    if response.trace:
        analysis=next((event for event in response.trace.events if event.get('event')=='analysis'),{})
        requested=analysis.get('query_date_end') or requested
    if not requested:return response
    docs={}
    for citation in response.citations:
        unit=getattr(store,'units_by_id',{}).get(citation.evidence_id,{})
        reviewed_until=_reviewed_until(unit)
        current=bool(reviewed_until and reviewed_until>=requested)
        within_snapshot=bool(snapshot and requested<=snapshot)
        docs[citation.evidence_id]={'document_id':unit.get('document_id'),
            'requested_until':requested,'snapshot_as_of':snapshot,'reviewed_until':reviewed_until,
            'status':'WITHIN_CORPUS_SNAPSHOT' if within_snapshot else 'REVIEWED_THROUGH_DATE' if current else 'FRESHNESS_UNVERIFIED'}
    unverified=any(v['status']=='FRESHNESS_UNVERIFIED' for v in docs.values())
    if response.trace:response.trace.events.append({'event':'document_freshness','evidence':docs,'unverified':unverified})
    if unverified:
        qualification=(f'Kết quả chỉ dựa trên dữ liệu chốt đến {snapshot}; chưa xác minh đầy đủ các thay đổi sau ngày này.'
            if snapshot else 'Chưa xác định được ngày chốt dữ liệu; chưa thể xác nhận các căn cứ đã cập nhật đến thời điểm bạn hỏi.')
        if qualification not in response.answer:response.answer=qualification+'\n\n'+response.answer
        response.warnings=list(dict.fromkeys(response.warnings+['CORPUS_MAY_BE_STALE']))
        response.limitations=list(dict.fromkeys(response.limitations+['FRESHNESS_UNVERIFIED']))
        response.legal_status='PROVISIONAL'
        if not allow_partial:
            response.status=Stop.INSUFFICIENT_EVIDENCE
            response.answer=qualification+' Chưa thể đưa ra kết luận cho thời điểm được hỏi.'
            response.claims=[];response.applicable_law_versions=[]
            for part in response.parts:
                part.answer_status='NOT_CHECKED';part.claim_ids=[]
                part.missing_requirements=list(dict.fromkeys(part.missing_requirements+['FRESHNESS_UNVERIFIED']))
            if response.trace:response.trace.stop_reason=response.status
        if response.status==Stop.SUFFICIENT:
            response.status=Stop.PARTIAL_ALLOWED
            if response.trace:response.trace.stop_reason=response.status
    return response
