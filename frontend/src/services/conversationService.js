const STORAGE_KEY = 'phap-dien-conversations-v1'
let transientSession = null

function read() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (value?.version === 1 && Array.isArray(value.conversations) && Array.isArray(value.messages)) return { ...value, initialized: true }
  } catch { /* Browser storage must not prevent opening chat. */ }
  return { version: 1, conversations: [], messages: [] }
}
function write(value) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); return true }
  catch { return false }
}
export function clientSession() {
  // Random capability for progress/cancel/retry; never an API key or user ID.
  try {
    let value = sessionStorage.getItem('phap-dien-client-session')
    if (!value) {
      value = crypto.randomUUID().replaceAll('-', '') + crypto.randomUUID().replaceAll('-', '')
      sessionStorage.setItem('phap-dien-client-session', value)
    }
    return value
  } catch {
    transientSession ||= crypto.randomUUID().replaceAll('-', '') + crypto.randomUUID().replaceAll('-', '')
    return transientSession
  }
}
export const conversationService = {
  loadConversations(seed = []) { const saved = read(); return saved.initialized ? saved.conversations : seed },
  saveConversations(conversations) { return write({ ...read(), conversations }) },
  loadMessages() {
    return read().messages.map(message => message.status === 'streaming'
      ? { ...message, status: 'error', content: 'Phiên trước bị gián đoạn. Bạn có thể thử lại yêu cầu.' }
      : message)
  },
  saveMessages(messages, conversationId) {
    const saved = read()
    if (conversationId) {
      // Late completion after a deleted chat must not recreate it.
      if (!saved.conversations.some(item => item.id === conversationId)) return false
      messages = [...saved.messages.filter(item => item.conversationId !== conversationId), ...messages.filter(item => item.conversationId === conversationId)]
    }
    return write({ ...saved, messages })
  },
  getConversations: () => Promise.resolve(read().conversations),
  getConversation: id => Promise.resolve(read().conversations.find(item => item.id === id) || null),
  create(title = 'Cuộc trò chuyện mới') {
    return { id: crypto.randomUUID(), title, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), preview: 'Chưa có tin nhắn' }
  },
  deleteConversation(id) {
    const saved = read()
    return write({ ...saved, conversations: saved.conversations.filter(item => item.id !== id), messages: saved.messages.filter(item => item.conversationId !== id) })
  },
}
