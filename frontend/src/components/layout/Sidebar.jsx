import { useState } from 'react'
import { Archive, ChevronLeft, ChevronRight, FileText, FolderOpen, MoreHorizontal, PanelLeftClose, Plus, Search, Settings } from 'lucide-react'
import { AppLogo } from './AppLogo'
import { IconButton } from '../ui/IconButton'

//du lieu mau
const groups = [
  { title: 'Hôm nay', ids: ['labor-termination', 'personal-income-tax'] },
  { title: 'Hôm qua', ids: ['labor-dispute', 'land-rights'] },
  { title: '7 ngày trước', ids: ['insurance'] },
]

function relativeTime(date) {
  return new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(new Date(date))
}

export function Sidebar({ conversations, activeId, onNavigate, onNewChat, collapsed, onCollapse, mobileOpen, onCloseMobile, path }) {
  const [search, setSearch] = useState('')
  const [menu, setMenu] = useState(null)
  const filtered = conversations.filter(item => `${item.title} ${item.preview}`.toLowerCase().includes(search.toLowerCase()))
  const byId = Object.fromEntries(filtered.map(item => [item.id, item]))
  
  return <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>

    <div className="sidebar-top">
      <AppLogo compact={collapsed} />

      <IconButton label={collapsed ? 'Mở rộng thanh bên' : 'Thu gọn thanh bên'} onClick={onCollapse} className="collapse-button">
        {collapsed ? <ChevronRight size={18} /> : <PanelLeftClose size={18} />}
      </IconButton>

      <IconButton label="Đóng menu" className="mobile-close" onClick={onCloseMobile}><ChevronLeft size={20} /></IconButton>
    </div>
    
    <div className="sidebar-content">
      <button className="new-chat" onClick={onNewChat}><Plus size={18} /><span>Cuộc trò chuyện mới</span></button>

      <label className="conversation-search">
        <Search size={16} />
        <input 
          value={search} 
          onChange={event => setSearch(event.target.value)} 
          placeholder="Tìm cuộc trò chuyện..." 
          aria-label="Tìm kiếm cuộc trò chuyện" />
      </label>
      <div className="conversation-scroll">
        {search && <p className="result-label">Kết quả tìm kiếm</p>}
        {filtered.length === 0 && <div className="search-empty"><Search size={20} /><p>Không tìm thấy cuộc trò chuyện phù hợp.</p></div>}
        
        {groups.map(group => {
          const items = group.ids.map(id => byId[id]).filter(Boolean)
          if (!items.length) return null
          return <section className="conversation-group" key={group.title}><h2>{group.title}</h2>{items.map(item => 
              <div className="conversation-wrap" key={item.id}>
                <button className={`conversation-item ${activeId === item.id && path.startsWith('/chat') ? 'active' : ''}`} onClick={() => onNavigate(`/chat/${item.id}`)}>
                  <FileText size={15} />
                  <span className="conversation-title">{item.title}</span>
                  <time>{relativeTime(item.updatedAt)}</time>
                </button>

                <IconButton label={`Tùy chọn ${item.title}`} className="conversation-more" onClick={() => setMenu(menu === item.id ? null : item.id)}><MoreHorizontal size={16} /></IconButton>
                {menu === item.id && 
                <div className="context-menu">
                  <button>Đổi tên</button>
                  <button>Ghim cuộc trò chuyện</button>
                  <button><Archive size={14} /> Lưu trữ</button>
                  <button className="danger">Xóa</button>
                </div>}
              </div>)}
            </section>
        })}
      </div>
    </div>
    <nav className="sidebar-bottom" aria-label="Điều hướng phụ">
      <button className={path === '/documents' ? 'active' : ''} onClick={() => onNavigate('/documents')}><FolderOpen size={17} /><span>Tài liệu</span></button>
      <button className={path === '/settings' ? 'active' : ''} onClick={() => onNavigate('/settings')}><Settings size={17} /><span>Cài đặt</span></button>
      <div className="profile"><span className="avatar">NA</span><span><strong>Nguyễn Anh</strong><small>Research workspace</small></span></div>
    </nav>
  </aside>
}
