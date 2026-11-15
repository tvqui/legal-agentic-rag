import { ArrowUpRight, BookOpenText, CalendarDays, FileText, Link, X } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { IconButton } from '../ui/IconButton'

export function SourceDrawer({ source, onClose }) {
  if (!source) return null
  const hasSourceText = source.excerptOrigin === 'ARTIFACT_SOURCE_TEXT' && typeof source.excerpt === 'string' && source.excerpt.trim().length > 0
  const copyLink = () => source.sourceUrl && navigator.clipboard?.writeText(source.sourceUrl)
  return <aside className="source-drawer" aria-label="Chi tiết nguồn pháp lý">
    <header className="source-header"><div><span className="eyebrow">NGUỒN PHÁP LÝ</span><h2>Nguồn tham chiếu</h2></div><IconButton label="Đóng nguồn" onClick={onClose}><X size={19} /></IconButton></header>
    <div className="source-body">
      <Badge tone="citation">Nguồn #{source.number}</Badge>
      <h3>{source.documentTitle}</h3>
      <p className="source-article">{[source.article, source.clause, source.point].filter(Boolean).join(' · ') || source.documentId}</p>
      <section className="source-excerpt">
        <span><BookOpenText size={16} /> Nội dung gốc trong dữ liệu nguồn</span>
        {hasSourceText
          ? <><blockquote>{source.excerpt}</blockquote><p className="source-excerpt-note">Giữ nguyên chữ trong dữ liệu trích xuất; cần đối chiếu văn bản gốc nếu có lỗi OCR.</p></>
          : <p className="source-unavailable">Chưa có nguyên văn từ dữ liệu nguồn. Hãy mở nguồn gốc để đối chiếu; phần AI diễn giải không được dùng thay bản trích.</p>}
      </section>
      <section className="source-metadata"><h4>Thông tin văn bản</h4><dl>
        <div><dt>Loại văn bản</dt><dd>{source.documentType}</dd></div>
        <div><dt>Ngày ban hành</dt><dd><CalendarDays size={14} /> {source.issuedDate || 'Chưa có trong API'}</dd></div>
        <div><dt>Hiệu lực từ</dt><dd>{source.effectiveDate ? <><Badge tone="success">Theo metadata</Badge> {source.effectiveDate}</> : 'Chưa xác định'}</dd></div>
        <div><dt>Evidence ID</dt><dd>{source.id}</dd></div>
      </dl></section>
      {source.sourceUrl
        ? <a href={source.sourceUrl} className="source-link" target="_blank" rel="noreferrer"><FileText size={16} /> Mở nguồn gốc <ArrowUpRight size={15} /></a>
        : <p className="source-unavailable">API chưa cung cấp URL nguồn.</p>}
      <button className="secondary-button" onClick={copyLink} disabled={!source.sourceUrl}><Link size={15} /> Sao chép liên kết nguồn</button>
    </div>
  </aside>
}
