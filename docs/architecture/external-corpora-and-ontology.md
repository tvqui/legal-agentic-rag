# Bổ sung corpus và ontology: đánh giá và triển khai 20/10/2026

Hai dataset phù hợp làm **nguồn bổ sung có kiểm tra**, không phải bản thay thế ngay cho corpus đã chốt. Ontology phù hợp làm từ vựng/schema dùng chung. Chưa có kết quả đánh giá Gold chứng minh độ chính xác tăng; cần đo build mới trên cùng câu hỏi và điều kiện trước khi kết luận.

## Những đề xuất đúng và những điểm cần sửa

| Đề xuất | Đánh giá và cách dùng |
|---|---|
| Án lệ → Fact Graph | Bản án cung cấp tình tiết, yêu cầu, chứng cứ, nhận định, kết quả. Phải tách lời khai khỏi sự kiện tòa xác lập. Án lệ được công nhận còn có nội dung quy tắc áp dụng, không thể quy toàn bộ về Fact Graph. |
| Legal → Rule Graph | Phù hợp với điều/khoản/điểm, điều kiện, ngoại lệ, dẫn chiếu và phiên bản. Quan hệ cấp văn bản không đủ để tự áp dụng sửa đổi ở cấp khoản/điểm. |
| “Ontology = 2” | Cách ghi chưa đủ rõ. Nếu nói tầng giữa, có thể vẽ Fact → Ontology → Rule; không phải thứ tự bắt buộc. Nếu nói OWL 2 thì đó là chuẩn biểu diễn ontology, không phải hai đồ thị/hai dataset. Repo đã có ba lớp trong `graph_builder.py`; không cần thay toàn bộ kiến trúc. |
| Ba bảng metadata/content/relationship | Hợp lý để lưu/ghép dữ liệu nguồn. Tên config thực tế là `relationships` (số nhiều). Không thay thế đồ thị, source verification, temporal intervals hay evidence spans. |

## Hai dataset đã đối chiếu

