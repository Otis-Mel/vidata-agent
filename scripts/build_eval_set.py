"""Dựng eval/questions.jsonl = 9 câu mẫu + câu mới, kiểm tra mọi gold SQL chạy được.

Quy ước (ghi rõ trong câu hỏi để đáp án chuẩn không mơ hồ):
  - "giờ Việt Nam" = order_ts (UTC) + 7 giờ
  - "tiền hàng" = SUM(quantity * unit_price), chưa gồm phí ship, chưa trừ voucher
  - "doanh thu" trong gold chỉ tính đơn status = 'completed' khi câu hỏi nói "đơn hoàn thành"
Chạy:  python scripts/build_eval_set.py   (sau khi sửa/thêm câu, chạy lại để kiểm tra)
Chia split: cứ 3 câu thì 1 câu vào "test" (cố định, không đổi). Tune prompt trên dev, báo cáo trên test.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.db import run_sql  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_questions_v2 import AMBIGUOUS_V2, ANSWERABLE_V2, OUT_OF_SCOPE_V2  # noqa: E402

VN = "(o.order_ts + INTERVAL 7 HOUR)"
HCM = "('TP. Hồ Chí Minh','HCM','TP.HCM','Sài Gòn','Ho Chi Minh')"
HN = "('Hà Nội','HN','Ha Noi','Hanoi')"
PROV = ("WITH n AS (SELECT customer_id, CASE WHEN province IN " + HCM + " THEN 'TP. Hồ Chí Minh' "
        "WHEN province IN " + HN + " THEN 'Hà Nội' ELSE province END AS prov FROM customers)")
GOODS = "SUM(oi.quantity*oi.unit_price)"

# (id, difficulty, question, gold_sql, traps)
ANSWERABLE = [
    ("e03", "easy", "Hệ thống hiện có tổng cộng bao nhiêu sản phẩm?", "SELECT COUNT(*) FROM products", []),
    ("e04", "easy", "Có bao nhiêu shop là shop Mall?", "SELECT COUNT(*) FROM sellers WHERE is_mall", []),
    ("e05", "easy", "Giá niêm yết cao nhất của một sản phẩm là bao nhiêu đồng?", "SELECT MAX(price) FROM products", []),
    ("e06", "easy", "Có bao nhiêu voucher giảm theo phần trăm?", "SELECT COUNT(*) FROM vouchers WHERE discount_type='percent'", []),
    ("e07", "easy", "Điểm đánh giá trung bình (số sao) của tất cả các review là bao nhiêu?", "SELECT AVG(rating) FROM reviews", []),
    ("e08", "easy", "Hiện có bao nhiêu đơn hàng đang trong trạng thái đang giao?", "SELECT COUNT(*) FROM orders WHERE status='delivering'", []),
    ("e09", "easy", "Có bao nhiêu danh mục gốc (không có danh mục cha)?", "SELECT COUNT(*) FROM categories WHERE parent_id IS NULL", []),

    ("m04", "medium", "Mỗi hãng vận chuyển đã giao thành công (shipment status = delivered) bao nhiêu đơn? Xếp giảm dần theo số đơn.",
     "SELECT carrier, COUNT(*) AS n FROM shipments WHERE status='delivered' GROUP BY carrier ORDER BY n DESC, carrier", []),
    ("m05", "medium", "5 danh mục con có tiền hàng cao nhất trong các đơn hoàn thành. Trả về category_id, tên danh mục và tiền hàng.",
     "SELECT c.category_id, c.name_vi, " + GOODS + " AS rev FROM orders o JOIN order_items oi ON oi.order_id=o.order_id "
     "JOIN products p ON p.product_id=oi.product_id JOIN categories c ON c.category_id=p.category_id "
     "WHERE o.status='completed' GROUP BY c.category_id, c.name_vi ORDER BY rev DESC, c.category_id LIMIT 5", ["status_filter"]),
    ("m06", "medium", "Có bao nhiêu đơn hoàn thành được đặt trong ngày 11/11/2025 theo giờ Việt Nam?",
     "SELECT COUNT(*) FROM orders o WHERE o.status='completed' AND CAST(" + VN + " AS DATE)=DATE '2025-11-11'", ["timezone", "status_filter"]),
    ("m07", "medium", "Trong năm 2025 (giờ Việt Nam), có bao nhiêu đơn (mọi trạng thái) được đặt trong khung 20:00 đến 22:59?",
     "SELECT COUNT(*) FROM orders o WHERE YEAR(" + VN + ")=2025 AND HOUR(" + VN + ") BETWEEN 20 AND 22", ["timezone"]),
    ("m08", "medium", "Có bao nhiêu khách hàng ở TP. Hồ Chí Minh (tính cả các cách ghi tên khác của thành phố này)?",
     "SELECT COUNT(*) FROM customers WHERE province IN " + HCM, ["province_variants"]),
    ("m09", "medium", "Có bao nhiêu khách hàng ở Hà Nội (tính cả các cách ghi tên khác)?",
     "SELECT COUNT(*) FROM customers WHERE province IN " + HN, ["province_variants"]),
    ("m10", "medium", "Trong năm 2025 (giờ Việt Nam), tỉ lệ phần trăm đơn bị hủy trên tổng số đơn đã có kết quả cuối (completed, cancelled, returned) là bao nhiêu? Làm tròn 2 chữ số.",
     "SELECT ROUND(100.0*SUM(CASE WHEN o.status='cancelled' THEN 1 ELSE 0 END)/COUNT(*),2) FROM orders o "
     "WHERE o.status IN ('completed','cancelled','returned') AND YEAR(" + VN + ")=2025", ["timezone", "denominator_definition"]),
    ("m11", "medium", "Điểm đánh giá trung bình theo từng danh mục gốc (tên danh mục gốc), làm tròn 2 chữ số, xếp giảm dần theo điểm đã làm tròn; nếu bằng nhau xếp theo tên danh mục theo thứ tự chữ cái.",
     "SELECT r.name_vi, ROUND(AVG(rv.rating),2) AS avg_rating FROM reviews rv "
     "JOIN order_items oi ON oi.order_item_id=rv.order_item_id JOIN products p ON p.product_id=oi.product_id "
     "JOIN categories c ON c.category_id=p.category_id JOIN categories r ON r.category_id=c.parent_id "
     "GROUP BY r.name_vi ORDER BY avg_rating DESC, r.name_vi", []),
    ("m12", "medium", "Trong năm 2026 (giờ Việt Nam), có bao nhiêu đơn không bị hủy có áp dụng voucher?",
     "SELECT COUNT(*) FROM orders o WHERE o.voucher_id IS NOT NULL AND o.status<>'cancelled' AND YEAR(" + VN + ")=2026", ["timezone", "status_filter"]),
    ("m13", "medium", "10 shop (seller_id) bán được nhiều sản phẩm nhất (tổng quantity) trong các đơn hoàn thành. Nếu bằng nhau lấy seller_id nhỏ hơn.",
     "SELECT p.seller_id, SUM(oi.quantity) AS qty FROM orders o JOIN order_items oi ON oi.order_id=o.order_id "
     "JOIN products p ON p.product_id=oi.product_id WHERE o.status='completed' GROUP BY p.seller_id ORDER BY qty DESC, p.seller_id LIMIT 10", ["status_filter"]),
    ("m14", "medium", "Thời gian giao trung bình của từng hãng vận chuyển cho các đơn đã giao thành công, tính bằng số ngày thập phân (= số giờ từ shipped_ts đến delivered_ts chia 24), làm tròn 2 chữ số.",
     "SELECT carrier, ROUND(AVG(DATE_DIFF('hour', shipped_ts, delivered_ts))/24.0,2) AS avg_days FROM shipments "
     "WHERE status='delivered' GROUP BY carrier ORDER BY carrier", []),
    ("m15", "medium", "Có bao nhiêu khách hàng có đúng 1 đơn hoàn thành?",
     "SELECT COUNT(*) FROM (SELECT customer_id FROM orders WHERE status='completed' GROUP BY customer_id HAVING COUNT(*)=1)", ["status_filter"]),
    ("m16", "medium", "Phí ship trung bình của đơn hoàn thành theo từng năm (giờ Việt Nam), làm tròn 0 chữ số.",
     "SELECT YEAR(" + VN + ") AS nam, ROUND(AVG(o.shipping_fee),0) AS phi_ship_tb FROM orders o WHERE o.status='completed' GROUP BY 1 ORDER BY 1", ["timezone", "status_filter"]),
    ("m17", "medium", "Có bao nhiêu sản phẩm chưa từng được bán (không xuất hiện trong order_items)?",
     "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.product_id=p.product_id)", []),
    ("m18", "medium", "Có bao nhiêu khách hàng đã đăng ký nhưng chưa từng đặt đơn nào (mọi trạng thái)?",
     "SELECT COUNT(*) FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id=c.customer_id)", []),

    ("h03", "hard", "Theo từng tháng của năm 2025 (giờ Việt Nam), với các đơn hoàn thành: tổng tiền hàng và tổng số tiền thu thành công (payments.status = paid). Cột tháng trả về dạng YYYY-MM.",
     "WITH g AS (SELECT order_id, SUM(quantity*unit_price) AS goods FROM order_items GROUP BY order_id), "
     "pay AS (SELECT order_id, SUM(amount) AS paid FROM payments WHERE status='paid' GROUP BY order_id) "
     "SELECT DATE_TRUNC('month', " + VN + ") AS thang, SUM(g.goods) AS tien_hang, SUM(pay.paid) AS da_thu "
     "FROM orders o JOIN g ON g.order_id=o.order_id LEFT JOIN pay ON pay.order_id=o.order_id "
     "WHERE o.status='completed' AND YEAR(" + VN + ")=2025 GROUP BY 1 ORDER BY 1", ["join_fanout", "timezone", "status_filter"]),
    ("h04", "hard", "Trong số khách có ít nhất 1 đơn hoàn thành, bao nhiêu phần trăm có từ 2 đơn hoàn thành trở lên? Làm tròn 2 chữ số.",
     "WITH c AS (SELECT customer_id, COUNT(*) AS n FROM orders WHERE status='completed' GROUP BY customer_id) "
     "SELECT ROUND(100.0*SUM(CASE WHEN n>=2 THEN 1 ELSE 0 END)/COUNT(*),2) FROM c", ["status_filter"]),
    ("h05", "hard", "Với các đơn hoàn thành trong năm 2025 (giờ Việt Nam), trả về số quý (1-4), tiền hàng của quý đó và phần trăm tăng trưởng so với quý liền trước làm tròn 2 chữ số. Chỉ xét các quý trong năm 2025 nên quý 1 có tăng trưởng NULL.",
     "WITH q AS (SELECT DATE_TRUNC('quarter', " + VN + ") AS quy, " + GOODS + " AS dt FROM orders o "
     "JOIN order_items oi ON oi.order_id=o.order_id WHERE o.status='completed' GROUP BY 1) "
     "SELECT EXTRACT(QUARTER FROM quy) AS quy_so, dt, ROUND(100.0*(dt-LAG(dt) OVER (ORDER BY quy))/LAG(dt) OVER (ORDER BY quy),2) AS tang_truong_pct "
     "FROM q WHERE YEAR(quy)=2025 ORDER BY quy", ["timezone", "window_function", "status_filter"]),
    ("h06", "hard", "5 tỉnh/thành của khách hàng (theo tỉnh ghi trong hồ sơ khách hàng) có tiền hàng cao nhất từ các đơn hoàn thành, gộp các cách ghi tên khác nhau của cùng một tỉnh.",
     PROV + " SELECT n.prov, " + GOODS + " AS dt FROM orders o JOIN n ON n.customer_id=o.customer_id "
     "JOIN order_items oi ON oi.order_id=o.order_id WHERE o.status='completed' GROUP BY n.prov ORDER BY dt DESC, n.prov LIMIT 5",
     ["province_variants", "status_filter"]),
    ("h07", "hard", "Với mỗi danh mục gốc, 3 sản phẩm (product_id) bán nhiều nhất theo tổng quantity trong đơn hoàn thành. Nếu bằng nhau lấy product_id nhỏ hơn. Trả về tên danh mục gốc, product_id, tổng quantity.",
     "WITH s AS (SELECT r.name_vi AS root, p.product_id, SUM(oi.quantity) AS qty FROM orders o "
     "JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id "
     "JOIN categories c ON c.category_id=p.category_id JOIN categories r ON r.category_id=c.parent_id "
     "WHERE o.status='completed' GROUP BY r.name_vi, p.product_id), "
     "k AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY root ORDER BY qty DESC, product_id) AS rn FROM s) "
     "SELECT root, product_id, qty FROM k WHERE rn<=3 ORDER BY root, qty DESC, product_id", ["window_function", "status_filter"]),
    ("h08", "hard", "Theo từng tháng của năm 2025 (giờ Việt Nam), tỉ lệ phần trăm đơn có dùng voucher trên các đơn không bị hủy, làm tròn 2 chữ số. Cột tháng trả về dạng YYYY-MM.",
     "SELECT DATE_TRUNC('month', " + VN + ") AS thang, ROUND(100.0*SUM(CASE WHEN o.voucher_id IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*),2) AS ty_le "
     "FROM orders o WHERE o.status<>'cancelled' AND YEAR(" + VN + ")=2025 GROUP BY 1 ORDER BY 1", ["timezone", "status_filter"]),
    ("h09", "hard", "Nhóm khách có đơn hoàn thành ĐẦU TIÊN vào tháng 3/2025 (giờ Việt Nam): bao nhiêu phần trăm trong số họ có ít nhất 1 đơn hoàn thành trong tháng 4/2025? Làm tròn 2 chữ số.",
     "WITH f AS (SELECT customer_id, CAST(DATE_TRUNC('month', MIN(order_ts + INTERVAL 7 HOUR)) AS DATE) AS m0 "
     "FROM orders WHERE status='completed' GROUP BY customer_id), "
     "coh AS (SELECT customer_id FROM f WHERE m0=DATE '2025-03-01'), "
     "ret AS (SELECT DISTINCT customer_id FROM orders WHERE status='completed' "
     "AND CAST(DATE_TRUNC('month', order_ts + INTERVAL 7 HOUR) AS DATE)=DATE '2025-04-01') "
     "SELECT ROUND(100.0*COUNT(ret.customer_id)/COUNT(*),2) FROM coh LEFT JOIN ret ON ret.customer_id=coh.customer_id", ["timezone", "cohort"]),
    ("h10", "hard", "Tỉ lệ phần trăm đơn bị hoàn trả (returned) trên các đơn đã giao xong (completed + returned) theo từng danh mục gốc; đếm theo đơn (một đơn có nhiều danh mục thì tính cho từng danh mục), làm tròn 2 chữ số. Trả về tên danh mục gốc và tỉ lệ.",
     "SELECT r.name_vi, ROUND(100.0*COUNT(DISTINCT CASE WHEN o.status='returned' THEN o.order_id END)/COUNT(DISTINCT o.order_id),2) AS ty_le "
     "FROM orders o JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id "
     "JOIN categories c ON c.category_id=p.category_id JOIN categories r ON r.category_id=c.parent_id "
     "WHERE o.status IN ('completed','returned') GROUP BY r.name_vi ORDER BY ty_le DESC, r.name_vi", ["denominator_definition", "join_fanout"]),
    ("h11", "hard", "Giá trị tiền hàng trung bình của một đơn hoàn thành theo từng phương thức thanh toán (đơn chia nhiều phương thức thì tính vào từng phương thức), làm tròn 0 chữ số, xếp giảm dần.",
     "WITH g AS (SELECT order_id, SUM(quantity*unit_price) AS goods FROM order_items GROUP BY order_id), "
     "m AS (SELECT DISTINCT order_id, method FROM payments) "
     "SELECT m.method, ROUND(AVG(g.goods),0) AS tb FROM orders o JOIN g ON g.order_id=o.order_id "
     "JOIN m ON m.order_id=o.order_id WHERE o.status='completed' GROUP BY m.method ORDER BY tb DESC, m.method", ["join_fanout", "status_filter"]),
    ("h12", "hard", "Bao nhiêu phần trăm dòng sản phẩm trong order_items có giá lúc mua thấp hơn giá niêm yết hiện tại (products.price) từ 10% trở lên (unit_price < 0.9 * price)? Làm tròn 2 chữ số.",
     "SELECT ROUND(100.0*SUM(CASE WHEN oi.unit_price<0.9*p.price THEN 1 ELSE 0 END)/COUNT(*),2) FROM order_items oi "
     "JOIN products p ON p.product_id=oi.product_id", ["price_at_purchase"]),
    ("h13", "hard", "Trong năm 2025 (giờ Việt Nam), có bao nhiêu ngày có trên 80 đơn hoàn thành?",
     "SELECT COUNT(*) FROM (SELECT CAST(" + VN + " AS DATE) AS d FROM orders o WHERE o.status='completed' "
     "AND YEAR(" + VN + ")=2025 GROUP BY 1 HAVING COUNT(*)>80)", ["timezone", "status_filter"]),
    ("h14", "hard", "Tổng tiền hàng của các đơn hoàn thành đặt từ ngày 24/09/2026 đến hết ngày 30/09/2026 theo giờ Việt Nam.",
     "SELECT " + GOODS + " FROM orders o JOIN order_items oi ON oi.order_id=o.order_id WHERE o.status='completed' "
     "AND CAST(" + VN + " AS DATE) BETWEEN DATE '2026-09-24' AND DATE '2026-09-30'", ["timezone", "status_filter"]),
]

AMBIGUOUS = [
    ("a02", "Doanh thu quý này là bao nhiêu?", "Doanh thu gross/net? gồm đơn hủy/hoàn? múi giờ? 'quý này' tính theo mốc nào?"),
    ("a03", "Cho tôi danh sách khách hàng VIP.", "Không có định nghĩa VIP (theo chi tiêu, số đơn hay tần suất?)."),
    ("a04", "Sản phẩm nào bán chạy nhất gần đây?", "'Gần đây' là bao lâu? 'Bán chạy' theo số lượng, doanh thu hay số đơn?"),
    ("a05", "Cho tôi biết tình hình kinh doanh tháng này.", "Quá chung chung: chỉ số nào, so với kỳ nào?"),
    ("a06", "Shop nào tốt nhất?", "'Tốt nhất' theo tiêu chí nào: doanh thu, đánh giá, tỉ lệ hoàn?"),
]
OUT_OF_SCOPE = [
    ("o02", "Mỗi ngày website có bao nhiêu lượt truy cập?", "Không có dữ liệu truy cập/traffic."),
    ("o03", "Chi phí quảng cáo và ROAS của từng chiến dịch là bao nhiêu?", "Không có dữ liệu quảng cáo."),
    ("o04", "Quận/huyện nào có nhiều đơn giao nhất?", "Chỉ có tỉnh/thành, không có quận/huyện."),
    ("o05", "Lợi nhuận gộp của từng sản phẩm là bao nhiêu?", "Không có giá vốn."),
    ("o06", "Số điện thoại của 10 khách mua nhiều nhất?", "Không có cột số điện thoại."),
]


# Làm rõ câu hỏi của file mẫu (xem eval/CHANGELOG.md). Chỉ đổi lời hỏi để hết mơ hồ, không đổi gold SQL.
OVERRIDES = {
    "h01": "Doanh thu hàng hóa của đơn hoàn thành theo từng tháng trong năm 2025 (giờ Việt Nam) và phần trăm tăng trưởng so với tháng liền trước, làm tròn 2 chữ số. Chỉ xét các tháng trong năm 2025 nên tháng 1 có tăng trưởng NULL. Cột tháng trả về dạng YYYY-MM.",
    "h02": "Tỉ lệ phần trăm (làm tròn 2 chữ số) đơn bị hoàn trả (returned) trên tổng số đơn đã giao xong (completed + returned) của từng hãng vận chuyển.",
}


def main():
    base = [json.loads(l) for l in (ROOT / "eval" / "questions_sample.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in base:
        if q["id"] in OVERRIDES:
            q["question"] = OVERRIDES[q["id"]]
    new = []
    for qid, diff, q, sql, traps in ANSWERABLE:
        new.append({"id": qid, "difficulty": diff, "type": "answerable", "question": q, "gold_sql": sql, "traps": traps})
    for qid, q, note in AMBIGUOUS:
        new.append({"id": qid, "difficulty": "hard", "type": "ambiguous", "question": q, "gold_sql": None,
                    "expected_behavior": "clarify", "notes": note})
    for qid, q, note in OUT_OF_SCOPE:
        new.append({"id": qid, "difficulty": "easy", "type": "out_of_scope", "question": q, "gold_sql": None,
                    "expected_behavior": "refuse_missing_data", "notes": note})
    new2 = []
    for qid, diff, q, sql, traps in ANSWERABLE_V2:
        new2.append({"id": qid, "difficulty": diff, "type": "answerable", "question": q, "gold_sql": sql, "traps": traps})
    for qid, q, note in AMBIGUOUS_V2:
        new2.append({"id": qid, "difficulty": "hard", "type": "ambiguous", "question": q, "gold_sql": None,
                     "expected_behavior": "clarify", "notes": note})
    for qid, q, note in OUT_OF_SCOPE_V2:
        new2.append({"id": qid, "difficulty": "easy", "type": "out_of_scope", "question": q, "gold_sql": None,
                     "expected_behavior": "refuse_missing_data", "notes": note})
    allq = base + new + new2
    ids = [q["id"] for q in allq]
    assert len(ids) == len(set(ids)), "trùng id"

    problems = 0
    for q in allq:
        if not q.get("gold_sql"):
            continue
        try:
            cols, rows = run_sql(q["gold_sql"])
        except Exception as e:  # noqa: BLE001
            print(f"LỖI SQL  {q['id']}: {e}")
            problems += 1
            continue
        flat = [c for r in rows for c in r]
        flag = ""
        if not rows or all(c is None for c in flat):
            flag = "  <-- RỖNG/NULL"
            problems += 1
        elif len(rows) == 1 and len(rows[0]) == 1 and rows[0][0] in (0, 0.0):
            flag = "  <-- =0 (kiểm tra lại)"
            problems += 1
        shown = rows[0] if len(rows) == 1 else f"{len(rows)} dòng, dòng đầu {rows[0]}"
        print(f"{q['id']:<4} {str(shown)[:95]}{flag}")

    for i, q in enumerate(allq):
        q["split"] = "test" if i % 3 == 2 else "dev"
    out = ROOT / "eval" / "questions.jsonl"
    out.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in allq) + "\n", encoding="utf-8")
    from collections import Counter
    print(f"\nĐã ghi {len(allq)} câu -> {out.name} | {Counter(q['type'] for q in allq)} | {Counter(q['split'] for q in allq)}")
    print(f"Số câu cần xem lại: {problems}")


if __name__ == "__main__":
    main()
