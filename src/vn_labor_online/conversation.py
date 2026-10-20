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


@dataclass
class ResolvedContext:
    query: str
    facts: dict = field(default_factory=dict)
    provenance: list[dict] = field(default_factory=list)
    used_turns: list[str] = field(default_factory=list)
    clarification: str | None = None
    query_date: str | None = None


def _topic(analysis):
    if any(k.startswith('CONTRACT.PROBATION_') for k in analysis.legal_subissues) or analysis.facts.get('contract_type') == 'PROBATION':
        return 'thử việc'
    issues = [i for i in analysis.legal_issues if i != 'GENERAL']
    if len(issues)>1 and profile_covers_issues(analysis):
        parents={key.split('.')[0] for key in analysis.legal_subissues}
        if len(parents)==1: issues=list(parents)
    if len(issues)>1 and 'CONTRACT' in issues:
        issues.remove('CONTRACT')
    return TOPIC_LABELS.get(issues[0]) if len(issues) == 1 else None


def resolve_context(request):
    current = analyze(intake(request.question, [], request.query_date, request.facts), request.query_date, request.facts)
    result = ResolvedContext(request.question)
    if not current.in_scope or RESET.search(request.question):
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
        continuing_subtopic = topic == 'thử việc' and next_topic == TOPIC_LABELS['WAGE'] and FOLLOWUP.search(text.strip())
        if next_topic and next_topic != topic and not continuing_subtopic:
            active = []
            topic = next_topic
        if topic:
            active.append((turn_id, text, analysis))
    current_topic = _topic(current)
    continuation = bool(FOLLOWUP.search(request.question.strip()))
    related_subtopic = topic == 'thử việc' and current_topic == TOPIC_LABELS['WAGE']
    if not active or (current_topic and current_topic != topic and not related_subtopic):
        if active and current_topic and re.match(r'^(?:còn|vậy|thế|thì)\b',request.question.strip(),re.I):
            result.clarification=f'Bạn đang hỏi tiếp về cùng trường hợp {topic}, hay chuyển sang một tình huống khác?'
        if continuation and not current_topic:
            result.clarification = 'Bạn đang hỏi tiếp về vấn đề nào? Vui lòng nêu chủ đề hoặc hoàn cảnh cần tra cứu.'
        return result
    # An independent, well-specified question must not silently inherit an old case.
    if not continuation:
        return result
    prior_actor=next((a.facts['actor'] for _,_,a in reversed(active) if a.facts.get('actor')),None)
    if current.facts.get('actor') and prior_actor and current.facts['actor']!=prior_actor:
        # Switching party is a new applicability scenario, not a fact correction.
        return result
    for turn_id, text, analysis in active:
        for candidate in analysis.fact_candidates:
            if not candidate.verified:
                continue
            # Parser offsets refer to normalized text. Rebase against the exact
            # original user turn before retaining a fact as conversation memory.
            pattern=r'\s+'.join(re.escape(word) for word in candidate.source_quote.split())
            matches=list(re.finditer(pattern,text)) if pattern else []
            if len(matches)!=1:
                continue
            start,end=matches[0].span()
            result.facts[candidate.field] = candidate.value
            result.provenance = [p for p in result.provenance if p['field'] != candidate.field]
            result.provenance.append({'field': candidate.field, 'turn_id': turn_id,
                'source_quote': text[start:end], 'char_start': start,
                'char_end': end, 'status': 'USER_REPORTED'})
        result.query_date = analysis.query_date or result.query_date
        result.used_turns.append(turn_id)
    # Current extraction, including explicit negations/corrections, wins over memory.
    result.facts.update(current.facts)
    result.provenance = [p for p in result.provenance if p['field'] not in current.facts]
    result.query = f'Về {topic}: {request.question}'
    # A factual reply resumes the prior requested tasks, not every old question
    # or its outdated numbers. Labels come from the versioned taxonomy.
    fact_reply=re.match(r'^(?:tôi làm\b|tôi là\b|tôi chỉ\b|thực ra\b|đính chính\b|tôi sửa\b|lương (?:là|của)|ngày (?:là|dự kiến)|không thuộc\b)',request.question.strip(),re.I)
    if fact_reply and not re.search(r'\?|bao lâu|bao nhiêu|có đúng|quy định gì|thì sao',request.question,re.I):
        previous=next((a for _,_,a in reversed(active) if a.legal_subissues),None)
        if previous:
            labels='; '.join(SUBISSUES[k] for k in previous.legal_subissues if k in SUBISSUES)
            result.query=f'Về {topic}: {labels}. Dữ kiện bổ sung: {request.question}'
            if previous.requested_outcome=='ASSESS_LEGALITY':
                result.query+=' Yêu cầu trước cần đánh giá: có đúng quy định không?'
    result.query_date = current.query_date or result.query_date
    return result
