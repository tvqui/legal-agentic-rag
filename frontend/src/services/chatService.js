const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

function documentType(number = '') {
  if (number.includes('/NĐ-CP')) return 'Nghị định'
  if (number.includes('/TT-')) return 'Thông tư'
  if (number.includes('/QH')) return number.startsWith('45/') ? 'Bộ luật' : 'Luật'
  if (number.includes('/QĐ-')) return 'Quyết định'
  return 'Văn bản pháp luật'
}

function claimExcerpt(payload, evidenceId) {
  return payload.claims
    ?.filter((claim) => claim.evidence_ids?.includes(evidenceId))
    .map((claim) => claim.text)
    .join('\n') || 'Nội dung được dẫn chiếu trong câu trả lời.'
}

function mapCitation(citation, payload, index) {
  const effectiveDate = citation.law_version?.split(' → ')[0] || null
  return {
    id: citation.evidence_id,
    number: index + 1,
    documentId: citation.document_number || citation.evidence_id,
    documentTitle: citation.title || citation.document_number || 'Nguồn pháp lý',
    documentType: documentType(citation.document_number),
    article: citation.article ? `Điều ${citation.article}` : '',
    clause: citation.clause ? `Khoản ${citation.clause}` : '',
    point: citation.point ? `Điểm ${citation.point}` : '',
    issuedDate: null,
    effectiveDate,
    excerpt: claimExcerpt(payload, citation.evidence_id),
    sourceUrl: citation.official_url || null,
    sourceSpan: citation.source_span || {},
  }
}

function numberEvidenceMarkers(answer, citations) {
  const numbers = new Map(citations.map((citation) => [citation.id, citation.number]))
  return answer.replace(/\[([^[]+?)\]/g, (marker, evidenceId) => {
    const number = numbers.get(evidenceId)
    return number ? `[${number}]` : marker
  })
}

function responseStatus(payload) {
  if (payload.status === 'INSUFFICIENT_EVIDENCE') return 'low-evidence'
  if (payload.status === 'ERROR') return 'error'
  return 'completed'
}

const NOTICE_LABELS = {
  official_source: 'Nguồn đang chờ người có chuyên môn xác minh.',
  applicable_version: 'Hiệu lực ở cấp điều khoản đang chờ người có chuyên môn xác minh.',
  SOURCE_CATALOG_HUMAN_REVIEW_INCOMPLETE: 'Nguồn đang chờ người có chuyên môn xác minh.',
  PROVISION_TEMPORAL_REVIEW_INCOMPLETE: 'Hiệu lực ở cấp điều khoản đang chờ người có chuyên môn xác minh.',
  GOLD_NOT_APPROVED: 'Bộ câu hỏi đánh giá chất lượng chưa được duyệt.',
  CORPUS_MAY_BE_STALE: 'Ngày được hỏi nằm ngoài ngày chốt của bộ dữ liệu.',
  QUERY_DATE_DEFAULTED_TO_CORPUS_SNAPSHOT: 'Bạn chưa nhập ngày tra cứu; hệ thống dùng ngày chốt của bộ dữ liệu.',
}

function humanizeNotice(value) {
  if (NOTICE_LABELS[value]) return NOTICE_LABELS[value]
  if (value.startsWith('DOCUMENT_LEVEL_TEMPORAL_FALLBACK_USED:')) {
    return 'Hiệu lực được kiểm tra tạm thời ở cấp văn bản.'
  }
  return value
}

function humanizeNotices(values = []) {
  return [...new Set(values.map(humanizeNotice))]
}

async function parseResponse(response) {
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new ApiError(`Backend trả về dữ liệu không hợp lệ (HTTP ${response.status}).`, response.status)
  }
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail || payload)
    throw new ApiError(detail || `Yêu cầu thất bại (HTTP ${response.status}).`, response.status, payload)
  }
  return payload
}

export const chatService = {
  async health(signal) {
    const response = await fetch(`${API_BASE_URL}/health`, { signal })
    return parseResponse(response)
  },

  async sendMessage({ conversationId, question, conversationContext = [], queryDate, signal }) {
    const request = {
      question,
      conversation_context: conversationContext.slice(-8),
    }
    if (queryDate) request.query_date = queryDate

    const response = await fetch(`${API_BASE_URL}/v1/answer`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    })
    const payload = await parseResponse(response)
    const citations = (payload.citations || []).map((citation, index) => mapCitation(citation, payload, index))
    return {
      id: payload.query_id || crypto.randomUUID(),
      conversationId,
      role: 'assistant',
      content: numberEvidenceMarkers(payload.answer || '', citations),
      createdAt: new Date().toISOString(),
      status: responseStatus(payload),
      citations,
      evidenceStatus: payload.evidence_status,
      answerStatus: payload.status,
      warnings: humanizeNotices(payload.warnings),
      limitations: humanizeNotices(payload.limitations),
      questions: payload.questions || [],
      buildId: payload.build_id,
      traceId: payload.trace_id,
    }
  },
}
