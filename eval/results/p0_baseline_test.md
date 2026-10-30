# Báo cáo eval: p0_baseline_test

- Model: `gemini-3.8-flash` | preset: `p0_baseline` | số câu: 33

## Tổng quan

| Metric | Giá trị |
|---|---|
| Execution accuracy (câu trả lời được) | **92.0%** |
| Tỉ lệ lỗi SQL | 0.0% |
| Tỉ lệ SQL chạy được nhưng sai kết quả | 8.0% |
| Hỏi làm rõ đúng (câu mơ hồ) | 100.0% |
| Từ chối đúng (câu ngoài phạm vi) | 100.0% |
| Số lần gọi LLM / câu (TB) | 1.00 |
| Độ trễ / câu (TB, giây) | 10.78 |
| Token vào / ra mỗi câu (TB) | 1010 / 1047 |

## Theo độ khó

| Độ khó | Accuracy | Số câu |
|---|---|---|
| medium | 88.9% | 9 |
| hard | 92.3% | 13 |
| easy | 100.0% | 3 |

## Theo loại bẫy

| Bẫy | Accuracy | Số câu |
|---|---|---|
| cohort | 100.0% | 1 |
| denominator_definition | 0.0% | 1 |
| join_fanout | 66.7% | 3 |
| multi_step | 100.0% | 2 |
| price_at_purchase | 100.0% | 1 |
| province_variants | 100.0% | 2 |
| status_filter | 93.3% | 15 |
| timezone | 100.0% | 9 |
| window_function | 100.0% | 3 |

## Câu sai (2)

**m05** (answerable, medium) — 5 danh mục con (trả về category_id và tên danh mục) có tiền hàng cao nhất trong các đơn hoàn thành.
- Lý do: wrong_result
- SQL agent:
```sql
SELECT c.category_id, c.name_vi
FROM categories c
JOIN products p ON c.category_id = p.category_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE c.parent_id IS NOT NULL
  AND o.status = 'completed'
GROUP BY c.category_id, c.name_vi
ORDER BY SUM(oi.quantity * oi.unit_price) DESC
LIMIT 5;
```

**h10** (answerable, hard) — Tỉ lệ phần trăm đơn bị hoàn trả (returned) trên các đơn đã giao xong (completed + returned) theo từng danh mục gốc; đếm theo đơn (một đơn có nhiều danh mục thì tính cho từng danh mục), làm tròn 2 chữ số.
- Lý do: wrong_result
- SQL agent:
```sql
WITH RECURSIVE cat_root AS (
    SELECT category_id, category_id AS root_category_id, name_vi AS root_category_name
    FROM categories
    WHERE parent_id IS NULL
    UNION ALL
    SELECT c.category_id, cr.root_category_id, cr.root_category_name
    FROM categories c
    JOIN cat_root cr ON c.parent_id = cr.category_id
),
order_root_categories AS (
    SELECT DISTINCT
        cr.root_category_id,
        cr.root_category_name,
        o.order_id,
        o.status
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    JOIN cat_root cr ON p.category_id = cr.category_id
    WHERE o.status IN ('completed', 'returned')
)
SELECT
    root_category_id,
    root_category_name,
    ROUND(COUNT(CASE WHEN status = 'returned' THEN 1 END) * 100.0 / COUNT(*), 2) AS return_rate_pct
FROM order_root_categories
GROUP BY root_category_id, root_category_name
ORDER BY root_category_id;
```
