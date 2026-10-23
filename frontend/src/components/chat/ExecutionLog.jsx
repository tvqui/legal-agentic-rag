import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Download, ListTree } from 'lucide-react'
import { executionOutputText, formatExecutionTime } from '../../services/executionLog'

const STATUS = { RUNNING: 'Đang chạy', DONE: 'Đã xong bước', SKIPPED: 'Bỏ qua', WARNING: 'Có giới hạn', ERROR: 'Lỗi bước', CANCELLED: 'Đã dừng' }

export function ExecutionLog({ steps = [], active = false, availability, dropped = 0 }) {
  const [expanded, setExpanded] = useState(active)
  const scrollRef = useRef(null)
  const followRef = useRef(true)
  useEffect(() => {
    if (active && followRef.current && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [steps, active, expanded])
  if (!availability && !steps.length) return null
  const failed = [...steps].reverse().find(item => item.status === 'ERROR')
  const running = [...steps].reverse().find(item => item.status === 'RUNNING')
  const download = () => {
    const blob = new Blob([JSON.stringify({ version: 'execution-steps-v1', steps, dropped }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = 'phap-dien-ai-tien-trinh.json'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section className="execution-log" aria-label="Nhật ký xử lý câu hỏi">
    <div className="execution-log-heading">
      <button type="button" className="execution-log-toggle" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>
        <ListTree size={16} /><span>Tiến trình xử lý · {steps.length} bước</span><ChevronDown size={16} className={expanded ? 'rotate' : ''} />
      </button>
      {steps.length > 0 && <button type="button" className="execution-log-download" onClick={download} title="Tải nhật ký JSON"><Download size={14} /> Tải log</button>}
    </div>
    {expanded && <>
      <p className="execution-log-note">Log từ bước thực thi trên máy chủ. “Đã xong bước” không chứng nhận kết luận pháp lý đúng. Bước bỏ qua không được tính là đã dùng công nghệ đó. Thời gian bước cha có thể gồm bước con, không cộng tất cả các dòng.</p>
      {availability === 'unsupported' && <p className="execution-log-note">Backend phiên này chưa cung cấp log chi tiết. Cần cập nhật và khởi động lại backend.</p>}
      {availability === 'waiting' && !steps.length && <p className="execution-log-note">Đang chờ log máy chủ; chưa xác nhận bước nào đã chạy.</p>}
      {availability === 'disconnected' && <p className="execution-log-alert">Kênh tiến trình đang gián đoạn. Log bên dưới là lần nhận gần nhất; chưa thể xác định máy chủ đã dừng hay vẫn chạy.</p>}
      {failed && <p className="execution-log-alert">Có lỗi ở bước: <strong>{failed.name}</strong>. Pipeline có thể đã dùng dự phòng; xem cả trạng thái câu trả lời.</p>}
      {!active && running && <p className="execution-log-note">Chưa nhận được trạng thái kết thúc cho một số bước; không coi chúng là đã hoàn tất.</p>}
      {dropped > 0 && <p className="execution-log-note">Đã bỏ {dropped} sự kiện cũ do giới hạn bộ nhớ. Tải log đang còn để đối chiếu.</p>}
      {steps.length > 0 && <div className="execution-log-scroll" ref={scrollRef} role="region" aria-label="Các bước, tầng, công nghệ và output" tabIndex={0}
        onScroll={event => { const node = event.currentTarget; followRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 50 }}>
        <table className="execution-log-table">
          <thead><tr><th>Bước / tầng</th><th>Công nghệ</th><th>Output tóm tắt</th><th>Thời gian</th></tr></thead>
          <tbody>{steps.map((item, index) => <tr key={`${item.id}-${index}`} className={`execution-row-${item.status.toLowerCase()}`}>
            <td><strong>{index + 1}. {item.name}</strong><span className="execution-layer">{item.layer}</span><span className={`execution-badge ${item.status.toLowerCase()}`}>{STATUS[item.status]}</span></td>
            <td>{item.status === 'SKIPPED' ? 'Không thực hiện bước này' : item.technology}</td>
            <td><span className="execution-output-type">{item.output_type}</span><pre>{executionOutputText(item.output)}</pre></td>
            <td>{item.status === 'SKIPPED' ? '—' : formatExecutionTime(item.elapsed_ms)}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </>}
  </section>
}
