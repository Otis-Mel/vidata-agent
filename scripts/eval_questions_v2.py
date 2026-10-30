"""Đợt câu hỏi thứ hai (n01-n36, a07-a12, o07-o12): 48 câu mới, nâng bộ eval lên 101 câu.

Nguyên tắc viết (rút ra từ các lần sửa trước, xem eval/CHANGELOG.md):
  - Mọi cột thời gian ghi rõ định dạng (tháng = YYYY-MM, thứ = ISO 1..7).
  - Mọi kết quả cần làm tròn đều ghi rõ số chữ số; tỉ lệ ghi rõ "phần trăm".
  - Câu top-N luôn có luật xử lý khi bằng nhau.
  - KHÔNG ghi yêu cầu sắp xếp (bộ chấm không so thứ tự dòng trừ khi câu hỏi có chữ "xếp").
  - Viết TRƯỚC khi chạy bất kỳ agent nào trên các câu này.
Quy ước chung: "giờ Việt Nam" = order_ts (UTC) + 7 giờ; "tiền hàng" = SUM(quantity * unit_price).
"""

VN = "(o.order_ts + INTERVAL 7 HOUR)"
HCM = "('TP. Hồ Chí Minh','HCM','TP.HCM','Sài Gòn','Ho Chi Minh')"
HN = "('Hà Nội','HN','Ha Noi','Hanoi')"
PROV = ("WITH n AS (SELECT customer_id, CASE WHEN province IN " + HCM + " THEN 'TP. Hồ Chí Minh' "
        "WHEN province IN " + HN + " THEN 'Hà Nội' ELSE province END AS prov FROM customers)")
GOODS_PER_ORDER = "g AS (SELECT order_id, SUM(quantity*unit_price) AS goods FROM order_items GROUP BY order_id)"
ROOT_JOIN = ("JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id "
             "JOIN categories c ON c.category_id=p.category_id JOIN categories rc ON rc.category_id=c.parent_id")

