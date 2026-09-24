export const conversationService = {
  getConversations: () => Promise.resolve([]),
  getConversation: () => Promise.resolve(null),
  create(title = 'Cuộc trò chuyện mới') {
    return { id: crypto.randomUUID(), title, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), preview: 'Chưa có tin nhắn' }
  },
  deleteConversation: () => Promise.resolve(),
}
