from __future__ import annotations
from collections import defaultdict
from datetime import date,timedelta
from difflib import SequenceMatcher
from .answer_quality import language_issues
from .legal_metadata import document_type,norm_role
from .compression import compress_evidence
from .taxonomy import requirement_evidence,locator_matches
from .models import ApplicabilityDecision,Evidence,EvidencePlan,EvidenceState,EvidenceSlot,SlotStatus,VerifiedEvidenceItem,VerifiedEvidencePack

DELEGATION_PHRASES=(
    'chính phủ quy định chi tiết',
    'bộ trưởng quy định chi tiết',
    'theo quy định của chính phủ',
    'được thực hiện theo quy định của chính phủ',
)

def _source_penalty(item:Evidence)->int:
    """Rank existing alternatives; never guess missing OCR words or edit bytes."""
    text=item.source_text or item.text
    suspect=('nguời','ngưòi','ngàỵ','sừ dụng','tố chức','phải có lực hành vi')
    return len(language_issues(text,allow_admin=True))+sum(text.lower().count(term) for term in suspect)

def extend_plan_for_evidence(plan:EvidencePlan,items:list[Evidence],facts:dict,query_date:str|None)->EvidencePlan:
    """Add only evidence-driven mandatory slots before graph expansion."""
    mandatory=list(plan.mandatory_slots)
    verified_text=' '.join(' '.join(y for y in (item.text,item.source_text) if y).lower() for item in items if item.verified)
    if any(phrase in verified_text for phrase in DELEGATION_PHRASES) and 'implementing_regulation' not in mandatory:
        mandatory.append('implementing_regulation')
    from .temporal import requires_transition_rule
    if requires_transition_rule(facts.get('contract_start_year'),query_date) and 'transitional_rule' not in mandatory:
        mandatory.append('transitional_rule')
    return plan.model_copy(update={'mandatory_slots':mandatory})

def _texts(items:list[Evidence],needles:tuple[str,...])->list[str]:
    return [x.unit_id for x in items if any(n in ' '.join(' '.join(y.split()) for y in (x.text,x.source_text,x.breadcrumb) if y).lower() for n in needles)]

