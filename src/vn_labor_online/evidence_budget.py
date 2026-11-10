"""Fair candidate scheduling is not evidence approval or a larger budget."""
def required_groups(plan):
    slots=[slot for slot in plan.mandatory_slots if slot in plan.slot_requirements]
    for offset in range(max((len(plan.slot_requirements[s]) for s in slots),default=0)):
        for slot in slots:
            if offset<len(plan.slot_requirements[slot]):yield slot,plan.slot_requirements[slot][offset]


def prioritize_candidates(items,plan,covered=()):
    from .taxonomy import locator_matches
    ordered=[];seen=set();covered=list(covered)
    for _,group in required_groups(plan):
        if any(any(locator_matches(item,loc) for loc in group) for item in covered+ordered):continue
        match=next((item for item in items if item.unit_id not in seen and any(locator_matches(item,loc) for loc in group)),None)
        if match:
            ordered.append(match);seen.add(match.unit_id)
    ordered.extend(item for item in items if item.unit_id not in seen)
    return ordered


def generation_evidence(pack):
    """Keep the requested rule rather than volunteering administrative fines.

    Retrieval and audit retain all candidates. This is a generation view only;
    explicit sources and mandatory dependencies always survive. An operative
    rule is not interchangeable with a sanction for violating that rule.
    """
    import re
    from .taxonomy import locator_matches
    # Reporting that an employer fined a worker is a fact to assess, not a
    # request for the administrative fine payable by that employer.
    asks_sanction=bool(re.search(r'xử\s+phạt|chế tài|hậu quả|xử lý thế nào|xử lý như thế nào|'
        r'mức\s+(?:xử\s+)?phạt|phạt\s+(?:tiền\s+)?(?:bao nhiêu|thế nào|như thế nào|ra sao)|'
        r'xử phạt\s+(?:hành chính|công ty|doanh nghiệp|người sử dụng lao động)|'
        r'có\s+bị\s+(?:xử\s+)?phạt|phạt[^.;?!]{0,25}mức nào',pack.query,re.I))
    if (not any(item.norm_role=='RULE' for item in pack.evidence)
        or asks_sanction):
        return list(pack.evidence)
    plan=pack.evidence_plan
    groups=[group for _,group in required_groups(plan)] if plan else []
    reference=pack.lookup_reference
    from .analysis import REF
    references=list(REF.finditer(pack.query))
    def explicitly_required(item):
        row={'kind':'PROVISION','document_number':item.instrument_number,
            'unit_id':item.evidence_id,'article_number':item.article,
            'clause_number':item.clause,'point_number':item.point,
            'text':item.full_text or item.text,'source_text':item.full_text or item.text}
        named=any(ref.group('instrument')==item.instrument_number and ref.group('article')==item.article
            and (not ref.group('clause') or ref.group('clause')==item.clause)
            and (not ref.group('point') or ref.group('point').lower()==str(item.point).lower()) for ref in references)
        return (named or any(locator_matches(row,locator) for group in groups for locator in group)
            or bool(reference and reference.instrument_number==item.instrument_number
                    and (not reference.article or reference.article==item.article)))
    return [item for item in pack.evidence if item.norm_role=='RULE' or explicitly_required(item)]
