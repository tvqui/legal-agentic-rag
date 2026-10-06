"""Versioned ONLINE issue profiles; labels guide retrieval, never establish facts.

No graph/index mutation is required. Parent labels stay compatible with old
OFFLINE releases. 12/14/16-day entitlements are conditional variants, not issues.
"""
from __future__ import annotations

import re
from .models import LegalLocator, QueryAnalysis
from .temporal import legal_regime_for

TAXONOMY_VERSION = 'labor-subissues-v1'
CURRENT_CODE = ['45/2019/QH14', '18/VBHN-VPQH']
OLD_CODE = ['10/2012/QH13']

# Mechanisms and remedies deliberately coexist rather than being exclusive siblings.
SUBISSUES = {
    'TERMINATION.EMPLOYEE_UNILATERAL': 'Người lao động đơn phương chấm dứt',
    'TERMINATION.EMPLOYER_UNILATERAL': 'Người sử dụng lao động đơn phương chấm dứt',
    'TERMINATION.MUTUAL_AGREEMENT': 'Hai bên thỏa thuận chấm dứt',
    'TERMINATION.EXPIRY': 'Hết hạn hợp đồng',
    'TERMINATION.DISMISSAL': 'Sa thải theo kỷ luật',
    'TERMINATION.ECONOMIC_RESTRUCTURING': 'Thay đổi cơ cấu, công nghệ hoặc lý do kinh tế',
    'TERMINATION.ENTERPRISE_TRANSFER': 'Sáp nhập, chuyển giao doanh nghiệp',
    'TERMINATION.ILLEGAL_TERMINATION': 'Câu hỏi về chấm dứt trái pháp luật',
    'TERMINATION.EMPLOYEE_LIABILITY': 'Hậu quả đối với người lao động',
    'TERMINATION.EMPLOYER_LIABILITY': 'Hậu quả đối với người sử dụng lao động',
    'TERMINATION.SEVERANCE': 'Trợ cấp thôi việc',
    'TERMINATION.JOB_LOSS_ALLOWANCE': 'Trợ cấp mất việc làm',
    'TERMINATION.WITHDRAWAL': 'Hủy bỏ thông báo đơn phương',
    'LEAVE.ANNUAL_LEAVE': 'Nghỉ hằng năm theo nhóm điều kiện',
    'LEAVE.SENIORITY_BONUS': 'Ngày nghỉ tăng theo thâm niên',
    'LEAVE.PRO_RATA_LEAVE': 'Nghỉ hằng năm khi chưa đủ 12 tháng',
    'LEAVE.TRAVEL_DAYS': 'Thời gian đi đường khi nghỉ hằng năm',
    'LEAVE.PUBLIC_HOLIDAY': 'Nghỉ lễ, Tết',
    'LEAVE.PERSONAL_LEAVE': 'Nghỉ việc riêng',
    'LEAVE.UNPAID_LEAVE': 'Nghỉ không hưởng lương',
    'LEAVE.UNUSED_LEAVE_PAYMENT': 'Thanh toán ngày nghỉ hằng năm chưa nghỉ',
}


