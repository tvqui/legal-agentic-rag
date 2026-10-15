import { LoaderCircle, Sparkles } from 'lucide-react'

const STAGES = { intake: 'Đã nhận câu hỏi', analysis: 'Đang phân tích câu hỏi', understanding: 'Đang xác định ý hỏi và ngữ cảnh', planning: 'Đang lập kế hoạch tìm căn cứ', retrieval: 'Đang truy xuất và lọc nguồn', applicability: 'Đang kiểm tra điều kiện áp dụng', generation: 'Đang tổng hợp và kiểm chứng câu trả lời', completed: 'Đã xử lý xong' }

export function AgentStatus({ active, stage }) {
  if (!active) return null
  return <section className="agent-status" aria-live="polite">
    <div className="agent-summary">
      <span className="agent-pulse"><Sparkles size={14} /></span>
      <span>{STAGES[stage] || 'Đang chờ máy chủ xác nhận tiến độ…'}</span>
      <LoaderCircle size={15} className="spin" />
    </div>
  </section>
}
