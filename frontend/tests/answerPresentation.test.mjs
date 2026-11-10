import { test } from 'node:test'
import assert from 'node:assert/strict'
import { answerBlocks, noticeGroups } from '../src/services/answerPresentation.js'

test('citations stay in the paragraph or list item they support', () => {
  const content = 'Kết luận. [1]\n\n- Quyền thứ nhất. [1] [2]\n- Nếu đủ điều kiện thì được hưởng. [3]\n\nPhần chưa trả lời: còn thiếu nguồn.'
  assert.deepEqual(answerBlocks(content), [
    { kind: 'paragraph', text: 'Kết luận. [1]' },
    { kind: 'list', items: ['Quyền thứ nhất. [1] [2]', 'Nếu đủ điều kiện thì được hưởng. [3]'] },
    { kind: 'paragraph', text: 'Phần chưa trả lời: còn thiếu nguồn.' },
  ])
})

test('presentation preserves numbers, negation, quotes and user text', () => {
  const text = '“Không quá 04 giờ/ngày”; điểm l; -1; <script>alert(1)</script> [2]'
  assert.equal(answerBlocks(text)[0].text, text)
  assert.deepEqual(answerBlocks(''), [])
})

test('diagnostics are separated without dropping legal limits or unknown warnings', () => {
  assert.deepEqual(noticeGroups({ limitations: ['Nguồn chưa được duyệt.', 'Nguồn chưa được duyệt.'], warnings: ['OLLAMA_TIMEOUT', 'Cần bổ sung căn cứ.', 'Dữ kiện còn mâu thuẫn.'] }), {
    important: ['Nguồn chưa được duyệt.', 'Cần bổ sung căn cứ.', 'Dữ kiện còn mâu thuẫn.'],
    details: ['OLLAMA_TIMEOUT'],
  })
})