def classify_subissues(query: str, facts: dict, issues: list[str]) -> list[str]:
    q = ' '.join(query.lower().split())
    found = []
    def add(label):
        if label not in found: found.append(label)
    has = lambda *terms: any(term in q for term in terms)
    intent = facts.get('query_intent')
    quantity = bool(re.search(r'bao nhiêu ngày|số ngày|tính ngày|\b\d+\s+ngày\b',q))
    special_mechanism = False
    for label, terms in (
        ('MUTUAL_AGREEMENT', ('thỏa thuận chấm dứt', 'thoả thuận chấm dứt', 'đồng ý cho nghỉ sớm')),
        ('EXPIRY', ('hết hạn hợp đồng', 'hợp đồng hết hạn', 'hết hạn hđlđ')),
        ('DISMISSAL', ('sa thải',)),
        ('ECONOMIC_RESTRUCTURING', ('thay đổi cơ cấu', 'thay đổi công nghệ', 'lý do kinh tế', 'tái cơ cấu', 'cắt giảm nhân sự')),
        ('ENTERPRISE_TRANSFER', ('sáp nhập', 'chia tách doanh nghiệp', 'chuyển quyền sở hữu doanh nghiệp')),
    ):
        if has(*terms) or label == 'MUTUAL_AGREEMENT' and intent == 'MUTUAL_TERMINATION':
            add('TERMINATION.' + label); special_mechanism = True
    if intent == 'WITHDRAW_TERMINATION' or has('hủy bỏ việc đơn phương', 'huỷ bỏ việc đơn phương'):
        add('TERMINATION.WITHDRAWAL'); special_mechanism = True
    compare = has('so sánh', 'phân biệt', 'khác nhau')
    unilateral = has('đơn phương', 'báo trước', 'muốn nghỉ', 'nghỉ ngay', 'nghỉ sau', 'xin nghỉ việc', 'tôi nghỉ việc')
    if 'TERMINATION' in issues and (not special_mechanism or compare):
        if facts.get('actor') == 'EMPLOYEE' or re.search(r'người lao động\s+(?:có quyền\s+)?đơn phương', q):
            if unilateral or facts.get('termination_basis'): add('TERMINATION.EMPLOYEE_UNILATERAL')
        if facts.get('actor') == 'EMPLOYER' or re.search(r'(?:công ty|người sử dụng lao động)\s+(?:có quyền\s+)?đơn phương', q):
            add('TERMINATION.EMPLOYER_UNILATERAL')
    if has('trợ cấp thôi việc'): add('TERMINATION.SEVERANCE')
    if has('trợ cấp mất việc'): add('TERMINATION.JOB_LOSS_ALLOWANCE')
    illegal_question = has('trái pháp luật', 'trái luật') or not special_mechanism and has('hậu quả', 'bồi thường')
    suspected_short_notice = ('TERMINATION.EMPLOYEE_UNILATERAL' in found and facts.get('notice_exception') is False
        and facts.get('contract_type') == 'INDEFINITE' and isinstance(facts.get('notice_days'), int)
        and facts['notice_days'] < (120 if facts.get('special_occupation') is True else 45))
    if 'TERMINATION' in issues and (illegal_question or suspected_short_notice):
        add('TERMINATION.ILLEGAL_TERMINATION')
        if (facts.get('actor') == 'EMPLOYEE' and facts.get('notice_exception') is not True
            or intent == 'UNLAWFUL_DEFINITION_CONSEQUENCES'):
            add('TERMINATION.EMPLOYEE_LIABILITY')
        elif facts.get('actor') == 'EMPLOYER': add('TERMINATION.EMPLOYER_LIABILITY')
    # Neither a label nor a question mentioning illegality sets a fact saying it is unlawful.
    if 'LEAVE' in issues:
        holiday = has('nghỉ lễ', 'ngày lễ', 'nghỉ tết', 'ngày tết', 'quốc khánh', 'giỗ tổ', 'tết nguyên đán')
        personal = has('nghỉ việc riêng', 'kết hôn', 'đám cưới', 'cha mất', 'mẹ mất', 'bố mất', 'tang lễ')
        unpaid = has('nghỉ không hưởng lương', 'nghỉ không lương')
        annual = has('nghỉ hằng năm', 'nghỉ hàng năm', 'nghỉ phép', 'phép năm', 'ngày phép', 'thâm niên', 'ngày cơ bản')
        payment = annual and has('chưa nghỉ', 'chưa sử dụng', 'còn dư') and has('thanh toán', 'trả tiền', 'tiền phép')
        if annual and (not payment or quantity): add('LEAVE.ANNUAL_LEAVE')
        if has('thâm niên') or annual and int(facts.get('service_years') or 0) >= 5:
            add('LEAVE.SENIORITY_BONUS')
        if annual and (has('chưa đủ 12 tháng', 'theo tỷ lệ') or isinstance(facts.get('worked_months'), int) and facts['worked_months'] < 12):
            add('LEAVE.PRO_RATA_LEAVE')
        if intent == 'TRAVEL_TIME' or annual and has('đi đường', 'đi và về'):
            add('LEAVE.TRAVEL_DAYS')
        if holiday: add('LEAVE.PUBLIC_HOLIDAY')
        if personal: add('LEAVE.PERSONAL_LEAVE')
        if unpaid: add('LEAVE.UNPAID_LEAVE')
        if payment:
            add('LEAVE.UNUSED_LEAVE_PAYMENT')
    return found


def parent_issues(issues: list[str], subissues: list[str]) -> list[str]:
    values = list(issues)
    for subissue in subissues:
        parent = subissue.split('.')[0]
        if parent not in values: values.append(parent)
    if 'TERMINATION.DISMISSAL' in subissues and 'DISCIPLINE' not in values:
        values.append('DISCIPLINE')
    return [value for value in values if value != 'GENERAL'] or ['GENERAL']


