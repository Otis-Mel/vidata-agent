# Ablation (split=dev, 68 câu, model `gemini-3.8-flash`)

| Cấu hình | Mô tả | Exec acc | Lỗi SQL | Sai kết quả | Hỏi lại đúng | Từ chối đúng | Lần gọi LLM/câu | Độ trễ/câu (s) | Token vào+ra/câu |
|---|---|---|---|---|---|---|---|---|---|
| `p0_baseline` | Single-agent, 1 prompt | **92.3%** | 0.0% | 1.9% | 50.0% | 100.0% | 1.00 | 9.7 | 2202 |
| `p0b_baseline_retry2` | Single-agent + tự sửa lỗi SQL (2 lần) | **92.3%** | 0.0% | 1.9% | 50.0% | 100.0% | 1.00 | 9.7 | 2202 |
| `p1_router` | + Router (hỏi lại / từ chối) | **88.5%** | 0.0% | 5.8% | 50.0% | 100.0% | 1.78 | 9.9 | 2886 |
| `p2_profile` | + Hồ sơ giá trị dữ liệu | **98.1%** | 0.0% | 0.0% | 87.5% | 100.0% | 1.76 | 10.1 | 4701 |
| `p3_selfcorrect` | + Tự sửa lỗi SQL (2 lần) | **98.1%** | 0.0% | 0.0% | 87.5% | 100.0% | 1.76 | 10.1 | 4701 |
| `p4_critic` | + Critic (1 vòng) | **98.1%** | 0.0% | 0.0% | 87.5% | 100.0% | 2.54 | 13.4 | 6876 |
| `p5_full` | + Chọn bảng (schema selector) | **96.2%** | 0.0% | 1.9% | 87.5% | 100.0% | 3.29 | 13.7 | 5122 |

_Độ trễ lấy từ lần gọi thật đầu tiên (cache lưu lại độ trễ gốc)._