"""Deterministic request tasks and separate evidence/answer completeness.

Routing labels never establish legal sufficiency. Only a validated semantic
verdict may mark an inferred substantive task ANSWERED.
"""
from __future__ import annotations
import hashlib,re
from .models import AnswerTask,AnswerPart
from .topics import detect_topics

REQUEST=re.compile(r'\?|hãy|cho biết|giải thích|bao nhiêu|bao lâu|thế nào|đúng không|được không|hay không|căn cứ nào|quy định gì|có quyền|phải làm gì',re.I)

def deterministic_tasks(query,subissues,topics,labels,route,outcome='EXPLAIN'):
    if route.value=='DIRECT': return []
    tasks=[]
    for key in subissues:
        description=labels[key]
        tasks.append(AnswerTask(task_id='issue_'+hashlib.sha256(key.encode()).hexdigest()[:10],
          request_quote=query,description=description,retrieval_query=description,
          legal_subissues=[key],legal_issues=[key.split('.')[0]],origin='DETERMINISTIC'))
    sentences=[s.strip() for s in re.split(r'(?<=[.?!])\s+|\n+',query) if s.strip()]
    request_spans=[]
    for sentence in sentences:
        # In "If [background], what repayment applies?", the conditional is
        # context, not a separate request to adjudicate termination legality.
        # Existing classified subissues are retained, including an explicit
        # request about notice alongside repayment.
        conditional=re.match(r'^(?:khi|nếu)\b.+?[,;]\s*(.+)$',sentence,re.I)
        span=conditional.group(1) if conditional and REQUEST.search(conditional.group(1)) else sentence
        if REQUEST.search(span): request_spans.append(span)
    explicit_topics={t.key for span in request_spans for t in detect_topics(span)}
    for topic in topics:
        if any(any(key.startswith(prefix) for prefix in topic.profile_prefixes) for key in subissues): continue
        if tasks and topic.key not in explicit_topics: continue
        tasks.append(AnswerTask(task_id='topic_'+topic.key,request_quote=query,
          description=topic.label,retrieval_query=topic.label,legal_issues=[topic.issue],
          topic_ids=[topic.key],origin='DETERMINISTIC'))
    if not tasks:
        tasks=[AnswerTask(task_id='question',request_quote=query,description=query,retrieval_query=query,origin='DETERMINISTIC')]
    if len(tasks)==1: tasks[0]=tasks[0].model_copy(update={'task_id':'question'})
    if outcome=='ASSESS_LEGALITY':
        by_issue={key:task.task_id for task in tasks for key in task.legal_subissues}
        dependencies={'TERMINATION.ILLEGAL_TERMINATION':['TERMINATION.EMPLOYEE_UNILATERAL','TERMINATION.EMPLOYER_UNILATERAL'],
          'TERMINATION.EMPLOYEE_LIABILITY':['TERMINATION.ILLEGAL_TERMINATION'],
          'TERMINATION.EMPLOYER_LIABILITY':['TERMINATION.ILLEGAL_TERMINATION']}
        for task in tasks:
            task.depends_on=list(dict.fromkeys(by_issue[key] for subissue in task.legal_subissues
              for key in dependencies.get(subissue,[]) if key in by_issue))
    if len(tasks)>12:
        # Preserve the full question as one accounting task rather than silently
        # dropping the 13th requested issue from the schema's bounded list.
        return [AnswerTask(task_id='question',request_quote=query,description=query,retrieval_query=query,origin='DETERMINISTIC')]
    return tasks

def merge_tasks(deterministic,proposed):
    """LLM decomposition can add detail, never silently delete baseline requests."""
    if not proposed: return deterministic
    by_id={task.task_id:task for task in deterministic}
    for task in proposed:
        if task.task_id in by_id:
            continue
        else: by_id[task.task_id]=task.model_copy(update={'legal_subissues':[],
          'legal_issues':[],'topic_ids':[],'origin':'RESEARCHER'})
    if len(by_id)>12: return deterministic
    return list(by_id.values())

def task_analysis(analysis,task):
    from .models import Route
    keys=list(task.legal_subissues)
    # Combined night/overtime rules are not two independent base entitlements.
    # Preserve the interaction already declared by the dated evidence planner.
    wage_pair={'WAGE.NIGHT_PAY','WAGE.OVERTIME_PAY'}
    if wage_pair<=set(analysis.legal_subissues) and wage_pair.intersection(keys):
        keys=list(dict.fromkeys(keys+[key for key in analysis.legal_subissues if key in wage_pair]))
    if 'CONTRACT.PROBATION_SANCTION' in keys:
        keys=list(dict.fromkeys(keys+[key for key in analysis.legal_subissues if key.startswith('CONTRACT.PROBATION_')]))
    return analysis.model_copy(update={'legal_subissues':keys,
      'legal_issues':list(dict.fromkeys(task.legal_issues+[key.split('.')[0] for key in keys])) or ['GENERAL'],
      'answer_tasks':[],'route':Route.STANDARD})


