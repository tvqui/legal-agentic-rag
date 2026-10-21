"""Resolve article containers to existing source units, without rewriting text
or treating retrieval as legal approval.
"""
from __future__ import annotations
import re,unicodedata


def _get(item,key,default=None):
    return item.get(key,default) if isinstance(item,dict) else getattr(item,key,default)


def heading_only(item):
    """Conservative detection of bare article titles, not arbitrary short law.

    A title stays usable as a graph/lookup anchor. It cannot by itself establish
    a substantive rule. An introductory paragraph with operative language is
    deliberately retained; its completeness still needs semantic review.
    """
    if _get(item,'kind') not in {None,'PROVISION'}: return False
    if not (_get(item,'article_number') or _get(item,'article')): return False
    if (_get(item,'clause_number') or _get(item,'clause') or _get(item,'point_number') or _get(item,'point')): return False
    source=_get(item,'source_text') or _get(item,'full_text') or _get(item,'text') or ''
    text=' '.join(unicodedata.normalize('NFC',source).lower().split())
    match=re.fullmatch(r'điều\s+\d+[a-zđ]?\s*[.:]\s*(.+)',text)
    if not match: return False
    title=match.group(1)
    operative=r'\b(?:phải|được|không|là|gồm|bao gồm|quy định|áp dụng|cấm|chịu trách nhiệm)\b'
    return not re.search(operative,title) and not re.search(r'\b\d+\s*(?:ngày|tháng|năm|giờ|%)',title)


def _overlaps(unit,start,end):
    lower=_get(unit,'valid_from') or _get(unit,'effective_from')
    upper=_get(unit,'valid_to') or _get(unit,'effective_to')
    return not (end and lower and lower>end or start and upper and upper<=start)


def _version_key(unit):
    return (_get(unit,'document_id') or _get(unit,'document_version_id') or _get(unit,'version_id'))


def enumeration_intro(item):
    """An actual structural parent introducing enumerated child provisions."""
    source=_get(item,'source_text') or _get(item,'full_text') or _get(item,'text') or ''
    return _get(item,'kind') in {None,'PROVISION'} and str(source).rstrip().endswith(':')


def resolve_article_requirements(plan,index,start=None,end=None):
    """Resolve titles and enumeration introductions at their requested scope.

    Each branch becomes a mandatory source group. Never truncate requirements
    to fit the retrieval budget; missing/clipped branches must remain gaps.
    Existing date filters, provenance and applicability audits still run.
    """
    from .models import LegalLocator
    resolved={}; notes=[]
    for slot,groups in plan.slot_requirements.items():
        expanded=[]
        for alternatives in groups:
            # A disjunction of different legal scopes cannot be safely changed
            # into a conjunction. Resolve only the same article across editions.
            scopes={(loc.article,loc.clause) for loc in alternatives}
            broad=bool(alternatives) and len(scopes)==1 and all(
                loc.point is None and not loc.exact_level and not loc.text_contains
                for loc in alternatives)
            if not broad:
                expanded.append(alternatives); continue
            branch_docs={}; branch_ids={}; seen_container=False; unsafe_alternative=False
            for loc in alternatives:
                for document in loc.documents:
                    pool=[u for u in index.get((document,loc.article),[]) if _overlaps(u,start,end or start)]
                    roots=[u for u in pool if str(_get(u,'clause_number') or '')==str(loc.clause or '') and not _get(u,'point_number')]
                    if any(not (heading_only(root) or enumeration_intro(root)) for root in roots):
                        unsafe_alternative=True; break
                    for root in roots:
                        version=_version_key(root)
                        if not version or not _get(root,'unit_id'): continue
                        descendants=[]
                        for unit in pool:
                            if _version_key(unit)!=version: continue
                            clause=str(_get(unit,'clause_number') or '')
                            point=str(_get(unit,'point_number') or '').lower()
                            if not clause and not point: continue
                            if loc.clause is not None and (clause!=str(loc.clause) or not point): continue
                            if _get(unit,'unit_id'): descendants.append(((clause,point),_get(unit,'unit_id')))
                        if not descendants: continue
                        seen_container=True
                        if not heading_only(root):
                            # An operative introduction carries the norm's
                            # polarity/conditions as well as its child list.
                            branch_docs.setdefault((str(loc.clause or ''),''),set()).add(document)
                            branch_ids.setdefault((str(loc.clause or ''),''),set()).add(_get(root,'unit_id'))
                        for path,uid in descendants:
                            branch_docs.setdefault(path,set()).add(document)
                            branch_ids.setdefault(path,set()).add(uid)
                if unsafe_alternative: break
            if not seen_container or unsafe_alternative or not branch_docs:
                expanded.append(alternatives); continue
            def order(path):
                clause,point=path
                return (int(clause) if clause.isdigit() else 100000,clause,point.replace('đ','d~'))
            article,scope_clause=next(iter(scopes))
            for clause,point in sorted(branch_docs,key=order):
                expanded.append([LegalLocator(documents=sorted(branch_docs[(clause,point)]),
                    article=article,clause=clause or None,point=point or None,exact_level=True,
                    unit_ids=sorted(branch_ids[(clause,point)]))])
            notes.append({'slot':slot,'article':article,'clause':scope_clause,'branch_groups':len(branch_docs)})
        # Keep explicit original requirements as well, while collapsing exact
        # duplicates introduced by another anchor in the same slot.
        unique=[]; seen=set()
        for group in expanded:
            key=tuple(loc.model_dump_json() for loc in group)
            if key not in seen: seen.add(key); unique.append(group)
        resolved[slot]=unique
    return plan.model_copy(update={'slot_requirements':resolved}),notes
