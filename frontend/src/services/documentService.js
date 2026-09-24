// ONLINE hiện chưa công bố endpoint liệt kê toàn bộ Document Registry.
// Giữ interface này để nối endpoint khi backend cung cấp mà không phải đổi UI.
export const documentService = {
  getSources: () => Promise.resolve([]),
  getDocument: () => Promise.resolve(null),
}
