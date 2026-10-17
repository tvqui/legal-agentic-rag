import { clientSession } from './conversationService.js'

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api')
  .trim()
  .replace(/\/+$/, '')
  .replace(/\/v1\/answer$/i, '')
  .replace(/\/v1$/i, '')
const REQUEST_TIMEOUT_MS = Number(import.meta.env?.VITE_API_TIMEOUT_MS || 210000)

export class ApiError extends Error {
  constructor(message, status = 0, details = null, category = 'NETWORK_ERROR', errorId = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
    this.category = category
    this.errorId = errorId
  }
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
    documentType: citation.document_type || 'Chưa có loại văn bản trong metadata',
    issuer: citation.issuer || null,
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
  if (['INSUFFICIENT_EVIDENCE', 'NEED_MORE_FACTS', 'ABSTAIN'].includes(payload.status)) return 'low-evidence'
  if (payload.status === 'ERROR') return 'error'
  return 'completed'
}

const NOTICE_LABELS = {
  official_source: 'Nguồn đang chờ người có chuyên môn xác minh.',
  applicable_version: 'Hiệu lực ở cấp điều khoản đang chờ người có chuyên môn xác minh.',
  SOURCE_CATALOG_HUMAN_REVIEW_INCOMPLETE: 'Nguồn đang chờ người có chuyên môn xác minh.',
  PROVISION_TEMPORAL_REVIEW_INCOMPLETE: 'Hiệu lực ở cấp điều khoản đang chờ người có chuyên môn xác minh.',
  GOLD_NOT_APPROVED: 'Bộ câu hỏi đánh giá chất lượng chưa được duyệt.',
  source_text_quality: 'Nội dung nguồn còn lỗi đọc chữ, cần đối chiếu bản gốc.',
  answer_completeness: 'Câu trả lời còn thiếu nội dung bắt buộc; cần kiểm tra chuỗi căn cứ.',
  answer_text_quality: 'Câu trả lời chưa đạt kiểm tra câu chữ.',
  answer_coverage: 'Một số phần của câu hỏi chưa có đủ căn cứ để trả lời.',
  pending_facts: 'Cần bổ sung dữ kiện để kết luận cho trường hợp cụ thể.',
  semantic_verification: 'Hệ thống chưa hoàn tất kiểm tra kết luận với nguồn.',
  ANSWER_SEMANTIC_REVIEW_INCOMPLETE: 'Chỉ trình bày phần đã kiểm được; câu hỏi còn phần chưa đủ căn cứ.',
  ANSWER_WITH_UNCONFIRMED_FACTS: 'Phần giải thích có điều kiện; chưa kết luận khi dữ kiện còn thiếu.',
  SOURCE_CLAUSE_BOUNDARY_NEEDS_REVIEW: 'Nguồn có đoạn đang gộp nhiều khoản; cần đối chiếu ranh giới khoản trong bản gốc.',
  ANSWER_QUALITY_BLOCKED: 'Câu trả lời chưa đạt kiểm tra chất lượng nội dung.',
  ANSWER_LANGUAGE_SAFE_FALLBACK: 'Hệ thống dùng cách trả lời dự phòng để giữ nguyên nội dung pháp lý.',
  CORPUS_MAY_BE_STALE: 'Bộ dữ liệu có thể chưa bao gồm thay đổi pháp luật sau ngày chốt.',
  QUERY_DATE_DEFAULTED_TO_CORPUS_SNAPSHOT: 'Bạn chưa nhập ngày tra cứu; hệ thống dùng ngày chốt của bộ dữ liệu.',
  CONVERSATION_CONTEXT_USED: 'Đã sử dụng ngữ cảnh từ lời bạn cung cấp ở các lượt trước.',
  CONVERSATION_CONTEXT_AMBIGUOUS: 'Chưa xác định rõ chủ đề của câu hỏi nối tiếp.',
  CORPUS_LEGAL_REVIEW_INCOMPLETE: 'Bộ dữ liệu chưa được duyệt pháp lý đầy đủ; kiểm tra căn cứ của từng nội dung.',
  per_task_answer_completeness: 'Chưa xác minh đầy đủ từng ý trong câu hỏi.',
  INDEPENDENT_TASK_RULES_ONLY: 'Chỉ trình bày phần có chuỗi căn cứ độc lập; các phần còn lại chưa đủ căn cứ.',
}

function humanizeNotice(value) {
  if (NOTICE_LABELS[value]) return NOTICE_LABELS[value]
  if (value.startsWith('ANSWER_SEMANTIC_REVIEW_ERROR:')) return 'Hệ thống chưa hoàn tất kiểm tra nội dung với nguồn; chưa thể kết luận.'
  if (value.startsWith('MISSING_REQUIRED_RULE:')) return 'Chưa tìm đủ quy định trực tiếp cần thiết để trả lời câu hỏi.'
  if (value.startsWith('SOURCE_TEXT_QUALITY:')) return 'Nội dung nguồn có chữ đáng ngờ, cần đối chiếu bản gốc.'
  if (value.startsWith('ANSWER_TEXT_QUALITY:') || value.startsWith('ANSWER_LANGUAGE_REPAIR_REJECTED:')) return 'Hệ thống phát hiện lỗi câu chữ và đã kiểm tra cách trả lời dự phòng.'
  if (value.startsWith('DOCUMENT_LEVEL_TEMPORAL_FALLBACK_USED:')) {
    return 'Hiệu lực được kiểm tra tạm thời ở cấp văn bản.'
  }
  return value
}