def state_for(items:list[Evidence],plan:EvidencePlan|list[str],query_date:str|None,allow_document_temporal_fallback:bool=False)->EvidenceState:
    mandatory=plan.mandatory_slots if isinstance(plan,EvidencePlan) else plan
    conditional=plan.conditional_slots if isinstance(plan,EvidencePlan) else []
    verified=[x for x in items if x.verified]; mapping={}
    for slot in [*mandatory,*conditional]:
        ids=[]; fallback_ids=[]
        if isinstance(plan,EvidencePlan) and slot in plan.slot_requirements:
            ids=requirement_evidence(verified,plan.slot_requirements[slot])
        elif slot=='governing_rule': ids=[x.unit_id for x in verified if x.provision_version_id and x.kind=='PROVISION']
        elif slot in {'authority','official_source'}:
            ids=[x.unit_id for x in verified if x.official_source and x.source_catalog_status=='VERIFIED']
            fallback_ids=[x.unit_id for x in verified if x.authority_rank>0 and x.source_url] if allow_document_temporal_fallback else []
        elif slot=='applicable_version':
            ids=[x.unit_id for x in verified if x.provision_temporal_verified] if query_date else [x.unit_id for x in verified]
            fallback_ids=[x.unit_id for x in verified if x.temporal_verified and not x.provision_temporal_verified] if query_date and allow_document_temporal_fallback else []
        elif slot=='mandatory_reference': ids=[x.unit_id for x in verified if {'REFERENCES','IMPLEMENTS'}&set(x.graph_relations)]
        elif slot=='notice_requirement': ids=_texts(verified,('báo trước','thông báo trước'))
        elif slot=='exceptions': ids=_texts(verified,('trừ trường hợp','không áp dụng','không phải','ngoại lệ','trừ khi','không cần báo trước','đối với người','công việc nặng nhọc','công việc đặc biệt nặng nhọc'))
        elif slot=='termination_conditions': ids=_texts(verified,('chấm dứt','đơn phương','sa thải','thôi việc'))
        elif slot=='legal_classification':
            ids=[x.unit_id for x in verified if str(x.article_number or '')=='39' and 'trái pháp luật' in ' '.join(y for y in (x.text,x.source_text,x.breadcrumb) if y).lower()]
        elif slot=='legal_consequences':
            groups=(('không được trợ cấp thôi việc',),('nửa tháng tiền lương','những ngày không báo trước'),('chi phí đào tạo',))
            grouped=[]
            for needles in groups:
                candidates=[x.unit_id for x in verified if str(x.article_number or '')=='40' and all(needle in ' '.join(y for y in (x.text,x.source_text,x.breadcrumb) if y).lower() for needle in needles)]
                if candidates: grouped.append(candidates[0])
            ids=grouped if len(grouped)==len(groups) else []
        elif slot=='exception_rule': ids=[x.unit_id for x in verified if str(x.article_number or '')=='35' and str(x.clause_number or '')=='2' and str(x.point_number or '') in {'b','d','g'}]
        elif slot=='wage_delay_reference': ids=[x.unit_id for x in verified if str(x.article_number or '')=='97' and str(x.clause_number or '')=='4']
        elif slot=='disclosure_reference': ids=[x.unit_id for x in verified if str(x.article_number or '')=='16' and str(x.clause_number or '')=='1']
        elif slot=='withdrawal_rule': ids=[x.unit_id for x in verified if str(x.article_number or '')=='38']
        elif slot=='agreement_rule': ids=[x.unit_id for x in verified if str(x.article_number or '')=='34' and str(x.clause_number or '')=='3']
        elif slot=='travel_time_rule': ids=[x.unit_id for x in verified if str(x.article_number or '')=='113' and str(x.clause_number or '')=='6']
        elif slot=='leave_base_rule': ids=[x.unit_id for x in verified if str(x.article_number or '')=='113' and str(x.clause_number or '')=='1' and str(x.point_number or '') in {'a','b','c'}]
        elif slot=='seniority_rule': ids=[x.unit_id for x in verified if str(x.article_number or '')=='114']
        elif slot=='proportional_leave_rule': ids=[x.unit_id for x in verified if (str(x.article_number or '')=='113' and str(x.clause_number or '')=='2') or (x.document_number=='145/2020/NĐ-CP' and str(x.article_number or '')=='66')]
        elif slot=='leave_calculation_rule': ids=[x.unit_id for x in verified if x.document_number=='145/2020/NĐ-CP' and str(x.article_number or '')=='66' and str(x.clause_number or '')=='1']
        elif slot=='conditions': ids=_texts(verified,('nếu ','khi ','trường hợp','điều kiện','đủ 12 tháng','làm việc đủ','có đủ','theo tỷ lệ','tương ứng'))
        elif slot=='implementing_regulation': ids=[x.unit_id for x in verified if 'IMPLEMENTS' in x.graph_relations or x.document_number and any(t in x.document_number for t in ('NĐ-CP','TT-'))]
        elif slot=='amendment_history': ids=[x.unit_id for x in verified if {'AMENDS','REPEALS','REPLACES','VERSION_OF'}&set(x.graph_relations)]
        elif slot=='case_law': ids=[x.unit_id for x in verified if x.kind=='CASE']
        elif slot=='transitional_rule':
            ids=[x.unit_id for x in verified if str(x.article_number or '')=='220' and x.document_number in {'45/2019/QH14','18/VBHN-VPQH'}]
        if ids: status=SlotStatus.FOUND_VERIFIED
        elif fallback_ids: status=SlotStatus.FOUND
        elif slot in conditional: status=SlotStatus.UNRESOLVED
        else: status=SlotStatus.MISSING
        mapping[slot]=EvidenceSlot(status=status,evidence_ids=ids or fallback_ids)
    gaps=[k for k in mandatory if mapping[k].status not in {SlotStatus.FOUND_VERIFIED,SlotStatus.NOT_APPLICABLE}]
    score=sum(1 if mapping[k].status==SlotStatus.FOUND_VERIFIED else .5 if mapping[k].status==SlotStatus.FOUND else 0 for k in mandatory)
    return EvidenceState(slots=mapping,gaps=gaps,coverage=score/max(1,len(mandatory)),
      mandatory_slots=mandatory,conditional_slots=conditional)

