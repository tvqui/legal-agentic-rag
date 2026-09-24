# Kiến trúc tổng thể

```text
Nguồn pháp luật → OFFLINE pipeline → Registry/Provisions/Graph/Indexes
                                               ↓
Frontend → ONLINE API → Query analysis → Hybrid retrieval → Applicability
                                               ↓
                                  Verified Evidence Pack
                                               ↓
                                  Adjudication → Reference Audit
```

Mã nguồn backend nằm trong `src/vn_labor_offline` và `src/vn_labor_online`; `frontend` chỉ gọi API và không tự thực hiện suy luận pháp lý.
