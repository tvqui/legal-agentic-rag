import { useEffect, useMemo, useState } from 'react'
import { Menu, Moon, Sun } from 'lucide-react'
import { Sidebar } from './components/layout/Sidebar'
import { IconButton } from './components/ui/IconButton'
import { ChatPage } from './pages/ChatPage'
import { SettingsPage } from './pages/SettingsPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { initialConversations } from './data/legalData'
import { conversationService } from './services/conversationService'

function getPath() {
  if (window.location.pathname !== '/') return window.location.pathname
  const first = conversationService.loadConversations(initialConversations)[0]
  return first ? `/chat/${first.id}` : '/chat'
}
function getTheme() {
  try { return localStorage.getItem('legal-ai-theme') || 'light' }
  catch { return 'light' }
}

export default function App() {
  const [path, setPath] = useState(getPath)
  const [conversations, setConversations] = useState(() => conversationService.loadConversations(initialConversations))
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [theme, setTheme] = useState(getTheme)
  const activeId = path.startsWith('/chat/') ? path.split('/').pop() : null
  const activeConversation = useMemo(() => conversations.find((item) => item.id === activeId), [conversations, activeId])
  useEffect(() => { conversationService.saveConversations(conversations) }, [conversations])

  useEffect(() => {
    const applied = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme
    document.documentElement.dataset.theme = applied
    try { localStorage.setItem('legal-ai-theme', theme) } catch { /* Theme still works without storage. */ }
  }, [theme])

  useEffect(() => {
    const pop = () => setPath(getPath())
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  const navigate = (next) => {
    window.history.pushState({}, '', next)
    setPath(next)
    setMobileOpen(false)
  }
  const newChat = () => {
    const conversation = conversationService.create()
    setConversations((current) => [conversation, ...current])
    conversationService.saveConversations([conversation, ...conversations])
    navigate(`/chat/${conversation.id}`)
  }
  const deleteChat = (id) => {
    const next = conversations.filter(item => item.id !== id)
    if (!conversationService.deleteConversation(id)) return
    setConversations(next)
    if (id === activeId) navigate(next.length ? `/chat/${next[0].id}` : '/chat')
  }
  const updateChat = (id, content) => {
    setConversations(current => {
      const next = current.map(item => item.id === id ? { ...item, preview: content.slice(0, 100), updatedAt: new Date().toISOString() } : item)
      conversationService.saveConversations(next)
      return next
    })
  }

  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <Sidebar conversations={conversations} activeId={activeId} onNavigate={navigate} onNewChat={newChat} onDelete={deleteChat} collapsed={collapsed} onCollapse={() => setCollapsed((value) => !value)} mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} path={path} />
    {mobileOpen && <button className="sidebar-scrim" aria-label="Đóng menu" onClick={() => setMobileOpen(false)} />}
    <section className="workspace">
      <header className="topbar">
        <IconButton label="Mở menu" className="topbar-menu" onClick={() => setMobileOpen(true)}><Menu size={20} /></IconButton>
        <div className="workspace-status"><span /> AI pháp luật lao động Việt Nam</div>
        <div className="topbar-actions">
          <IconButton label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</IconButton>
          <span className="topbar-avatar">NA</span>
        </div>
      </header>
      {path.startsWith('/settings')
        ? <SettingsPage theme={theme} setTheme={setTheme} />
        : path.startsWith('/documents')
          ? <DocumentsPage />
          : <ChatPage key={activeId || 'empty'} activeConversation={activeConversation} onConversationUpdate={updateChat} onMenu={() => setMobileOpen(true)} />}
    </section>
  </div>
}