# (id, difficulty, question, gold_sql, traps)
ANSWERABLE_V2 = [
    ("n01", "hard", "Với các đơn hoàn thành, tổng tiền hàng và tổng phí ship theo từng hãng vận chuyển (bảng shipments). Trả về carrier, tổng tiền hàng, tổng phí ship.",
     "WITH " + GOODS_PER_ORDER + " SELECT s.carrier, SUM(g.goods) AS tien_hang, SUM(o.shipping_fee) AS phi_ship FROM orders o "
     "JOIN shipments s ON s.order_id=o.order_id JOIN g ON g.order_id=o.order_id WHERE o.status='completed' GROUP BY s.carrier",
     ["join_fanout", "status_filter"]),
    ("n02", "hard", "Với các đơn hoàn thành, số đơn và tổng tiền hàng theo từng phương thức thanh toán (đơn chia nhiều phương thức thì tính cho từng phương thức). Trả về phương thức, số đơn, tổng tiền hàng.",
     "WITH " + GOODS_PER_ORDER + ", m AS (SELECT DISTINCT order_id, method FROM payments) SELECT m.method, COUNT(*) AS so_don, SUM(g.goods) AS tien_hang "
     "FROM orders o JOIN g ON g.order_id=o.order_id JOIN m ON m.order_id=o.order_id WHERE o.status='completed' GROUP BY m.method",
     ["join_fanout", "status_filter"]),
    ("n03", "medium", "Có bao nhiêu đơn hoàn thành được thanh toán bằng từ 2 phương thức khác nhau trở lên?",
     "SELECT COUNT(*) FROM (SELECT p.order_id FROM payments p JOIN orders o ON o.order_id=p.order_id WHERE o.status='completed' "
     "GROUP BY p.order_id HAVING COUNT(DISTINCT p.method)>=2)", ["multi_payment", "status_filter"]),
    ("n04", "hard", "Số đơn hoàn thành theo từng thứ trong tuần (giờ Việt Nam), dùng thứ ISO: 1 = Thứ Hai, ..., 7 = Chủ Nhật. Trả về thứ và số đơn.",
     "SELECT ISODOW(" + VN + ") AS thu, COUNT(*) AS so_don FROM orders o WHERE o.status='completed' GROUP BY 1", ["timezone", "status_filter"]),
    ("n05", "medium", "Giờ nào trong ngày (0-23, giờ Việt Nam) có nhiều đơn hoàn thành nhất trong toàn bộ dữ liệu? Trả về giờ và số đơn; nếu bằng nhau lấy giờ nhỏ hơn.",
     "SELECT HOUR(" + VN + ") AS gio, COUNT(*) AS so_don FROM orders o WHERE o.status='completed' GROUP BY 1 ORDER BY so_don DESC, gio LIMIT 1",
     ["timezone", "status_filter"]),
    ("n06", "medium", "Có bao nhiêu đơn hoàn thành được đặt từ 18:00 đến 23:59 giờ Việt Nam trong ngày 12/12/2025?",
     "SELECT COUNT(*) FROM orders o WHERE o.status='completed' AND CAST(" + VN + " AS DATE)=DATE '2025-12-12' AND HOUR(" + VN + ")>=18",
     ["timezone", "status_filter"]),
    ("n07", "hard", "Số khách hàng mới theo từng tháng của năm 2025 (giờ Việt Nam). Khách mới của một tháng là khách có đơn hoàn thành đầu tiên rơi vào tháng đó. Trả về tháng dạng YYYY-MM và số khách mới.",
     "WITH f AS (SELECT customer_id, MIN(order_ts + INTERVAL 7 HOUR) AS first_ts FROM orders WHERE status='completed' GROUP BY customer_id) "
     "SELECT STRFTIME(first_ts, '%Y-%m') AS thang, COUNT(*) AS so_khach FROM f WHERE YEAR(first_ts)=2025 GROUP BY 1",
     ["timezone", "cohort", "status_filter"]),
    ("n08", "hard", "Trong nhóm khách có đơn hoàn thành ĐẦU TIÊN vào tháng 5/2025 (giờ Việt Nam), bao nhiêu phần trăm có thêm ít nhất 1 đơn hoàn thành khác trong vòng 30 ngày kể từ thời điểm đơn hoàn thành đầu tiên? Làm tròn 2 chữ số.",
     "WITH oc AS (SELECT customer_id, order_ts + INTERVAL 7 HOUR AS ts FROM orders WHERE status='completed'), "
     "f AS (SELECT customer_id, MIN(ts) AS first_ts FROM oc GROUP BY customer_id), "
     "coh AS (SELECT customer_id, first_ts FROM f WHERE CAST(DATE_TRUNC('month', first_ts) AS DATE)=DATE '2025-05-01') "
     "SELECT ROUND(100.0*SUM(CASE WHEN EXISTS (SELECT 1 FROM oc WHERE oc.customer_id=coh.customer_id AND oc.ts>coh.first_ts "
     "AND oc.ts<=coh.first_ts + INTERVAL 30 DAY) THEN 1 ELSE 0 END)/COUNT(*),2) FROM coh", ["timezone", "cohort"]),
    ("n09", "hard", "Tiền hàng của đơn hoàn thành theo từng tháng trong năm 2025 (giờ Việt Nam) và tiền hàng lũy kế từ tháng 1 đến tháng đó. Trả về tháng dạng YYYY-MM, tiền hàng của tháng, tiền hàng lũy kế.",
     "WITH m AS (SELECT STRFTIME(" + VN + ", '%Y-%m') AS thang, SUM(oi.quantity*oi.unit_price) AS dt FROM orders o "
     "JOIN order_items oi ON oi.order_id=o.order_id WHERE o.status='completed' AND YEAR(" + VN + ")=2025 GROUP BY 1) "
     "SELECT thang, dt, SUM(dt) OVER (ORDER BY thang) AS luy_ke FROM m", ["timezone", "window_function", "status_filter"]),
    ("n10", "hard", "Trong từng tháng của quý 4/2025 (giờ Việt Nam), 3 sản phẩm (product_id) có tiền hàng cao nhất từ các đơn hoàn thành; nếu bằng nhau lấy product_id nhỏ hơn. Trả về tháng dạng YYYY-MM, product_id, tiền hàng.",
     "WITH s AS (SELECT STRFTIME(" + VN + ", '%Y-%m') AS thang, oi.product_id, SUM(oi.quantity*oi.unit_price) AS dt FROM orders o "
     "JOIN order_items oi ON oi.order_id=o.order_id WHERE o.status='completed' AND CAST(" + VN + " AS DATE) BETWEEN DATE '2025-10-01' AND DATE '2025-12-31' GROUP BY 1, 2), "
     "k AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY thang ORDER BY dt DESC, product_id) AS rn FROM s) SELECT thang, product_id, dt FROM k WHERE rn<=3",
     ["timezone", "window_function", "status_filter"]),
    ("n11", "hard", "Tiền hàng của đơn hoàn thành theo từng danh mục gốc (tên danh mục gốc) trong toàn bộ dữ liệu, kèm tỉ trọng phần trăm trên tổng tiền hàng của các danh mục, làm tròn 2 chữ số.",
     "WITH r AS (SELECT rc.name_vi AS root, SUM(oi.quantity*oi.unit_price) AS dt FROM orders o " + ROOT_JOIN + " WHERE o.status='completed' GROUP BY rc.name_vi) "
     "SELECT root, dt, ROUND(100.0*dt/SUM(dt) OVER (), 2) AS ty_trong FROM r", ["window_function", "status_filter"]),
    ("n12", "hard", "Với mỗi danh mục gốc, shop (seller_id) có tiền hàng cao nhất từ các đơn hoàn thành; nếu bằng nhau lấy seller_id nhỏ hơn. Trả về tên danh mục gốc, seller_id, tiền hàng.",
     "WITH s AS (SELECT rc.name_vi AS root, p.seller_id, SUM(oi.quantity*oi.unit_price) AS dt FROM orders o " + ROOT_JOIN + " WHERE o.status='completed' GROUP BY rc.name_vi, p.seller_id), "
     "k AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY root ORDER BY dt DESC, seller_id) AS rn FROM s) SELECT root, seller_id, dt FROM k WHERE rn=1",
     ["window_function", "status_filter"]),
    ("n13", "hard", "Có bao nhiêu khách hàng đã có đơn hoàn thành chứa sản phẩm thuộc cả hai danh mục gốc 'Thời trang nữ' và 'Mẹ & Bé' (không nhất thiết trong cùng một đơn)?",
     "WITH cc AS (SELECT DISTINCT o.customer_id, rc.name_vi AS root FROM orders o " + ROOT_JOIN + " WHERE o.status='completed') "
     "SELECT COUNT(*) FROM (SELECT customer_id FROM cc WHERE root IN ('Thời trang nữ','Mẹ & Bé') GROUP BY customer_id HAVING COUNT(DISTINCT root)=2)",
     ["multi_step", "status_filter"]),
    ("n14", "medium", "5 khách hàng (customer_id) có tổng tiền hàng từ đơn hoàn thành cao nhất; nếu bằng nhau lấy customer_id nhỏ hơn. Trả về customer_id và tổng tiền hàng.",
     "SELECT o.customer_id, SUM(oi.quantity*oi.unit_price) AS tong FROM orders o JOIN order_items oi ON oi.order_id=o.order_id "
     "WHERE o.status='completed' GROUP BY o.customer_id ORDER BY tong DESC, o.customer_id LIMIT 5", ["status_filter"]),
    ("n15", "hard", "Số ngày trung bình giữa hai đơn hoàn thành liên tiếp của cùng một khách (tính trên tất cả các cặp đơn liên tiếp của mọi khách), theo ngày lịch giờ Việt Nam, làm tròn 2 chữ số.",
     "WITH oc AS (SELECT customer_id, order_id, CAST(order_ts + INTERVAL 7 HOUR AS DATE) AS d FROM orders WHERE status='completed'), "
     "x AS (SELECT DATE_DIFF('day', LAG(d) OVER (PARTITION BY customer_id ORDER BY d, order_id), d) AS diff FROM oc) "
     "SELECT ROUND(AVG(diff), 2) FROM x WHERE diff IS NOT NULL", ["timezone", "window_function", "status_filter"]),
    ("n16", "hard", "Tổng số tiền giảm giá từ voucher của các đơn hoàn thành trong năm 2025 (giờ Việt Nam). Voucher percent giảm tiền hàng * value / 100 (làm tròn xuống đồng), voucher fixed giảm đúng value đồng, và mức giảm không vượt quá tiền hàng của đơn.",
     "WITH " + GOODS_PER_ORDER + " SELECT SUM(LEAST(CASE WHEN v.discount_type='percent' THEN CAST(FLOOR(g.goods*v.value/100.0) AS BIGINT) ELSE v.value END, g.goods)) "
     "FROM orders o JOIN g ON g.order_id=o.order_id JOIN vouchers v ON v.voucher_id=o.voucher_id WHERE o.status='completed' AND YEAR(" + VN + ")=2025",
     ["timezone", "multi_step", "status_filter"]),
    ("n17", "medium", "5 mã voucher (code) được dùng nhiều nhất trong các đơn không bị hủy của năm 2025 (giờ Việt Nam); nếu bằng nhau lấy code theo thứ tự chữ cái. Trả về code và số đơn.",
     "SELECT v.code, COUNT(*) AS so_don FROM orders o JOIN vouchers v ON v.voucher_id=o.voucher_id WHERE o.status<>'cancelled' AND YEAR(" + VN + ")=2025 "
     "GROUP BY v.code ORDER BY so_don DESC, v.code LIMIT 5", ["timezone", "status_filter"]),
    ("n18", "medium", "Phí ship trung bình (làm tròn 0 chữ số) của đơn hoàn thành theo 3 nhóm tiền hàng: 'duoi_200k' (dưới 200.000), '200k_500k' (từ 200.000 đến 500.000), 'tren_500k' (trên 500.000). Trả về nhóm và phí ship trung bình.",
     "WITH " + GOODS_PER_ORDER + " SELECT CASE WHEN g.goods<200000 THEN 'duoi_200k' WHEN g.goods<=500000 THEN '200k_500k' ELSE 'tren_500k' END AS nhom, "
     "ROUND(AVG(o.shipping_fee),0) AS phi_ship_tb FROM orders o JOIN g ON g.order_id=o.order_id WHERE o.status='completed' GROUP BY 1", ["status_filter", "bucketing"]),
    ("n19", "hard", "Có bao nhiêu sản phẩm đã từng được bán mà giá lúc mua trung bình (trung bình unit_price trên các dòng order_items của sản phẩm) thấp hơn giá niêm yết hiện tại (products.price) hơn 10%?",
     "SELECT COUNT(*) FROM (SELECT p.product_id FROM products p JOIN order_items oi ON oi.product_id=p.product_id GROUP BY p.product_id, p.price HAVING AVG(oi.unit_price) < 0.9*p.price)",
     ["price_at_purchase"]),
    ("n20", "hard", "Trong các shop có ít nhất 100 đơn đã giao xong (completed + returned; đếm số đơn khác nhau có chứa sản phẩm của shop), shop nào có tỉ lệ phần trăm đơn bị hoàn trả (returned) cao nhất? Trả về seller_id và tỉ lệ làm tròn 2 chữ số; nếu bằng nhau lấy seller_id nhỏ hơn.",
     "WITH so AS (SELECT DISTINCT p.seller_id, o.order_id, o.status FROM orders o JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id "
     "WHERE o.status IN ('completed','returned')) SELECT seller_id, ROUND(100.0*SUM(CASE WHEN status='returned' THEN 1 ELSE 0 END)/COUNT(*),2) AS ty_le FROM so "
     "GROUP BY seller_id HAVING COUNT(*)>=100 ORDER BY SUM(CASE WHEN status='returned' THEN 1 ELSE 0 END)*1.0/COUNT(*) DESC, seller_id LIMIT 1",
     ["denominator_definition", "join_fanout"]),
    ("n21", "medium", "Bao nhiêu phần trăm đơn hoàn thành có ít nhất 1 review (review gắn với dòng sản phẩm của đơn)? Làm tròn 2 chữ số.",
     "SELECT ROUND(100.0*COUNT(DISTINCT CASE WHEN rv.review_id IS NOT NULL THEN o.order_id END)/COUNT(DISTINCT o.order_id),2) FROM orders o "
     "JOIN order_items oi ON oi.order_id=o.order_id LEFT JOIN reviews rv ON rv.order_item_id=oi.order_item_id WHERE o.status='completed'", ["join_fanout", "status_filter"]),
    ("n22", "hard", "Với khách ở Hà Nội và khách ở TP. Hồ Chí Minh (gộp mọi cách ghi tên của hai thành phố này): số khách có ít nhất 1 đơn hoàn thành và tổng tiền hàng của họ từ các đơn hoàn thành. Trả về tên chuẩn ('Hà Nội' hoặc 'TP. Hồ Chí Minh'), số khách, tổng tiền hàng.",
     PROV + ", " + GOODS_PER_ORDER + " SELECT n.prov, COUNT(DISTINCT o.customer_id) AS so_khach, SUM(g.goods) AS tien_hang FROM orders o JOIN n ON n.customer_id=o.customer_id "
     "JOIN g ON g.order_id=o.order_id WHERE o.status='completed' AND n.prov IN ('Hà Nội','TP. Hồ Chí Minh') GROUP BY n.prov", ["province_variants", "join_fanout", "status_filter"]),
    ("n23", "hard", "Thời gian giao trung bình (số ngày thập phân = số giờ từ shipped_ts đến delivered_ts chia 24, làm tròn 2 chữ số) của 3 tỉnh/thành (theo tỉnh của khách, gộp các cách ghi tên) có nhiều đơn giao thành công nhất (shipments.status = delivered); nếu bằng nhau lấy tên tỉnh theo thứ tự chữ cái. Trả về tỉnh/thành, số đơn, thời gian giao trung bình.",
     PROV + " SELECT n.prov, COUNT(*) AS so_don, ROUND(AVG(DATE_DIFF('hour', s.shipped_ts, s.delivered_ts))/24.0, 2) AS ngay_tb FROM shipments s "
     "JOIN orders o ON o.order_id=s.order_id JOIN n ON n.customer_id=o.customer_id WHERE s.status='delivered' GROUP BY n.prov ORDER BY so_don DESC, n.prov LIMIT 3",
     ["province_variants"]),
    ("n24", "hard", "Tháng nào (dạng YYYY-MM, giờ Việt Nam) có nhiều đơn bị hủy nhất? Trả về tháng và số đơn hủy; nếu bằng nhau lấy tháng sớm hơn.",
     "SELECT STRFTIME(" + VN + ", '%Y-%m') AS thang, COUNT(*) AS so_don FROM orders o WHERE o.status='cancelled' GROUP BY 1 ORDER BY so_don DESC, thang LIMIT 1", ["timezone"]),
    ("n25", "medium", "Tổng phí ship của các đơn hoàn thành đặt trong tháng 11/2025 (giờ Việt Nam).",
     "SELECT SUM(o.shipping_fee) FROM orders o WHERE o.status='completed' AND YEAR(" + VN + ")=2025 AND MONTH(" + VN + ")=11", ["timezone", "status_filter"]),
    ("n26", "medium", "Tỉ lệ phần trăm review 1-2 sao theo từng hãng vận chuyển (review gắn với đơn qua order_items, hãng vận chuyển qua shipments), làm tròn 2 chữ số. Trả về carrier và tỉ lệ.",
     "SELECT s.carrier, ROUND(100.0*SUM(CASE WHEN rv.rating<=2 THEN 1 ELSE 0 END)/COUNT(*),2) AS ty_le FROM reviews rv "
     "JOIN order_items oi ON oi.order_item_id=rv.order_item_id JOIN shipments s ON s.order_id=oi.order_id GROUP BY s.carrier", []),
    ("n27", "hard", "Có bao nhiêu đơn hoàn thành có tiền hàng cao hơn mức tiền hàng trung bình của toàn bộ các đơn hoàn thành?",
     "WITH g AS (SELECT o.order_id, SUM(oi.quantity*oi.unit_price) AS goods FROM orders o JOIN order_items oi ON oi.order_id=o.order_id WHERE o.status='completed' GROUP BY o.order_id) "
     "SELECT COUNT(*) FROM g WHERE goods > (SELECT AVG(goods) FROM g)", ["multi_step", "status_filter"]),
    ("n28", "medium", "Trung vị (median) tiền hàng của một đơn hoàn thành đặt trong năm 2025 (giờ Việt Nam), làm tròn 0 chữ số.",
     "WITH g AS (SELECT o.order_id, SUM(oi.quantity*oi.unit_price) AS goods FROM orders o JOIN order_items oi ON oi.order_id=o.order_id "
     "WHERE o.status='completed' AND YEAR(" + VN + ")=2025 GROUP BY o.order_id) SELECT ROUND(MEDIAN(goods), 0) FROM g", ["timezone", "status_filter"]),
    ("n29", "hard", "Có bao nhiêu khách có đơn hoàn thành đầu tiên vào năm 2024 (giờ Việt Nam) và vẫn có ít nhất 1 đơn hoàn thành trong năm 2026 (giờ Việt Nam)?",
     "WITH oc AS (SELECT customer_id, order_ts + INTERVAL 7 HOUR AS ts FROM orders WHERE status='completed'), f AS (SELECT customer_id, MIN(ts) AS first_ts FROM oc GROUP BY customer_id) "
     "SELECT COUNT(*) FROM f WHERE YEAR(first_ts)=2024 AND EXISTS (SELECT 1 FROM oc WHERE oc.customer_id=f.customer_id AND YEAR(oc.ts)=2026)", ["timezone", "cohort"]),
    ("n30", "easy", "Có tất cả bao nhiêu review 5 sao?", "SELECT COUNT(*) FROM reviews WHERE rating=5", []),
    ("n31", "easy", "Có bao nhiêu shop đã đăng ít nhất một sản phẩm?", "SELECT COUNT(DISTINCT seller_id) FROM products", []),
    ("n32", "easy", "Voucher giảm cố định (fixed) có mức giảm cao nhất là voucher nào? Trả về code và mức giảm; nếu bằng nhau lấy code theo thứ tự chữ cái.",
     "SELECT code, value FROM vouchers WHERE discount_type='fixed' ORDER BY value DESC, code LIMIT 1", []),
    ("n33", "medium", "Có bao nhiêu đơn đang giao (status = delivering) được đặt trước ngày 25/09/2026 theo giờ Việt Nam?",
     "SELECT COUNT(*) FROM orders o WHERE o.status='delivering' AND CAST(" + VN + " AS DATE) < DATE '2026-09-25'", ["timezone"]),
    ("n34", "medium", "Tiền hàng trung bình của một dòng sản phẩm (quantity * unit_price) trong order_items theo từng danh mục gốc (tên danh mục gốc), làm tròn 0 chữ số, tính trên tất cả các dòng.",
     "SELECT rc.name_vi, ROUND(AVG(oi.quantity*oi.unit_price), 0) AS tb FROM order_items oi JOIN products p ON p.product_id=oi.product_id "
     "JOIN categories c ON c.category_id=p.category_id JOIN categories rc ON rc.category_id=c.parent_id GROUP BY rc.name_vi", []),
    ("n35", "medium", "Trong các đơn hoàn thành đặt năm 2025 (giờ Việt Nam), bao nhiêu phần trăm đơn có ít nhất một dòng thanh toán bằng COD? Làm tròn 2 chữ số.",
     "SELECT ROUND(100.0*COUNT(DISTINCT CASE WHEN p.method='COD' THEN o.order_id END)/COUNT(DISTINCT o.order_id), 2) FROM orders o JOIN payments p ON p.order_id=o.order_id "
     "WHERE o.status='completed' AND YEAR(" + VN + ")=2025", ["join_fanout", "timezone", "status_filter"]),
    ("n36", "medium", "Có bao nhiêu khách hàng có tên tỉnh ghi theo một cách KHÔNG chuẩn của Hà Nội hoặc TP. Hồ Chí Minh (tức là các cách ghi khác 'Hà Nội' và 'TP. Hồ Chí Minh' nhưng vẫn là hai thành phố này)?",
     "SELECT COUNT(*) FROM customers WHERE province IN ('HCM','TP.HCM','Sài Gòn','Ho Chi Minh','HN','Ha Noi','Hanoi')", ["province_variants"]),
]

