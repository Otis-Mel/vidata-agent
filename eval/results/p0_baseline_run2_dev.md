# Báo cáo eval: p0_baseline_run2_dev

- Model: `gemini-3.8-flash` | preset: `p0_baseline` | số câu: 36

## Tổng quan

| Metric | Giá trị |
|---|---|
| Execution accuracy (câu trả lời được) | **92.9%** |
| Tỉ lệ lỗi SQL | 0.0% |
| Tỉ lệ SQL chạy được nhưng sai kết quả | 0.0% |
| Hỏi làm rõ đúng (câu mơ hồ) | 50.0% |
| Từ chối đúng (câu ngoài phạm vi) | 100.0% |
| Số lần gọi LLM / câu (TB) | 1.00 |
| Độ trễ / câu (TB, giây) | 7.63 |
| Token vào / ra mỗi câu (TB) | 1003 / 778 |

## Theo độ khó

| Độ khó | Accuracy | Số câu |
|---|---|---|
| easy | 100.0% | 7 |
| medium | 91.7% | 12 |
| hard | 88.9% | 9 |

## Theo loại bẫy

| Bẫy | Accuracy | Số câu |
|---|---|---|
| cohort | 100.0% | 1 |
| denominator_definition | 100.0% | 2 |
| join_fanout | 100.0% | 2 |
| no_join_needed | 100.0% | 1 |
| price_at_purchase | 100.0% | 1 |
| province_variants | 33.3% | 3 |
| status_filter | 90.9% | 11 |
| timezone | 100.0% | 10 |
| window_function | 100.0% | 1 |

## Câu sai (4)

**m02** (answerable, medium) — 5 tỉnh/thành có nhiều đơn hoàn thành nhất, tính cả khách ghi tên tỉnh theo nhiều cách khác nhau?
- Lý do: từ chối nhầm (cannot_answer): Cơ sở dữ liệu không có bảng danh mục hoặc quy tắc chuẩn hóa tên tỉnh/thành để ánh xạ các cách viết khác nhau.

**a01** (ambiguous, hard) — Doanh thu tháng trước là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND date_trunc('month', o.order_ts + INTERVAL 7 HOUR) = '2026-09-01';
```

**h06** (answerable, hard) — 5 tỉnh/thành của khách hàng (theo tỉnh ghi trong hồ sơ khách hàng) có tiền hàng cao nhất từ các đơn hoàn thành, gộp các cách ghi tên khác nhau của cùng một tỉnh.
- Lý do: từ chối nhầm (cannot_answer): Cơ sở dữ liệu không có bảng danh mục hoặc quy tắc ánh xạ/chuẩn hóa các cách ghi tên tỉnh/thành phố khác nhau.

**a02** (ambiguous, hard) — Doanh thu quý này là bao nhiêu?
- Lý do: không hỏi làm rõ (behavior=answer)
- SQL agent:
```sql
SELECT 
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
  AND o.order_ts + INTERVAL 7 HOUR >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.order_ts + INTERVAL 7 HOUR <= TIMESTAMP '2026-10-14 23:59:59';
```