Nguồn thứ nhất: [TMQuan — anle-toaan-gov-vn](https://huggingface.co/datasets/tmquan/anle-toaan-gov-vn).

- Dataset card công bố 1.844 văn bản, chỉ 9 là án lệ (`is_precedent=true`); phần còn lại là bản án nguồn. Có nhiều lĩnh vực, phải chọn lao động và kiểm lại nhãn.
- Dữ liệu `documents` chứa markdown đã xử lý, URL trang/PDF, số bản án, ngày, loại, các trích dẫn được regex/LLM trích xuất. Đây là đầu vào ứng viên; không phải việc đã xác minh lại bản gốc.
- Bộ nhập chỉ lấy `documents`. Vector có sẵn dùng Nemotron 4096 chiều; dự án đang dùng BGE-m3. Không nhập vector này vào cùng FAISS index. Không dùng tọa độ UMAP/t-SNE thay cho vector retrieval.
- Giữ nguyên markdown, SHA-256 và tọa độ trích dẫn. Kiểm giới hạn span không đồng nghĩa đã kiểm đúng luật được dẫn. Án lệ cần kiểm quyết định công bố, nội dung được công nhận và phạm vi tương tự.

Nguồn thứ hai: [Thịnh Ngô — vietnamese-legal-documents](https://huggingface.co/datasets/th1nhng0/vietnamese-legal-documents).

- Snapshot hiện công bố 171.556 metadata, 170.824 content, 1.033.255 relationships. Thiếu content không được hiểu là văn bản không có nội dung; một số bản chỉ có PDF.
- Config hiện tại dùng khóa **string**, có số, UUID, tiền tố portal. Ghép `metadata.id = content.id`, `relationships.doc_id → metadata.id`; không ép thành số nguyên.
- Có 17.706 mã văn bản đích không có metadata trong snapshot theo card. Bộ nhập giữ mã đích chưa giải quyết, không tạo văn bản giả.
- Nội dung hiện tại là `content_html`, khác `legacy_content` dạng text. HTML được giữ nguyên và có hash; text nhìn thấy là bản dẫn xuất riêng, không được gán tọa độ PDF.
- Không suy luận chiều sửa đổi từ nhãn bằng phép đoán. `Bị sửa đổi`, `Sửa đổi`, `Căn cứ` được giữ nguyên cho review; không tạo legal-change đã duyệt.
- Trạng thái/ngày hiệu lực là tuyên bố cấp văn bản tại thời điểm crawl, chưa chứng minh hiệu lực từng điều khoản tại ngày hỏi. Schema hiện không cung cấp URL văn bản; không dựng URL ItemID từ UUID.

Cả hai card khai báo CC BY 4.0. Manifest giữ tên tác giả, URL dataset và revision để ghi công; điều này không thay cho kiểm tra điều kiện sử dụng nguồn gốc khi phân phối sản phẩm.

Revision được khóa trong mã để lần chạy không vô tình trộn hai snapshot:

```text
tmquan/anle-toaan-gov-vn                 d6124923ddcba618811644f433de7c748a291e22
th1nhng0/vietnamese-legal-documents      8977887f17be2defae4c5171d55562e1cde7d695
```

## Kiểm tra OWL người dùng cung cấp

Bản gốc được giữ tại `config/labor_ontology_v3.owl`, SHA-256:

```text
2cba5c1babf3708803ea452ae2e5f1ea692d0144c2831a5f2cec5830c4603221
```

Kiểm kê RDF/XML: 636 subject có tên, 105 class, 149 object property, 119 datatype property, 46 legal issue, 228 named individual. Không phát hiện local resource bị thiếu định nghĩa trong phép kiểm cấu trúc này. Đây **không phải** kiểm tính nhất quán bằng OWL reasoner.

Những điểm tốt: phân biệt PartyAllegation/CourtEstablishedFact/CourtHolding; điều kiện/ngoại lệ; nguồn/span; UNKNOWN không bị hiểu là FALSE. File định nghĩa D1–D4 và D5 về chứng cứ/kết quả, có lưu ý không dùng kết quả xử án để làm đặc trưng dự đoán trước xét xử. Không ép mô hình sáu chiều hiện tại của dự án về số chiều của file.

Những giới hạn: namespace `example.org`; versionInfo 3.0 nhưng versionIRI 1.0.0; có ABox quy phạm/checklist minh họa `sampleOnly=true`, chưa xác minh pháp lý. Bản gốc không bị sửa để che các giới hạn này.

Tích hợp thực hiện **45/46 issue** qua crosswalk rõ ràng sang 13 nhóm OFFLINE đã có, lấy 67 nhãn/đồng nghĩa tiếng Việt làm gợi ý tìm chủ đề. `ISSUE_PROTECTED_EMPLOYEE` chưa ánh xạ vì các nhãn như “đang điều trị” quá rộng. Không nạp rule mẫu, không coi factor là tình tiết có thật, không tự thêm câu hỏi bắt buộc, không sửa Evidence Planner của ONLINE theo các liên kết này.

`config/issues.yaml` bật từ vựng này cho **lần xây OFFLINE tiếp theo**. Hash phải khớp; thiếu file/đổi nội dung thì dừng để kiểm tra thay vì âm thầm dùng một bản khác. Báo cáo build ở `reports/ontology_vocabulary.json`. Có thể tắt `ontology_vocabulary.enabled` để so sánh ablation với cách phân loại cũ.

## Bộ nhập đã bổ sung

```text
python -m vn_labor_offline.external_sources
    fetch           tải đọc Parquet revision cố định, streaming
    stage           đọc JSONL cục bộ, ghi rõ origin chưa được xác nhận
    ontology-audit  kiểm cấu trúc OWL và xuất báo cáo
```

Mỗi lệnh `fetch`/`stage` tạo **thư mục mới**, không ghi đè. Đầu ra:

- `external_sources.sqlite`: ba bảng metadata/content/relationships, thêm rejected cho lỗi dòng. Metadata và content có khóa ngoại; quan hệ chưa giải quyết giữ external target trong JSON gốc.
- `source_review_queue.jsonl`: hồ sơ nguồn, các kiểm tra cần làm; reviewer để trống, trạng thái `REVIEW_REQUIRED`.
- `manifest.json`: revision, license, hash DB, số đã quét/chọn/loại, giới hạn, độ phủ, lỗi và bản trùng. `approved_for_online=false` luôn giữ nguyên ở bước staging.

`dataset_scan_complete` chỉ có thể true khi đọc hết các bảng nguồn Parquet đã pin. Đọc hết file JSONL hoặc mẫu API chỉ xác nhận hết **đầu vào được cung cấp**, không chứng minh đã quét hết dataset. Origin mẫu API/JSONL không được coi là đã xác minh revision.

Lọc lao động dựa vào metadata/chủ đề/số loại bản án. Đây là bộ lọc đề xuất, có thể bỏ sót hoặc chọn nhầm; không phải máy phân loại pháp lý đã duyệt. Không dùng nhắc tới “lao động” trong thân văn bản hoặc tên Bộ để mặc nhiên chọn văn bản. Một bản không tìm thấy trong **lượt quét giới hạn** được ghi `NOT_OBSERVED`, không bị kết luận mất dữ liệu.

Mặc định quét tối đa 2.000 dòng **mỗi bảng**, giữ tối đa 100 hồ sơ. `--max-scan 0` cho phép quét toàn bộ, phải chọn chủ động; không nạp toàn bộ corpus vào pandas/RAM. Dữ liệu HTML vẫn có thể tải đáng kể vì đọc tuần tự Parquet; đây không phải API lấy riêng đúng 100 văn bản. Có giới hạn 24 MB/dòng. Lỗi tải/đọc trả nonzero và giữ manifest FAILED; bị từ chối dòng trả exit 2 để người chạy xem lỗi. Exit 0 chỉ xác nhận staging hoàn tất, không phải đạt legal review.

## Chạy trên Kaggle, chưa cần thay backend đang chạy

Sau khi code mới đã push, dùng notebook riêng hoặc phiên OFFLINE, bật Internet. Không chạy lệnh này trong cell backend đang phục vụ người dùng.

```python
import subprocess, sys
from pathlib import Path

ROOT = Path('/kaggle/working/legal-agentic-rag')  # repo đã clone/cập nhật
def run(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)

run('-m', 'pip', 'install', '-e', '.[external-sources]')
run('-m', 'vn_labor_offline.external_sources', 'ontology-audit',
    '--ontology', 'config/labor_ontology_v3.owl',
    '--output', '/kaggle/working/external_ontology_audit.json')
run('-m', 'vn_labor_offline.external_sources', 'fetch', '--source', 'cases',
    '--output', '/kaggle/working/external_cases', '--max-scan', '2000', '--max-records', '100')
run('-m', 'vn_labor_offline.external_sources', 'fetch', '--source', 'legal',
    '--output', '/kaggle/working/external_legal', '--max-scan', '5000', '--max-records', '100')
```

Không cần Gemini/OpenAI API cho bước này. Public dataset không bắt buộc HF_TOKEN. Chạy lại dùng tên thư mục mới để giữ hồ sơ trước. Lượt giới hạn chưa tìm đủ content/relationships là tình huống có thể xảy ra; xem manifest trước khi tăng giới hạn. Muốn quét hết ba bảng legal có thể dùng `--max-scan 0`; việc này tốn băng thông/disk/thời gian và chưa làm dữ liệu thành căn cứ đã duyệt.

## Khi nào dữ liệu mới thực sự cải thiện câu trả lời?

1. Kiểm danh sách ứng viên và bản trùng với source catalog hiện tại. Xác minh số văn bản, nguồn gốc/PDF, SHA, độ đầy đủ nội dung, loại bản án/án lệ; không nhận lại bản thứ hai chỉ vì khác URL hoặc external ID.
2. Đưa bản gốc đã kiểm vào source catalog/corpus qua luồng review hiện có. Xác minh chiều quan hệ, phạm vi thay đổi, ngày hiệu lực, ngoại lệ và khoảng hiệu lực điều khoản. Bộ staging không tự thực hiện promotion này.
3. Xây OFFLINE trong output riêng bằng pipeline Kaggle hiện có; parse, tạo spans, enrichment có kiểm chứng, graph, BGE-m3 và BM25 theo cùng build. Từ vựng OWL tự tham gia phân loại chủ đề trong bước này. Không append vector từ dataset vào index cũ.
4. Chạy validation và đánh giá bộ câu hỏi đã có, bổ sung câu hỏi ngoài benchmark với Gold được duyệt. So sánh recall, chọn đúng actor/ngày, coverage, citation và độ trễ. Nếu corpus lớn hơn mà recall/latency giảm thì điều chỉnh tuyển chọn/reranking; không đánh đồng nhiều node với chất lượng cao.
5. Chỉ pin ONLINE sang artifact mới sau kiểm tra phù hợp. Corpus/backend hiện có không tự đổi chỉ vì chạy staging.

## Kết quả kiểm tra thực tế

- Bộ kiểm thử mới kiểm scope, khóa string/UUID, nhãn án lệ, span, HTML rỗng, bản trùng, lỗi ngày, giới hạn quét, lỗi mạng, rollback, hash/crosswalk OWL và quy tắc minh họa bị loại. Kết quả full suite ghi tại `artifacts/reports/external_sources_20261020_tests.log`.
- Đã đọc schema và mẫu thật bằng API Hugging Face: 30 bản án cho 1 ứng viên lao động (`2/2021/LĐ-ST`), 33 trích dẫn ứng viên, 7 trích dẫn thiếu span; 30 metadata cho 3 ứng viên lao động. Đây là mẫu API **không chứng minh revision**, không phải lượt quét toàn dataset. Hai content mẫu và các relationship mẫu không trùng 3 ID metadata đã chọn, nên không thể dùng để kết luận các văn bản đó thiếu nội dung trong dataset.
- Mẫu gốc: `review/inputs/external_20261020/viewer_probe_rows/`. Báo cáo kiểm lại bằng phiên bản cuối của bộ nhập: `review/inputs/external_20261020/live_sample_rechecked/`.
- Đường tải Parquet qua SDK trên máy này gặp lỗi kết nối `WinError 10054`; API filter cũng có lần timeout, trong khi API rows thông thường đọc được. Không tắt TLS hoặc tự nhận đường tải end-to-end đã PASS. Lỗi khởi tạo tải được kiểm thử để lưu FAILED manifest và không tạo bản ghi được phê duyệt. Kaggle cần thử lệnh fetch giới hạn trước khi quét toàn bộ.
- OWL audit thật: `artifacts/reports/external_ontology_20261020.json`. Không có local reference chưa định nghĩa trong phép kiểm cấu trúc; vẫn giữ các cảnh báo namespace/version/sample ABox.

Không chạy lại OCR, embedding, enrichment GPU, full OFFLINE hay nạp Aura trong thay đổi này. Chưa tạo ZIP upload mới: nếu dùng bundle upload thay vì git clone, chạy `python scripts/package_kaggle.py` để đóng gói mã/config/OWL mới trước khi upload; ZIP cũ không tự thay đổi.
