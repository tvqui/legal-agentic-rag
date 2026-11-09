"""Ground separately requested non-labour parts without dropping labour tasks."""
import re

LABOUR_REQUEST=re.compile(r'\b(?:tiền lương|trả lương|khấu trừ lương|thử việc|nghỉ phép|phép năm|'
    r'nghỉ hằng năm|nghỉ hàng năm|báo trước|sa thải|kỷ luật lao động|chấm dứt hợp đồng lao động|'
    r'hợp đồng lao động|công đoàn|tai nạn lao động|bảo hiểm xã hội|bảo hiểm thất nghiệp|'
    r'thai sản|quấy rối tại nơi làm việc|giữ (?:bằng|bản chính|căn cước)|làm thêm giờ)\b',re.I)
FOREIGN_REQUEST=re.compile(r'\b(?:ly hôn|quyền nuôi con|chia di sản|tranh chấp đất|thửa đất|'
    r'quyền sử dụng đất|(?:cấp|xin|đổi|gia hạn)(?: lại)? hộ chiếu|mua bán nhà|chuyển nhượng căn hộ|'
    r'thuế chuyển nhượng|mức án|phạt tù|cấu thành tội)\b',re.I)


def mixed_scope_exclusions(query):
    # Keep exact substrings for provenance. A crime can be a dismissal fact:
    # do not exclude a segment which asks a labour-law conclusion about it.
    segments=re.split(r'(?<=[.;?!])\s+|\n+|;\s*|\s+(?:đồng thời|ngoài ra|và)\s+(?=(?:tôi|thủ tục|việc|cần)\b)',query)
    foreign=[segment.strip() for segment in segments
             if FOREIGN_REQUEST.search(segment) and not LABOUR_REQUEST.search(segment)]
    labour=any(LABOUR_REQUEST.search(segment) for segment in segments if segment.strip() not in foreign)
    return list(dict.fromkeys(foreign)) if labour else []
