"""Broad labour-domain routing hints. These are NOT approved legal profiles.

No amounts, statutory locations or benchmark IDs live in this registry. An
intent label can request evidence; it can never make evidence sufficient.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
import re,unicodedata

VERSION='labor-topics-v1'

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
 Topic('contract_types','Loại và hình thức hợp đồng lao động','CONTRACT',('loại hợp đồng','hợp đồng miệng','hợp đồng điện tử','không ký hợp đồng','giao kết hợp đồng'),('CONTRACT.CONTRACT_TYPES','CONTRACT.EMPLOYER_INFORMATION','CONTRACT.PROHIBITED_ACTS')),
 Topic('contract_renewal','Hết hạn và ký tiếp hợp đồng','CONTRACT',('ký lại hợp đồng','tái ký','gia hạn hợp đồng','hợp đồng thứ ba','ký 3 lần')),
 Topic('recruitment_information','Thông tin và hành vi khi tuyển dụng','CONTRACT',('tuyển dụng','ứng viên','giữ bằng','giữ bản chính','đặt cọc'),('CONTRACT.EMPLOYER_INFORMATION','CONTRACT.PROHIBITED_ACTS')),
 Topic('probation','Thỏa thuận, thời hạn, tiền lương và kết thúc thử việc','CONTRACT',('thử việc',),('CONTRACT.PROBATION_',)),
 Topic('wage_payment','Trả lương và bảo vệ tiền lương','WAGE',('trả lương','kỳ hạn lương','chậm lương','khấu trừ lương','phiếu lương','bảng kê lương'),('CONTRACT.PROBATION_PAY',)),
 Topic('minimum_wage','Lương tối thiểu và căn cứ tính','WAGE',('lương tối thiểu',)),
 Topic('overtime','Làm thêm giờ và tiền lương làm thêm','WORKING_TIME',('làm thêm giờ','tăng ca','tiền làm thêm'),('WORKING_TIME.OVERTIME_LIMITS','WAGE.OVERTIME_PAY')),
 Topic('night_work','Làm việc ban đêm và tiền lương','WORKING_TIME',('ban đêm','ca đêm'),('WAGE.NIGHT_PAY',)),
 Topic('normal_hours','Thời giờ làm việc và nghỉ giữa giờ','WORKING_TIME',('giờ làm việc','thời giờ làm việc','nghỉ giữa giờ','nghỉ hằng tuần','nghỉ hàng tuần')),
 Topic('annual_leave','Nghỉ hằng năm và thâm niên','LEAVE',('nghỉ hằng năm','nghỉ hàng năm','nghỉ phép','phép năm','ngày phép','thâm niên'),('LEAVE.ANNUAL_LEAVE','LEAVE.SENIORITY_BONUS','LEAVE.PRO_RATA_LEAVE','LEAVE.TRAVEL_DAYS','LEAVE.UNUSED_LEAVE_PAYMENT')),
 Topic('other_leave','Nghỉ lễ, nghỉ việc riêng và nghỉ không lương','LEAVE',('nghỉ lễ','nghỉ tết','nghỉ việc riêng','nghỉ không lương','nghỉ không hưởng lương','kết hôn'),('LEAVE.PUBLIC_HOLIDAY','LEAVE.PERSONAL_LEAVE','LEAVE.UNPAID_LEAVE')),
 Topic('training','Học nghề, tập nghề và đào tạo','TRAINING',('học nghề','tập nghề','đào tạo','thực tập'),('TRAINING.',)),
 Topic('suspension','Tạm hoãn hợp đồng lao động','CONTRACT',('tạm hoãn','hoãn hợp đồng')),
 Topic('job_transfer','Chuyển người lao động làm công việc khác','CONTRACT',('chuyển làm công việc khác','chuyển công việc','điều chuyển','điều động','công việc khác so với hợp đồng')),
 Topic('termination_grounds','Căn cứ và thủ tục chấm dứt hợp đồng','TERMINATION',('chấm dứt hợp đồng','hợp đồng hết hạn','hết hạn hợp đồng'),('TERMINATION.',)),
 Topic('employee_exit','Người lao động đơn phương chấm dứt','TERMINATION',('người lao động đơn phương','tôi muốn nghỉ','xin nghỉ việc'),('TERMINATION.EMPLOYEE_UNILATERAL','TERMINATION.EMPLOYEE_LIABILITY')),
 Topic('employer_exit','Người sử dụng lao động đơn phương chấm dứt','TERMINATION',('người sử dụng lao động đơn phương','công ty đơn phương','công ty cho nghỉ'),('TERMINATION.EMPLOYER_UNILATERAL','TERMINATION.EMPLOYER_LIABILITY')),
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
 'equality':('phân biệt đối xử trong lao động','đối xử bất bình đẳng'),
 'older_workers':('người cao tuổi làm việc','đã hưởng lương hưu'),
 'labour_hire':('thuê lại người lao động',),
 'individual_dispute':('tranh chấp cá nhân','kiện công ty'),
 'collective_dispute':('tranh chấp về quyền','tranh chấp về lợi ích'),
 'occupational_safety':('vệ sinh, an toàn lao động',),
 'unemployment':('đóng bhtn','hưởng thất nghiệp'),
 'retirement':('nghỉ hưu','tuổi nghỉ hưu'),
 'employee_data':('theo dõi nhân viên','giám sát nhân viên'),
}
TOPICS=[replace(topic,phrases=topic.phrases+ALIASES.get(topic.key,())) for topic in TOPICS]

def detect_topics(query):
    text=fold(query)
    # Personal leave is an absence, not termination. Keep separately stated
    # termination clauses available instead of excluding the entire question.
    termination_text=re.sub(r'(?<!\w)(?:toi muon |xin )?nghi viec rieng(?!\w)',' ',text)
    return [topic for topic in TOPICS if any(re.search(r'(?<!\w)'+re.escape(fold(phrase))+r'(?!\w)',
      termination_text if topic.issue=='TERMINATION' else text) for phrase in topic.phrases)]