def profile_requirements(analysis: QueryAnalysis) -> dict[str, list[list[LegalLocator]]]:
    """All groups must have a verified match; locators within a group are alternatives.

    Locations are retrieval hints for a dated code family, not legal status.
    Temporal/authority/applicability checks remain mandatory downstream.
    """
    historical = legal_regime_for(analysis.query_date) == 'BLLD_2012'
    docs = OLD_CODE if historical else CURRENT_CODE
    def loc(article, clause=None, point=None, documents=None):
        return LegalLocator(documents=documents or docs, article=str(article), clause=clause, point=point)
    requirements = {}
    def require(slot, *groups): requirements[slot] = list(groups)
    def rule(slot, new_article, old_article, clause=None):
        require(slot, [loc(old_article if historical else new_article, clause)])
    for key in analysis.legal_subissues:
        if key == 'TERMINATION.EMPLOYEE_UNILATERAL':
            basis = analysis.facts.get('termination_basis')
            if not historical and basis in {'LATE_WAGE', 'EMPLOYER_MISINFORMATION', 'SEXUAL_HARASSMENT'}:
                point = {'LATE_WAGE':'b', 'EMPLOYER_MISINFORMATION':'g', 'SEXUAL_HARASSMENT':'d'}[basis]
                require('employee_unilateral_rule', [loc('35', '2', point)])
                require('exception_rule', [loc('35', '2', point)])
                if basis == 'LATE_WAGE': require('wage_delay_reference', [loc('97', '4')])
                if basis == 'EMPLOYER_MISINFORMATION': require('disclosure_reference', [loc('16', '1')])
            elif not historical and analysis.facts.get('contract_type') == 'INDEFINITE':
                require('employee_unilateral_rule', [loc('35', '1', 'a')])
                require('notice_requirement', [loc('35', '1', 'a')])
                if analysis.facts.get('special_occupation') is True:
                    require('special_notice_delegation', [loc('35', '1', 'd')])
                    require('special_notice_rule', [loc('7', '2', 'a', documents=['145/2020/NĐ-CP'])])
            elif historical and analysis.facts.get('contract_type') == 'INDEFINITE':
                require('employee_unilateral_rule', [loc('37', '3')])
                require('notice_requirement', [loc('37', '3')])
            else: rule('employee_unilateral_rule', '35', '37')
        elif key == 'TERMINATION.EMPLOYER_UNILATERAL':
            rule('employer_unilateral_rule', '36', '38')
            rule('employer_protection_rule', '37', '39')
        elif key == 'TERMINATION.MUTUAL_AGREEMENT':
            rule('agreement_rule', '34', '36', '3')
        elif key == 'TERMINATION.EXPIRY': rule('expiry_rule', '34', '36', '1')
        elif key == 'TERMINATION.DISMISSAL':
            rule('dismissal_ground_rule', '125', '126')
            rule('dismissal_procedure_rule', '122', '123')
        elif key == 'TERMINATION.ECONOMIC_RESTRUCTURING':
            rule('restructuring_ground_rule', '42', '44')
            rule('employment_plan_rule', '44', '46')
        elif key == 'TERMINATION.ENTERPRISE_TRANSFER':
            rule('enterprise_transfer_rule', '43', '45')
            rule('employment_plan_rule', '44', '46')
        elif key == 'TERMINATION.ILLEGAL_TERMINATION': rule('legal_classification', '39', '41')
        elif key == 'TERMINATION.EMPLOYEE_LIABILITY':
            article = '43' if historical else '40'
            require('legal_consequences', *[[loc(article, str(i))] for i in (1, 2, 3)])
        elif key == 'TERMINATION.EMPLOYER_LIABILITY': rule('employer_legal_consequences', '41', '42')
        elif key == 'TERMINATION.SEVERANCE':
            require('severance_rule', *[[loc('48' if historical else '46', str(i))] for i in (1,2,3)])
        elif key == 'TERMINATION.JOB_LOSS_ALLOWANCE':
            require('job_loss_allowance_rule', *[[loc('49' if historical else '47', str(i))] for i in (1,2,3)])
        elif key == 'TERMINATION.WITHDRAWAL': rule('withdrawal_rule', '38', '40')
        elif key == 'LEAVE.ANNUAL_LEAVE':
            article = '111' if historical else '113'; facts = analysis.facts
            if facts.get('query_intent') == 'ANNUAL_LEAVE_CALC':
                category = facts.get('work_category')
                point = 'c' if category == 'SPECIAL_HEAVY' else 'b' if category == 'HEAVY' or facts.get('minor') or facts.get('disabled') else 'a' if category == 'NORMAL' else None
                require('leave_base_rule', [loc(article, '1', point)])
            else:
                require('leave_base_rule', *[[loc(article, '1', point)] for point in ('a', 'b', 'c')])
        elif key == 'LEAVE.SENIORITY_BONUS': rule('seniority_rule', '114', '112')
        elif key == 'LEAVE.PRO_RATA_LEAVE':
            if historical:
                require('proportional_leave_rule', [loc('114', '2')])
            else:
                require('proportional_leave_rule', [loc('113', '2')])
                require('leave_calculation_rule', [loc('66', '1', documents=['145/2020/NĐ-CP'])])
        elif key == 'LEAVE.TRAVEL_DAYS':
            require('travel_time_rule', [loc('111' if historical else '113', '4' if historical else '6')])
        elif key == 'LEAVE.PUBLIC_HOLIDAY':
            # General holiday questions require the whole set, not just one day.
            require('public_holiday_rule', *[[loc('115' if historical else '112', '1', point)]
              for point in ('a','b','c','d','đ','e')])
        elif key == 'LEAVE.PERSONAL_LEAVE':
            require('personal_leave_rule', *[[loc('116' if historical else '115', '1', point)]
              for point in ('a','b','c')])
        elif key == 'LEAVE.UNPAID_LEAVE':
            require('unpaid_leave_rule', [loc('116' if historical else '115', '2')],
                    [loc('116' if historical else '115', '3')])
        elif key == 'LEAVE.UNUSED_LEAVE_PAYMENT':
            require('unused_leave_payment_rule', [loc('114' if historical else '113', '1' if historical else '3')])
    return requirements


