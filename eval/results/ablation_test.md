# Ablation (split=test, 33 câu, model `gemini-3.8-flash`)

| Cấu hình | Mô tả | Exec acc | Lỗi SQL | Sai kết quả | Hỏi lại đúng | Từ chối đúng | Lần gọi LLM/câu | Độ trễ/câu (s) | Token vào+ra/câu |
|---|---|---|---|---|---|---|---|---|---|
| `p0_baseline` | Single-agent, 1 prompt | **92.0%** | 0.0% | 8.0% | 100.0% | 100.0% | 1.00 | 10.8 | 2057 |
| `p2_profile` | + Hồ sơ giá trị dữ liệu | **92.0%** | 0.0% | 8.0% | 100.0% | 100.0% | 1.76 | 12.7 | 4723 |
| `p4_critic` | + Critic (1 vòng) | **92.0%** | 0.0% | 8.0% | 100.0% | 100.0% | 2.52 | 16.9 | 6902 |

_Độ trễ lấy từ lần gọi thật đầu tiên (cache lưu lại độ trễ gốc)._