def assess_parts(analysis,selected,claims,semantic_review,allow_fallback,legal_ready=False):
    from .analysis import plan_evidence
    from .evidence import state_for
    from .pipeline import _actionable_gaps
    verdicts={}
    # Only iterations that passed semantic validation are recorded with coverage.
    for iteration in semantic_review.get('iterations',[]):
        if isinstance(iteration,dict):
            for value in iteration.get('coverage',[]): verdicts[value['task_id']]=value
    public_claims={claim.claim_id:claim for claim in claims}
    by_id={item.unit_id:item for item in selected}
    parts=[]
    for task in analysis.answer_tasks:
        plan=plan_evidence(task_analysis(analysis,task))
        state=state_for(selected,plan,analysis.query_date,allow_fallback)
        missing=_actionable_gaps(state.gaps,selected,allow_fallback)
        evidence_missing=list(missing)
        if plan.slot_requirements:
            from .taxonomy import locator_matches
            evidence_ids=list(dict.fromkeys(item.unit_id for groups in plan.slot_requirements.values()
              for alternatives in groups for item in selected if any(locator_matches(item,locator) for locator in alternatives)))
        else:
            evidence_ids=list(dict.fromkeys(uid for slot in state.slots.values() for uid in slot.evidence_ids))
        verdict=verdicts.get(task.task_id)
        claim_ids=[cid for cid in (verdict or {}).get('claim_ids',[]) if cid in public_claims]
        cited={uid for cid in claim_ids for uid in public_claims[cid].evidence_ids}
        cited_state=state_for([by_id[uid] for uid in cited if uid in by_id],plan,analysis.query_date,allow_fallback)
        cited_gaps=_actionable_gaps(cited_state.gaps,selected,allow_fallback)
        status='NOT_CHECKED'
        if verdict and verdict.get('status')=='ANSWERED' and claim_ids and not missing and not cited_gaps:
            status='ANSWERED'
        elif verdict: status='PARTIAL' if claim_ids else 'MISSING'
        elif not evidence_ids: status='MISSING'
        if verdict and verdict.get('missing'): missing=list(dict.fromkeys(missing+[verdict['missing']]))
        if status=='NOT_CHECKED': missing=list(dict.fromkeys(missing+['substantive_answer_not_independently_checked']))
        parts.append(AnswerPart(task_id=task.task_id,question=task.request_quote,description=task.description,
          evidence_status='FOUND' if evidence_ids and not evidence_missing and (plan.slot_requirements or verdict) else 'PARTIAL' if evidence_ids else 'MISSING',
          answer_status=status,evidence_ids=evidence_ids,claim_ids=claim_ids,missing_requirements=missing,
          legal_status='REVIEWED' if legal_ready else 'PROVISIONAL'))
    by_task={part.task_id:part for part in parts}
    # Propagate prerequisite gaps; a consequence cannot be a complete applied
    # conclusion while the legality classification it depends on is unanswered.
    while True:
        changed=False
        for task in analysis.answer_tasks:
            part=by_task[task.task_id]
            unavailable=[parent for parent in task.depends_on if parent not in by_task or by_task[parent].answer_status!='ANSWERED']
            if unavailable:
                part.missing_requirements=list(dict.fromkeys(part.missing_requirements+
                  ['prerequisite_task:'+parent for parent in unavailable]))
                if part.answer_status=='ANSWERED':
                    part.answer_status='PARTIAL'; changed=True
        if not changed: break
    return parts

def independent_partial_plan(analysis,selected,allow_fallback):
    """Find complete dated rule chains; never promote a generic lexical hit.

    Returned plan checks the independently answerable subset. The global plan
    and its missing requirements remain visible, so this can only yield PARTIAL.
    """
    from .analysis import plan_evidence
    from .evidence import state_for
    from .pipeline import _actionable_gaps
    from .models import EvidencePlan
    eligible={}
    for task in analysis.answer_tasks:
        if not task.legal_subissues: continue
        scoped=task_analysis(analysis,task)
        plan=plan_evidence(scoped)
        if not plan.slot_requirements: continue
        state=state_for(selected,plan,analysis.query_date,allow_fallback)
        if not _actionable_gaps(state.gaps,selected,allow_fallback): eligible[task.task_id]=(task,plan,state)
    # A consequence/application cannot survive without its prerequisite task.
    while True:
        invalid=[uid for uid,(task,_,_) in eligible.items() if any(dep not in eligible for dep in task.depends_on)]
        if not invalid: break
        for uid in invalid: del eligible[uid]
    if not eligible: return None,[]
    mandatory=[]; requirements={}; ids=[]
    for task,plan,state in eligible.values():
        mandatory.extend(plan.mandatory_slots); requirements.update(plan.slot_requirements)
        for slot in plan.slot_requirements: ids.extend(state.slots[slot].evidence_ids)
    return EvidencePlan(mandatory_slots=list(dict.fromkeys(mandatory)),slot_requirements=requirements),list(dict.fromkeys(ids))