AMBIGUOUS_V2 = [
    ("a07", "Tháng nào bán tốt nhất?", "Tiêu chí 'tốt nhất' (doanh thu, số đơn, lợi nhuận?) và phạm vi thời gian đều không rõ."),
    ("a08", "Có bao nhiêu khách hàng mới trong tuần này?", "'Khách mới' là mới đăng ký hay mới mua đơn đầu? 'Tuần này' tính từ mốc nào?"),
    ("a09", "Tỉ lệ hoàn đơn là bao nhiêu?", "Mẫu số (mọi đơn hay đơn đã giao), khoảng thời gian, hủy có tính là hoàn không?"),
    ("a10", "Hãng vận chuyển nào tốt nhất?", "'Tốt nhất' theo tốc độ, tỉ lệ giao thành công hay đánh giá?"),
    ("a11", "Sản phẩm nào đang có vấn đề?", "'Có vấn đề' không được định nghĩa (đánh giá thấp, hoàn trả nhiều, bán chậm?)."),
    ("a12", "Doanh thu của Hà Nội so với TP.HCM như thế nào?", "Doanh thu gross/net, kỳ nào, tính theo tỉnh khách hay tỉnh shop?"),
]

OUT_OF_SCOPE_V2 = [
    ("o07", "Tỉ lệ khách quay lại mua hàng theo từng kênh marketing (Facebook, Google, TikTok) là bao nhiêu?", "Không có dữ liệu kênh marketing/nguồn truy cập."),
    ("o08", "Số lượng tồn kho hiện tại của 10 sản phẩm bán chạy nhất là bao nhiêu?", "Không có dữ liệu tồn kho."),
    ("o09", "Thời gian trung bình khách xem trang sản phẩm trước khi đặt hàng là bao lâu?", "Không có dữ liệu hành vi duyệt web."),
    ("o10", "Những từ khóa nào xuất hiện nhiều nhất trong nội dung các review?", "Bảng reviews chỉ có số sao, không có nội dung bình luận."),
    ("o11", "Độ tuổi trung bình của khách hàng là bao nhiêu?", "Không có ngày sinh hay tuổi."),
    ("o12", "Doanh thu chia theo thiết bị đặt hàng (iOS, Android, web) là bao nhiêu?", "Không có dữ liệu thiết bị."),
]