function humanizeNotices(values = []) {
  return [...new Set(values.filter(value => !['ANSWER_LAYOUT_CLEANED', 'ANSWER_LANGUAGE_REPAIRED'].includes(value)).map(humanizeNotice))]
}

export async function parseResponse(response) {
  let payload
  try {
    payload = await response.json()
  } catch {
    const category = response.ok ? 'INVALID_RESPONSE' : response.status === 429 ? 'SERVICE_BUSY' : response.status >= 500 ? 'UPSTREAM_ERROR' : 'BACKEND_ERROR'
    throw new ApiError(response.ok ? 'Dịch vụ trả về nội dung không đọc được.' : `Dịch vụ tạm thời không xử lý được yêu cầu (HTTP ${response.status}).`, response.status, null, category, response.headers.get('X-Request-ID'))
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new ApiError('Dịch vụ trả về nội dung không đọc được.', response.status, null, 'INVALID_RESPONSE')
  }
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : null
    const message = payload.message || detail || `Yêu cầu thất bại (HTTP ${response.status}).`
    throw new ApiError(message, response.status, payload.details || payload, payload.category || 'BACKEND_ERROR', payload.error_id || response.headers.get('X-Request-ID'))
  }
  return payload
}

function boundedSignal(parentSignal, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController()
  const abort = () => controller.abort(parentSignal?.reason)
  if (parentSignal?.aborted) abort()
  else parentSignal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), timeoutMs)
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer)
      parentSignal?.removeEventListener('abort', abort)
    },
  }
}

export const chatService = {
  async progress(messageId, signal) {
    const capability = clientSession()
    if (!capability) return null
    const bounded = boundedSignal(signal, 5000)
    try {
      const response = await fetch(`${API_BASE_URL}/v1/requests/${encodeURIComponent(messageId)}`, {
        headers: { 'X-Client-Session': capability }, signal: bounded.signal,
      })
      return response.ok ? response.json() : null
    } finally { bounded.cleanup() }
  },
  async cancel(messageId) {
    const capability = clientSession()
    if (!capability || !messageId) return
    const bounded = boundedSignal(null, 5000)
    try {
      await fetch(`${API_BASE_URL}/v1/requests/${encodeURIComponent(messageId)}/cancel`, {
        method: 'POST', headers: { 'X-Client-Session': capability }, signal: bounded.signal,
      })
    } catch { /* Backend budget still applies if the tunnel is lost. */ }
    finally { bounded.cleanup() }
  },
  async health(signal) {
    const bounded = boundedSignal(signal, Math.min(REQUEST_TIMEOUT_MS, 15000))
    try {
      const response = await fetch(`${API_BASE_URL}/health`, { signal: bounded.signal })
      return await parseResponse(response)
    } finally {
      bounded.cleanup()
    }
  },

  async sendMessage({ conversationId, messageId, question, conversationContext = [], conversationTurns = [], facts = {}, queryDate, signal }) {
    const request = {
      question,
      conversation_context: conversationContext.slice(-20),
      conversation_turns: conversationTurns.slice(-20),
      conversation_id: conversationId,
      message_id: messageId,
      facts,
    }
    if (queryDate) request.query_date = queryDate

    const bounded = boundedSignal(signal)
    let payload
    try {
      const response = await fetch(`${API_BASE_URL}/v1/answer`, {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(clientSession() ? { 'X-Client-Session': clientSession() } : {}) },
        body: JSON.stringify(request),
        signal: bounded.signal,
      })
      payload = await parseResponse(response)
    } catch (error) {
      if (bounded.signal.aborted && !signal?.aborted) {
        void this.cancel(messageId)
        throw new ApiError('AI backend xử lý quá thời gian cho phép. Vui lòng thử lại.', 408, null, 'TIMEOUT')
      }
      throw error
    } finally {
      bounded.cleanup()
    }
    if (typeof payload.answer !== 'string' || !['SUFFICIENT', 'PARTIAL_ALLOWED', 'NEED_MORE_FACTS', 'INSUFFICIENT_EVIDENCE', 'CONFLICTING_EVIDENCE', 'ABSTAIN', 'ERROR'].includes(payload.status) || !Array.isArray(payload.citations) || payload.citations.some(item => !item || typeof item.evidence_id !== 'string')) {
      throw new ApiError('Cấu trúc câu trả lời từ dịch vụ không hợp lệ.', 200, null, 'INVALID_RESPONSE')
    }
    const citations = payload.citations.map((citation, index) => mapCitation(citation, payload, index))
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
      facts: payload.facts || {},
      buildId: payload.build_id,
      traceId: payload.trace_id,
      legalStatus: payload.legal_status,
      parts: payload.parts || [],
    }
  },
}
