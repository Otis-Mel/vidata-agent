# Nhật ký thay đổi bộ eval

Quy tắc: mọi thay đổi bộ chấm/câu hỏi sau khi đã xem kết quả đều phải ghi ở đây, nêu lý do, áp dụng cho TẤT CẢ
split và chạy lại TẤT CẢ cấu hình. Không chỉnh để agent "trông tốt hơn", chỉ sửa lỗi của bộ chấm và sự mơ hồ của câu hỏi.

## 2026-10-15 — sửa sau khi đọc danh sách câu sai của p1_router (dev)
Đọc 11 câu sai, đối chiếu SQL của agent với gold: một nửa là lỗi của bộ eval, không phải của agent.

**Bộ chấm (`src/eval_utils.py`)**
1. *Thứ tự dòng*: trước đây dùng `ORDER BY` của gold để quyết định có so thứ tự hay không, nên phạt oan agent khi câu hỏi
   không yêu cầu sắp xếp (m03: cùng giá trị, khác thứ tự dòng). Nay chỉ so thứ tự khi câu hỏi có chữ "xếp".
2. *Biểu diễn thời gian*: '2025-03', timestamp đầu tháng và DATE được coi là cùng một giá trị (h03, h08: cùng số liệu, khác
   định dạng tháng). Timestamp có giờ thật vẫn không bị gộp.

**Câu hỏi (`scripts/build_eval_set.py`)**
3. h02: thêm "tỉ lệ phần trăm, làm tròn 2 chữ số" (agent trả phân số 0.06, gold 6.01: câu hỏi chưa nêu đơn vị).
4. h05, h01: nêu rõ chỉ xét các kỳ trong năm 2025 nên kỳ đầu là NULL; h05 yêu cầu trả về số quý (1-4).
5. h06: nêu rõ là tỉnh của khách hàng (agent hỏi lại vì cả khách và shop đều có tỉnh: sự mơ hồ có thật).
6. e03: đổi cách hỏi cho tự nhiên ("tổng cộng bao nhiêu sản phẩm?").

**Giữ nguyên (lỗi thật của agent):** m02, m09 (bỏ sót 'Hanoi'), h06 phần từ chối ở p1, a01, a02 (không hỏi lại).

Gold SQL không đổi (trừ h05 trả về số quý thay vì timestamp). Test hồi quy: `tests/test_grader.py` dùng đúng SQL của agent
từ lần chạy này và kiểm tra cả hai chiều (tha câu đúng, vẫn phạt câu sai thật).

Lưu ý trung thực: split test chưa từng được chạy bởi bất kỳ agent nào; các sửa đổi trên là sửa lỗi chung của bộ chấm
và áp dụng như nhau cho dev và test.

## 2026-10-21 — định dạng cột tháng (sau khi so p0 và p2 bằng compare_runs.py)
Câu h03 "bị làm hỏng" ở p2. Chạy lại SQL của p2: cả 12 tháng, tiền hàng và tiền thu **trùng khớp từng số** với gold; chỉ khác
cột tháng (p2 trả 1..12, gold trả ngày đầu tháng). Đó là lỗi câu hỏi chưa nêu định dạng (cùng loại với h05), không phải lỗi của p2.

Sửa: các câu trả về cột tháng (h01, h03, h08) nay ghi rõ "Cột tháng trả về dạng YYYY-MM". Bộ chấm vẫn coi `'2025-03'` và
ngày đầu tháng là cùng một giá trị, nhưng số tháng trần (1..12) không còn được chấp nhận vì câu hỏi đã yêu cầu định dạng.
Gold SQL không đổi. Cả 7 cấu hình phải chạy lại cho các câu này (câu hỏi đổi nên cache không dùng lại).

Bài học: mỗi câu trả về cột thời gian phải nêu định dạng; đã soát toàn bộ câu có cột thời gian (h01, h03, h05, h08, m16).
Lưu ý: kết quả này cho thấy cùng một cấu hình có thể chọn định dạng khác nhau giữa các lần chạy (p0 trả YYYY-MM, p2 trả số tháng),
nên các chênh lệch 1-2 câu giữa cấu hình chưa nên diễn giải là tác động của cấu hình.

## 2026-10-21 — mở rộng bộ eval từ 53 lên 101 câu (đợt v2)
Lý do: trên dev cũ, p2/p3/p4 đều đạt 100% câu trả lời được (28 câu) nên không còn phân biệt được các cấu hình.

Thêm 48 câu (`scripts/eval_questions_v2.py`): 36 trả lời được (n01-n36), 6 mơ hồ (a07-a12), 6 ngoài phạm vi (o07-o12).
Trọng tâm: nhân dòng nhiều bảng (n01, n02, n20-n22, n35), múi giờ (n04-n10, n24, n25, n33), cohort/giữ chân (n07, n08, n29),
window function (n09, n10, n12, n15), tên tỉnh nhiều cách viết (n22, n23, n36), nhiều bước (n13, n16, n27).

