# Kiểm tra phản biện và sửa chất lượng ONLINE — 08/10/2026

Hai nhận xét được đối chiếu với source thực tế và JSONL `labor_285_v2_20261007T160304Z`, không chỉ bảng trạng thái. Phần lớn lỗi nội dung được nêu là có thật. Một số kết luận về nguyên nhân, mức độ hoàn thiện và cách tối ưu cần điều chỉnh. Đợt sửa này ưu tiên lỗi đã tái hiện được, giữ kiểm tra nguồn/hiệu lực và không chạy lại OFFLINE.

## 1. Nhận xét nào đúng, nhận xét nào cần phản biện?

| Nhận xét của người đánh giá | Kết quả đối chiếu | Cách xử lý |
| --- | --- | --- |
| Profile tập trung vào hợp đồng, chấm dứt và nghỉ phép | Đúng với v2; nhiều vấn đề khác còn đi qua xử lý tổng quát | Bổ sung 7 subissue về thời gian thử việc, đào tạo, làm thêm và tiền lương ban đêm; không tuyên bố bao phủ toàn bộ pháp luật |
| OFFLINE và ONLINE có bộ nhãn khác nhau, bỏ sót đường tới một số issue | Đúng; khác tên chưa tự nó là lỗi, thiếu mapping mới gây mất đường truy xuất | Tạo mapping tương thích tập trung và kiểm tra mọi issue key trong `config/issues.yaml` đều có đường truy xuất ONLINE |
| Mọi câu đều gọi đủ ba LLM, chưa có đường nhanh | Quá rộng. v2 đã có `profile_fast_path`, exact lookup và bỏ Researcher ở một số ca | Mở rộng đường nhanh có điều kiện, kiểm tra căn cứ đầy đủ trước khi dùng; phát hiện và bỏ thêm 5 lời gọi Researcher thừa |
| Claim audit dùng overlap 35% nên không chứng minh được entailment | Đúng. Cùng từ khóa vẫn có thể đảo nghĩa | Thêm guard đảo nghĩa, sai loại văn bản, nghĩa vụ/ngoại lệ tự bịa và đơn vị ngày; thêm proposition định lượng cho thử việc. Overlap còn là bộ lọc sơ bộ cho claim tổng quát |
| Fact gate hỏi quá nhiều hoặc hỏi sai dữ kiện | Đúng tại các ca thực tập, chi phí đào tạo và tự nguyện không nhận tiền làm thêm | Phân biệt câu hỏi giải thích quy tắc, giả định đã trái pháp luật, và yêu cầu kết luận cho vụ việc thực tế |
| OLD-1.3/1.4 bị từ chối vì OCR | Thông báo có nói vậy nhưng nguyên nhân thực tế khác: yêu cầu sai `leave_base_rule` và `party_definitions` | Sửa phân loại, kế hoạch căn cứ và phân biệt `answer_completeness`, `answer_text_quality` với `source_text_quality`; giữ nguyên guard OCR |
| Graph có quan hệ được ưu tiên nhưng mặc định bị chặn | Đúng với cấu hình được giao kèm | Bổ sung các quan hệ vào mặc định và ba YAML, dùng cùng chuẩn hóa tiếng Việt khi tính relevance |
| Startup phải lỗi nếu thiếu bất kỳ quan hệ nào trong `GAP_RELATIONS` | Không nên áp dụng nguyên xi: cấu hình traversal hẹp có thể là chủ ý | Không bắt buộc mọi cấu hình tùy biến phải cho phép mọi edge; vẫn giữ giới hạn node/hop/round |
| Metadata loại văn bản/cơ quan ban hành chưa đi hết tới model/UI | Đúng | Truyền metadata qua evidence pack/citation/prompt; UI dùng trường backend, không tự đoán VBHN thành nghị định |
| Giảm token xuống 512/768 và giảm toàn bộ candidate budget sẽ vừa nhanh vừa đúng | Chưa có bằng chứng. Có thể làm cụt JSON hoặc mất ngoại lệ | Giữ giới hạn token và ngân sách retrieval hiện có; giảm công việc thừa ở những chuỗi quy tắc đã có căn cứ đầy đủ |
| Tăng hạn mức auditor hoặc tự cho overflow PASS giải quyết false insufficient | Tăng số lượng chưa giải quyết đúng/sai; tự PASS tạo lỗi mới | Ưu tiên candidate thuộc chuỗi cần thiết và khóa quyết định xác định được; overflow chưa xác minh vẫn không được nâng thành PASS |
| Pooling HTTP giúp giảm độ trễ | Có ích nhưng không phải nguồn tiết kiệm chính so với tránh inference | Tái sử dụng HTTP client, retry tối đa một lần cho lỗi HTTP tạm thời, đóng client khi API dừng |
| Có thể chấm 5,5–7/10 và kết luận độ chính xác chung | Là nhận định chuyên môn hữu ích, chưa phải metric Gold của 285 câu | Không biến điểm nhận xét thành accuracy đã đo; lưu đầu ra thật và các kiểm tra nội dung riêng |

