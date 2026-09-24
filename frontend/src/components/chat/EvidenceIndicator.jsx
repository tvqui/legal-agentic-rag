import { Info, ShieldCheck } from 'lucide-react'

const labels = {
  SUFFICIENT: 'Đủ bằng chứng',
  PARTIAL: 'Bằng chứng một phần',
  INSUFFICIENT: 'Chưa đủ bằng chứng',
  CONFLICTING: 'Bằng chứng xung đột',
  NEED_MORE_FACTS: 'Cần thêm dữ kiện',
}

export function EvidenceIndicator({ sourceCount = 0, evidenceStatus, answerStatus }) {
  return <div className="evidence-indicator" title={`Trạng thái backend: ${answerStatus || 'không xác định'}`}>
    <ShieldCheck size={15} />
    <span><strong>{sourceCount} nguồn</strong> được dẫn</span>
    <span className="evidence-score"><Info size={12} /> {labels[evidenceStatus] || evidenceStatus || 'Chưa đánh giá'}</span>
  </div>
}
