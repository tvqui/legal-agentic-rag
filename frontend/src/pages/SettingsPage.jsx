import { Check } from 'lucide-react'

export function SettingsPage({ theme, setTheme }) {
  return <main className="utility-page"><header><span className="eyebrow">WORKSPACE</span><h1>Cài đặt</h1><p>Tùy chỉnh trải nghiệm nghiên cứu pháp lý của bạn.</p></header><div className="settings-grid">
    <section className="settings-card"><h2>Giao diện</h2><p>Chọn chế độ hiển thị phù hợp với môi trường làm việc.</p><div className="appearance-options">{[['light','Sáng'],['dark','Tối'],['system','Theo hệ thống']].map(([value,label]) => <button key={value} className={theme === value ? 'selected' : ''} onClick={() => setTheme(value)}><span className={`theme-preview ${value}`} />{label}{theme === value && <Check size={16} />}</button>)}</div></section>
    <section className="settings-card settings-info"><h2>Minh bạch thông tin</h2><p>Thông tin pháp luật cần được đối chiếu với nguồn và thời điểm có hiệu lực. Các kết quả đang ở trạng thái chưa đủ căn cứ sẽ được hiển thị rõ ràng trong cuộc trò chuyện.</p><div className="settings-guideline">Thiết lập giao diện chỉ được lưu trên trình duyệt này.</div></section>
  </div></main>
}
