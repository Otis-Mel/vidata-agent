# ViDataAgent

Multi-agent text-to-SQL cho dữ liệu thương mại điện tử Việt Nam: hỏi bằng tiếng Việt → agent viết SQL, chạy trong sandbox
read-only, tự sửa lỗi, kiểm tra kết quả (critic), hỏi lại khi câu hỏi mơ hồ, từ chối khi thiếu dữ liệu.
Điểm chính của project là **đo lường**: bộ eval 101 câu, ablation 7 cấu hình, chia dev/test, nhật ký sửa bộ eval.

> Dữ liệu là **giả lập** (có chủ đích đặt "bẫy"), seed cố định nên tái lập được.

## Kết quả chính
- Với Gemini 3.8 Flash, **kiến trúc nhiều agent không cải thiện accuracy đo được** trên benchmark này (test: 23/25 ở baseline,
  + hồ sơ giá trị dữ liệu, + critic), trong khi chi phí token tăng 2.3 đến 3.4 lần.
- Một đóng góp có cơ chế rõ trên dev: đưa giá trị dữ liệu thật vào prompt giúp giảm các lần từ chối nhầm ở câu về tên tỉnh
  (92.3% → 98.1%); hiệu quả này không lặp lại trên test.
- Phát hiện đáng giá nhất là về **đo lường**: phần lớn "lỗi" ban đầu là lỗi của bộ chấm và câu hỏi (baseline đo ra 71.4% rồi
  92.9% trên cùng 28 câu dev sau khi sửa bộ chấm; cả 3 câu sai trên test đều là lỗi thiết kế câu hỏi). Xem `eval/CHANGELOG.md`.

## Kiến trúc
```
Câu hỏi ─► Router ──clarify / cannot_answer──► trả lời ngay
              │ answer
              ▼
        (Schema selector) ─► SQL agent (+ hồ sơ giá trị dữ liệu, tự sửa lỗi) ─► Critic ─► (Explainer)
                                   │                                              │ revise
                                   └──────────── chạy sandbox read-only ◄─────────┘
```
| Thành phần | File | Việc làm |
|---|---|---|
| Router | `src/agents/multi.py` | phân loại: trả lời / hỏi lại / thiếu dữ liệu |
| Hồ sơ giá trị | `src/profile.py` | tự thống kê giá trị cột chữ và khoảng thời gian từ DB (value linking) |
| SQL agent | `src/agents/multi.py` | sinh SQL, tự sửa khi lỗi (số lần cấu hình được) |
| Critic | `src/agents/multi.py` | xem SQL + kết quả thật, bắt lỗi "chạy được nhưng sai", yêu cầu sửa |
| Sandbox | `src/db.py` | chỉ SELECT/WITH, read-only, giới hạn 1000 dòng, timeout 10s |
| LLM | `src/llm.py` | Gemini, retry, cache, đo token và độ trễ |

## Chạy
Cần Python 3.10 trở lên.
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # điền GEMINI_API_KEY (và GEMINI_MODEL nếu cần); KHÔNG commit .env
python scripts/generate_data.py       # tạo data/ecommerce.duckdb (seed cố định)

# kiểm tra không cần key (LLM giả)
python tests/test_pipeline.py && python tests/test_multi.py && python tests/test_grader.py
python scripts/audit_eval.py          # soát lỗi thiết kế bộ eval
python scripts/trap_check.py          # bộ eval có bắt được lỗi múi giờ / trạng thái / tên tỉnh không

# đo (gọi Gemini thật, tốn token)
python eval/run_eval.py --preset p0_baseline              # 1 cấu hình, split dev
python scripts/run_ablation.py                            # 7 cấu hình -> eval/results/ablation_dev.md
python scripts/run_ablation.py --split test --presets p0_baseline p2_profile p4_critic   # chỉ chạy test MỘT lần
python scripts/compare_runs.py p0_baseline p2_profile     # câu nào được cứu / bị hỏng giữa hai cấu hình