def select_for_plan(items:list[Evidence],plan:EvidencePlan,query_date:str|None,allow_document_temporal_fallback:bool,limit:int)->tuple[list[Evidence],EvidenceState]:
    """Greedily preserve evidence that fills mandatory slots before score-only fill."""
    ordered=[]; seen_identity=set(); seen_content=set()
    for item in items:
        # Collapse duplicate retrieval hits, while retaining distinct legal
        # versions so the conflict detector can compare overlapping versions.
        identity=(item.provision_identity_id,item.provision_version_id or item.unit_id)
        if identity in seen_identity: continue
        seen_identity.add(identity)
        # Collapse only byte-equivalent normalized passages at the same legal
        # location in the current code/consolidation family. Changed and old
        # provisions remain distinct; all conflicts are checked on input items.
        family='BLLD_2019' if item.document_number in {'45/2019/QH14','18/VBHN-VPQH'} else item.document_number or item.document_id or item.unit_id
        content=(family,item.article_number,item.clause_number,item.point_number,
          item.valid_from,item.valid_to,' '.join((item.source_text or item.text).split()))
        if content in seen_content: continue
        seen_content.add(content); ordered.append(item)
    selected=[]; selected_ids=set()
    # Allocate scarce room to explicit legal requirements first. These items
    # often satisfy the generic source/version slots too, avoiding a redundant
    # high-scoring item that crowds out the last required clause or point.
    slot_order=([slot for slot in plan.mandatory_slots if slot in plan.slot_requirements]
      +[slot for slot in plan.mandatory_slots if slot not in plan.slot_requirements])
    for slot in slot_order:
        if slot in plan.slot_requirements:
            # Preserve each required group before filling remaining room by
            # score. A one-item probe cannot satisfy a multi-clause requirement.
            for alternatives in plan.slot_requirements[slot]:
                if any(any(locator_matches(item,locator) for locator in alternatives) for item in selected):
                    continue
                matches=[item for item in ordered if item.verified and any(locator_matches(item,locator) for locator in alternatives)]
                matches.sort(key=lambda item:(not item.provision_temporal_verified,
                  not (item.official_source and item.source_catalog_status=='VERIFIED'),
                  _source_penalty(item),item.document_number!='18/VBHN-VPQH',-item.authority_rank,-item.score,item.unit_id))
                if matches and len(selected)<limit:
                    chosen=matches[0]
                    selected.append(chosen); selected_ids.add(chosen.unit_id)
            continue
        existing=state_for(selected,EvidencePlan(mandatory_slots=[slot]),query_date,allow_document_temporal_fallback).slots[slot]
        if existing.status==SlotStatus.FOUND_VERIFIED:
            continue
        if slot=='legal_consequences':
            probe=state_for(ordered,EvidencePlan(mandatory_slots=[slot]),query_date,allow_document_temporal_fallback).slots[slot]
            if probe.status in {SlotStatus.FOUND_VERIFIED,SlotStatus.FOUND}:
                by_id={item.unit_id:item for item in ordered}
                for evidence_id in probe.evidence_ids:
                    if evidence_id not in selected_ids and evidence_id in by_id and len(selected)<limit:
                        selected.append(by_id[evidence_id]); selected_ids.add(evidence_id)
            continue
        ranked=[]
        for item in ordered:
            probe=state_for([item],EvidencePlan(mandatory_slots=[slot]),query_date,allow_document_temporal_fallback).slots[slot]
            if probe.status in {SlotStatus.FOUND_VERIFIED,SlotStatus.FOUND}:
                ranked.append((probe.status==SlotStatus.FOUND_VERIFIED,item.score,item))
        ranked.sort(key=lambda row:(not row[0],-row[1],row[2].unit_id))
        if ranked and ranked[0][2].unit_id not in selected_ids and len(selected)<limit:
            selected.append(ranked[0][2]); selected_ids.add(ranked[0][2].unit_id)
    # Profiles define the complete mandatory legal chain; don't pad that chain
    # with unrelated high-ranked passages. Generic and exact-article searches
    # retain their existing selection budget.
    for item in ([] if plan.slot_requirements else ordered):
        if len(selected)>=limit: break
        if item.unit_id not in selected_ids:
            selected.append(item); selected_ids.add(item.unit_id)
    return selected,state_for(selected,plan,query_date,allow_document_temporal_fallback)

