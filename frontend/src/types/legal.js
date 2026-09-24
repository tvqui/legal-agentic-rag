/**
 * @typedef {Object} Citation
 * @property {string} id evidence_id từ backend
 * @property {number} number số hiển thị trong câu trả lời
 * @property {string} documentId
 * @property {string} documentTitle
 * @property {string} documentType
 * @property {string=} article
 * @property {string=} clause
 * @property {string=} point
 * @property {string=} excerpt
 * @property {string=} sourceUrl
 * @property {string=} effectiveDate
 *
 * @typedef {Object} Message
 * @property {string} id
 * @property {string} conversationId
 * @property {'user'|'assistant'} role
 * @property {string} content
 * @property {string} createdAt
 * @property {'streaming'|'completed'|'error'|'low-evidence'=} status
 * @property {Citation[]=} citations
 * @property {string=} evidenceStatus
 * @property {string=} answerStatus
 * @property {string[]=} warnings
 * @property {string[]=} limitations
 * @property {string[]=} questions
 */

export const messageStatuses = ['streaming', 'completed', 'error', 'low-evidence']
