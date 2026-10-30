"""So sánh kết quả SQL (execution accuracy) và phân loại hành vi cho câu không trả lời được."""
import re
from datetime import date, datetime
from decimal import Decimal

_MONTH_STR = re.compile(r"^\d{4}-\d{2}$")                     # '2025-03'  == đầu tháng 3/2025
_MIDNIGHT_STR = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]00:00:00(\.0+)?$")  # '2025-03-01 00:00:00' == ngày 2025-03-01


def _norm(v):
    """Chuẩn hoá giá trị để so sánh. Ngày/tháng được quy về dạng 'YYYY-MM-DD' vì 'tháng 3/2025' có thể được
    biểu diễn là '2025-03', một timestamp đầu tháng hay một DATE; các cách này cùng nghĩa."""
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else str(v)
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if _MONTH_STR.match(s):
        return s + "-01"
    m = _MIDNIGHT_STR.match(s)
    return m.group(1) if m else s


def norm_rows(rows):
    return [tuple(_norm(c) for c in r) for r in rows]


def _cell_equal(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(0.01, 1e-4 * max(abs(a), abs(b)))
    return a == b


def _sort_key(row):
    return tuple("" if c is None else (f"{round(c, 1):020.1f}" if isinstance(c, float) else str(c)) for c in row)


def has_order_by(sql: str) -> bool:
    return bool(re.search(r"\border\s+by\b", sql or "", re.I))


def requires_order(question_text: str) -> bool:
    """Chỉ so thứ tự dòng khi CÂU HỎI yêu cầu sắp xếp (có chữ 'xếp'). Nếu không, thứ tự dòng không phải
    là một phần của đáp án (trước đây dùng ORDER BY của gold nên phạt oan agent, vd câu m03)."""
    return bool(re.search(r"\bxếp\b", question_text or "", re.I))


def results_match(gold_rows, pred_rows, ordered: bool) -> bool:
    g, p = norm_rows(gold_rows), norm_rows(pred_rows)
    if len(g) != len(p):
        return False
    if g and len(g[0]) != len(p[0]):
        return False
    if not ordered:
        g, p = sorted(g, key=_sort_key), sorted(p, key=_sort_key)
    return all(len(a) == len(b) and all(_cell_equal(x, y) for x, y in zip(a, b)) for a, b in zip(g, p))


def judge(question: dict, result, gold_rows=None) -> tuple[bool, str]:
    """-> (đúng?, lý do). `result` là AgentResult."""
    qtype = question["type"]
    if qtype == "answerable":
        if result.behavior == "error":
            return False, f"exec_error: {result.message}"
        if result.behavior in ("clarify", "cannot_answer"):
            return False, f"từ chối nhầm ({result.behavior}): {result.message}"
        ok = results_match(gold_rows, result.rows, requires_order(question["question"]))
        return ok, "ok" if ok else "wrong_result"
    if qtype == "ambiguous":
        ok = result.behavior == "clarify"
        return ok, "ok" if ok else f"không hỏi làm rõ (behavior={result.behavior})"
    if qtype == "out_of_scope":
        ok = result.behavior == "cannot_answer"
        return ok, "ok" if ok else f"không từ chối (behavior={result.behavior})"
    return False, f"type lạ: {qtype}"
