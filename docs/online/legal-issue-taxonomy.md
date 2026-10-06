# Taxonomy vấn đề pháp lý cho ONLINE

## Đánh giá đề xuất

Phân nhỏ `TERMINATION` và `LEAVE` là hướng hợp lý. Label rộng chỉ cho biết lĩnh vực; label cụ thể giúp lập kế hoạch tìm căn cứ, loại căn cứ sai chủ thể và kiểm tra phần còn thiếu trước khi trả lời. Việc này có thể giảm những lỗi đã gặp: dùng quy định dành cho công ty khi người lao động xin nghỉ, nhầm nghỉ lễ với nghỉ hằng năm, hoặc trả lời thời hạn báo trước mà bỏ qua hậu quả.

Cần điều chỉnh ba điểm trong đề xuất ban đầu:

1. **Một câu hỏi có thể thuộc nhiều vấn đề.** Cơ chế chấm dứt, tính hợp pháp, trợ cấp và thanh toán phép chưa nghỉ là những khía cạnh có thể cùng xuất hiện. Không chọn duy nhất một nhánh rồi bỏ các nhánh khác.
2. **12/14/16 ngày là các mức hưởng có điều kiện của nghỉ hằng năm.** Dùng `LEAVE.ANNUAL_LEAVE`, rồi xét nhóm công việc, tuổi và tình trạng khuyết tật. Người dùng nhắc “14 ngày” không chứng minh họ thuộc nhóm được hưởng mức đó.
3. **Label chỉ hướng dẫn tìm kiếm.** Label `ILLEGAL_TERMINATION` có nghĩa câu hỏi cần xem xét tính trái pháp luật, không phải hệ thống đã kết luận người dùng chấm dứt trái pháp luật. Tương tự, tìm đúng số điều chưa đủ để xác nhận đúng phiên bản, nguồn hoặc điều kiện áp dụng.

## Phạm vi hiện được triển khai

Phiên bản `labor-subissues-v1` có 21 vấn đề cụ thể trong hai nhóm này. Các nhóm rộng khác vẫn dùng luồng hiện có; chưa triển khai toàn bộ taxonomy pháp luật lao động hoặc các lĩnh vực liên quan như bảo hiểm xã hội.

| Nhóm | Mã vấn đề | Ý nghĩa |
| --- | --- | --- |
| TERMINATION | EMPLOYEE_UNILATERAL | Người lao động đơn phương chấm dứt |
| TERMINATION | EMPLOYER_UNILATERAL | Người sử dụng lao động đơn phương chấm dứt |
| TERMINATION | MUTUAL_AGREEMENT | Hai bên thỏa thuận chấm dứt |
| TERMINATION | EXPIRY | Hết hạn hợp đồng |
| TERMINATION | DISMISSAL | Sa thải theo kỷ luật |
| TERMINATION | ECONOMIC_RESTRUCTURING | Thay đổi cơ cấu, công nghệ hoặc lý do kinh tế |
| TERMINATION | ENTERPRISE_TRANSFER | Sáp nhập, chuyển giao doanh nghiệp |
| TERMINATION | ILLEGAL_TERMINATION | Xem xét chấm dứt trái pháp luật |
| TERMINATION | EMPLOYEE_LIABILITY | Hậu quả đối với người lao động |
| TERMINATION | EMPLOYER_LIABILITY | Hậu quả đối với người sử dụng lao động |
| TERMINATION | SEVERANCE | Trợ cấp thôi việc |
| TERMINATION | JOB_LOSS_ALLOWANCE | Trợ cấp mất việc làm |
| TERMINATION | WITHDRAWAL | Hủy bỏ thông báo đơn phương |
| LEAVE | ANNUAL_LEAVE | Nghỉ hằng năm theo nhóm điều kiện |
| LEAVE | SENIORITY_BONUS | Ngày nghỉ tăng theo thâm niên |
| LEAVE | PRO_RATA_LEAVE | Nghỉ theo tỷ lệ khi chưa đủ 12 tháng |
| LEAVE | TRAVEL_DAYS | Thời gian đi đường khi nghỉ hằng năm |
| LEAVE | PUBLIC_HOLIDAY | Nghỉ lễ, Tết |
| LEAVE | PERSONAL_LEAVE | Nghỉ việc riêng |
| LEAVE | UNPAID_LEAVE | Nghỉ không hưởng lương |
| LEAVE | UNUSED_LEAVE_PAYMENT | Thanh toán ngày nghỉ hằng năm chưa nghỉ |

Mã đầy đủ gồm cả nhóm, ví dụ `TERMINATION.SEVERANCE`. `DISMISSAL` đồng thời giữ nhóm cha `DISCIPLINE` vì sa thải còn liên quan đến xử lý kỷ luật.

## Luồng xử lý

