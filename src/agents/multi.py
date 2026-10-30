"""Multi-agent pipeline cho text-to-SQL, mỗi thành phần bật/tắt được để làm ablation.

Luồng:  Router -> (Schema selector) -> SQL agent (+ value profile, self-correction) -> Critic -> (Explainer)

Các agent (mỗi agent là 1 prompt/1 lần gọi LLM):
  router    : phân loại answer / clarify / cannot_answer
  selector  : chọn bảng liên quan (chỉ có ý nghĩa khi schema lớn; với 10 bảng có thể không giúp ích)
  sql       : sinh SQL, tự sửa khi chạy lỗi
  critic    : xem SQL + kết quả thực tế, bắt lỗi "chạy được nhưng sai", yêu cầu sửa
  explainer : diễn giải kết quả bằng tiếng Việt (chỉ bật cho demo, tắt khi eval để đỡ tốn)

Lưu ý trung thực: checklist của critic mã hoá các lỗi SQL phổ biến (nhân dòng khi join, múi giờ, giá trị chuỗi).
Bộ eval có bẫy cùng loại, nên phải tune trên split "dev" và báo cáo trên split "test".
"""
import json
import re
from dataclasses import dataclass

import duckdb

from src.agents.baseline import AS_OF_DATE, SYSTEM, AgentResult, BaselineAgent, parse_response
from src.db import UnsafeSQL, run_sql
from src.llm import LLM
from src.profile import profile_for
from src.schema_text import all_tables, load_schema_for_prompt

ROUTER = """Nhiệm vụ: phân loại câu hỏi về dữ liệu thương mại điện tử.

Cơ sở dữ liệu (DuckDB):
{schema}

{profile}

Hôm nay là {today}.
Câu hỏi: {question}

Chọn đúng một loại:
- "answer": dữ liệu đủ để trả lời và câu hỏi đủ rõ (hoặc có cách hiểu mặc định hợp lý).
- "clarify": câu hỏi có nhiều cách hiểu cho kết quả khác nhau đáng kể (định nghĩa chỉ số, phạm vi thời gian, tiêu chí xếp hạng không rõ) và không thể chọn một mặc định hợp lý.
- "cannot_answer": thông tin cần thiết KHÔNG có trong schema (cột hoặc bảng không tồn tại).

Chỉ trả về JSON: {{"type": "answer" | "clarify" | "cannot_answer", "message": "câu hỏi làm rõ hoặc lý do ngắn"}}"""

SELECTOR = """Nhiệm vụ: chọn bảng cần dùng để trả lời câu hỏi.

Cơ sở dữ liệu:
{schema}

Câu hỏi: {question}

Chỉ trả về JSON: {{"tables": ["tên_bảng", ...]}} gồm mọi bảng cần thiết (kể cả bảng trung gian để join)."""

SQL_PROMPT = """Cơ sở dữ liệu (DuckDB):
{schema}

Giá trị thực tế trong dữ liệu:
{profile}

Hôm nay là {today}.
Câu hỏi: {question}

{rules}"""

RULES_BASE = "Chỉ trả về MỘT câu SQL DuckDB (SELECT hoặc WITH) trong khối ```sql ... ```. Không giải thích."
RULES_NO_ROUTER = RULES_BASE + """
Nếu dữ liệu không có thông tin cần thiết: trả về đúng một dòng `CANNOT_ANSWER: <lý do>`.
Nếu câu hỏi mơ hồ đến mức có nhiều cách hiểu cho kết quả khác nhau: trả về đúng một dòng `CLARIFY: <câu hỏi làm rõ>`."""

REVISE = """{base}

Lần trước bạn viết SQL:
```sql
{sql}
```
{feedback}

Hãy sửa và trả lại MỘT câu SQL hoàn chỉnh theo cùng quy tắc."""

