import { Menu, MoreHorizontal, PanelRightOpen } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ChatInput } from '../components/chat/ChatInput'
import { AgentStatus } from '../components/chat/AgentStatus'
import { Message } from '../components/chat/Message'
import { SourceDrawer } from '../components/source/SourceDrawer'
import { IconButton } from '../components/ui/IconButton'
import { chatService } from '../services/chatService'

export function ChatPage({ activeConversation, onMenu }) {
  const [messages, setMessages] = useState([])
  const [source, setSource] = useState(null)
  const [generating, setGenerating] = useState(false)
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

  useEffect(() => () => abortRef.current?.abort(), [])

  const sendMessage = async (content) => {
    if (!activeConversation || generating) return
    const now = new Date().toISOString()
    const user = { id: crypto.randomUUID(), conversationId: activeConversation.id, role: 'user', content, createdAt: now }
    const assistantId = crypto.randomUUID()
    // Prior assistant answers contain long legal quotations and must not be fed
    // back as if they were facts in the user's next question.
    const context = conversationMessages
      .filter((message) => message.role === 'user')
      .slice(-4)
      .map((message) => message.content)
    setMessages((current) => [...current, user, {
      id: assistantId,
      conversationId: activeConversation.id,
      role: 'assistant',
      content: 'Đang phân tích câu hỏi và truy xuất nguồn pháp lý…',
      createdAt: now,
      status: 'streaming',
      citations: [],
    }])
    setGenerating(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const answer = await chatService.sendMessage({
        conversationId: activeConversation.id,
        question: content,
        conversationContext: context,
        signal: controller.signal,
      })
      setMessages((current) => current.map((item) => item.id === assistantId ? { ...answer, id: assistantId } : item))
    } catch (error) {
      const stopped = error?.name === 'AbortError'
      setMessages((current) => current.map((item) => item.id === assistantId ? {
        ...item,
        content: stopped ? 'Yêu cầu đã được dừng.' : `Không thể kết nối với AI backend: ${error.message}`,
        status: 'error',
      } : item))
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setGenerating(false)
    }
  }

  const retry = () => {
    const previous = [...conversationMessages].reverse().find((message) => message.role === 'user')
    if (previous) sendMessage(previous.content)
  }

  const stop = () => abortRef.current?.abort()

  if (!activeConversation) return <main className="empty-chat"><div><span className="empty-mark">§</span><h1>Chưa có cuộc trò chuyện</h1><p>Bắt đầu bằng cách đặt câu hỏi về pháp luật lao động Việt Nam.</p></div></main>
  return <main className={`chat-page ${source ? 'source-open' : ''}`}>
    <header className="conversation-header">
      <IconButton label="Mở menu" className="mobile-menu" onClick={onMenu}><Menu size={20} /></IconButton>
      <div className="conversation-heading"><span className="eyebrow">LEGAL AI WORKSPACE</span><h1>{activeConversation.title}</h1></div>
      <div className="conversation-tools">
        <span className="source-count">{citations.length} nguồn trong câu trả lời gần nhất</span>
        <IconButton label="Mở nguồn gần nhất" disabled={!citations.length} onClick={() => setSource(citations[0])}><PanelRightOpen size={18} /></IconButton>
        <IconButton label="Tùy chọn cuộc trò chuyện"><MoreHorizontal size={19} /></IconButton>
      </div>
    </header>
    <div className="chat-scroll" ref={scrollRef}><div className="chat-content">
      <AgentStatus active={generating} />
      {conversationMessages.map((message) => <Message key={message.id} message={message} onCitation={setSource} onRetry={retry} />)}
      {conversationMessages.length === 0 && <div className="conversation-empty"><span>§</span><h2>Cuộc trò chuyện mới</h2><p>Đặt câu hỏi để bắt đầu nghiên cứu trên dữ liệu pháp luật lao động Việt Nam.</p></div>}
    </div></div>
    <ChatInput onSend={sendMessage} onStop={stop} generating={generating} />
    {source && <SourceDrawer source={source} onClose={() => setSource(null)} />}
  </main>
}