1. Query Analyzer nhận câu hỏi, ngữ cảnh và ngày tra cứu; xác định nhóm cha, vấn đề cụ thể và dữ kiện. Phân loại cụ thể hiện dùng quy tắc xác định. Researcher có thể bổ sung dữ kiện có bằng chứng trong câu hỏi; sau đó hệ thống tính lại các label hợp lệ.
2. Evidence Planner giữ các yêu cầu nguồn/phiên bản hiện có và bổ sung `slot_requirements`. Mỗi yêu cầu có danh sách văn bản, Điều, Khoản và Điểm tương ứng với chế độ pháp luật theo ngày tra cứu.
3. Retriever lấy ứng viên theo các vị trí này bên cạnh các kênh tìm kiếm hiện có. Nó giữ ứng viên từ các văn bản/phiên bản thay thế để bước lọc hiệu lực quyết định tiếp.
4. Bộ lọc nguồn, hiệu lực và Applicability Auditor tiếp tục kiểm tra. Quy tắc loại cứng chặn căn cứ sai chủ thể hoặc sai cơ chế trong phạm vi đã định nghĩa; LLM không được nâng quyết định loại cứng thành PASS.
5. Evidence Coverage kiểm tra từng yêu cầu trên **bằng chứng đã qua kiểm tra**. Bộ chọn bằng chứng ưu tiên giữ đủ từng nhóm Khoản/Điểm bắt buộc, tránh để kết quả có điểm tìm kiếm cao nhưng không phù hợp chiếm hết chỗ.
6. Nếu còn thiếu, tên slot hướng dẫn đi tiếp trên các quan hệ graph hiện có. Giới hạn số vòng, số node, thời gian và kích thước bằng chứng vẫn áp dụng. Hết ngân sách mà chưa đủ thì giữ trạng thái thiếu/một phần.
7. Sinh câu trả lời và kiểm tra trích dẫn tiếp tục dùng luồng hiện có. Taxonomy không tự phê duyệt nguồn, hiệu lực hay chất lượng pháp lý của câu trả lời.

### Cách hiểu yêu cầu bằng chứng

`slot_requirements` sử dụng hai tầng:

- Các nhóm bên ngoài đều phải được đáp ứng: **AND**.
- Các vị trí bên trong một nhóm là lựa chọn thay thế: **OR**.

Ví dụ câu hỏi tổng quan về nghỉ hằng năm yêu cầu đủ ba nhóm Điểm a, b, c. Một căn cứ chỉ nói về mức 12 ngày không đáp ứng cả slot. Câu hỏi tính mức hưởng cho một người đã xác định nhóm công việc thì sử dụng điểm phù hợp thay vì mặc định lấy cả ba mức như thể cùng áp dụng.

Slot hậu quả của người lao động theo chế độ hiện hành được tách thành các nhóm Khoản 1, 2, 3 Điều 40; slot trợ cấp thôi việc/mất việc yêu cầu các khoản về điều kiện, thời gian tính và tiền lương tính. Thiếu một nhóm thì slot chưa đầy đủ. Yêu cầu vị trí vẫn là hướng dẫn truy xuất; nội dung, ngoại lệ và dẫn chiếu phải được kiểm tra tiếp.

Các profile dùng vị trí tương ứng của Bộ luật Lao động 2012 khi ngày tra cứu thuộc chế độ đó, thay vì dùng vị trí của Bộ luật 2019 cho câu hỏi lịch sử. Đây không phải xác nhận rằng corpus chứa đầy đủ mọi sửa đổi qua mọi thời kỳ.

## Những lỗi được kiểm soát thêm

- Không dùng căn cứ đơn phương của người sử dụng lao động để lấp slot đơn phương của người lao động; câu hỏi so sánh hai chủ thể vẫn giữ cả hai nhánh.
- Thỏa thuận, hết hạn, sa thải và thay đổi cơ cấu có kế hoạch riêng; không mặc định yêu cầu thời hạn báo trước như người lao động đơn phương nghỉ.
- Câu hỏi đánh giá sa thải hỏi lý do, thủ tục và tình trạng được bảo vệ; câu hỏi đánh giá trợ cấp hỏi thời gian làm việc, bảo hiểm thất nghiệp và căn cứ chấm dứt.
- Nghỉ việc riêng không bị nhận nhầm thành xin nghỉ việc. Nghỉ lễ không đi vào bộ tính phép năm.
- Câu hỏi vừa nghỉ việc vừa hỏi tiền phép còn dư giữ cả hai nội dung; câu hỏi thanh toán tiền phép đơn thuần không bắt nhập nhóm công việc để tính số ngày khi chưa yêu cầu tính.
- Chuỗi dẫn chiếu riêng, ví dụ nghỉ ngay do chậm lương và ngoại lệ liên quan, vẫn giữ slot tương ứng.
- Trùng số Điều nhưng khác văn bản không đáp ứng yêu cầu. Bằng chứng chưa qua kiểm tra không đáp ứng profile chỉ nhờ label hoặc điểm tìm kiếm cao.

## Kiểm tra đã thực hiện

