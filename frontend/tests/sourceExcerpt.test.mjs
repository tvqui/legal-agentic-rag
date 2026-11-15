import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chatService } from '../src/services/chatService.js'

async function mapSource(citation) {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({
    query_id: 'source-test', status: 'PARTIAL_ALLOWED', answer: 'Đây là lời diễn giải. [prov_source]',
    claims: [{ claim_id: 'c', text: 'Lời AI không phải nguyên văn nguồn.', evidence_ids: ['prov_source'] }],
    citations: [{ evidence_id: 'prov_source', ...citation }],
  }))
  try {
    return (await chatService.sendMessage({ conversationId: 'c', messageId: 'm', question: 'Test' })).citations[0]
  } finally { globalThis.fetch = previousFetch }
}

test('source excerpt preserves raw characters after the API JSON round trip', async () => {
  const raw = '  Điều 7. Nguồn\r\n\t1. Không quá 02 ngày; nếu đủ điều kiện.\n  a) Giữ  hai khoảng trắng, dấu “ngoặc”, a\u0301 và <script>không thực thi</script>.\n'
  const source = await mapSource({ source_text: raw })
  assert.equal(source.excerpt, raw)
  assert.equal(source.excerptOrigin, 'ARTIFACT_SOURCE_TEXT')
  assert.ok(!source.excerpt.includes('Lời AI'))
})

test('old backend or missing raw source never substitutes a generated claim', async () => {
  for (const value of [undefined, null, '', '  \n\t', { text: 'Not a string' }]) {
    const source = await mapSource({ source_text: value })
    assert.equal(source.excerpt, null)
    assert.equal(source.excerptOrigin, null)
  }
})
