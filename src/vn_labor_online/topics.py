"""Broad labour-domain routing hints. These are NOT approved legal profiles.

No amounts, statutory locations or benchmark IDs live in this registry. An
intent label can request evidence; it can never make evidence sufficient.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
import re,unicodedata

VERSION='labor-topics-v3'

def fold(text):
    text=unicodedata.normalize('NFD',text.lower()).replace('đ','d')
    text=' '.join(''.join(c for c in text if unicodedata.category(c)!='Mn').split())
    for abbreviation,expanded in {'hdld':'hop dong lao dong','nld':'nguoi lao dong',
      'nsdld':'nguoi su dung lao dong','tuldtt':'thoa uoc lao dong tap the'}.items():
        text=re.sub(r'\b'+abbreviation+r'\b',expanded,text)
    return text

@dataclass(frozen=True)
class Topic:
    key:str
    label:str
    issue:str
    phrases:tuple[str,...]
    profile_prefixes:tuple[str,...]=()

# A topic is a mechanism or question domain, never an entitlement/conclusion.
TOPICS=[
 Topic('relationship','Xác định quan hệ lao động','CONTRACT',('quan hệ lao động','hợp đồng dịch vụ','hợp đồng cộng tác viên'),('CONTRACT.RELATIONSHIP_QUALIFICATION',)),
 Topic('contract_types','Loại và hình thức hợp đồng lao động','CONTRACT',('loại hợp đồng','hợp đồng miệng','hợp đồng điện tử','không ký hợp đồng','giao kết hợp đồng'),('CONTRACT.CONTRACT_TYPES','CONTRACT.FORM','CONTRACT.DURATION','CONTRACT.CONTINUATION','CONTRACT.MULTIPLE_EMPLOYERS','CONTRACT.APPENDIX','CONTRACT.CONFIDENTIALITY','CONTRACT.EMPLOYER_INFORMATION','CONTRACT.PROHIBITED_ACTS')),
 Topic('contract_renewal','Hết hạn và ký tiếp hợp đồng','CONTRACT',('ký lại hợp đồng','tái ký','gia hạn hợp đồng','hợp đồng thứ ba','ký 3 lần'),('CONTRACT.CONTINUATION','CONTRACT.APPENDIX')),
 Topic('recruitment_information','Thông tin và hành vi khi tuyển dụng','CONTRACT',('tuyển dụng','ứng viên','giữ bằng','giữ bản chính','đặt cọc'),('CONTRACT.EMPLOYER_INFORMATION','CONTRACT.PROHIBITED_ACTS')),
 Topic('probation','Thỏa thuận, thời hạn, tiền lương và kết thúc thử việc','CONTRACT',('thử việc',),('CONTRACT.PROBATION_',)),
 Topic('wage_payment','Trả lương và bảo vệ tiền lương','WAGE',('trả lương','kỳ hạn lương','chậm lương','khấu trừ lương','phiếu lương','bảng kê lương'),('CONTRACT.PROBATION_PAY','WAGE.EQUAL_PAY','WAGE.MINIMUM_FLOOR','WAGE.PAYMENT_','WAGE.DOWNTIME')),
 Topic('minimum_wage','Lương tối thiểu và căn cứ tính','WAGE',('lương tối thiểu',),('WAGE.MINIMUM_FLOOR',)),
 Topic('overtime','Làm thêm giờ và tiền lương làm thêm','WORKING_TIME',('làm thêm giờ','tăng ca','tiền làm thêm'),('WORKING_TIME.OVERTIME_LIMITS','WORKING_TIME.OVERTIME_CONSENT','WORKING_TIME.EMERGENCY_OVERTIME','WAGE.OVERTIME_PAY')),
 Topic('night_work','Làm việc ban đêm và tiền lương','WORKING_TIME',('ban đêm','ca đêm'),('WAGE.NIGHT_PAY','WORKING_TIME.NIGHT_DEFINITION')),
 Topic('normal_hours','Thời giờ làm việc và nghỉ giữa giờ','WORKING_TIME',('giờ làm việc','thời giờ làm việc','nghỉ giữa giờ','nghỉ hằng tuần','nghỉ hàng tuần'),('WORKING_TIME.NORMAL_HOURS','WORKING_TIME.WEEKLY_POLICY','WORKING_TIME.WEEKLY_REST','WORKING_TIME.NIGHT_DEFINITION','WORKING_TIME.REST_BREAK','WORKING_TIME.SHIFT_INTERVAL')),
 Topic('annual_leave','Nghỉ hằng năm và thâm niên','LEAVE',('nghỉ hằng năm','nghỉ hàng năm','nghỉ phép','phép năm','ngày phép','thâm niên'),('LEAVE.ANNUAL_LEAVE','LEAVE.ANNUAL_SCHEDULE','LEAVE.SENIORITY_BONUS','LEAVE.PRO_RATA_LEAVE','LEAVE.TRAVEL_DAYS','LEAVE.UNUSED_LEAVE_PAYMENT')),
 Topic('other_leave','Nghỉ lễ, nghỉ việc riêng và nghỉ không lương','LEAVE',('nghỉ lễ','nghỉ tết','nghỉ việc riêng','nghỉ không lương','nghỉ không hưởng lương','kết hôn'),('LEAVE.PUBLIC_HOLIDAY','LEAVE.PERSONAL_LEAVE','LEAVE.UNPAID_LEAVE')),
 Topic('training','Học nghề, tập nghề và đào tạo','TRAINING',('học nghề','tập nghề','đào tạo','thực tập'),('TRAINING.',)),
 Topic('suspension','Tạm hoãn hợp đồng lao động','CONTRACT',('tạm hoãn','hoãn hợp đồng')),
 Topic('job_transfer','Chuyển người lao động làm công việc khác','CONTRACT',('chuyển làm công việc khác','chuyển công việc','điều chuyển','điều động','công việc khác so với hợp đồng')),
 Topic('termination_grounds','Căn cứ và thủ tục chấm dứt hợp đồng','TERMINATION',('chấm dứt hợp đồng','hợp đồng hết hạn','hết hạn hợp đồng'),('TERMINATION.','CONTRACT.PROBATION_CANCELLATION')),
 Topic('employee_exit','Người lao động đơn phương chấm dứt','TERMINATION',('người lao động đơn phương','tôi muốn nghỉ','xin nghỉ','chủ động xin nghỉ'),('TERMINATION.EMPLOYEE_UNILATERAL','TERMINATION.EMPLOYEE_LIABILITY','CONTRACT.PROBATION_CANCELLATION')),
 Topic('employer_exit','Người sử dụng lao động đơn phương chấm dứt','TERMINATION',('người sử dụng lao động đơn phương','công ty đơn phương','công ty chủ động chấm dứt','công ty cho nghỉ'),('TERMINATION.EMPLOYER_UNILATERAL','TERMINATION.EMPLOYER_LIABILITY','CONTRACT.PROBATION_CANCELLATION')),
 Topic('unlawful_exit','Chấm dứt trái pháp luật và hậu quả','TERMINATION',('chấm dứt trái pháp luật','đơn phương trái pháp luật','nghỉ trái luật'),('TERMINATION.ILLEGAL_TERMINATION','TERMINATION.EMPLOYEE_LIABILITY','TERMINATION.EMPLOYER_LIABILITY')),
 Topic('severance','Trợ cấp thôi việc và mất việc','TERMINATION',('trợ cấp thôi việc','trợ cấp mất việc'),('TERMINATION.SEVERANCE','TERMINATION.JOB_LOSS_ALLOWANCE')),
 Topic('restructuring','Cơ cấu, công nghệ và tổ chức lại doanh nghiệp','TERMINATION',('thay đổi cơ cấu','lý do kinh tế','tái cơ cấu','sáp nhập','chia tách doanh nghiệp'),('TERMINATION.ECONOMIC_RESTRUCTURING','TERMINATION.ENTERPRISE_TRANSFER')),
 Topic('discipline','Căn cứ, hình thức và thủ tục kỷ luật','DISCIPLINE',('kỷ luật lao động','xử lý kỷ luật','sa thải','khiển trách'),('TERMINATION.DISMISSAL',)),
 Topic('internal_rules','Nội quy lao động','DISCIPLINE',('nội quy lao động','đăng ký nội quy')),
 Topic('material_liability','Trách nhiệm vật chất và bồi thường tài sản','DISCIPLINE',('trách nhiệm vật chất','làm hỏng','làm mất tài sản','bồi thường tài sản','bồi thường thiệt hại tài sản')),
 Topic('harassment','Quấy rối tình dục tại nơi làm việc','HARASSMENT',('quấy rối tình dục','quấy rối tại nơi làm việc')),
 Topic('equality','Bình đẳng và phân biệt đối xử','EQUALITY',('phân biệt đối xử','bình đẳng giới','phân biệt giới tính','phân biệt tuyển dụng')),
 Topic('maternity','Lao động nữ, mang thai và thai sản','MATERNITY',('lao động nữ','mang thai','thai sản','nuôi con nhỏ','nuôi con dưới')),
 Topic('minor_workers','Lao động chưa thành niên','MINOR_WORKER',('chưa thành niên','chưa đủ 18 tuổi','dưới 18 tuổi','dưới 15 tuổi')),
 Topic('older_workers','Lao động cao tuổi','RETIREMENT',('lao động cao tuổi','người lao động cao tuổi','đã nghỉ hưu')),
 Topic('disabled_workers','Lao động là người khuyết tật','DISABILITY',('khuyết tật',)),
 Topic('domestic_workers','Lao động giúp việc gia đình','DOMESTIC_WORKER',('giúp việc gia đình','người giúp việc')),
 Topic('foreign_workers','Lao động nước ngoài tại Việt Nam','FOREIGN_WORKER',('lao động nước ngoài','giấy phép lao động','người nước ngoài làm việc')),
 Topic('overseas_workers','Người Việt Nam đi làm việc ở nước ngoài','OVERSEAS_WORKER',('đi làm việc ở nước ngoài','xuất khẩu lao động','đi lao động nước ngoài')),
 Topic('labour_hire','Cho thuê lại lao động','LABOUR_HIRE',('cho thuê lại lao động','thuê lại lao động')),
 Topic('dialogue','Đối thoại tại nơi làm việc','COLLECTIVE_RELATIONS',('đối thoại tại nơi làm việc','đối thoại định kỳ')),
 Topic('bargaining','Thương lượng tập thể','COLLECTIVE_RELATIONS',('thương lượng tập thể',)),
 Topic('collective_agreement','Thỏa ước lao động tập thể','COLLECTIVE_RELATIONS',('thỏa ước lao động tập thể','thỏa ước tập thể')),
 Topic('worker_representation','Công đoàn và tổ chức đại diện người lao động','UNION',('công đoàn','tổ chức đại diện người lao động','tổ chức đại diện nlđ')),
 Topic('individual_dispute','Tranh chấp lao động cá nhân','DISPUTE',('tranh chấp lao động cá nhân','hòa giải viên','khởi kiện','tòa án lao động')),
 Topic('collective_dispute','Tranh chấp lao động tập thể','DISPUTE',('tranh chấp lao động tập thể','trọng tài lao động','tranh chấp tập thể')),
 Topic('strike','Đình công','COLLECTIVE_RELATIONS',('đình công',)),
 Topic('occupational_safety','An toàn, vệ sinh lao động','SAFETY',('an toàn lao động','vệ sinh lao động','an toàn vệ sinh','bảo hộ lao động')),
 Topic('occupational_accident','Tai nạn lao động và bệnh nghề nghiệp','SAFETY',('tai nạn lao động','bệnh nghề nghiệp')),
 Topic('social_insurance','Bảo hiểm xã hội','SOCIAL_INSURANCE',('bảo hiểm xã hội','bhxh')),
 Topic('health_insurance','Bảo hiểm y tế','HEALTH_INSURANCE',('bảo hiểm y tế','bhyt')),
 Topic('unemployment','Bảo hiểm thất nghiệp và việc làm','UNEMPLOYMENT_INSURANCE',('bảo hiểm thất nghiệp','trợ cấp thất nghiệp','bhtn')),
 Topic('retirement','Tuổi nghỉ hưu và hưu trí','RETIREMENT',('tuổi nghỉ hưu','tuổi hưu','hưu trí','lương hưu')),
 Topic('remedies','Xử phạt, khiếu nại và thời hiệu','DISPUTE',('xử phạt','vi phạm hành chính','phạt hành chính','thời hiệu','thời hạn khởi kiện','khiếu nại','thanh tra lao động')),
 Topic('income_tax','Thuế thu nhập cá nhân từ tiền lương','TAX',('thuế thu nhập cá nhân','thuế tncn')),
 Topic('employee_data','Dữ liệu cá nhân và giám sát người lao động','PERSONAL_DATA',('dữ liệu cá nhân','thông tin cá nhân','sinh trắc','camera','giám sát người lao động')),
]

ALIASES={
 'relationship':('freelance','không phải hợp đồng lao động','bản chất quan hệ'),
 'contract_types':('loại hđlđ','ký hđlđ','ký hợp đồng lao động'),
 'contract_renewal':('hđlđ hết hạn','hợp đồng của tôi hết hạn','tiếp tục làm việc sau khi hết hạn'),
 'wage_payment':('tiền lương theo hợp đồng','tiền công','tiền thưởng','thưởng tết'),
 'minimum_wage':('trả dưới mức tối thiểu','dưới tối thiểu'),
 'normal_hours':('giờ/ngày','ngày/tuần','giờ một ngày','thời gian làm việc','nghỉ hàng tuần'),
 'night_work':('giờ đêm','làm đêm'),
 'annual_leave':('nghỉ 12','nghỉ 14','nghỉ 16','ngày nghỉ hằng năm'),
 'other_leave':('lễ tết','lễ, tết','người thân mất','người thân của tôi vừa mất'),
 'suspension':('hoàn thành nghĩa vụ quân sự','trở lại làm việc sau tạm hoãn'),
 'job_transfer':('chuyển việc tạm thời','chuyển sang làm','chuyển sang bộ phận','chuyển người lao động sang việc khác'),
 'termination_grounds':('hđlđ chấm dứt','nghỉ việc','thôi việc','thời hạn báo trước','báo trước','đơn phương chấm dứt'),
 'employee_exit':('người lao động gửi đơn nghỉ','người lao động phải báo trước','tôi chỉ báo trước'),
 'employer_exit':('doanh nghiệp đơn phương','người sử dụng lao động cho nghỉ'),
 'unlawful_exit':('nghỉ trái pháp luật','sa thải trái pháp luật'),
 'internal_rules':('đăng ký nội quy','sửa nội quy'),
 'material_liability':('thiệt hại tài sản','mất dụng cụ','hư hỏng tài sản'),
 'equality':('phân biệt đối xử trong lao động','đối xử bất bình đẳng','chỉ tuyển nam','chỉ tuyển nữ','không tuyển nam','không tuyển nữ'),
 'older_workers':('người cao tuổi làm việc','đã hưởng lương hưu'),
 'labour_hire':('thuê lại người lao động',),
 'individual_dispute':('tranh chấp cá nhân','kiện công ty','hòa giải','ra tòa án'),
 'collective_dispute':('tranh chấp về quyền','tranh chấp về lợi ích'),
 'occupational_safety':('vệ sinh, an toàn lao động',),
 'unemployment':('đóng bhtn','hưởng thất nghiệp'),
 'retirement':('nghỉ hưu','tuổi nghỉ hưu'),
 'employee_data':('theo dõi nhân viên','giám sát nhân viên'),
}
TOPICS=[replace(topic,phrases=topic.phrases+ALIASES.get(topic.key,())) for topic in TOPICS]


def occupational_accident_context(query):
    text=fold(query)
    injury=any(term in text for term in ('tai nan','bi thuong','chan thuong'))
    workplace=any(term in text for term in ('trong gio lam viec','tai noi lam viec','khi dang lam viec',
        'khi thuc hien cong viec','lam nhiem vu','trong ca lam','tai xuong','trong xuong','tai cong truong'))
    return 'tai nan lao dong' in text or injury and workplace


def detect_topics(query):
    text=fold(query)
    explicit_hours=bool(re.search(r'(?:lam(?: viec)?|thoi gio lam viec|thoi gian lam viec)[^.;?!]{0,35}(?:toi da|gioi han)[^.;?!]{0,25}(?:bao nhieu|may)\s+(?:gio|tieng)\b',text))
    accident_context=occupational_accident_context(query)
    # Occurrence during working hours is context for investigating an accident,
    # not automatically a request about hour limits or proof of a legal accident.
    hours_text=re.sub(r'\btrong gio lam viec\b',' ',text) if accident_context else text
    # Personal leave is an absence, not termination. Keep separately stated
    # termination clauses available instead of excluding the entire question.
    termination_text=re.sub(r'(?<!\w)(?:toi muon |xin )?nghi viec rieng(?!\w)',' ',text)
    matched=[topic for topic in TOPICS if (topic.key=='occupational_accident' and accident_context)
      or (topic.key=='normal_hours' and explicit_hours) or any(
      re.search(r'(?<!\w)'+re.escape(fold(phrase))+r'(?!\w)',
      termination_text if topic.issue=='TERMINATION' else hours_text if topic.key=='normal_hours' else text)
      and _surface_phrase_matches(query,phrase)
      for phrase in topic.phrases)]
    return [topic for topic in matched if _category_topic_relevant(topic,text)]


_CATEGORY_TOPICS={'older_workers','minor_workers','disabled_workers','domestic_workers','foreign_workers'}


def _category_topic_relevant(topic,text):
    if topic.key not in _CATEGORY_TOPICS:return True
    found=False
    for phrase in topic.phrases:
        for match in re.finditer(r'(?<!\w)'+re.escape(fold(phrase))+r'(?!\w)',text):
            found=True
            prefix=re.split(r'[.;!?,]|\b(?:nhung|tuy nhien)\b',text[max(0,match.start()-90):match.start()])[-1]
            negative=re.search(r'\b(?:khong|chang)(?:\s+(?:he|phai|la|nguoi|thuoc|nhom|doi|tuong|lam|cong|viec)){0,9}\s*$',prefix)
            if not negative:return True
    return not found


def excluded_category_issues(query,topics):
    """Negative case attributes must not create independent specialist tasks."""
    text=fold(query)
    excluded={topic.issue for topic in TOPICS if topic.key in _CATEGORY_TOPICS
              and not _category_topic_relevant(topic,text)}
    return excluded-{topic.issue for topic in topics}


_TONES={'\u0300','\u0301','\u0303','\u0309','\u0323'}

def _surface_phrase_matches(query,phrase):
    """Use supplied Vietnamese accents to disambiguate folded collisions.

    Unaccented tokens remain supported. Tone position variants such as hòa/hoà
    are equivalent; different supplied tones, e.g. đình/định, are not erased.
    """
    query=unicodedata.normalize('NFC',query.lower())
    for abbreviation,expanded in {'hdld':'hợp đồng lao động','hđlđ':'hợp đồng lao động',
            'nld':'người lao động','nlđ':'người lao động','nsdld':'người sử dụng lao động',
            'nsdlđ':'người sử dụng lao động','tuldtt':'thỏa ước lao động tập thể'}.items():
        query=re.sub(r'\b'+abbreviation+r'\b',expanded,query)
    actual=re.findall(r'\w+',query);expected=re.findall(r'\w+',unicodedata.normalize('NFC',phrase.lower()))
    def compatible(a,b):
        if fold(a)!=fold(b):return False
        left=unicodedata.normalize('NFD',a);right=unicodedata.normalize('NFD',b)
        if not any(unicodedata.category(c)=='Mn' for c in left):return True
        return (''.join(c for c in left if c not in _TONES)==''.join(c for c in right if c not in _TONES)
            and sorted(c for c in left if c in _TONES)==sorted(c for c in right if c in _TONES))
    return any(all(compatible(a,b) for a,b in zip(actual[i:i+len(expected)],expected))
        for i in range(len(actual)-len(expected)+1))
