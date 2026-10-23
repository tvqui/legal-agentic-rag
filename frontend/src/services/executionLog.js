export const EXECUTION_LIMIT = 160
const STATUSES = new Set(['RUNNING', 'DONE', 'SKIPPED', 'WARNING', 'ERROR', 'CANCELLED'])

export function normalizeExecutionSteps(value) {
  if (!Array.isArray(value)) return []
  return value.slice(-EXECUTION_LIMIT).filter(item => item && typeof item === 'object'
    && typeof item.name === 'string' && STATUSES.has(item.status)).map(item => ({
    id: Number.isSafeInteger(item.id) ? item.id : 0,
    step: String(item.step || '').slice(0, 60),
    name: item.name.slice(0, 180),
    layer: String(item.layer || '').slice(0, 140),
    technology: String(item.technology || '').slice(0, 180),
    output_type: String(item.output_type || '').slice(0, 180),
    status: item.status,
    elapsed_ms: typeof item.elapsed_ms === 'number' && Number.isFinite(item.elapsed_ms) ? Math.max(0, item.elapsed_ms) : null,
    output: item.output && typeof item.output === 'object' ? item.output : {},
  }))
}

export function formatExecutionTime(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(1)} ms`
}

const LABELS = {
  so_nguon: 'Số nguồn', evidence_ids: 'Mã bằng chứng', loai_nguon_trong_ket_qua: 'Loại nguồn trong kết quả',
  ly_do: 'Lý do', ket_qua: 'Kết quả', trang_thai: 'Trạng thái', loai_loi: 'Loại lỗi', ma_loi: 'Mã lỗi',
  so_query: 'Truy vấn bổ sung', so_task: 'Số ý cần trả lời', so_y: 'Số ý', so_y_can_tra_loi: 'Số ý cần trả lời',
  so_canh_bao: 'Số cảnh báo', so_claim: 'Số nhận định', so_trich_dan: 'Số trích dẫn',
  van_de: 'Vấn đề', van_de_con: 'Vấn đề con', truong_du_kien: 'Trường dữ kiện nhận được',
  luot_ngu_canh: 'Số lượt ngữ cảnh', can_hoi_lai: 'Cần hỏi lại', thieu_du_kien: 'Số dữ kiện còn thiếu',
  o_bat_buoc: 'Ô căn cứ bắt buộc', o_co_dieu_kien: 'Ô có điều kiện', o_con_thieu: 'Ô còn thiếu',
  so_nhom_can_cu: 'Số nhóm căn cứ', ngay_tra_cuu: 'Ngày tra cứu', tuyen: 'Tuyến', nhanh: 'Nhánh',
  du_chuoi: 'Đủ chuỗi căn cứ', so_nguon_PASS: 'Nguồn PASS', so_vong: 'Số vòng',
  node_da_xet: 'Node đã xét', node_moi: 'Node mới', canh_da_xet: 'Cạnh đã xét', vong: 'Vòng',
  tang_node_da_duyet: 'Các tầng node mới đã duyệt',
  ly_do_dung: 'Lý do dừng', nguon_duoc_giu: 'Nguồn được giữ', giu_lai: 'Giữ lại', loai: 'Bị loại',
  vuot_kiem_tra_may: 'Vượt kiểm tra máy', co_loi_cung: 'Nguồn có lỗi cứng',
  so_nguon_co_canh_bao: 'Nguồn có cảnh báo', cho_fallback_cap_van_ban: 'Cho kiểm ngày tạm ở cấp văn bản',
  so_kenh: 'Số kênh', so_kenh_bo_sung: 'Kênh theo task', so_ky_tu: 'Số ký tự',
  trang_thai_du_kien: 'Trạng thái dự kiến', trang_thai_tung_y: 'Trạng thái từng ý',
  giai_thich_co_dieu_kien: 'Giải thích có điều kiện', so_thong_tin_can_bo_sung: 'Thông tin cần bổ sung',
  kieu_du_lieu: 'Kiểu dữ liệu', so_truong: 'Số trường', dau_ra: 'Đầu ra',
}
function displayValue(value) {
  if (value === true) return 'Có'
  if (value === false) return 'Không'
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return value.length ? value.map(displayValue).join(', ') : 'Không có'
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}: ${displayValue(item)}`).join('; ') || 'Không có'
  return String(value)
}
export function executionOutputText(output) {
  return Object.entries(output || {}).map(([key, value]) => `${LABELS[key] || key}: ${displayValue(value)}`).join('\n') || 'Đang xử lý, chưa có output.'
}
