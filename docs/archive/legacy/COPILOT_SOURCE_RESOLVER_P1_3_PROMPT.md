# Prompt Copilot P1.3 — chốt state/identity/evidence trước batch direct URL

Đọc toàn bộ:

1. `SOURCE_RESOLVER_P0_P1_REVIEW.md`
2. `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`
3. `AUTOMATIC_LEGAL_SOURCE_RESOLVER_PLAN.md`
4. code hiện tại trong `src/vn_labor_offline/source_resolver/`
5. `tests/test_source_resolver.py`
6. `config/source_provider_registry.yaml`

Kết quả P1.2 đã chứng minh HTTP download/hash hoạt động với record `0a5bedfa76589540`: PDF official của Tòa án tải thành công và SHA trùng corpus, nhưng record còn `NEEDS_REVIEW` vì không có identity page riêng. Hãy hoàn thiện P1.3 trước khi chạy 8 direct URL.

## 1. Cho phép binary official cung cấp identity có kiểm chứng

Khi không có `identity_url` riêng nhưng có direct binary official:

- trích text an toàn từ binary đã tải;
- PDF: dùng PyMuPDF sẵn có, ưu tiên các trang đầu nhưng cho phép quét đủ trong giới hạn cấu hình;
- DOCX: dùng `python-docx`/ZIP XML an toàn;
- DOC hoặc định dạng chưa có extractor an toàn: giữ `NEEDS_REVIEW`, không gọi Office/macro;
- xác minh `canonical_identifier` từ nội dung, dùng normalizer chịu được khoảng trắng/dấu gạch Unicode nhưng không fuzzy đến mức nhầm số văn bản;
- với judicial, lưu thêm court/date/title khi trích được để giảm nguy cơ hai quyết định cùng số;
- evidence phải ghi `identity_source=BINARY_CONTENT`, text hash, trang/phạm vi đã đọc và reason code;
- không lưu toàn bộ nội dung pháp lý vào log nếu không cần.

Chỉ cho record thành `AUTO_EXACT_SHA` khi:

1. provider/final URL official và hợp lệ;
2. binary magic/MIME hợp lệ;
3. SHA binary trùng corpus;
4. identity được xác nhận từ identity page hoặc từ chính binary;
5. evidence đầy đủ.

Thêm test bằng PDF fixture có số `01/2022/LĐ-GĐT`: direct binary exact SHA và không có identity page phải đạt `AUTO_EXACT_SHA`. PDF không chứa số hoặc chứa số khác phải ở `NEEDS_REVIEW`.

## 2. Sửa tổng hợp state/reason theo candidate

Không dùng một biến `reasons` chung vừa overwrite vừa extend giữa các candidate. Tạo outcome riêng cho từng role/candidate rồi tổng hợp rõ ràng.

Các lỗi sau không được bị `decide()` ghi đè thành `FETCH_PENDING`:

- `PROVIDER_NOT_ALLOWED`;
- `URL_OUTSIDE_ALLOWLIST`/`FINAL_URL_OUTSIDE_ALLOWLIST`;
- redirect limit/loop;
- HTTP/network failure sau retry;
- size limit hoặc binary không hợp lệ.

Định nghĩa precedence có test:

- required fetch bị chặn/thất bại -> `BLOCKED` hoặc `NEEDS_REVIEW` theo reason cụ thể;
- binary chưa được thử vì network tắt -> `FETCH_PENDING`;
- binary exact + identity fail/missing -> `NEEDS_REVIEW`;
- binary exact + identity verified -> `AUTO_EXACT_SHA`;
- SHA mismatch -> `NEEDS_REVIEW`;
- secondary source -> không được auto exact.

Resume phải khôi phục authority/identity/binary outcomes đầy đủ từ evidence trước đó, không chỉ binary state.

## 3. Sửa provider registry theo seed thực

Viết test đọc cả 8 `direct_download_url` trong seed và yêu cầu mỗi URL match đúng một provider với role `BINARY` và đúng source group.

Đặc biệt bổ sung/kiểm:

- `vbpl.vn/FileData/...` cho binary, tách khỏi route HTML identity;
- `datafiles.chinhphu.vn`;
- `congbobanan.toaan.gov.vn`;
- `natlex.ilo.org`;
- các redirect/cross-host chính thức thực sự cần thiết.

