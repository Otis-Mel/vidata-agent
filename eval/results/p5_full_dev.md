# Báo cáo eval: p5_full_dev

- Model: `gemini-3.8-flash` | preset: `p5_full` | số câu: 68

## Tổng quan

| Metric | Giá trị |
|---|---|
| Execution accuracy (câu trả lời được) | **96.2%** |
| Tỉ lệ lỗi SQL | 0.0% |
| Tỉ lệ SQL chạy được nhưng sai kết quả | 1.9% |
| Hỏi làm rõ đúng (câu mơ hồ) | 87.5% |
| Từ chối đúng (câu ngoài phạm vi) | 100.0% |
| Số lần gọi LLM / câu (TB) | 3.29 |
| Độ trễ / câu (TB, giây) | 13.71 |
| Token vào / ra mỗi câu (TB) | 3772 / 1350 |

## Theo độ khó

| Độ khó | Accuracy | Số câu |
|---|---|---|
| easy | 100.0% | 9 |
| medium | 100.0% | 23 |
| hard | 90.0% | 20 |

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
| province_variants | 80.0% | 5 |
| status_filter | 92.0% | 25 |
| timezone | 100.0% | 20 |
| window_function | 100.0% | 5 |

## Câu sai (3)

**h06** (answerable, hard) — 5 tỉnh/thành của khách hàng (theo tỉnh ghi trong hồ sơ khách hàng) có tiền hàng cao nhất từ các đơn hoàn thành, gộp các cách ghi tên khác nhau của cùng một tỉnh.
- Lý do: wrong_result
- SQL agent:
```sql
SELECT 
    CASE 
        WHEN c.province IN ('TP. Hồ Chí Minh', 'TP.HCM', 'Sài Gòn', 'HCM', 'Ho Chi Minh') THEN 'TP. Hồ Chí Minh'
        WHEN c.province IN ('Hà Nội', 'HN', 'Ha Noi', 'Hanoi') THEN 'Hà Nội'
        ELSE c.province 
    END AS province,
    SUM(oi.quantity * oi.unit_price) AS total_amount
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND c.province IS NOT NULL
GROUP BY province
ORDER BY total_amount DESC
LIMIT 5;
```

**a02** (ambiguous, hard) — Doanh thu quý này là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND o.order_ts + INTERVAL 7 HOUR >= '2026-10-01'
  AND o.order_ts + INTERVAL 7 HOUR < '2027-01-01';
```

**n02** (answerable, hard) — Với các đơn hoàn thành, số đơn và tổng tiền hàng theo từng phương thức thanh toán (đơn chia nhiều phương thức thì tính cho từng phương thức). Trả về phương thức, số đơn, tổng tiền hàng.
- Lý do: từ chối nhầm (clarify): Bạn muốn tính 'tổng tiền hàng' theo số tiền thanh toán thực tế của từng phương thức (bảng payments, có thể gồm phí ship/giảm giá) hay theo giá trị sản phẩm (order_items)? Nếu tính theo sản phẩm, khi đơn chia nhiều phương thức thì phân bổ theo tỷ lệ nào?
