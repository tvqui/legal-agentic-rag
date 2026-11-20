import { BookOpenText, BriefcaseBusiness, CalendarDays, ChevronRight, FileText, Menu, PanelRightOpen, Scale, ShieldCheck, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ChatInput } from '../components/chat/ChatInput'
import { AgentStatus } from '../components/chat/AgentStatus'
import { Message } from '../components/chat/Message'
import { SourceDrawer } from '../components/source/SourceDrawer'
import { IconButton } from '../components/ui/IconButton'
import { chatService } from '../services/chatService'
import { conversationService } from '../services/conversationService'
import { normalizeExecutionSteps } from '../services/executionLog'

const STARTER_PROMPTS = [
  { icon: CalendarDays, title: 'Nghỉ phép năm', description: 'Số ngày nghỉ và cách tính phép', question: 'Theo pháp luật lao động Việt Nam hiện hành, người lao động được nghỉ phép năm bao nhiêu ngày và điều kiện áp dụng là gì?' },
  { icon: BriefcaseBusiness, title: 'Chấm dứt hợp đồng', description: 'Báo trước và quyền lợi khi nghỉ việc', question: 'Người lao động muốn đơn phương chấm dứt hợp đồng lao động thì phải báo trước bao lâu theo quy định hiện hành?' },
  { icon: Scale, title: 'Tiền lương & làm thêm', description: 'Lương tăng ca và các khoản liên quan', question: 'Theo pháp luật lao động Việt Nam, tiền lương làm thêm giờ vào ngày nghỉ hằng tuần được tính thế nào?' },
  { icon: FileText, title: 'Hợp đồng lao động', description: 'Thời hạn, nội dung và quyền của bạn', question: 'Hợp đồng lao động cần có những nội dung chủ yếu nào theo pháp luật lao động Việt Nam hiện hành?' },
]

function WelcomePanel({ onAsk }) {
  return <section className="welcome-panel" aria-labelledby="welcome-heading">
    <div className="welcome-symbol" aria-hidden="true"><span className="welcome-symbol-ring"/><Scale size={31} strokeWidth={1.7}/></div>
    <div className="welcome-kicker"><Sparkles size={13}/> HIỂU LUẬT ĐỂ BẢO VỆ QUYỀN LỢI</div>
    <h2 id="welcome-heading">Quyền lợi của bạn,<br /><em>giải thích thật dễ hiểu.</em></h2>
    <p className="welcome-description">Hỏi về hợp đồng, lương, nghỉ phép và những tình huống tại nơi làm việc. Pháp Điển AI giúp bạn tìm hiểu quy định liên quan cùng căn cứ để đối chiếu.</p>
    <div className="starter-intro"><span>GỢI Ý ĐỂ BẮT ĐẦU</span><ChevronRight size={14}/></div>
    <div className="starter-grid">
      {STARTER_PROMPTS.map(({ icon: Icon, title, description, question }) => <button className="starter-card" type="button" key={title} onClick={() => onAsk(question)}>
        <span className="starter-icon"><Icon size={19} strokeWidth={1.85}/></span><span className="starter-card-content"><strong>{title}</strong><small>{description}</small></span><ChevronRight className="starter-arrow" size={16}/>
      </button>)}
    </div>
    <p className="welcome-footnote"><ShieldCheck size={14}/> Luôn xem căn cứ và hiệu lực văn bản trước khi sử dụng thông tin.</p>
  </section>
}