Không mở route `/*` chỉ để test pass nếu có thể khai báo mẫu cụ thể. Registry/version phải được ghi trong evidence.

## 4. Giữ evidence bất biến và merge diff có dữ liệu thật

- Một lần fetch mới không được overwrite evidence cũ. Dùng event/evidence ID có timestamp/hash và truy vấn latest evidence cho resume.
- Candidate/record có thể trỏ tới latest evidence nhưng lịch sử vẫn còn.
- Lưu final identity URL và final binary URL vào record aggregate hoặc lấy đúng từ candidate/evidence khi export/merge.
- `merge --dry-run` phải lấy URL theo đúng vai trò; không tìm `row.final_url` nếu record không có trường đó.
- Diff chỉ đề xuất record `AUTO_EXACT_SHA` và phải cho thấy trường cụ thể được thêm/sửa. Không tạo diff khổng lồ chỉ vì serialize lại toàn bộ YAML.
- Catalog không được ghi thật.

Vì `config/source_catalog.yaml` chỉ có 61 entry còn review draft có 95, lệnh resolve/integrity trong giai đoạn này dùng:

```text
--catalog review_inputs/v8_1/source_catalog_review_draft.yaml
--corpus-root data
```

Nếu `--corpus-root` được truyền, thiếu bất kỳ file nào phải fail; hiện tại code chỉ hash khi file tồn tại và bỏ qua file thiếu.

## 5. Hoàn thiện CLI cho direct batch

- Áp dụng `--provider`, `--limit` và bộ lọc trước khi in kết quả `--dry-run`.
- Thêm `--direct-only` để chọn đúng các record có `direct_download_url`.
- Dry-run `--all --direct-only` phải báo đúng 8 record và liệt kê record ID/provider/URL, không truy cập mạng.
- Không dùng lại smoke DB để làm mất bằng chứng cũ. Batch tiếp theo dùng DB mới, ví dụ `artifacts/00_manifest/source_resolution_direct8.sqlite`.

## 6. Test bắt buộc

Ngoài test đang có, thêm tối thiểu:

1. direct official PDF exact SHA + identity trong PDF -> exact;
2. exact SHA nhưng identity khác/missing -> review;
3. provider/network/redirect/size error không bị hạ thành fetch pending;
4. resume tái tạo đúng kết quả tổng hợp;
5. cả 8 direct URLs match registry BINARY;
6. VBPL `FileData` không bị mất khi canonicalize identity;
7. evidence refresh giữ cả lịch sử;
8. `--corpus-root` thiếu file bị fail;
9. `--direct-only --dry-run` trả 8;
10. merge diff dùng final URL thật, chỉ chứa thay đổi liên quan và không sửa catalog.

Chạy:

```text
python -m compileall -q src/vn_labor_offline/source_resolver
python -m unittest tests.test_source_resolver
python -m unittest discover -s tests -q
```

Cập nhật số test theo kết quả thực tế; hiện lần kiểm độc lập gần nhất chạy **12 resolver tests và 113 repository tests**, không phải 112.

## 7. Network sau khi test PASS

1. Giữ nguyên DB smoke cũ làm bằng chứng.
2. Dùng DB/cache mới.
3. Chạy lại riêng record `0a5bedfa76589540`; kỳ vọng `AUTO_EXACT_SHA` chỉ khi identity thực sự trích và khớp từ PDF.
4. Nếu đúng, chạy `--all --direct-only --limit 8 --network` với concurrency 1/rate limit 1 giây.
5. Export summary/evidence/review queue riêng cho batch direct8.
6. Không chạy 84 candidate, không discovery, không merge thật và không chạy pipeline/Aura trong vòng này.

## 8. Báo cáo

Cập nhật `AUTOMATIC_SOURCE_RESOLVER_IMPLEMENTATION_REPORT.md`:

- sửa mô tả schema thành version 2;
- bỏ câu cũ nói merge chỉ in no-op nếu không còn đúng;
- ghi đúng tổng số test;
- báo kết quả từng direct URL: record/path/provider/final URL/MIME/size/download SHA/corpus SHA/identity source/state/reasons;
- nêu rõ số exact/review/blocked;
- xác nhận corpus và hai catalog không đổi.

Không thay rule để ép 8/8 PASS. Kết quả khác SHA, thiếu identity hoặc provider không đủ bằng chứng phải giữ ở review/block đúng lý do.
