import { SendHorizontal, Square } from 'lucide-react'
import { useRef, useState } from 'react'

export function ChatInput({ onSend, onStop, generating }) {
  const [value, setValue] = useState('')
  const textarea = useRef(null)
  const resize = (event) => {
    event.target.style.height = 'auto'
    event.target.style.height = `${Math.min(event.target.scrollHeight, 140)}px`
  }
  const send = () => {
    if (!value.trim() || generating) return
    onSend(value.trim())
    setValue('')
    if (textarea.current) textarea.current.style.height = 'auto'
  }
  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send()
    }
  }
  return <div className="chat-input-region">
    <div className="chat-input-shell">
      <textarea ref={textarea} value={value} onChange={(event) => { setValue(event.target.value); resize(event) }} onKeyDown={handleKeyDown} placeholder="Hỏi về pháp luật lao động Việt Nam..." aria-label="Nhập câu hỏi pháp luật" rows="1" />
      <div className="input-actions">
        <span>Enter để gửi · Shift + Enter xuống dòng</span>
        {generating
          ? <button className="stop-button" type="button" title="Dừng yêu cầu" onClick={onStop}><Square size={14} fill="currentColor" /> Dừng</button>
          : <button className="send-button" type="button" onClick={send} disabled={!value.trim()} aria-label="Gửi câu hỏi"><SendHorizontal size={17} /></button>}
      </div>
    </div>
    <p className="input-disclaimer">Kết quả hỗ trợ tra cứu, có thể ở chế độ provisional; hãy kiểm tra nguồn và trạng thái bằng chứng trước khi ra quyết định.</p>
  </div>
}