CRITIC = """Nhiệm vụ: kiểm tra kết quả truy vấn SQL cho câu hỏi dưới đây.

Cơ sở dữ liệu:
{schema}

Giá trị thực tế trong dữ liệu:
{profile}

Hôm nay là {today}.
Câu hỏi: {question}

SQL:
```sql
{sql}
```
Kết quả thực tế: {nrows} dòng, các cột {cols}. {auto_flags}
Một số dòng đầu:
{preview}

Kiểm tra từng điểm:
1. SQL có đúng yêu cầu câu hỏi không (cột trả về, phép tính, tử số/mẫu số, sắp xếp, giới hạn)?
2. Join bảng 1-nhiều (order_items, payments, shipments, reviews) có làm nhân dòng khiến SUM/COUNT/AVG bị sai không?
3. Điều kiện trạng thái đơn hàng có khớp ý câu hỏi không?
4. Mốc thời gian: nếu câu hỏi tính theo giờ Việt Nam thì phải quy đổi từ UTC trước khi cắt ngày/tháng/năm.
5. Giá trị chuỗi dùng trong WHERE có khớp giá trị thực tế, có cách viết khác cùng nghĩa bị bỏ sót không?
6. Kết quả rỗng, NULL hoặc bất thường?

Chỉ trả về JSON: {{"verdict": "ok" | "revise", "issues": "mô tả ngắn các lỗi cần sửa (để trống nếu ok)"}}"""

EXPLAIN = """Nhiệm vụ: diễn giải kết quả truy vấn cho người dùng không rành kỹ thuật.

Câu hỏi: {question}
SQL đã chạy:
```sql
{sql}
```
Kết quả ({nrows} dòng), cột {cols}:
{preview}

Trả lời bằng tiếng Việt, tối đa 4 câu, nêu số liệu chính. Nếu có giả định quan trọng (định nghĩa doanh thu, múi giờ, trạng thái đơn) thì nói rõ."""


@dataclass
class PipelineConfig:
    router: bool = True
    schema_select: bool = False
    value_profile: bool = True
    max_retries: int = 2
    critic_rounds: int = 1
    explain: bool = False


PRESETS = {
    "p0_baseline": None,                                        # BaselineAgent, không retry
    "p0b_baseline_retry2": "baseline_retry2",                    # BaselineAgent + tự sửa lỗi
    "p1_router": PipelineConfig(value_profile=False, max_retries=0, critic_rounds=0),
    "p2_profile": PipelineConfig(max_retries=0, critic_rounds=0),
    "p3_selfcorrect": PipelineConfig(max_retries=2, critic_rounds=0),
    "p4_critic": PipelineConfig(max_retries=2, critic_rounds=1),
    "p5_full": PipelineConfig(schema_select=True, max_retries=2, critic_rounds=1),
}


def make_agent(preset: str, llm: LLM, explain: bool = False):
    if preset == "p0_baseline":
        return BaselineAgent(llm, max_retries=0)
    if preset == "p0b_baseline_retry2":
        return BaselineAgent(llm, max_retries=2)
    cfg = PRESETS[preset]
    if explain:
        cfg = PipelineConfig(**{**cfg.__dict__, "explain": True})
    return PipelineAgent(llm, cfg)


def parse_json(text: str):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _preview(rows, n=8):
    return "\n".join(str(tuple(r)) for r in rows[:n]) or "(không có dòng nào)"


