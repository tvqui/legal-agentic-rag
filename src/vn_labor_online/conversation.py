"""Conservative context resolution from user turns, never assistant assertions."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .analysis import analyze, intake
from .taxonomy import profile_covers_issues,SUBISSUES


TOPIC_LABELS = {
    'CONTRACT': 'hợp đồng lao động', 'TERMINATION': 'chấm dứt hợp đồng lao động',
    'WAGE': 'tiền lương', 'LEAVE': 'nghỉ phép', 'WORKING_TIME': 'thời giờ làm việc',
    'DISCIPLINE': 'kỷ luật lao động', 'TRAINING': 'đào tạo nghề',
    'SOCIAL_INSURANCE': 'bảo hiểm xã hội', 'HARASSMENT': 'quấy rối tại nơi làm việc',
    'SAFETY': 'an toàn lao động', 'DISPUTE': 'tranh chấp lao động',
    'MATERNITY': 'thai sản', 'UNION': 'công đoàn', 'FOREIGN_WORKER': 'lao động nước ngoài',
    'UNEMPLOYMENT_INSURANCE': 'bảo hiểm thất nghiệp', 'MINOR_WORKER': 'lao động chưa thành niên',
    'RETIREMENT': 'nghỉ hưu', 'OVERSEAS_WORKER': 'đi làm việc ở nước ngoài',
    'COLLECTIVE_RELATIONS': 'quan hệ lao động tập thể',
}
RESET = re.compile(r'\b(?:chuyện khác|vấn đề khác|tình huống mới|trường hợp khác|công ty khác|giả sử|giả định|nếu như|nếu tôi|nếu công ty|đổi chủ đề)\b', re.I)
FOLLOWUP = re.compile(r'^(?:(?:nếu\s+)?(?:hết|sau|trong)\s+(?:thời gian|thời hạn|giai đoạn)\s+(?:đó|này)\b|còn\b|vậy\b|thế\b|thì\b|trường hợp (?:đó|này)|điều đó|việc đó|thử bao lâu|bao lâu|bao nhiêu|bao giờ|khi nào|mấy (?:ngày|tháng|năm)|tại sao|vì sao|tôi làm\b|tôi là\b|tôi chỉ\b|thực ra\b|đính chính\b|tôi sửa\b|lương (?:là|của)|ngày (?:là|dự kiến)|không thuộc\b)', re.I)


FACT_REPLY = re.compile(
    r'^(?:tôi\s+(?:(?:không|chưa)\s+)?(?:làm|là|thuộc|chỉ)\b|'
    r'(?:công việc|ngành nghề|nghề|hợp đồng|mức lương|loại hợp đồng)\s+'
    r'(?:(?:của tôi|này)\s+)?(?:là|không|chưa|thuộc)\b|'
    r'tôi bổ sung\b|bổ sung(?: dữ kiện| thông tin| thêm| cho cùng vụ việc)?\s*[:：]|'
    r'thực ra\b|đính chính\b|tôi sửa\b|lương (?:là|của)|'
    r'ngày (?:là|dự kiến)|không thuộc\b)', re.I)
CORRECTION = re.compile(r'^(?:đính chính\b|(?:tôi\s+)?xin\s+đính chính\b|tôi sửa\b|tôi xin sửa\b|sửa lại\b|xin sửa\b|thông tin trước .*? sai\b)', re.I)
CONFIRMATION = re.compile(r'^(?:(?:tôi\s+)?(?:xin\s+)?xác nhận\b|thông tin đúng là\b)', re.I)
TEMPORAL_CHANGE = re.compile(
    r'\b(?:từ|kể từ|áp dụng từ|tăng từ|giảm từ)\s+(?:ngày|tháng)\b|'
    r'\b(?:mức lương|lương công việc)[^.?!]{0,80}\b(?:tăng|giảm|thay đổi)\b',
    re.I,
)
MATERIAL_FACTS = {
    'contract_type', 'contract_duration_months', 'termination_basis', 'notice_days', 'notice_exception',
    'termination_date', 'work_category', 'special_occupation',
    'protected_status', 'salary_base_amount', 'salary_base_unit',
}
FACT_LABELS = {
    'contract_type': 'loại hợp đồng', 'contract_duration_months': 'thời hạn hợp đồng',
    'termination_basis': 'lý do chấm dứt',
    'notice_days': 'thời gian báo trước', 'notice_exception': 'trường hợp miễn báo trước',
    'termination_date': 'ngày chấm dứt', 'work_category': 'nhóm công việc',
    'special_occupation': 'ngành, nghề hoặc công việc đặc thù',
    'protected_status': 'tình trạng được bảo vệ',
    'salary_base_amount': 'mức lương công việc', 'salary_base_unit': 'đơn vị tiền lương',
}


@dataclass
class ResolvedContext:
    query: str
    facts: dict = field(default_factory=dict)
    provenance: list[dict] = field(default_factory=list)
    used_turns: list[str] = field(default_factory=list)
    clarification: str | None = None
    clarification_reason: str | None = None
    query_date: str | None = None


def _topic(analysis):
    if any(k.startswith('CONTRACT.PROBATION_') for k in analysis.legal_subissues) or analysis.facts.get('contract_type') == 'PROBATION':
        return 'thử việc'
    issues = [i for i in analysis.legal_issues if i != 'GENERAL']
    if not issues and analysis.facts.get('contract_type'):
        return TOPIC_LABELS['CONTRACT']
    if len(issues)>1 and profile_covers_issues(analysis):
        parents={key.split('.')[0] for key in analysis.legal_subissues}
        if len(parents)==1: issues=list(parents)
    if len(issues)>1 and 'CONTRACT' in issues:
        issues.remove('CONTRACT')
    return TOPIC_LABELS.get(issues[0]) if len(issues) == 1 else None


def _provenance_record(turn_id, text, candidate, status='USER_REPORTED'):
    pattern=r'\s+'.join(re.escape(word) for word in candidate.source_quote.split())
    matches=list(re.finditer(pattern,text)) if pattern else []
    if len(matches)!=1:
        return None
    start,end=matches[0].span()
    return {'field':candidate.field,'value':candidate.value,'turn_id':turn_id,
        'source_quote':text[start:end],'char_start':start,'char_end':end,'status':status}


def resolve_context(request):
    current = analyze(intake(request.question, [], request.query_date, request.facts), request.query_date, request.facts)
    result = ResolvedContext(request.question)
    if not current.in_scope and not request.conversation_turns and not request.conversation_context:
        return result
    current_records=[record for candidate in current.fact_candidates
        if candidate.verified and (record:=_provenance_record('current_request',request.question,candidate))]
    correction=bool(CORRECTION.search(request.question.strip()) or CONFIRMATION.search(request.question.strip()))
    if RESET.search(request.question) and not correction:
        result.facts=dict(current.facts)
        result.provenance=current_records
        result.query_date=current.query_date
        return result
    # Typed turns are preferred. Legacy context remains user-only for compatibility.
    turns = [(t.turn_id, t.content) for t in request.conversation_turns] if request.conversation_turns else [
        (f'legacy_{i}', text) for i, text in enumerate(request.conversation_context)]
    active = []
    topic = None
    for turn_id, text in turns[-20:]:
        envelope = intake(text, [])
        # Old browser history can contain accidental one-character messages.
        # They are not legal context and must not break a later valid question.
        if len(envelope.normalized_query) < 2:
            continue
        analysis = analyze(envelope)
        next_topic = _topic(analysis)
        if RESET.search(text) or not analysis.in_scope:
            active, topic = [], None
            # Hypothetical scenarios must never become the next turn's personal facts.
            continue
        continuing_subtopic = topic == 'thử việc' and next_topic == TOPIC_LABELS['WAGE'] and (
            FOLLOWUP.search(text.strip()) or FACT_REPLY.search(text.strip()))
        related_contract_turn=(topic in {TOPIC_LABELS['CONTRACT'],TOPIC_LABELS['TERMINATION']}
            and next_topic in {TOPIC_LABELS['CONTRACT'],TOPIC_LABELS['TERMINATION']}
            and bool(FOLLOWUP.search(text.strip()) or FACT_REPLY.search(text.strip())
                or CORRECTION.search(text.strip()) or CONFIRMATION.search(text.strip())))
        if next_topic and next_topic != topic and not continuing_subtopic and not related_contract_turn:
            active = []
            topic = next_topic
        if topic:
            active.append((turn_id, text, analysis))
    current_topic = _topic(current)
    continuation = bool(FOLLOWUP.search(request.question.strip()) or FACT_REPLY.search(request.question.strip()) or correction)
    related_subtopic = topic == 'thử việc' and current_topic == TOPIC_LABELS['WAGE']
    prior_fact_fields={candidate.field for _,_,analysis in active
        for candidate in analysis.fact_candidates if candidate.verified}
    current_fact_fields={candidate.field for candidate in current.fact_candidates if candidate.verified}
    correction_matches_prior=correction and bool(prior_fact_fields.intersection(current_fact_fields))
    same_topic=current_topic==topic
    prior_issues={issue for _,_,analysis in active for issue in analysis.legal_issues}
    current_issues=set(current.legal_issues)
    prior_probation=topic=='thử việc' or any(
        key.startswith('CONTRACT.PROBATION_') for _,_,analysis in active for key in analysis.legal_subissues)
    current_probation=current.facts.get('contract_type')=='PROBATION' or any(
        key.startswith('CONTRACT.PROBATION_') for key in current.legal_subissues)
    contract_termination_related=not prior_probation and not current_probation and (
        ('TERMINATION' in current_issues and 'contract_type' in prior_fact_fields) or
        ('TERMINATION' in prior_issues and 'contract_type' in current_fact_fields))
    related_issue_context=bool(prior_issues.intersection(current_issues))
    if not active or (current_topic and current_topic != topic and not related_subtopic and
      not correction_matches_prior and not contract_termination_related and not related_issue_context) or (
        not continuation and not same_topic and not correction_matches_prior and
        not contract_termination_related and not related_issue_context):
        if active and current_topic and re.match(r'^(?:còn|vậy|thế|thì)\b',request.question.strip(),re.I):
            result.clarification=f'Bạn đang hỏi tiếp về cùng trường hợp {topic}, hay chuyển sang một tình huống khác?'
            result.clarification_reason='AMBIGUOUS_FOLLOWUP'
        if continuation and not current_topic:
            result.clarification = 'Bạn đang hỏi tiếp về vấn đề nào? Vui lòng nêu chủ đề hoặc hoàn cảnh cần tra cứu.'
            result.clarification_reason='AMBIGUOUS_FOLLOWUP'
        return result
    prior_actor=next((a.facts['actor'] for _,_,a in reversed(active) if a.facts.get('actor')),None)
    if current.facts.get('actor') and prior_actor and current.facts['actor']!=prior_actor and not correction:
        # A party switch is a separate scenario, not a correction to the old case.
        result.facts=dict(current.facts)
        result.provenance=current_records
        result.query_date=current.query_date
        return result
    temporal_change=bool(TEMPORAL_CHANGE.search(request.question))
    sources={}
    conflicts=set()
    for turn_id, text, analysis in active:
        turn_actor=analysis.facts.get('actor')
        previous_actor=sources.get('actor',(None,None))[0]
        if turn_actor and previous_actor and turn_actor!=previous_actor and not (
            CORRECTION.search(text.strip()) or CONFIRMATION.search(text.strip())):
            # A change in the acting party starts a new user-described scenario.
            sources.clear()
            result.provenance=[]
            conflicts.clear()
        for candidate in analysis.fact_candidates:
            if not candidate.verified:
                continue
            record=_provenance_record(turn_id,text,candidate)
            if record is None:
                continue
            previous=sources.get(candidate.field)
            if previous and previous[0]!=candidate.value:
                previous_record=result.provenance[previous[1]]
                if CORRECTION.search(text.strip()) or CONFIRMATION.search(text.strip()):
                    previous_record.update(status='SUPERSEDED',superseded_by=turn_id)
                    record['supersedes']=[previous_record['turn_id']]
                    conflicts.discard(candidate.field)
                elif candidate.field in {'salary_base_amount','salary_base_unit'} and TEMPORAL_CHANGE.search(text):
                    previous_record.update(status='SUPERSEDED_BY_TIME',effective_to=analysis.query_date)
                    record['effective_from']=analysis.query_date
                elif candidate.field in MATERIAL_FACTS:
                    previous_record['status']='CONFLICT'
                    record['status']='CONFLICT'
                    conflicts.add(candidate.field)
                else:
                    previous_record.update(status='UPDATED',superseded_by=turn_id)
            result.provenance.append(record)
            sources[candidate.field]=(candidate.value,len(result.provenance)-1)
            if CORRECTION.search(text.strip()) or CONFIRMATION.search(text.strip()):
                conflicts.discard(candidate.field)
                for old in result.provenance[:-1]:
                    if old['field']==candidate.field and old.get('status')=='CONFLICT':
                        old.update(status='SUPERSEDED',superseded_by=turn_id)
                record['status']='USER_REPORTED'
        result.query_date = analysis.query_date or result.query_date
        result.used_turns.append(turn_id)
    result.facts={field:value for field,(value,_) in sources.items() if field not in conflicts}
    for candidate in current.fact_candidates:
        if not candidate.verified: continue
        record=_provenance_record('current_request',request.question,candidate)
        if record is None: continue
        previous=sources.get(candidate.field)
        if previous and previous[0]!=candidate.value:
            previous_record=result.provenance[previous[1]]
            if correction:
                previous_record.update(status='SUPERSEDED',superseded_by='current_request')
                record['supersedes']=[previous_record['turn_id']]
                conflicts.discard(candidate.field)
            elif candidate.field in {'salary_base_amount','salary_base_unit'} and temporal_change:
                previous_record.update(status='SUPERSEDED_BY_TIME',effective_to=current.query_date)
                record['effective_from']=current.query_date
            elif candidate.field in MATERIAL_FACTS:
                previous_record['status']='CONFLICT'
                record['status']='CONFLICT'
                conflicts.add(candidate.field)
            else:
                previous_record.update(status='UPDATED',superseded_by='current_request')
        result.provenance.append(record)
        sources[candidate.field]=(candidate.value,len(result.provenance)-1)
        if correction:
            # Explicitly confirming either of the previously conflicting values
            # resolves this field, including when it equals the latest value.
            for old in result.provenance[:-1]:
                if old['field']==candidate.field and old.get('status')=='CONFLICT':
                    old.update(status='SUPERSEDED',superseded_by='current_request')
            record['status']='USER_REPORTED'
            conflicts.discard(candidate.field)
        if candidate.field not in conflicts:
            result.facts[candidate.field]=candidate.value
    # Current extraction, including explicit negations/corrections, wins unless
    # a material same-case contradiction still needs user confirmation.
    for field,value in current.facts.items():
        if field in conflicts:
            result.facts.pop(field,None)
        else:
            result.facts[field]=value
    if conflicts:
        labels=', '.join(FACT_LABELS.get(field,field) for field in sorted(conflicts))
        result.clarification=f'Thông tin về {labels} đang mâu thuẫn trong cùng trường hợp. Bạn xác nhận dữ kiện nào là đúng?'
        result.clarification_reason='MATERIAL_FACT_CONFLICT'
        return result
    if result.facts.get('contract_type') in {'INDEFINITE','PROBATION'}:
        result.facts.pop('contract_duration_months',None)
        for record in result.provenance:
            if record['field']=='contract_duration_months' and record.get('status')=='USER_REPORTED':
                record.update(status='SUPERSEDED',superseded_by='contract_type')
    if not continuation:
        return ResolvedContext(request.question,facts=dict(current.facts),
          provenance=current_records,query_date=current.query_date)
    resolved_topic=topic if related_subtopic else current_topic or topic
    result.query = f'Về {resolved_topic}: {request.question}'
    # A factual reply resumes the prior requested tasks, not every old question
    # or its outdated numbers. Labels come from the versioned taxonomy.
    fact_reply=FACT_REPLY.search(request.question.strip())
    if fact_reply and not re.search(r'\?|bao lâu|bao nhiêu|có đúng|quy định gì|thì sao',request.question,re.I):
        previous=next((a for _,_,a in reversed(active) if a.legal_subissues),None)
        if previous:
            labels='; '.join(dict.fromkeys(task.description for task in previous.answer_tasks))
            if not labels:
                labels='; '.join(SUBISSUES[k] for k in previous.legal_subissues if k in SUBISSUES)
            result.query=f'Về {resolved_topic}: Câu hỏi trước gồm các nội dung: {labels}. Dữ kiện bổ sung: {request.question}'
            if previous.requested_outcome=='ASSESS_LEGALITY':
                result.query+=' Yêu cầu trước cần đánh giá: có đúng quy định không?'
    result.query_date = current.query_date or result.query_date
    return result