def build_verified_pack(query:str,query_date:str|None,facts:dict,state:EvidenceState,items:list[Evidence],
                        decisions:list[ApplicabilityDecision]|None=None,requested_outcome:str='OTHER')->VerifiedEvidencePack:
    by_decision={x.evidence_id:x for x in decisions or []}
    packed=[VerifiedEvidenceItem(evidence_id=x.unit_id,instrument_number=x.document_number,article=x.article_number,
      document_type=document_type(x.document_number,x.document_title,x.document_type),document_title=x.document_title,issuer=x.issuer,
      norm_role=norm_role(x.document_number,x.document_title,x.source_text or x.text),
      clause=x.clause_number,point=x.point_number,text=compress_evidence(x,query),valid_from=x.valid_from,
      valid_to=x.valid_to,official_url=x.source_url,authority_rank=x.authority_rank,binding=x.binding,
      official_source=x.official_source,provenance_span=x.provenance_span,
      applicability=by_decision.get(x.unit_id),warnings=x.audit_warnings) for x in items if x.verified
      and (decisions is None or x.unit_id in by_decision and by_decision[x.unit_id].audit_status=='PASS'
        and by_decision[x.unit_id].relevant and by_decision[x.unit_id].supports_claim)]
    return VerifiedEvidencePack(query=query,query_date=query_date,facts=facts,requested_outcome=requested_outcome,
      coverage_state=state,evidence=packed)

def detect_authoritative_conflicts(items:list[Evidence],query_date:str|None,query_date_end:str|None=None)->list[list[str]]:
    """Find materially different authoritative versions that are valid at the same time.

    A month/year query can intersect two consecutive versions without those versions
    ever overlapping.  That is a missing-date problem, not an authoritative conflict,
    so pairs must overlap each other as well as the requested interval.
    """
    groups=defaultdict(list)
    for item in items:
        if item.provision_identity_id and item.provision_temporal_verified and item.authority_rank>0: groups[item.provision_identity_id].append(item)
    conflicts=[]
    query_start=date.fromisoformat(query_date) if query_date else date.min
    inclusive_end=date.fromisoformat(query_date_end) if query_date_end else query_start
    query_end_exclusive=date.max if not query_date or inclusive_end==date.max else inclusive_end+timedelta(days=1)
    for values in groups.values():
        active=[]
        for item in values:
            start=date.fromisoformat(item.valid_from) if item.valid_from else date.min
            end=date.fromisoformat(item.valid_to) if item.valid_to else date.max
            if max(start,query_start)<min(end,query_end_exclusive): active.append((item,start,end))
        for i,(left,left_start,left_end) in enumerate(active):
            for right,right_start,right_end in active[i+1:]:
                if max(left_start,right_start,query_start)>=min(left_end,right_end,query_end_exclusive): continue
                similarity=SequenceMatcher(None,' '.join((left.source_text or left.text).split()),' '.join((right.source_text or right.text).split())).ratio()
                if similarity<.85: conflicts.append([left.unit_id,right.unit_id])
    return conflicts