class PipelineAgent:
    def __init__(self, llm: LLM, cfg: PipelineConfig | None = None):
        self.llm = llm
        self.cfg = cfg or PipelineConfig()
        self.today = AS_OF_DATE.strftime("%d/%m/%Y")

    # ---- tiện ích ----
    def _call(self, res: AgentResult, step: str, prompt: str):
        out = self.llm.generate(prompt, system=SYSTEM)
        res.attempts += 1
        res.in_tokens += out.in_tokens
        res.out_tokens += out.out_tokens
        res.latency_s += out.latency_s
        res.trace.append({"step": step, "in_tokens": out.in_tokens, "out_tokens": out.out_tokens,
                          "cached": out.cached, "output": out.text.strip()[:700]})
        return out

    def _sql_step(self, res, base, step, sql=None, feedback=None):
        prompt = base if feedback is None else REVISE.format(base=base, sql=sql, feedback=feedback)
        return parse_response(self._call(res, step, prompt).text)

    # ---- luồng chính ----
    def answer(self, question: str) -> AgentResult:
        cfg, res = self.cfg, AgentResult(behavior="error")
        tables = all_tables()

        if cfg.router:
            schema_all = load_schema_for_prompt()
            prof_all = profile_for() if cfg.value_profile else ""
            d = parse_json(self._call(res, "router", ROUTER.format(
                schema=schema_all, profile=prof_all, today=self.today, question=question)).text)
            rtype = (d or {}).get("type", "answer")
            if rtype == "clarify":
                res.behavior, res.message = "clarify", str((d or {}).get("message", ""))
                return res
            if rtype == "cannot_answer":
                res.behavior, res.message = "cannot_answer", str((d or {}).get("message", ""))
                return res

        if cfg.schema_select:
            d = parse_json(self._call(res, "selector", SELECTOR.format(
                schema=load_schema_for_prompt(), question=question)).text)
            chosen = [t for t in (d or {}).get("tables", []) if t in tables]
            tables = chosen or tables

        schema = load_schema_for_prompt(tables)
        profile = profile_for(tables) if cfg.value_profile else "(không có)"
        base = SQL_PROMPT.format(schema=schema, profile=profile, today=self.today, question=question,
                                 rules=RULES_BASE if cfg.router else RULES_NO_ROUTER)

        # --- SQL agent + self-correction ---
        kind, payload = self._sql_step(res, base, "sql")
        err = None
        for attempt in range(cfg.max_retries + 1):
            if kind == "clarify":
                res.behavior, res.message = "clarify", payload
                return res
            if kind == "cannot":
                res.behavior, res.message = "cannot_answer", payload
                return res
            if kind == "none":
                err, shown = "Model không trả về SQL hợp lệ.", "(không có)"
            else:
                res.sql, shown = payload, payload
                try:
                    res.cols, res.rows = run_sql(payload)
                    err = None
                    break
                except (UnsafeSQL, duckdb.Error, TimeoutError) as e:
                    err = f"{type(e).__name__}: {e}"
            if attempt < cfg.max_retries:
                kind, payload = self._sql_step(res, base, "sql_fix", shown, f"SQL này bị lỗi khi chạy:\n{err}")
        if err:
            res.behavior, res.message = "error", err
            return res
        res.behavior = "answer"

        # --- Critic ---
        for _ in range(cfg.critic_rounds):
            flags = []
            if not res.rows:
                flags.append("CẢNH BÁO: kết quả rỗng.")
            elif all(c is None for r in res.rows for c in r):
                flags.append("CẢNH BÁO: toàn bộ giá trị là NULL.")
            d = parse_json(self._call(res, "critic", CRITIC.format(
                schema=schema, profile=profile, today=self.today, question=question, sql=res.sql,
                nrows=len(res.rows), cols=res.cols, auto_flags=" ".join(flags),
                preview=_preview(res.rows))).text)
            if not d or d.get("verdict") != "revise":
                break
            kind, payload = self._sql_step(res, base, "sql_revise", res.sql,
                                           f"Người kiểm tra chỉ ra vấn đề với SQL này: {d.get('issues', '')}")
            if kind != "sql":
                break
            try:
                cols, rows = run_sql(payload)
            except (UnsafeSQL, duckdb.Error, TimeoutError):
                break                                            # bản sửa lỗi -> giữ kết quả cũ
            res.sql, res.cols, res.rows = payload, cols, rows

        # --- Explainer (tuỳ chọn) ---
        if cfg.explain:
            res.answer_text = self._call(res, "explain", EXPLAIN.format(
                question=question, sql=res.sql, nrows=len(res.rows), cols=res.cols,
                preview=_preview(res.rows, 20))).text.strip()
        return res
