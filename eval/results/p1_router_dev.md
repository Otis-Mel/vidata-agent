# Báo cáo eval: p1_router_dev

- Model: `gemini-3.8-flash` | preset: `p1_router` | số câu: 68

## Tổng quan

| Metric | Giá trị |
|---|---|
| Execution accuracy (câu trả lời được) | **88.5%** |
| Tỉ lệ lỗi SQL | 0.0% |
| Tỉ lệ SQL chạy được nhưng sai kết quả | 5.8% |
| Hỏi làm rõ đúng (câu mơ hồ) | 50.0% |
| Từ chối đúng (câu ngoài phạm vi) | 100.0% |
| Số lần gọi LLM / câu (TB) | 1.78 |
| Độ trễ / câu (TB, giây) | 9.92 |
| Token vào / ra mỗi câu (TB) | 1781 / 1105 |

## Theo độ khó

| Độ khó | Accuracy | Số câu |
|---|---|---|
| easy | 100.0% | 9 |
| medium | 87.0% | 23 |
| hard | 85.0% | 20 |

## Theo loại bẫy

| Bẫy | Accuracy | Số câu |
|---|---|---|
| bucketing | 100.0% | 1 |
| cohort | 100.0% | 3 |
| denominator_definition | 100.0% | 3 |
| join_fanout | 83.3% | 6 |
| multi_payment | 100.0% | 1 |
| multi_step | 100.0% | 1 |
| no_join_needed | 100.0% | 1 |
| price_at_purchase | 100.0% | 1 |
| province_variants | 0.0% | 5 |
| status_filter | 92.0% | 25 |
| timezone | 100.0% | 20 |
| window_function | 100.0% | 5 |

## Câu sai (10)

**m02** (answerable, medium) — 5 tỉnh/thành có nhiều đơn hoàn thành nhất, tính cả khách ghi tên tỉnh theo nhiều cách khác nhau?
- Lý do: từ chối nhầm (cannot_answer): Cơ sở dữ liệu không có bảng danh mục hoặc ánh xạ chuẩn hóa tên tỉnh/thành phố để xử lý và gộp các biến thể tên khác nhau do người dùng nhập.

**a01** (ambiguous, hard) — Doanh thu tháng trước là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND o.order_ts + INTERVAL 7 HOUR >= TIMESTAMP '2026-09-01 00:00:00'
  AND o.order_ts + INTERVAL 7 HOUR < TIMESTAMP '2026-10-01 00:00:00';
```

**m09** (answerable, medium) — Có bao nhiêu khách hàng ở Hà Nội (tính cả các cách ghi tên khác)?
- Lý do: wrong_result
- SQL agent:
```sql
SELECT COUNT(*) AS total_customers
FROM customers
WHERE LOWER(province) LIKE '%hà nội%'
   OR LOWER(province) LIKE '%ha noi%'
   OR UPPER(TRIM(province)) = 'HN';
```

**h06** (answerable, hard) — 5 tỉnh/thành của khách hàng (theo tỉnh ghi trong hồ sơ khách hàng) có tiền hàng cao nhất từ các đơn hoàn thành, gộp các cách ghi tên khác nhau của cùng một tỉnh.
- Lý do: từ chối nhầm (clarify): Cần làm rõ quy tắc chuẩn hóa hoặc danh sách các biến thể cụ thể của tên tỉnh/thành cần gộp (ví dụ: bỏ tiền tố 'Tỉnh/TP', bảng ánh xạ cụ thể giữa các cách viết), do cơ sở dữ liệu hiện chỉ lưu chuỗi tự do trong cột province mà không có bảng danh mục chuẩn hóa.

**a02** (ambiguous, hard) — Doanh thu quý này là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND date_trunc('quarter', o.order_ts + INTERVAL 7 HOUR) = DATE '2026-10-01';
```

**n02** (answerable, hard) — Với các đơn hoàn thành, số đơn và tổng tiền hàng theo từng phương thức thanh toán (đơn chia nhiều phương thức thì tính cho từng phương thức). Trả về phương thức, số đơn, tổng tiền hàng.
- Lý do: wrong_result
- SQL agent:
```sql
SELECT 
    p.method,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(p.amount) AS total_amount
FROM orders o
JOIN payments p ON o.order_id = p.order_id
WHERE o.status = 'completed'
  AND p.status = 'paid'
GROUP BY p.method;
```

**n23** (answerable, hard) — Thời gian giao trung bình (số ngày thập phân = số giờ từ shipped_ts đến delivered_ts chia 24, làm tròn 2 chữ số) của 3 tỉnh/thành (theo tỉnh của khách, gộp các cách ghi tên) có nhiều đơn giao thành công nhất (shipments.status = delivered); nếu bằng nhau lấy tên tỉnh theo thứ tự chữ cái. Trả về tỉnh/thành, số đơn, thời gian giao trung bình.
- Lý do: wrong_result
- SQL agent:
```sql
SELECT 
    CASE 
        WHEN c.province ILIKE '%Hồ Chí Minh%' OR c.province ILIKE '%HCM%' THEN 'Hồ Chí Minh'
        WHEN c.province ILIKE '%Hà Nội%' THEN 'Hà Nội'
        WHEN c.province ILIKE '%Đà Nẵng%' THEN 'Đà Nẵng'
        ELSE TRIM(REGEXP_REPLACE(c.province, '^(Tỉnh|Thành phố|TP\.?)\s*', '', 'i'))
    END AS province,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(AVG(date_diff('hour', s.shipped_ts, s.delivered_ts) / 24.0), 2) AS avg_delivery_days
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN shipments s ON o.order_id = s.order_id
WHERE s.status = 'delivered'
  AND s.shipped_ts IS NOT NULL
  AND s.delivered_ts IS NOT NULL
  AND c.province IS NOT NULL
GROUP BY 1
ORDER BY order_count DESC, province ASC
LIMIT 3;
```

**n36** (answerable, medium) — Có bao nhiêu khách hàng có tên tỉnh ghi theo một cách KHÔNG chuẩn của Hà Nội hoặc TP. Hồ Chí Minh (tức là các cách ghi khác 'Hà Nội' và 'TP. Hồ Chí Minh' nhưng vẫn là hai thành phố này)?
- Lý do: từ chối nhầm (clarify): Vui lòng làm rõ danh sách hoặc quy tắc nhận diện cụ thể các biến thể tên không chuẩn của Hà Nội (ví dụ: 'HN', 'Ha Noi',...) và TP. Hồ Chí Minh (ví dụ: 'HCM', 'TPHCM', 'Sài Gòn', 'Thành phố Hồ Chí Minh',...).

**a08** (ambiguous, hard) — Có bao nhiêu khách hàng mới trong tuần này?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT COUNT(*) AS new_customers_count
FROM customers
WHERE signup_date >= date_trunc('week', DATE '2026-10-14')
  AND signup_date <= DATE '2026-10-14';
```

**a09** (ambiguous, hard) — Tỉ lệ hoàn đơn là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COUNT(CASE WHEN status = 'returned' THEN 1 END) * 100.0 / COUNT(*) AS return_rate
FROM orders;
```
