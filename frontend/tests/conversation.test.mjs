import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { conversationService, clientSession } from '../src/services/conversationService.js'
import { parseResponse, chatService } from '../src/services/chatService.js'

function storage() {
  const values = new Map()
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
}
beforeEach(() => {
  globalThis.localStorage = storage()
  globalThis.sessionStorage = storage()
})

test('history survives service reload; deletion removes messages and does not resurrect seed chats', () => {
  const chat = conversationService.create('Test')
  conversationService.saveConversations([chat])
  conversationService.saveMessages([{ id: 'user-1', conversationId: chat.id, role: 'user', content: 'Câu hỏi' }], chat.id)
  assert.equal(conversationService.loadMessages()[0].content, 'Câu hỏi')
  assert.equal(conversationService.loadConversations()[0].id, chat.id)
  conversationService.deleteConversation(chat.id)
  assert.deepEqual(conversationService.loadMessages(), [])
  assert.deepEqual(conversationService.loadConversations([{ id: 'sample' }]), [])
  conversationService.saveMessages([{ conversationId: chat.id, content: 'Late response' }], chat.id)
  assert.deepEqual(conversationService.loadMessages(), [])
})

test('saving one chat preserves other chats; interrupted response becomes retryable', () => {
  conversationService.saveConversations([{ id: 'a' }, { id: 'b' }])
  conversationService.saveMessages([{ id: '1', conversationId: 'a', status: 'streaming' }], 'a')
  conversationService.saveMessages([{ id: '2', conversationId: 'b', content: 'Keep' }], 'b')
  assert.equal(conversationService.loadMessages().length, 2)
  assert.equal(conversationService.loadMessages().find(m => m.id === '1').status, 'error')
})

test('storage quota failure is reported, not silent data deletion', () => {
  globalThis.localStorage = { getItem: () => null, setItem: () => { throw new Error('quota') } }
  assert.equal(conversationService.saveMessages([]), false)
})

test('progress capability is stable per tab and not an API key', () => {
  const token = clientSession()
  assert.match(token, /^[a-f0-9]{64}$/)
  assert.equal(clientSession(), token)
})

test('HTML 503 is an upstream error, distinct from insufficient legal evidence', async () => {
  await assert.rejects(() => parseResponse(new Response('<html>Unavailable</html>', { status: 503 })), error => error.category === 'UPSTREAM_ERROR' && error.status === 503)
  await assert.rejects(() => parseResponse(new Response(JSON.stringify({ category: 'TIMEOUT', error_id: 'err1', message: 'Timeout' }), { status: 504 })), error => error.category === 'TIMEOUT' && error.errorId === 'err1')
})

test('request sends exact user turns and stable message ID without assistant facts', async () => {
  const previousFetch = globalThis.fetch
  let sent
  globalThis.fetch = async (_url, options) => {
    sent = JSON.parse(options.body)
    return new Response(JSON.stringify({ query_id: 'q', status: 'NEED_MORE_FACTS', answer: 'Clarify', citations: [] }))
  }
  try {
    await chatService.sendMessage({ conversationId: 'c', messageId: 'm', question: 'Còn bao lâu?', conversationTurns: [{ turn_id: 't', role: 'user', content: 'Tôi đang thử việc.' }] })
    assert.equal(sent.message_id, 'm')
    assert.equal(sent.conversation_id, 'c')
    assert.deepEqual(sent.facts, {})
    assert.equal(sent.conversation_turns[0].role, 'user')
  } finally { globalThis.fetch = previousFetch }
})

test('a JSON 200 without a valid answer is not displayed as a completed answer', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({ status: 'ok' }))
  try {
    await assert.rejects(() => chatService.sendMessage({ conversationId: 'c', messageId: 'm', question: 'Test' }), error => error.category === 'INVALID_RESPONSE')
  } finally { globalThis.fetch = previousFetch }
})

test('per-task completeness and provisional legal status survive response mapping', async () => {
  const previousFetch = globalThis.fetch
  const parts = [
    { task_id: 'pay', description: 'Tiền lương', answer_status: 'ANSWERED', legal_status: 'PROVISIONAL' },
    { task_id: 'duration', description: 'Thời gian', answer_status: 'MISSING', legal_status: 'PROVISIONAL' },
  ]
  globalThis.fetch = async () => new Response(JSON.stringify({ query_id: 'q', status: 'PARTIAL_ALLOWED', answer: 'Phần đã có căn cứ', citations: [], parts, legal_status: 'PROVISIONAL' }))
  try {
    const result = await chatService.sendMessage({ conversationId: 'c', messageId: 'm', question: 'Test' })
    assert.equal(result.legalStatus, 'PROVISIONAL')
    assert.deepEqual(result.parts, parts)
  } finally { globalThis.fetch = previousFetch }
})