streamlit run app.py                                      # demo UI
docker build -t vidata-agent . && docker run --env-file .env -p 8501:8501 vidata-agent
```
Lưu ý: `scripts/build_eval_set.py` ghi đè `eval/questions.jsonl` (kèm kiểm tra gold SQL).

## Dữ liệu và bẫy
10 bảng, ~40k đơn (01/2024 đến 09/2026). Bẫy: tên tỉnh nhiều cách viết, timestamp UTC so với giờ Việt Nam, 1 đơn nhiều dòng
`payments` (join nhân dòng làm lệch tổng khoảng 12%), "doanh thu" mơ hồ, giá lúc mua khác giá niêm yết, đơn đang giao chưa có ngày giao.

## Evaluation
`eval/questions.jsonl`: 101 câu (77 trả lời được, 12 mơ hồ, 12 ngoài phạm vi; dev 68, test 33), mỗi câu có gold SQL
(hoặc hành vi kỳ vọng) và nhãn bẫy.

**Bộ chấm** (`src/eval_utils.py`): so sánh tập kết quả thực thi, không so chuỗi SQL. Bỏ qua tên cột; bỏ qua thứ tự dòng trừ khi
câu hỏi có chữ "xếp"; số thực so với sai số nhỏ; `'2025-03'`, ngày đầu tháng và DATE được coi là cùng một giá trị. **Cột phải khớp
đúng**: trả thêm hoặc thiếu cột đều bị tính sai (đây là nguyên nhân của các câu sai trên test). Câu mơ hồ chỉ đạt khi agent hỏi lại,
câu ngoài phạm vi chỉ đạt khi agent từ chối.

**Quy trình chống overfit:**
- Prompt của agent **không bị chỉnh** sau khi xem kết quả; chỉ có bộ eval được sửa, mỗi lần đều ghi vào `eval/CHANGELOG.md`.
- Split test chạy đúng một lần với cấu hình chọn trước. Tuy vậy ba câu test (m05, m11, h10) bị phát hiện lỗi thiết kế SAU khi chạy
  và đã được sửa lời hỏi; số test chính thức giữ nguyên, kết quả sửa nằm ở mục "Phân tích sau khi chạy test".
- Checklist của critic mã hoá các lỗi SQL phổ biến mà benchmark cũng có, nên chỉ số test mới là số đáng tin hơn số dev.

## Kết quả
Model: gemini-3.8-flash, temperature 0.

**Dev** (68 câu, 52 trả lời được):

| Cấu hình | Exec acc | Hỏi lại đúng | Lần gọi LLM/câu | Token/câu |
|---|---|---|---|---|
| p0 Single-agent | 92.3% | 50.0% | 1.00 | 2,202 |
| p0b + tự sửa lỗi SQL | 92.3% | 50.0% | 1.00 | 2,202 |
| p1 + Router | 88.5% | 50.0% | 1.78 | 2,886 |
| p2 + Hồ sơ giá trị dữ liệu | 98.1% | 87.5% | 1.76 | 4,701 |
| p3 + tự sửa lỗi SQL | 98.1% | 87.5% | 1.76 | 4,701 |
| p4 + Critic | 98.1% | 87.5% | 2.54 | 6,876 |
| p5 + Chọn bảng | 96.2% | 87.5% | 3.29 | 5,122 |

**Test** (33 câu, 25 trả lời được, chạy một lần):

| Cấu hình | Exec acc (chính thức) | Hỏi lại đúng | Từ chối đúng | Token/câu | Độ trễ/câu |
|---|---|---|---|---|---|
| p0 Single-agent | 92.0% (23/25) | 100% | 100% | 2,057 | 10.8 s |
| p2 + Hồ sơ giá trị | 92.0% (23/25) | 100% | 100% | 4,723 | 12.7 s |
| p4 + Critic | 92.0% (23/25) | 100% | 100% | 6,902 | 16.9 s |

Với 23/25, khoảng tin cậy 95% của mỗi con số khoảng 75% đến 98%.

**Phân tích sau khi chạy test (post-hoc):** cả 3 câu sai (m05, m11, h10) đều là lỗi thiết kế câu hỏi, không phải lỗi agent:
m05 gold trả thêm cột tiền hàng mà câu hỏi không đòi; m11 có ba danh mục trùng điểm 4.23 mà câu hỏi không nêu luật khi bằng nhau;
h10 agent đếm đúng theo đơn nhưng thêm cột `category_id` vì câu hỏi không nêu cột cần trả về. Chạy lại chính các câu SQL của
agent cho thấy giá trị đúng ở 25/25 câu ở cả ba cấu hình. Chi tiết trong `eval/CHANGELOG.md`.

**Nhận xét:**
- Hồ sơ giá trị dữ liệu giảm các lần từ chối nhầm ở câu về tên tỉnh trên dev nhưng không lặp lại trên test (baseline không từ chối nhầm câu nào ở đó).
- Tự sửa lỗi SQL không có tác dụng: tỉ lệ lỗi SQL là 0%, bước này không bao giờ được kích hoạt (nên không tốn thêm chi phí).
- Critic không thêm câu đúng nào nhưng tăng thêm khoảng 46% token so với p2 (3.4 lần so với baseline).
- Router và chọn bảng không giúp ích (kém hơn một chút trên dev, trong mức nhiễu).
- Kết luận: với model mạnh, benchmark này không phân biệt được các cấu hình; chưa kiểm tra với model yếu hơn.

## Hạn chế
- Dữ liệu giả lập; bộ eval do tác giả tự viết (101 câu) và đã được sửa nhiều lần sau khi xem kết quả dev (xem `eval/CHANGELOG.md`).
- Bộ test nhỏ (25 câu trả lời được): chênh lệch vài câu nằm trong mức nhiễu. Mới chạy lặp lại một lần để kiểm tra độ ổn định.
- 12 câu có gold nhiều cột mà lời hỏi chưa nêu rõ cột cần trả về (liệt kê bởi `scripts/audit_eval.py`).
- 5 câu có bẫy múi giờ (m10, h13, h14, n15, n17) không nhạy với lỗi múi giờ (`scripts/trap_check.py`).
- Chưa thử model yếu hơn, nơi các agent phụ trợ nhiều khả năng có tác dụng lớn hơn.
- Chưa có tracing ngoài (Langfuse); có `trace` từng bước trong kết quả và trong UI.