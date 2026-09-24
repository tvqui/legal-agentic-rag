import { LoaderCircle, Sparkles } from 'lucide-react'

export function AgentStatus({ active }) {
  if (!active) return null
  return <section className="agent-status" aria-live="polite">
    <div className="agent-summary">
      <span className="agent-pulse"><Sparkles size={14} /></span>
      <span>AI đang phân tích, truy xuất và kiểm tra bằng chứng pháp lý</span>
      <LoaderCircle size={15} className="spin" />
    </div>
  </section>
}
