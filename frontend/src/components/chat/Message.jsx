import { AlertTriangle, Check, Clipboard, MoreHorizontal, Pencil, RefreshCw, ThumbsDown, ThumbsUp, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { EvidenceIndicator } from './EvidenceIndicator'
import { IconButton } from '../ui/IconButton'

function formatTime(value) {
  return new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function RichContent({ content, citations = [], onCitation }) {
  const segments = content.split(/(\[\d+\])/g)
  return <div className="message-text">{segments.map((segment, index) => {
    const match = segment.match(/^\[(\d+)\]$/)
    if (match) {
      const citation = citations[Number(match[1]) - 1]
      return citation
        ? <button className="citation" onClick={() => onCitation(citation)} key={index} aria-label={`Mở nguồn ${match[1]}`}>{segment}</button>
        : <span key={index}>{segment}</span>
    }
    return segment.split('\n').map((line, lineIndex) => line
      ? <p key={`${index}-${lineIndex}`}>{line}</p>
      : <br key={`${index}-${lineIndex}`} />)
  })}</div>
}

function ErrorState({ message, onRetry }) {
  const lowEvidence = message.status === 'low-evidence'
  return <div className={`message-state ${message.status}`}>
    <strong>{lowEvidence ? 'Chưa có đủ căn cứ pháp lý đã xác minh.' : 'Không thể hoàn thành yêu cầu.'}</strong>
    <p>{message.content}</p>
    <button className="text-action" onClick={onRetry}><RefreshCw size={14} /> Thử lại</button>
  </div>
}

function ReviewNotice({ message }) {
  const notices = [...(message.limitations || []), ...(message.warnings || [])]
  if (!notices.length && !message.questions?.length) return null
  return <div className="response-notice">
    <AlertTriangle size={15} />
    <div>
      {notices.length > 0 && <p><strong>Giới hạn/cảnh báo:</strong> {notices.join(' · ')}</p>}
      {message.questions?.map((question) => <p key={question}><strong>Cần bổ sung:</strong> {question}</p>)}
    </div>
  </div>
}

export function Message({ message, onCitation, onRetry }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'
  const copy = async () => {
    await navigator.clipboard?.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1300)
  }
  const menuRef = useRef(null)
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return <article className={`message ${isUser ? 'user-message' : 'assistant-message'}`}>
    <div className="message-avatar">{isUser ? <UserRound size={17} /> : <span>PD</span>}</div>
    <div className="message-body">
      <div className="message-meta">
        <strong>{isUser ? 'Bạn' : 'Pháp Điển AI'}</strong>
        <time>{formatTime(message.createdAt)}</time>
        {!isUser && message.status === 'streaming' && <span className="streaming-label">Đang trả lời</span>}
      </div>
      {['error', 'low-evidence'].includes(message.status)
        ? <ErrorState message={message} onRetry={onRetry} />
        : <RichContent content={message.content} citations={message.citations} onCitation={onCitation} />}
      {message.status === 'streaming' && <span className="streaming-cursor" aria-label="Đang phát nội dung" />}
      {!isUser && message.status === 'completed' && <>
        <ReviewNotice message={message} />
        <EvidenceIndicator sourceCount={message.citations?.length || 0} evidenceStatus={message.evidenceStatus} answerStatus={message.answerStatus} />
      </>}
      <div className="message-actions">
        <IconButton label={copied ? 'Đã sao chép' : 'Sao chép'} onClick={copy}>{copied ? <Check size={15} /> : <Clipboard size={15} />}</IconButton>
        {isUser
          ? <IconButton label="Chỉnh sửa tin nhắn"><Pencil size={15} /></IconButton>
          : <>
            <IconButton label="Tạo lại câu trả lời" onClick={onRetry}><RefreshCw size={15} /></IconButton>
            <IconButton label="Hữu ích"><ThumbsUp size={15} /></IconButton>
            <IconButton label="Chưa hữu ích"><ThumbsDown size={15} /></IconButton>
          </>}
        <div className="action-more" ref={menuRef}>
          <IconButton label="Thêm tùy chọn" onClick={() => setMenuOpen(!menuOpen)}><MoreHorizontal size={16} /></IconButton>
          {menuOpen && <div className="context-menu message-menu"><button onClick={copy}>Sao chép</button><button>Báo cáo nội dung</button></div>}
        </div>
      </div>
    </div>
  </article>
}