def locator_matches(item, locator: LegalLocator) -> bool:
    get = item.get if isinstance(item, dict) else lambda key: getattr(item, key, None)
    return (get('kind') == 'PROVISION' and get('document_number') in locator.documents
        and str(get('article_number') or '') == locator.article
        and (locator.clause is None or str(get('clause_number') or '') == locator.clause)
        and (locator.point is None or str(get('point_number') or '').lower() == locator.point))


def requirement_evidence(items, groups) -> list[str]:
    found = []
    for alternatives in groups:
        matches = [item.unit_id for item in items if any(locator_matches(item, locator) for locator in alternatives)]
        if not matches: return []
        found.extend(matches)
    return list(dict.fromkeys(found))


def plan_with_profiles(analysis: QueryAnalysis, legacy_plan):
    if analysis.route.value == 'DIRECT' and analysis.requested_outcome == 'LOOKUP':
        return legacy_plan
    requirements = profile_requirements(analysis)
    mandatory = list(legacy_plan.mandatory_slots)
    standalone = {'TERMINATION.MUTUAL_AGREEMENT', 'TERMINATION.EXPIRY', 'TERMINATION.DISMISSAL',
        'TERMINATION.ECONOMIC_RESTRUCTURING', 'TERMINATION.ENTERPRISE_TRANSFER',
        'TERMINATION.SEVERANCE', 'TERMINATION.JOB_LOSS_ALLOWANCE'}
    unilateral = {'TERMINATION.EMPLOYEE_UNILATERAL', 'TERMINATION.EMPLOYER_UNILATERAL'}
    if standalone.intersection(analysis.legal_subissues) and not unilateral.intersection(analysis.legal_subissues):
        mandatory = [slot for slot in mandatory if slot not in {'termination_conditions', 'notice_requirement', 'exceptions', 'mandatory_reference'}]
    if any(key.startswith('LEAVE.') for key in analysis.legal_subissues):
        mandatory = [slot for slot in mandatory if slot not in {'conditions', 'exceptions'}]
    if 'TERMINATION.EMPLOYEE_UNILATERAL' in analysis.legal_subissues and analysis.facts.get('notice_exception') is not None:
        mandatory = [slot for slot in mandatory if slot != 'exceptions']
    if legal_regime_for(analysis.query_date) == 'BLLD_2012':
        # Never demand 2019-only exception/calculation locations for a 2012 query.
        mandatory = [slot for slot in mandatory if slot not in {
            'exception_rule', 'wage_delay_reference', 'disclosure_reference', 'leave_calculation_rule'}]
    # Don't let unrelated coarse branching discard one part of a multi-issue request.
    mandatory = list(dict.fromkeys(mandatory + list(requirements)))
    if requirements:
        mandatory = [slot for slot in mandatory if slot != 'mandatory_reference']
    return legacy_plan.model_copy(update={'mandatory_slots': mandatory, 'slot_requirements': requirements})


