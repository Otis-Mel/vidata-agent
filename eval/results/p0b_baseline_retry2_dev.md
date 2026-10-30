# Báo cáo eval: p0b_baseline_retry2_dev

- Model: `gemini-3.8-flash` | preset: `p0b_baseline_retry2` | số câu: 68

## Tổng quan

| Metric | Giá trị |
|---|---|
| Execution accuracy (câu trả lời được) | **92.3%** |
| Tỉ lệ lỗi SQL | 0.0% |
| Tỉ lệ SQL chạy được nhưng sai kết quả | 1.9% |
| Hỏi làm rõ đúng (câu mơ hồ) | 50.0% |
| Từ chối đúng (câu ngoài phạm vi) | 100.0% |
| Số lần gọi LLM / câu (TB) | 1.00 |
| Độ trễ / câu (TB, giây) | 9.72 |
| Token vào / ra mỗi câu (TB) | 1009 / 1193 |

## Theo độ khó

| Độ khó | Accuracy | Số câu |
|---|---|---|
| easy | 100.0% | 9 |
| medium | 91.3% | 23 |
| hard | 90.0% | 20 |

## Theo loại bẫy

| Bẫy | Accuracy | Số câu |
|---|---|---|
| bucketing | 100.0% | 1 |
| cohort | 100.0% | 3 |
| denominator_definition | 100.0% | 3 |
| join_fanout | 100.0% | 6 |
| multi_payment | 100.0% | 1 |
| multi_step | 100.0% | 1 |
| no_join_needed | 100.0% | 1 |
| price_at_purchase | 100.0% | 1 |
| province_variants | 20.0% | 5 |
| status_filter | 96.0% | 25 |
| timezone | 100.0% | 20 |
| window_function | 100.0% | 5 |

## Câu sai (8)

**m02** (answerable, medium) — 5 tỉnh/thành có nhiều đơn hoàn thành nhất, tính cả khách ghi tên tỉnh theo nhiều cách khác nhau?
- Lý do: từ chối nhầm (cannot_answer): Không có bảng danh mục hoặc quy tắc chuẩn hóa ánh xạ các cách ghi khác nhau của tỉnh/thành phố.

**a01** (ambiguous, hard) — Doanh thu tháng trước là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND o.order_ts + INTERVAL '7 hour' >= TIMESTAMP '2026-09-01 00:00:00'
  AND o.order_ts + INTERVAL '7 hour' < TIMESTAMP '2026-10-01 00:00:00';
```

**h06** (answerable, hard) — 5 tỉnh/thành của khách hàng (theo tỉnh ghi trong hồ sơ khách hàng) có tiền hàng cao nhất từ các đơn hoàn thành, gộp các cách ghi tên khác nhau của cùng một tỉnh.
- Lý do: từ chối nhầm (cannot_answer): Cơ sở dữ liệu không có bảng chuẩn hóa hoặc quy tắc ánh xạ các cách ghi khác nhau của tên tỉnh/thành phố.

**a02** (ambiguous, hard) — Doanh thu quý này là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND (o.order_ts + INTERVAL 7 HOUR) >= '2026-10-01 00:00:00'
  AND (o.order_ts + INTERVAL 7 HOUR) < '2027-01-01 00:00:00';
```

**n23** (answerable, hard) — Thời gian giao trung bình (số ngày thập phân = số giờ từ shipped_ts đến delivered_ts chia 24, làm tròn 2 chữ số) của 3 tỉnh/thành (theo tỉnh của khách, gộp các cách ghi tên) có nhiều đơn giao thành công nhất (shipments.status = delivered); nếu bằng nhau lấy tên tỉnh theo thứ tự chữ cái. Trả về tỉnh/thành, số đơn, thời gian giao trung bình.
- Lý do: wrong_result
- SQL agent:
```sql
SELECT 
    CASE 
        WHEN c.province ILIKE '%Hồ Chí Minh%' OR c.province ILIKE '%HCM%' THEN 'TP. Hồ Chí Minh'
        WHEN c.province ILIKE '%Hà Nội%' OR c.province ILIKE '%HN%' THEN 'Hà Nội'
        WHEN c.province ILIKE '%Đà Nẵng%' THEN 'Đà Nẵng'
        WHEN c.province ILIKE '%Hải Phòng%' THEN 'Hải Phòng'
        WHEN c.province ILIKE '%Cần Thơ%' THEN 'Cần Thơ'
        WHEN c.province ILIKE '%Bình Dương%' THEN 'Bình Dương'
        WHEN c.province ILIKE '%Đồng Nai%' THEN 'Đồng Nai'
        ELSE TRIM(REGEXP_REPLACE(c.province, '^(Tỉnh|Thành phố|TP\.?)\s*', '', 'i'))
    END AS province,
    COUNT(DISTINCT o.order_id) AS total_orders,
    ROUND(AVG(DATE_DIFF('second', s.shipped_ts, s.delivered_ts) / 86400.0), 2) AS avg_delivery_days
FROM orders o
JOIN shipments s ON o.order_id = s.order_id
JOIN customers c ON o.customer_id = c.customer_id
WHERE s.status = 'delivered'
  AND s.shipped_ts IS NOT NULL
  AND s.delivered_ts IS NOT NULL
GROUP BY 1
ORDER BY total_orders DESC, province ASC
LIMIT 3;
```

**n36** (answerable, medium) — Có bao nhiêu khách hàng có tên tỉnh ghi theo một cách KHÔNG chuẩn của Hà Nội hoặc TP. Hồ Chí Minh (tức là các cách ghi khác 'Hà Nội' và 'TP. Hồ Chí Minh' nhưng vẫn là hai thành phố này)?
- Lý do: từ chối nhầm (clarify): Bạn có thể cung cấp danh sách cụ thể các biến thể (hoặc quy tắc nhận diện) được coi là cách ghi không chuẩn của Hà Nội và TP. Hồ Chí Minh (ví dụ: 'HN', 'TP.HCM', 'Sài Gòn', viết không dấu,...) không?

**a08** (ambiguous, hard) — Có bao nhiêu khách hàng mới trong tuần này?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT COUNT(*) AS new_customer_count
FROM customers
WHERE signup_date >= DATE_TRUNC('week', DATE '2026-10-14')
  AND signup_date <= DATE '2026-10-14';
```

**a09** (ambiguous, hard) — Tỉ lệ hoàn đơn là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COUNT(CASE WHEN status = 'returned' THEN 1 END) * 100.0 / COUNT(*) AS return_rate_percentage
FROM orders;
```