Quy tắc áp dụng cho mọi câu mới: ghi rõ định dạng cột thời gian (YYYY-MM, thứ ISO), số chữ số làm tròn, đơn vị phần trăm,
luật xử lý khi bằng nhau ở câu top-N, không yêu cầu thứ tự dòng. Các câu mới được viết TRƯỚC khi chạy bất kỳ agent nào.

Kiểm tra gold: mọi gold SQL chạy được, không rỗng/NULL/0; n16 (giảm giá voucher) được đối chiếu độc lập bằng cách tính ngược từ
bảng payments và khớp đến từng đồng; n21, n01 đối chiếu bằng cách đếm tay.

Split: 53 câu cũ GIỮ NGUYÊN split; 48 câu mới được nối vào cuối danh sách và chia theo cùng quy tắc (cứ 3 câu thì 1 vào test).
Kết quả: dev 68 câu, test 33 câu. 32 câu dev mới chưa từng được agent nào chạy nên là lần đánh giá "nhìn lần đầu" sạch.
Chưa ai chạy agent trên 33 câu test. Chỉ chạy test một lần, sau khi chốt cấu hình.

## 2026-10-21 — SỬA SAU KHI ĐÃ CHẠY TEST (m05, m11); số test đã báo cáo KHÔNG đổi
Sau khi chạy split test một lần (p0/p2/p4 đều 23/25), đọc các câu sai và đối chiếu với gold phát hiện 2 lỗi thiết kế câu hỏi:
- m11: 3 danh mục gốc trùng điểm 4.23 sau khi làm tròn; câu hỏi yêu cầu xếp thứ tự nhưng KHÔNG nêu luật khi bằng nhau,
  trong khi gold xếp theo tên. Agent đúng giá trị vẫn có thể bị chấm sai vì thứ tự các dòng bằng nhau là tuỳ ý.
- m05: câu hỏi yêu cầu trả về category_id và tên, nhưng gold trả thêm cột tiền hàng; agent làm đúng theo chữ của câu hỏi (2 cột) sẽ bị chấm sai.
Sửa: chỉ đổi lời hỏi (nêu luật bằng nhau cho m11, nêu đủ 3 cột cho m05), gold SQL không đổi.
Thêm `scripts/audit_eval.py` (soát câu yêu cầu thứ tự mà có giá trị trùng); đã quét toàn bộ 101 câu: chỉ m11 vi phạm.

Quy tắc báo cáo: các số test đã báo cáo (23/25 ở cả p0, p2, p4) được GIỮ NGUYÊN, đã chạy trên lời hỏi cũ, không chạy lại.
Phân tích sau-khi-biết (post-hoc), chỉ có giá trị khi cả hai lỗi thiết kế được xác nhận bằng SQL của agent: loại m05 và m11 khỏi
tập test thì cả ba cấu hình đều 22/23 (95.7%), chỉ sai h10. Kết luận "không khác biệt đo được" không đổi.

## 2026-10-21 — ĐÍNH CHÍNH sau khi xem SQL thật của agent trên test (h10, m05, m11)
Đã chạy lại chính các câu SQL của agent trên dữ liệu và so với gold. Kết quả:
- m05 (p0): agent trả 2 cột (category_id, tên) đúng yêu cầu câu hỏi; top-5 GIỐNG gold, gold có thêm cột tiền hàng. Lỗi thiết kế câu hỏi.
- m11 (p2, p4): cùng tập (tên, điểm) với gold; chỉ khác thứ tự ba danh mục cùng điểm 4.23. Lỗi thiết kế câu hỏi (thiếu luật khi bằng nhau).
- h10 (p0, p2, p4): ĐÍNH CHÍNH nhận định trước đó (đã nghi là lỗi nhân dòng thật). Cả p0 và p2 đếm đúng theo đơn (DISTINCT) và cho
  tỉ lệ GIỐNG gold; chỉ bị chấm sai vì trả thêm cột category_id (câu hỏi không nêu cột cần trả về). Lỗi thiết kế câu hỏi, không phải lỗi agent,
  và critic không bắt sai vì không có gì sai.
Sửa: h10 nay ghi "Trả về tên danh mục gốc và tỉ lệ." Gold không đổi.

Hệ quả: cả 3 câu sai trên test của cả 3 cấu hình đều là lỗi thiết kế bộ eval; giá trị agent trả về đúng ở 25/25 câu trả lời được.
Số chính thức đã báo cáo vẫn là 23/25 (chạy bằng bộ chấm và lời hỏi tại thời điểm chạy); 25/25 là kết quả post-hoc sau khi xác minh bằng SQL.
Câu trong phần "post-hoc: 22/23" ở mục trước được thay bằng kết quả này.

Còn 12 câu có gold nhiều cột mà lời hỏi không nêu cột cần trả về (xem `scripts/audit_eval.py`). Tất cả đều đã đạt ở mọi cấu hình đã chạy
(trừ m11 ở trên), nên giữ nguyên để không tiếp tục chỉnh bộ eval; ghi trong phần hạn chế của README.
