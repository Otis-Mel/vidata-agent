# Báo cáo eval: p4_critic_test

- Model: `gemini-3.8-flash` | preset: `p4_critic` | số câu: 33

## Tổng quan

| Metric | Giá trị |
|---|---|
| Execution accuracy (câu trả lời được) | **92.0%** |
| Tỉ lệ lỗi SQL | 0.0% |
| Tỉ lệ SQL chạy được nhưng sai kết quả | 8.0% |
| Hỏi làm rõ đúng (câu mơ hồ) | 100.0% |
| Từ chối đúng (câu ngoài phạm vi) | 100.0% |
| Số lần gọi LLM / câu (TB) | 2.52 |
| Độ trễ / câu (TB, giây) | 16.93 |
| Token vào / ra mỗi câu (TB) | 5424 / 1478 |

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
| status_filter | 100.0% | 15 |
| timezone | 100.0% | 9 |
| window_function | 100.0% | 3 |

## Câu sai (2)

**m11** (answerable, medium) — Điểm đánh giá trung bình theo từng danh mục gốc (tên danh mục gốc), làm tròn 2 chữ số, xếp giảm dần.
- Lý do: wrong_result
- SQL agent:
```sql
WITH RECURSIVE cat_tree AS (
    SELECT 
        category_id, 
        category_id AS root_id, 
        name_vi AS root_name
    FROM categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT 
        c.category_id, 
        ct.root_id, 
        ct.root_name
    FROM categories c
    JOIN cat_tree ct ON c.parent_id = ct.category_id
)
SELECT 
    ct.root_name AS root_category_name,
    ROUND(AVG(r.rating), 2) AS avg_rating
FROM reviews r
JOIN order_items oi ON r.order_item_id = oi.order_item_id
JOIN products p ON oi.product_id = p.product_id
JOIN cat_tree ct ON p.category_id = ct.category_id
GROUP BY ct.root_id, ct.root_name
ORDER BY avg_rating DESC;
```

**h10** (answerable, hard) — Tỉ lệ phần trăm đơn bị hoàn trả (returned) trên các đơn đã giao xong (completed + returned) theo từng danh mục gốc; đếm theo đơn (một đơn có nhiều danh mục thì tính cho từng danh mục), làm tròn 2 chữ số.
- Lý do: wrong_result
- SQL agent:
```sql
WITH RECURSIVE cat_tree AS (
    SELECT category_id AS root_id, name_vi AS root_name, category_id
    FROM categories
    WHERE parent_id IS NULL
    UNION ALL
    SELECT ct.root_id, ct.root_name, c.category_id
    FROM categories c
    JOIN cat_tree ct ON c.parent_id = ct.category_id
)
SELECT
    ct.root_id AS category_id,
    ct.root_name AS category_name,
    ROUND(
        COUNT(DISTINCT CASE WHEN o.status = 'returned' THEN o.order_id END) * 100.0 / 
        COUNT(DISTINCT o.order_id), 
        2
    ) AS return_rate_percent
FROM cat_tree ct
JOIN products p ON ct.category_id = p.category_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status IN ('completed', 'returned')
GROUP BY ct.root_id, ct.root_name
ORDER BY ct.root_id;
```
