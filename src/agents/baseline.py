"""Single-agent baseline: 1 prompt (schema + câu hỏi) -> SQL -> chạy.

max_retries=0  : baseline thuần.
max_retries>0  : bật self-correction (gửi lại SQL + lỗi cho model), dùng cho ablation sau này.
"""
import re
from dataclasses import dataclass, field
from datetime import date

import duckdb

from src.db import UnsafeSQL, run_sql
from src.llm import LLM
from src.schema_text import load_schema_for_prompt

# Ngày "hôm nay" cố định để eval tái lập được (câu hỏi kiểu "tháng trước" cần mốc này).
AS_OF_DATE = date(2026, 10, 14)

SYSTEM = "Bạn là chuyên gia phân tích dữ liệu, viết SQL DuckDB chính xác cho cơ sở dữ liệu thương mại điện tử."

PROMPT = """Cơ sở dữ liệu (DuckDB):

{schema}

Hôm nay là {today}.

Câu hỏi của người dùng (tiếng Việt):
{question}

Quy tắc trả lời:
- Nếu trả lời được: chỉ trả về MỘT câu SQL DuckDB (SELECT hoặc WITH) trong khối ```sql ... ```. Không giải thích.
- Nếu dữ liệu không có thông tin cần thiết để trả lời: trả về đúng một dòng `CANNOT_ANSWER: <lý do ngắn>`.
- Nếu câu hỏi mơ hồ đến mức có nhiều cách hiểu cho kết quả khác nhau: trả về đúng một dòng `CLARIFY: <câu hỏi làm rõ>`.
"""

RETRY = """{base}

Lần thử trước bạn viết SQL:
```sql
{sql}
```
SQL này bị lỗi khi chạy:
{error}

Hãy sửa và trả lại MỘT câu SQL hoàn chỉnh theo cùng quy tắc."""


@dataclass
class AgentResult:
    behavior: str                      # answer | clarify | cannot_answer | error
    sql: str | None = None
    cols: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    message: str = ""                  # lý do/ câu hỏi làm rõ/ thông báo lỗi
    attempts: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    latency_s: float = 0.0
    answer_text: str = ""            # diễn giải bằng lời (nếu bật explain)
    trace: list = field(default_factory=list)   # từng bước của pipeline (để debug/demo)


def parse_response(text: str):
    """-> (kind, payload) với kind in {'sql','clarify','cannot','none'}."""
    t = (text or "").strip()
    m = re.search(r"^\W*CLARIFY\s*:\s*(.+)$", t, re.I | re.M)
    if m:
        return "clarify", m.group(1).strip()
    m = re.search(r"^\W*CANNOT_ANSWER\s*:\s*(.+)$", t, re.I | re.M)
    if m:
        return "cannot", m.group(1).strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", t, re.S | re.I)
    if m and m.group(1).strip():
        return "sql", m.group(1).strip()
    if re.match(r"^\s*(select|with)\b", t, re.I):
        return "sql", t
    return "none", t


class BaselineAgent:
    def __init__(self, llm: LLM, max_retries: int = 0):
        self.llm = llm
        self.max_retries = max_retries
        self.schema = load_schema_for_prompt()

    def answer(self, question: str) -> AgentResult:
        base = PROMPT.format(schema=self.schema, today=AS_OF_DATE.strftime("%d/%m/%Y"), question=question)
        res = AgentResult(behavior="error")
        prev_sql, prev_err = None, None
        for attempt in range(self.max_retries + 1):
            prompt = base if attempt == 0 else RETRY.format(base=base, sql=prev_sql, error=prev_err)
            out = self.llm.generate(prompt, system=SYSTEM)
            res.attempts = attempt + 1
            res.in_tokens += out.in_tokens
            res.out_tokens += out.out_tokens
            res.latency_s += out.latency_s
            kind, payload = parse_response(out.text)
            if kind == "clarify":
                res.behavior, res.message = "clarify", payload
                return res
            if kind == "cannot":
                res.behavior, res.message = "cannot_answer", payload
                return res
            if kind == "none":
                res.behavior, res.message = "error", "Model không trả về SQL hợp lệ."
                prev_sql, prev_err = "(không có)", res.message
                continue
            res.sql = payload
            try:
                res.cols, res.rows = run_sql(payload)
                res.behavior, res.message = "answer", ""
                return res
            except (UnsafeSQL, duckdb.Error, TimeoutError) as e:
                res.behavior, res.message = "error", f"{type(e).__name__}: {e}"
                prev_sql, prev_err = payload, res.message
        return res
