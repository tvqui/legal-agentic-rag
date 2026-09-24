import { useEffect, useMemo, useState } from 'react'
import { Menu, Moon, Sun } from 'lucide-react'
import { Sidebar } from './components/layout/Sidebar'
import { IconButton } from './components/ui/IconButton'
import { ChatPage } from './pages/ChatPage'
import { SettingsPage } from './pages/SettingsPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { initialConversations } from './data/legalData'
import { conversationService } from './services/conversationService'

function getPath() { return window.location.pathname === '/' ? '/chat/labor-termination' : window.location.pathname }

export default function App() {
  const [path, setPath] = useState(getPath)
  const [conversations, setConversations] = useState(initialConversations)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('legal-ai-theme') || 'light')
  const activeId = path.startsWith('/chat/') ? path.split('/').pop() : null
  const activeConversation = useMemo(() => conversations.find((item) => item.id === activeId), [conversations, activeId])

  useEffect(() => {
    const applied = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme
    document.documentElement.dataset.theme = applied
    localStorage.setItem('legal-ai-theme', theme)
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
    navigate(`/chat/${conversation.id}`)
  }

  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <Sidebar conversations={conversations} activeId={activeId} onNavigate={navigate} onNewChat={newChat} collapsed={collapsed} onCollapse={() => setCollapsed((value) => !value)} mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} path={path} />
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
          : <ChatPage activeConversation={activeConversation} onMenu={() => setMobileOpen(true)} />}
    </section>
  </div>
}