Một locator hoặc profile được nhận diện không tự chứng minh nội dung đúng hay đủ điều kiện áp dụng. URL có dạng chính thức cũng không thay thế việc đối chiếu đúng tài liệu và phiên bản. Đường nhanh vẫn đi qua kiểm tra artifact, temporal, provenance, applicability, coverage và reference audit.

Không nên dùng mẫu trả lời hiện hành cho truy vấn lịch sử chỉ vì cùng số điều. Kiểm thử bổ sung xác nhận thời gian thử việc trước năm 2021 dùng bộ ba mức của văn bản cũ, không chèn nhóm 180 ngày của luật mới. Nguồn để đối chiếu phiên bản gồm [Bộ luật Lao động trên Cổng Chính phủ](https://chinhphu.vn/?classid=1&docid=198540&pageid=27160&typegroupid=3) và [Văn bản hợp nhất 18/VBHN-VPQH](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm).

## 2. Các lỗi nội dung đã sửa

| Ca benchmark | Lỗi cũ xác nhận được | Hành vi sau sửa |
| --- | --- | --- |
| OLD-1.3 | Câu chỉ hỏi đi đường nhưng yêu cầu thêm đủ các nhóm nghỉ hằng năm | Lấy khoản 6 Điều 113, trả điều kiện và phép tính đi đường; không đòi ngày cơ sở không được hỏi |
| OLD-1.4 | “Định nghĩa” và “người lao động” ở hai chỗ khác nhau bị hiểu thành định nghĩa chủ thể | Phân biệt Điều 39 và các khoản của Điều 40 |
| NEW-4.1 | Thiếu mức 180 ngày; còn đổi 60/30 ngày thành ngày làm việc | Đủ bốn nhánh và kiểm tra đúng đơn vị; thiếu một nhánh thì không dùng renderer đầy đủ |
| NEW-5.1 | Biến xử phạt hành vi “không đào tạo/không ký” thành lệnh “không được đào tạo/không được ký” | Chọn quy định học/tập nghề phù hợp; chặn inversion ở cả đầu ra model và reference audit |
| NEW-5.4 | Hỏi ngày phát sinh tiền lương thay vì loại quan hệ thực tập | Hỏi thực tập theo trường, học/tập nghề, thử việc hay làm việc thực tế có trả công và quản lý |
| NEW-6.3 | Xét lại loại hợp đồng, báo trước dù câu hỏi đã giả định trái pháp luật | Giữ giả định của đề bài; lấy nghĩa vụ hoàn trả và hợp đồng/chi phí đào tạo, không ghi giả định thành phán quyết vụ việc |
| NEW-6.4 | Tự thêm lý do chính đáng và ngoại lệ đào tạo vào Điều 35; gọi VBHN là nghị định | Trả lời có điều kiện theo thỏa thuận đào tạo và chi phí có chứng từ; không tự kết luận mọi trường hợp nghỉ sớm đều phải trả mọi khoản |
| NEW-9.1 | Thiếu căn cứ do slot chung; còn nguy cơ lấy một điểm nhỏ thay cho khoản về mức 300 giờ | Kiểm tra đủ giới hạn và điều kiện áp dụng; parent slot phải khớp đúng cấp khoản |
| NEW-9.3 | Liệt kê các ngày lễ thay vì chuỗi quy định trả lương | Dùng Điều 98 và Điều 57 Nghị định 145; không liệt kê lại Điều 112; câu hỏi “kết hợp quy định nào” được giải thích ngắn hơn câu hỏi công thức/tính tiền |
| NEW-9.5 | Chặn câu giải thích nghĩa vụ trả tiền làm thêm vì thiếu ngày sự việc | Nêu nghĩa vụ và các mức với căn cứ tương ứng; không dùng sự đồng ý làm thêm thay cho nghĩa vụ trả lương |

Kiểm thử còn chặn việc hiểu câu hỏi “có bị coi là trái pháp luật không?” hoặc câu chứa “không trái pháp luật” thành tiền đề đã trái pháp luật. Khi câu hỏi đào tạo có yêu cầu riêng về thời hạn báo trước, kế hoạch phải giữ cả hai chuỗi căn cứ; không dùng renderer chỉ trả lời báo trước cho câu nhiều vấn đề.

Các ca đã tốt như OLD-1.1, OLD-1.2, OLD-3.1, NEW-2.4 và NEW-3.1 được giữ trong bộ kiểm tra để tránh sửa lỗi mới làm hỏng chuỗi dẫn chiếu, chủ thể và hậu quả pháp lý cũ.

Không áp dụng kiến nghị “chỉ cần tìm thấy Điều 25 là render cả bốn mức”: thiếu nhánh, sai đơn vị hoặc sai phiên bản sẽ khiến renderer không được sử dụng. `exact_level` cũng chặn việc một điểm nhỏ tự thỏa yêu cầu về nội dung của cả khoản. Với các profile mới, mỗi nhóm căn cứ cần thiết được kiểm độc lập.

## 3. Phạm vi code đã đổi

- `analysis.py`, `taxonomy.py`, `researcher.py`: phân loại, giả định của câu hỏi, fact gate, profile có ngày tra cứu; taxonomy hiện tại là `labor-subissues-v3`.
- `issue_mapping.py`, `retrieval.py`, `graph.py` và các YAML: mapping nhãn tương thích, index tra cứu document/article, quan hệ traversal và tokenizer thống nhất.
- `models.py`, `evidence.py`, `compression.py`: metadata loại/cơ quan văn bản, phân biệt quy phạm và xử phạt, locator đúng cấp, chọn nguồn sạch hơn sau khi lọc hiệu lực/authority, giữ đầy đủ phần nguồn cần cho chuỗi profile.
- `profile_generation.py`, `claim_validation.py`, `generation.py`, `audit.py`, `answer_quality.py`: trả lời bằng chuỗi căn cứ, guard nghĩa/đơn vị, chống lặp claim mà vẫn giữ citation, không tự sửa chữ OCR hoặc số điều bằng phỏng đoán.
- `providers.py`, `pipeline.py`, `api.py`: pooling, retry hữu hạn, cleanup và `/ready.taxonomy_version` để kiểm tra bản backend đang chạy.
- `frontend/src/services/chatService.js`: hiển thị đúng metadata và thông báo rõ thiếu nội dung/ràng buộc nguồn.
- `docker-compose.yml`: lấy mật khẩu từ môi trường, bind cổng Neo4j ở localhost, bỏ quyền `apoc.*` không giới hạn. Đây là hardening cấu hình, không phải bằng chứng về chất lượng pháp lý. Chưa khởi động Docker/Aura trong đợt kiểm tra này.

Không thêm nhà cung cấp AI hoặc yêu cầu thêm API key cho các sửa đổi này. Mô hình hiện có vẫn được dùng cho câu hỏi chưa xử lý chắc chắn bằng quy tắc; không tự tắt các kênh retrieval trong cấu hình vận hành.

## 4. Kiểm chứng và giới hạn của số đo

- Toàn bộ test suite: **345/345 PASS**; bộ mới có 30 ca kiểm thử, gồm trường hợp âm tính và truy vấn lịch sử.
- Python `compileall`: PASS; `git diff --check`: PASS.
- Frontend production build và ESLint: PASS.
- Replay 15 câu gốc từ JSONL cũ trên ZIP V8.1: **15/15 PASS** theo các kiểm tra nội dung cụ thể, không chỉ HTTP/status.
- Kiểm tra thêm với `config/online_kaggle.yaml`: **15/15 PASS**, giữ cấu hình đầy đủ và đặt tripwire ở các lời gọi model/retrieval nặng. Không có lời gọi thừa bị phát hiện sau sửa. 14 câu đi đường profile, một câu đi fact gate.

Trong kiểm tra cấu hình đầy đủ, thời gian `ask()` cục bộ đã khởi tạo dao động khoảng **4–61 ms**, trung bình khoảng **33 ms**. Đây là số đo code/quy tắc, có ghi trace; không gồm khởi động, tải dữ liệu, mạng ngrok, GPU hoặc inference. Tripwire chứng minh các ca này không cần gọi thành phần nặng; nó không đo tốc độ của các thành phần đó. **Không được dùng số này làm latency toàn bộ 285 câu hay tuyên bố mức cải thiện so với benchmark Kaggle cũ.**

Benchmark Kaggle cũ có 285 câu, gồm 25 câu OLD, 250 câu NEW và 10 câu nhiều vấn đề; trung bình 29,025 giây, P95 61,090 giây. HTTP 200 cả 285 câu chỉ xác nhận dịch vụ trả về, không phải độ chính xác pháp lý. Chưa chạy lại 285 câu trên backend mới trong đợt sửa này.

Output kiểm chứng:

- `artifacts/online_benchmarks/review_content_20261008_full_config.jsonl`: câu hỏi gốc, câu trả lời đầy đủ, checks và thời gian từng câu.
- `artifacts/online_benchmarks/review_content_20261008_full_config.summary.json`: summary, checksum baseline, checks từng ca và `forbidden_calls: []`.
- `scripts/verify_review_content.py`: công cụ chạy lại; không tạo câu hỏi giả khi baseline thiếu record.

Tất cả kết quả có căn cứ vẫn là `PARTIAL_ALLOWED` vì nguồn/hiệu lực chưa được duyệt đầy đủ; câu thực tập là `NEED_MORE_FACTS`. Không ghi reviewer, approval hay Gold giả. Dữ liệu, corpus, ZIP release, build ID, indexes và Aura không được thay bằng build mới.

## 5. Những phần chưa thể coi là hoàn tất

1. **Lỗi ranh giới khoản trong dữ liệu V8.1.** Đoạn trích Điều 61 khoản 2 của VBHN chứa cả phần bắt đầu bằng `3.33 ... không được thu học phí`. ONLINE thông báo `SOURCE_CLAUSE_BOUNDARY_NEEDS_REVIEW` và nêu rõ nguồn đang gộp khoản 2–3. Không âm thầm đổi locator thành khoản 3. Cần xử lý footnote/ranh giới cấu trúc ở lần OFFLINE tiếp theo và đối chiếu bản gốc. Không lấy lại nguyên văn khoản 3 cũ rồi coi là hiện hành; xem [VBHN chính thức](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-18-vbhn-vpqh-468971.htm) và [Luật 124/2025/QH15](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/01/luat124-2025.pdf) khi đối chiếu thay đổi.
2. **Mapping chưa phải một taxonomy cấu hình chung hoàn toàn.** Đã kiểm tính tương thích các nhãn của graph hiện hữu; chưa chuyển toàn bộ ontology/profile sang một YAML dùng chung và chưa rebuild graph.
3. **Typed proposition chưa bao phủ mọi legal operation.** Mới thêm contract định lượng cho thử việc; các phép tính nghỉ phép hiện có vẫn dùng logic xác định sẵn. Claim tổng quát còn dùng lexical screen và guard lỗi đã biết, chưa có bộ chứng minh ngữ nghĩa cho mọi mệnh đề.
4. **Chưa có Gold chuyên gia cho cả 285 câu.** PASS ở 15 ca chỉ xác nhận các lỗi/chains đã kiểm tra; không chứng minh toàn bộ ngành luật hoặc mọi cách hỏi tương đương đều đúng.
5. **Nguồn, temporal và corpus freshness vẫn cần reviewer.** Tự nhận diện URL/loại văn bản không giải quyết đầy đủ thẩm quyền, phiên bản và thay đổi sau ngày chốt corpus.
6. **Câu ngoài các profile mới vẫn có thể cần model và graph.** Không hứa mọi câu trả trong vài giây; chưa đổi database hoặc giảm candidate/token budget khi chưa đo recall.
7. **Trace và vận hành production cần bước riêng.** Chưa thêm chính sách ẩn dữ liệu nhạy cảm/retention, kiểm tải đồng thời hoặc tái cấu trúc toàn bộ CI trong đợt sửa nội dung này.

## 6. Cách sử dụng bản sửa

Tại thư mục dự án:

```powershell
.\run.bat test
.\run.bat online-check

.\.venv\Scripts\python.exe scripts/verify_review_content.py `
  --baseline artifacts/online_benchmarks/labor_285_v2_20261007T160304Z.jsonl `
  --config config/online_kaggle.yaml `
  --verify-fast-path `
  --output artifacts/online_benchmarks/review_content_20261008_full_config
```

Lệnh replay cần baseline và ZIP V8.1 đang có trên máy này; nếu thiếu chúng, dừng và cung cấp đúng file, không dựng lại dữ liệu giả. Artifact và báo cáo có thể đang bị `.gitignore`, không nhất thiết xuất hiện trong một checkout sạch.

Muốn Kaggle sử dụng bản sửa, cần commit/push **cả file mới lẫn file đã sửa**, rồi dừng backend cũ và chạy lại cell cập nhật `origin/main`, cài project và cell `online_remote.py` theo hướng dẫn Kaggle hiện có. Tôi chưa push hay khởi động lại dịch vụ của bạn.

Kiểm tra `/ready` bằng URL ngrok và bearer token đang dùng: `taxonomy_version` phải là **`labor-subissues-v3`**. `/ready` chưa có trường này hoặc trace còn v2 nghĩa là backend chưa dùng bản sửa. Ready không có nghĩa dữ liệu đã được duyệt pháp lý, và các model có thể vẫn ở trạng thái lazy.

Sau đó khởi động lại frontend để lấy code mới; cập nhật `VITE_BACKEND_TARGET` nếu URL ngrok đổi. Thử trước các ca thử việc, đào tạo và lương ban đêm, rồi đo lại đầy đủ 285 câu ở cùng cấu hình/ngày tra cứu. Tách kết quả lạnh/ấm, số lời gọi model, đường EXACT/PROFILE/HYBRID, thời gian từng giai đoạn và chất lượng claim/citation; không chỉ so sánh status hoặc tốc độ.

**Các sửa ONLINE này dùng được ngay với release V8.1, không buộc chạy lại OFFLINE để thử chúng.** Lần chạy OFFLINE tiếp theo dành cho sửa ranh giới khoản/footnote và hoàn tất input review; không đổi release đang phục vụ ONLINE giữa một lượt benchmark.
