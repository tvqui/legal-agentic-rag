import { Scale } from 'lucide-react'

export function AppLogo({ compact = false }) {
  return <div className="app-logo" aria-label="Pháp Điển AI">
    <span className="logo-mark"><Scale size={18} strokeWidth={2.2} /></span>
    {!compact && <span><strong>Pháp Điển</strong><small>AI RESEARCH</small></span>}
  </div>
}