- Toàn bộ regression suite: **294 test PASS**, thời gian chạy được ghi nhận **7,350 giây** trên môi trường kiểm thử local.
- File `tests/online/test_issue_taxonomy.py`: **26 test PASS**. Bao gồm phân loại nhiều vấn đề, chủ thể, cơ chế chấm dứt, ngày lịch sử, giữ nhiều nhóm bằng chứng và thiếu ngân sách.
- Đọc retrieval units từ ZIP V8.1 Aura: **8/8 tình huống có ứng viên cho mọi slot profile** trong bài kiểm tra cấu trúc. Kết quả chi tiết ở `artifacts/reports/online_issue_taxonomy_candidate_check.json`.

Bài kiểm tra ZIP chỉ đối chiếu vị trí cấu trúc. Nó không xác nhận URL còn truy cập được, nội dung OCR đúng, hiệu lực đã được chuyên gia duyệt hoặc câu trả lời LLM chính xác. Tests dùng fixture và provider giả lập; chưa chạy lại benchmark câu hỏi trên backend Kaggle thật trong lần thay đổi này. Không có tỷ lệ tăng độ chính xác được đo để báo cáo.

## Cập nhật và kiểm thử trên Kaggle

Thay đổi này nằm ở ONLINE và đọc các artifacts hiện có. **Không cần chạy lại OFFLINE, Dense, BM25 hoặc nạp lại Aura chỉ vì taxonomy này.** Cần đưa code mới lên remote Git, cập nhật checkout Kaggle, rồi khởi động lại backend để nạp code mới.

Nếu checkout Kaggle sạch và chạy nhánh `main`, dùng một cell:

```python
%cd /kaggle/working/legal-agentic-rag
!git pull --ff-only origin main
```

Nếu Git báo checkout có thay đổi/xung đột, xử lý thông báo đó; không dùng lệnh reset xóa thay đổi. Không khởi động thêm một backend thứ hai trên cùng port. Dừng backend cũ theo luồng notebook đang dùng, rồi chạy lại cell khởi động backend. Frontend vẫn kết nối URL backend đó; nếu tunnel đổi URL thì cập nhật cấu hình frontend và khởi động lại Vite.

Kiểm thử các câu sau và đọc trace trong response:

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| Người lao động làm việc đủ 12 tháng được nghỉ phép năm bao nhiêu ngày? | `LEAVE.ANNUAL_LEAVE`; đủ ba nhóm điều kiện, không chỉ mức 12 ngày |
| Người lao động không thuộc ngoại lệ/đặc thù, HĐLĐ không xác định thời hạn, báo trước 20 ngày; hậu quả là gì? | Nhánh người lao động, tính hợp pháp và hậu quả; không lấy quy định công ty làm căn cứ chính |
| Trợ cấp thôi việc và trợ cấp mất việc khác nhau thế nào? | Hai nhánh và hai bộ yêu cầu cùng tồn tại |
| Công ty sa thải tôi có đúng không? | Nhánh sa thải; yêu cầu dữ kiện thủ tục/lý do, không hỏi báo trước như xin nghỉ |
| Tôi nghỉ việc và còn phép năm chưa nghỉ; tiền phép được giải quyết thế nào? | Cả chấm dứt và thanh toán phép còn dư; không bỏ phần thứ hai |
| Ngày 15/12/2020, người lao động HĐLĐ không xác định thời hạn muốn đơn phương nghỉ việc; thời hạn báo trước là gì? | Profile dùng chế độ lịch sử, không thay bằng căn cứ chỉ có hiệu lực từ 2021 |

Trace `analysis` phải có `taxonomy_version` và `subissues`; trace `evidence_plan` phải có `slot_requirements`. Trạng thái một phần vẫn phù hợp khi nguồn/hiệu lực chưa duyệt; không chuyển VERIFIED bằng tay để làm bài kiểm tra đạt.

## Giới hạn và hướng mở rộng

Phân loại quy tắc có thể bỏ sót cách diễn đạt mới, nhầm phủ định hoặc phân biệt chưa đủ các tình huống phức tạp. Cần bổ sung test từ câu hỏi thật và benchmark có đáp án được duyệt trước khi mở rộng taxonomy.

Các slot cấp Điều cho một số profile tổng quát chưa biểu diễn đầy đủ mọi điều kiện và ngoại lệ theo từng tình huống. Chúng hỗ trợ tìm và kiểm thiếu căn cứ; không thay thế kiểm tra claim–evidence, dẫn chiếu, nội dung điều khoản và chuyên gia pháp lý. Ngày chốt corpus và trạng thái human review vẫn là giới hạn của hệ thống.

Hiện chưa thêm node `LegalSubIssue` vào graph OFFLINE. Nếu sau này cần tìm kiếm/đánh giá trên toàn bộ taxonomy ở cấp graph, có thể bổ sung các node/quan hệ có phiên bản, dữ liệu gán nhãn và kiểm thử tương ứng trong một lần rebuild riêng. Không cần rebuild chỉ để sử dụng các profile ONLINE hiện tại.
