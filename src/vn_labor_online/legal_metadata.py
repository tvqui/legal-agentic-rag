"""Display metadata and norm role, derived from existing artifact fields."""
import re
def document_type(number, title=None, declared=None):
    if declared: return declared
    number=str(number or '').upper(); title=str(title or '').lower()
    if '/VBHN-' in number: return 'Văn bản hợp nhất'
    if '/NĐ-CP' in number: return 'Nghị định'
    if '/TT-' in number: return 'Thông tư'
    if '/QĐ-' in number: return 'Quyết định'
    if '/QH' in number:
        return 'Bộ luật' if 'bộ luật' in title else 'Luật'
    return None

def norm_role(number, title, text):
    if number=='12/2022/NĐ-CP' or 'xử phạt' in str(title or '').lower():
        return 'SANCTION'
    # A prohibition OF a fine is a governing rule, not a sanction merely
    # because the words 'phạt tiền' occur in its quoted text.
    if re.search(r'\b(?:bị\s+)?phạt tiền\s+(?:từ\b|đến\b|\d)',str(text or '').lower()):return 'SANCTION'
    return 'RULE'