def profile_fact_questions(subissues, facts, query_date):
    """Only issue-specific facts, used for alternate termination mechanisms."""
    missing = []
    if 'TERMINATION.DISMISSAL' in subissues:
        if not facts.get('discipline_reason') and not facts.get('termination_reason'):
            missing.append('Công ty nêu hành vi và lý do cụ thể nào để sa thải?')
        if not facts.get('discipline_procedure'):
            missing.append('Công ty đã thực hiện những bước nào trong thủ tục xử lý kỷ luật?')
        if facts.get('protected_status') is None:
            missing.append('Người lao động có đang mang thai, nghỉ thai sản hoặc thuộc thời gian được bảo vệ khi xử lý kỷ luật không?')
    if 'TERMINATION.EXPIRY' in subissues and not facts.get('contract_type'):
        missing.append('Hợp đồng có xác định thời hạn không và ngày hết hạn ghi trong hợp đồng là ngày nào?')
    if any(key in subissues for key in ('TERMINATION.ECONOMIC_RESTRUCTURING', 'TERMINATION.ENTERPRISE_TRANSFER')):
        if not facts.get('employment_plan'):
            missing.append('Công ty đã xây dựng và thực hiện phương án sử dụng lao động như thế nào?')
    if any(key in subissues for key in ('TERMINATION.SEVERANCE','TERMINATION.JOB_LOSS_ALLOWANCE')):
        if not any(facts.get(field) is not None for field in ('worked_months','service_years','service_months')):
            missing.append('Người lao động đã làm việc cho người sử dụng lao động này bao lâu?')
        if facts.get('unemployment_insurance_period') is None:
            missing.append('Thời gian đã tham gia bảo hiểm thất nghiệp và thời gian đã được trả trợ cấp trước đây là bao lâu?')
        if not facts.get('termination_reason') and not facts.get('mutual_termination_agreement'):
            missing.append('Hợp đồng chấm dứt theo căn cứ hoặc lý do nào?')
    return missing


def taxonomy_exclusion(item, subissues: list[str], facts: dict) -> str | None:
    doc = item.document_number
    if doc not in CURRENT_CODE + OLD_CODE: return None
    old = doc in OLD_CODE; article = str(item.article_number or '')
    employee = 'TERMINATION.EMPLOYEE_UNILATERAL' in subissues
    employer = 'TERMINATION.EMPLOYER_UNILATERAL' in subissues
    if employee and not employer and article in ({'38', '39', '42'} if old else {'36', '37', '41'}):
        return 'SUBISSUE_WRONG_ACTOR_EMPLOYER_RULE'
    if employer and not employee and article in ({'37', '43'} if old else {'35', '40'}):
        return 'SUBISSUE_WRONG_ACTOR_EMPLOYEE_RULE'
    alternate = any(key in subissues for key in ('TERMINATION.DISMISSAL', 'TERMINATION.ECONOMIC_RESTRUCTURING',
        'TERMINATION.ENTERPRISE_TRANSFER', 'TERMINATION.MUTUAL_AGREEMENT', 'TERMINATION.EXPIRY'))
    if alternate and not employee and not employer and article in ({'37', '38'} if old else {'35', '36'}):
        return 'SUBISSUE_TERMINATION_MECHANISM_MISMATCH'
    annual = any(key in subissues for key in ('LEAVE.ANNUAL_LEAVE', 'LEAVE.SENIORITY_BONUS',
        'LEAVE.PRO_RATA_LEAVE', 'LEAVE.TRAVEL_DAYS', 'LEAVE.UNUSED_LEAVE_PAYMENT'))
    other_leave = any(key in subissues for key in ('LEAVE.PUBLIC_HOLIDAY', 'LEAVE.PERSONAL_LEAVE', 'LEAVE.UNPAID_LEAVE'))
    if other_leave and not annual and article in ({'111', '112', '114'} if old else {'113', '114'}):
        return 'SUBISSUE_LEAVE_TYPE_MISMATCH'
    if annual and facts.get('query_intent') == 'ANNUAL_LEAVE_CALC' and article == ('111' if old else '113') and item.clause_number == '1':
        category = facts.get('work_category')
        expected = 'c' if category == 'SPECIAL_HEAVY' else 'b' if category == 'HEAVY' or facts.get('minor') or facts.get('disabled') else 'a' if category == 'NORMAL' else None
        if expected and item.point_number and item.point_number != expected:
            return 'SUBISSUE_LEAVE_CATEGORY_MISMATCH'
    return None
