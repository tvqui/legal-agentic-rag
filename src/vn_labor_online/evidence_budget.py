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
