import { Database, Search } from 'lucide-react'

export function DocumentsPage() {
  return <main className="utility-page">
    <header><span className="eyebrow">KNOWLEDGE BASE</span><h1>Tài liệu</h1><p>Document Registry đang được quản lý bởi OFFLINE artifacts.</p></header>
    <label className="document-search"><Search size={18} /><input placeholder="Tìm kiếm tài liệu..." disabled /></label>
    <section className="document-list">
      <article className="document-card">
        <span className="document-icon"><Database size={21} /></span>
        <div><h2>Chưa có API duyệt Document Registry</h2><p>Chat vẫn truy xuất trực tiếp Dense, BM25 và graph thông qua `/v1/answer`.</p></div>
      </article>
    </section>
  </main>
}
