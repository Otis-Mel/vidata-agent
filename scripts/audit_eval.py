"""Soát lỗi thiết kế bộ eval (không gọi LLM):
  - Câu yêu cầu sắp xếp ("xếp") mà cột số trong gold có giá trị TRÙNG và câu hỏi không nêu luật khi bằng nhau
    -> thứ tự các dòng bằng nhau là tuỳ ý, agent đúng vẫn có thể bị chấm sai (đã xảy ra với m11).
Chạy:  python scripts/audit_eval.py     (trả về mã lỗi 1 nếu có câu cần sửa)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.db import run_sql  # noqa: E402
from src.eval_utils import requires_order  # noqa: E402


def audit(questions):
    flagged = []
    for q in questions:
        if q["type"] != "answerable" or not requires_order(q["question"]):
            continue
        cols, rows = run_sql(q["gold_sql"])
        tied = [cols[i] for i in range(len(cols)) if isinstance(rows[0][i], (int, float)) and len({r[i] for r in rows}) < len(rows)]
        if tied and "bằng nhau" not in q["question"]:
            flagged.append((q["id"], f"cột {tied} có giá trị trùng nhưng câu hỏi không nêu luật khi bằng nhau"))
    return flagged


def unspecified_columns(questions):
    """Câu có gold từ 2 cột trở lên mà lời hỏi không có chữ 'trả về': agent phải đoán cột nào cần trả (đã gây lỗi ở m05, h10:
    agent thêm cột id thừa hoặc thiếu cột tiền hàng và bị chấm sai dù giá trị đúng). Chỉ cảnh báo, cần người soát."""
    out = []
    for q in questions:
        if q["type"] == "answerable" and "trả về" not in q["question"].lower():
            cols = run_sql(q["gold_sql"])[0]
            if len(cols) >= 2:
                out.append((q["id"], q.get("split", "?"), cols))
    return out


if __name__ == "__main__":
    qs = [json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = audit(qs)
    for qid, why in bad:
        print(f"CẦN SỬA {qid}: {why}")
    warn = unspecified_columns(qs)
    if warn:
        print(f"\nCẢNH BÁO (không làm audit thất bại): {len(warn)} câu có gold nhiều cột nhưng lời hỏi không nêu cột cần trả về:")
        for qid, split, cols in warn:
            print(f"  {qid:<4} [{split}] gold trả {cols}")
    print("audit OK" if not bad else f"{len(bad)} câu cần sửa")
    sys.exit(1 if bad else 0)
