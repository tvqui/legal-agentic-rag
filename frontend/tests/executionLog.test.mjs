import { test } from 'node:test'
import assert from 'node:assert/strict'
import { normalizeExecutionSteps, formatExecutionTime, executionOutputText } from '../src/services/executionLog.js'
import { chatService } from '../src/services/chatService.js'

test('missing or unsupported server data never fabricates executed stages', () => {
  assert.deepEqual(normalizeExecutionSteps(undefined), [])
  assert.deepEqual(normalizeExecutionSteps([{ name: 'Fake', status: 'SUCCESS_GUESS' }]), [])
})
test('normalization bounds history and preserves skipped/error distinction', () => {
  const steps = Array.from({ length: 180 }, (_, id) => ({ id, step: 'dense', name: 'Dense', layer: 'Retriever', status: id === 179 ? 'ERROR' : 'SKIPPED', technology: 'FAISS', elapsed_ms: 12, output: { so_nguon: 0 } }))
  const normalized = normalizeExecutionSteps(steps)
  assert.equal(normalized.length, 160)
  assert.equal(normalized.at(-1).status, 'ERROR')
  assert.equal(normalized[0].status, 'SKIPPED')
  assert.equal(formatExecutionTime(1250), '1.25 s')
  assert.equal(formatExecutionTime(undefined), '—')
  assert.match(executionOutputText({ so_nguon: 3, o_con_thieu: [] }), /Số nguồn: 3/)
})
test('fast answer carries complete execution log even before first polling round', async () => {
  const old = globalThis.fetch
  const step = { id: 1, name: 'Profile', layer: 'Pipeline', technology: 'Python', status: 'DONE', output: { du_chuoi: true } }
  globalThis.fetch = async () => new Response(JSON.stringify({ query_id: 'q', status: 'PARTIAL_ALLOWED', answer: 'answer', citations: [], trace: { execution_steps: [step], execution_steps_dropped: 2 } }))
  try {
    const response = await chatService.sendMessage({ question: 'Question' })
    assert.equal(response.executionAvailability, 'available')
    assert.equal(response.executionLog[0].name, 'Profile')
    assert.equal(response.executionDropped, 2)
  } finally { globalThis.fetch = old }
})
test('old backend stays usable but marked as not providing detailed progress', async () => {
  const old = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({ query_id: 'q', status: 'NEED_MORE_FACTS', answer: 'Clarify', citations: [] }))
  try {
    const response = await chatService.sendMessage({ question: 'Question' })
    assert.equal(response.executionAvailability, 'unsupported')
    assert.deepEqual(response.executionLog, [])
  } finally { globalThis.fetch = old }
})
test('error details retain execution stage and server error category', async () => {
  const old = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({ category: 'SERVICE_UNAVAILABLE', message: 'Unavailable', details: { execution_steps: [{ id: 1, name: 'Review', status: 'ERROR' }] } }), { status: 503 })
  try {
    await assert.rejects(() => chatService.sendMessage({ question: 'Question' }), error => error.status === 503 && error.details.execution_steps[0].name === 'Review')
  } finally { globalThis.fetch = old }
})
