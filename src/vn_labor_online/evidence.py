from __future__ import annotations
from collections import defaultdict
from datetime import date,timedelta
from difflib import SequenceMatcher
from .compression import compress_evidence
from .models import ApplicabilityDecision,Evidence,EvidencePlan,EvidenceState,EvidenceSlot,SlotStatus,VerifiedEvidenceItem,VerifiedEvidencePack

def _texts(items:list[Evidence],needles:tuple[str,...])->list[str]:
    return [x.unit_id for x in items if any(n in ' '.join(' '.join(y.split()) for y in (x.text,x.source_text,x.breadcrumb) if y).lower() for n in needles)]

def state_for(items:list[Evidence],plan:EvidencePlan|list[str],query_date:str|None,allow_document_temporal_fallback:bool=False)->EvidenceState:
    mandatory=plan.mandatory_slots if isinstance(plan,EvidencePlan) else plan
    conditional=plan.conditional_slots if isinstance(plan,EvidencePlan) else []
    verified=[x for x in items if x.verified]; mapping={}
    for slot in [*mandatory,*conditional]:
        ids=[]; fallback_ids=[]
        if slot=='governing_rule': ids=[x.unit_id for x in verified if x.provision_version_id and x.kind=='PROVISION']
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
        elif slot=='conditions': ids=_texts(verified,('nếu ','khi ','trường hợp','điều kiện','đủ 12 tháng','làm việc đủ','có đủ','theo tỷ lệ','tương ứng'))
        elif slot=='implementing_regulation': ids=[x.unit_id for x in verified if 'IMPLEMENTS' in x.graph_relations or x.document_number and any(t in x.document_number for t in ('NĐ-CP','TT-'))]
        elif slot=='amendment_history': ids=[x.unit_id for x in verified if {'AMENDS','REPEALS','REPLACES','VERSION_OF'}&set(x.graph_relations)]
        elif slot=='case_law': ids=[x.unit_id for x in verified if x.kind=='CASE']
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
    ordered=[]; seen_identity=set()
    for item in items:
        # Collapse duplicate retrieval hits, while retaining distinct legal
        # versions so the conflict detector can compare overlapping versions.
        identity=(item.provision_identity_id,item.provision_version_id or item.unit_id)
        if identity in seen_identity: continue
        seen_identity.add(identity); ordered.append(item)
    selected=[]; selected_ids=set()
    for slot in plan.mandatory_slots:
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
    for item in ordered:
        if len(selected)>=limit: break
        if item.unit_id not in selected_ids:
            selected.append(item); selected_ids.add(item.unit_id)
    return selected,state_for(selected,plan,query_date,allow_document_temporal_fallback)

def build_verified_pack(query:str,query_date:str|None,facts:dict,state:EvidenceState,items:list[Evidence],
                        decisions:list[ApplicabilityDecision]|None=None,requested_outcome:str='OTHER')->VerifiedEvidencePack:
    by_decision={x.evidence_id:x for x in decisions or []}
    packed=[VerifiedEvidenceItem(evidence_id=x.unit_id,instrument_number=x.document_number,article=x.article_number,
      clause=x.clause_number,point=x.point_number,text=compress_evidence(x,query),valid_from=x.valid_from,
      valid_to=x.valid_to,official_url=x.source_url,authority_rank=x.authority_rank,binding=x.binding,
      official_source=x.official_source,provenance_span=x.provenance_span,
      applicability=by_decision.get(x.unit_id),warnings=x.audit_warnings) for x in items if x.verified]
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