export function ChatPage({ activeConversation, onMenu, onConversationUpdate }) {
  const [messages, setMessages] = useState(() => conversationService.loadMessages())
  const messagesRef = useRef(messages)
  const [source, setSource] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(null)
  const [storageError, setStorageError] = useState(false)
  const scrollRef = useRef(null)
  const abortRef = useRef(null)
  const conversationMessages = useMemo(
    () => messages.filter((message) => message.conversationId === activeConversation?.id),
    [messages, activeConversation?.id],
  )
  const latestAssistant = [...conversationMessages].reverse().find((message) => message.role === 'assistant' && message.status !== 'streaming')
  const citations = latestAssistant?.citations || []

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [conversationMessages.length, generating])

  useEffect(() => () => {
    abortRef.current?.controller.abort()
    if (abortRef.current) void chatService.cancel(abortRef.current.messageId)
  }, [])

  const updateMessages = (change) => {
    const next = change(messagesRef.current)
    messagesRef.current = next
    setMessages(next)
    setStorageError(!conversationService.saveMessages(next, activeConversation?.id))
  }

  const sendMessage = async (content, retryUser = null) => {
    if (!activeConversation || generating) return
    const now = new Date().toISOString()
    const user = retryUser || { id: crypto.randomUUID(), conversationId: activeConversation.id, role: 'user', content, createdAt: now }
    const assistantId = crypto.randomUUID()
    // Send exact user turns. Assistant answers are never promoted to facts.
    const turns = conversationMessages
      .filter((message) => message.role === 'user')
      .slice(-20)
      .map((message) => ({ turn_id: message.id, role: 'user', content: message.content }))
    const request = retryUser?.requestPayload || {
      conversationId: activeConversation.id, messageId: user.id,
      question: content, conversationTurns: turns,
    }
    user.requestPayload = request
    updateMessages((current) => [...current.filter(item => !retryUser || item.replyTo !== user.id), ...(retryUser ? [] : [user]), {
      id: assistantId,
      conversationId: activeConversation.id,
      role: 'assistant',
      replyTo: user.id,
      content: 'Đang phân tích câu hỏi và truy xuất nguồn pháp lý…',
      createdAt: now,
      status: 'streaming',
      citations: [],
      executionLog: [],
      executionAvailability: 'waiting',
    }])
    setGenerating(true)
    setProgress(null)
    const controller = new AbortController()
    abortRef.current = { controller, messageId: user.id }
    const pollController = new AbortController()
    let lastExecutionLog = []
    let lastDropped = 0
    let pollTimer
    const poll = async () => {
      if (pollController.signal.aborted) return
      try {
        const result = await chatService.progress(user.id, pollController.signal)
        if (result && !pollController.signal.aborted) {
          setProgress(result.stage)
          lastExecutionLog = normalizeExecutionSteps(result.steps)
          lastDropped = result.dropped || 0
          updateMessages(current => current.map(item => item.id === assistantId ? {
            ...item, executionLog: lastExecutionLog, executionDropped: lastDropped,
            executionAvailability: Array.isArray(result.steps) ? 'available' : 'unsupported',
          } : item))
        }
      } catch {
        if (!pollController.signal.aborted) updateMessages(current => current.map(item => item.id === assistantId
          ? { ...item, executionAvailability: 'disconnected' } : item))
      }
      if (!pollController.signal.aborted) pollTimer = setTimeout(poll, 2500)
    }
    pollTimer = setTimeout(poll, 1000)
    try {
      const answer = await chatService.sendMessage({ ...request, signal: controller.signal })
      updateMessages((current) => current.map((item) => item.id === assistantId ? { ...answer, id: assistantId, replyTo: user.id } : item))
      onConversationUpdate?.(activeConversation.id, content)
    } catch (error) {
      const stopped = error?.name === 'AbortError'
      const errorSteps = normalizeExecutionSteps(error.details?.execution_steps)
      updateMessages((current) => current.map((item) => item.id === assistantId ? {
        ...item,
        content: stopped ? 'Đã gửi yêu cầu dừng. Bước đang chạy trên máy chủ có thể cần thêm thời gian để kết thúc.' : error.message,
        status: 'error',
        errorInfo: stopped ? null : { category: error.category, errorId: error.errorId, status: error.status },
        executionLog: errorSteps.length ? errorSteps : lastExecutionLog,
        executionDropped: error.details?.execution_steps_dropped || lastDropped,
        executionAvailability: errorSteps.length ? 'available' : 'disconnected',
      } : item))
    } finally {
      clearTimeout(pollTimer)
      pollController.abort()
      if (abortRef.current?.controller === controller) abortRef.current = null
      setGenerating(false)
    }
  }

  const retry = () => {
    const previous = [...conversationMessages].reverse().find((message) => message.role === 'user')
    if (previous) sendMessage(previous.content, previous)
  }

  const stop = () => {
    if (abortRef.current) void chatService.cancel(abortRef.current.messageId)
    abortRef.current?.controller.abort()
  }

  if (!activeConversation) return <main className="empty-chat"><div><span className="empty-mark">§</span><h1>Chưa có cuộc trò chuyện</h1><p>Bắt đầu bằng cách đặt câu hỏi về pháp luật lao động Việt Nam.</p></div></main>
  return <main className={`chat-page ${source ? 'source-open' : ''}`}>
    <header className="conversation-header">
      <IconButton label="Mở menu" className="mobile-menu" onClick={onMenu}><Menu size={20} /></IconButton>
      <div className="conversation-heading"><span className="eyebrow"><BookOpenText size={12}/> TRA CỨU & GIẢI ĐÁP</span><h1>{activeConversation.title}</h1></div>
      <div className="conversation-tools">
        <span className="source-count">{citations.length} nguồn trong câu trả lời gần nhất</span>
        <IconButton label="Mở nguồn gần nhất" disabled={!citations.length} onClick={() => setSource(citations[0])}><PanelRightOpen size={18} /></IconButton>
      </div>
    </header>
    <div className="chat-scroll" ref={scrollRef}><div className="chat-content">
      {storageError && <p role="alert">Không lưu được lịch sử trên trình duyệt. Hãy kiểm tra dung lượng hoặc quyền lưu trữ trước khi đóng trang.</p>}
      <AgentStatus active={generating} stage={progress} />
      {conversationMessages.map((message) => <Message key={message.id} message={message} onCitation={setSource} onRetry={retry} />)}
      {conversationMessages.length === 0 && !generating && <WelcomePanel onAsk={sendMessage} />}
    </div></div>
    <ChatInput onSend={sendMessage} onStop={stop} generating={generating} />
    {source && <SourceDrawer source={source} onClose={() => setSource(null)} />}
  </main>
}
