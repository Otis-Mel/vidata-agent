"""Test hồi quy cho bộ chấm, dùng SQL thật của agent từ lần chạy p1_router (xem eval/CHANGELOG.md).
Chạy: python tests/test_grader.py"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.baseline import AgentResult  # noqa: E402
from src.db import run_sql  # noqa: E402
from src.eval_utils import judge, requires_order, results_match  # noqa: E402

Q = {q["id"]: q for q in map(json.loads, (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if True else [])}


def grade(qid, sql):
    cols, rows = run_sql(sql)
    res = AgentResult(behavior="answer", sql=sql, cols=cols, rows=rows)
    gold_rows = run_sql(Q[qid]["gold_sql"])[1]
    return judge(Q[qid], res, gold_rows)


# --- đơn vị: biểu diễn thời gian cùng nghĩa phải khớp ---
g = [(datetime(2025, 1, 1), 5)]
assert results_match(g, [("2025-01", 5)], False)
assert results_match(g, [(date(2025, 1, 1), 5)], False)
assert results_match(g, [("2025-01-01 00:00:00", 5)], False)
assert not results_match(g, [("2025-02", 5)], False)                 # khác tháng -> vẫn sai
assert not results_match([(datetime(2025, 1, 1, 13, 5), 5)], [("2025-01", 5)], False)  # có giờ thật -> không bị coi là đầu tháng

# --- đơn vị: chỉ so thứ tự khi câu hỏi yêu cầu 'xếp' ---
assert requires_order("Xếp giảm dần theo số đơn.") and not requires_order("Tổng tiền theo từng phương thức?")
assert results_match([("a", 1), ("b", 2)], [("b", 2), ("a", 1)], ordered=False)
assert not results_match([("a", 1), ("b", 2)], [("b", 2), ("a", 1)], ordered=True)

# --- SQL thật của agent: những câu từng bị chấm oan phải PASS ---
ok, why = grade("m03", "SELECT method, SUM(amount) AS total_amount FROM payments WHERE status = 'paid' GROUP BY method;")
assert ok, why                                                         # chỉ khác thứ tự dòng

ok, why = grade("h08", """SELECT STRFTIME(order_ts + INTERVAL 7 HOUR, '%Y-%m') AS month,
 ROUND(100.0 * COUNT(voucher_id) / COUNT(*), 2) AS voucher_usage_rate FROM orders
 WHERE status != 'cancelled' AND order_ts + INTERVAL 7 HOUR >= TIMESTAMP '2025-01-01 00:00:00'
 AND order_ts + INTERVAL 7 HOUR < TIMESTAMP '2026-01-01 00:00:00' GROUP BY 1 ORDER BY 1;""")
assert ok, why                                                         # chỉ khác định dạng tháng

ok, why = grade("h03", """WITH item_summary AS (SELECT order_id, SUM(quantity * unit_price) AS total_goods FROM order_items GROUP BY order_id),
 payment_summary AS (SELECT order_id, SUM(amount) AS total_paid FROM payments WHERE status = 'paid' GROUP BY order_id)
 SELECT strftime(o.order_ts + INTERVAL 7 HOUR, '%Y-%m') AS month, COALESCE(SUM(i.total_goods), 0) AS g, COALESCE(SUM(p.total_paid), 0) AS p
 FROM orders o LEFT JOIN item_summary i ON o.order_id = i.order_id LEFT JOIN payment_summary p ON o.order_id = p.order_id
 WHERE o.status = 'completed' AND EXTRACT(YEAR FROM o.order_ts + INTERVAL 7 HOUR) = 2025
 GROUP BY strftime(o.order_ts + INTERVAL 7 HOUR, '%Y-%m') ORDER BY month;""")
assert ok, why

ok, why = grade("h05", """WITH qs AS (SELECT EXTRACT(QUARTER FROM o.order_ts + INTERVAL 7 HOUR) AS quarter, SUM(oi.quantity * oi.unit_price) AS v
 FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = 'completed'
 AND EXTRACT(YEAR FROM o.order_ts + INTERVAL 7 HOUR) = 2025 GROUP BY 1)
 SELECT quarter, v, ROUND((v - LAG(v) OVER (ORDER BY quarter)) * 100.0 / LAG(v) OVER (ORDER BY quarter), 2) FROM qs ORDER BY quarter;""")
assert ok, why

# --- SQL thật của agent: những câu sai THẬT vẫn phải FAIL (bộ chấm không được dễ dãi) ---
ok, why = grade("m09", """SELECT COUNT(*) FROM customers WHERE LOWER(province) LIKE '%hà nội%' OR LOWER(province) LIKE '%ha noi%'
 OR UPPER(TRIM(province)) = 'HN';""")
assert not ok and why == "wrong_result", (ok, why)                      # bỏ sót 'Hanoi'

ok, why = grade("h02", """SELECT s.carrier, COUNT(CASE WHEN o.status = 'returned' THEN 1 END) * 1.0 / COUNT(*) AS return_rate
 FROM shipments s JOIN orders o ON s.order_id = o.order_id WHERE o.status IN ('completed', 'returned') GROUP BY s.carrier;""")
assert not ok, why                                                      # phân số, câu hỏi giờ yêu cầu phần trăm

ok, why = grade("m06", "SELECT COUNT(*) FROM orders WHERE status='completed' AND CAST(order_ts AS DATE)=DATE '2025-11-11'")
assert not ok, why                                                      # quên đổi múi giờ -> sai thật

# --- h03: câu hỏi yêu cầu tháng dạng YYYY-MM; số tháng trần (SQL thật của p2, số liệu đúng hết) không đúng định dạng ---
assert "YYYY-MM" in Q["h03"]["question"] and "YYYY-MM" in Q["h08"]["question"] and "YYYY-MM" in Q["h01"]["question"]
ok, why = grade("h03", """WITH co AS (SELECT order_id, EXTRACT(MONTH FROM order_ts + INTERVAL 7 HOUR) AS month FROM orders
 WHERE status='completed' AND EXTRACT(YEAR FROM order_ts + INTERVAL 7 HOUR)=2025),
 it AS (SELECT order_id, SUM(quantity*unit_price) AS g FROM order_items GROUP BY order_id),
 pt AS (SELECT order_id, SUM(amount) AS p FROM payments WHERE status='paid' GROUP BY order_id)
 SELECT co.month, SUM(COALESCE(it.g,0)), SUM(COALESCE(pt.p,0)) FROM co LEFT JOIN it USING(order_id) LEFT JOIN pt USING(order_id)
 GROUP BY co.month ORDER BY co.month""")
assert not ok and why == "wrong_result", (ok, why)

# --- soát thiết kế bộ eval: không còn câu yêu cầu thứ tự mà có giá trị trùng và thiếu luật khi bằng nhau (lỗi m11) ---
sys.path.insert(0, str(ROOT / "scripts"))
from audit_eval import audit  # noqa: E402
assert audit(list(Q.values())) == [], audit(list(Q.values()))
assert "bằng nhau" in Q["m11"]["question"] and "tiền hàng" in Q["m05"]["question"] and "Trả về tên danh mục gốc" in Q["h10"]["question"]

print("TẤT CẢ TEST BỘ CHẤM PASS")
