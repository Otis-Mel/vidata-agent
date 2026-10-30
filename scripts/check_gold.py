"""Chạy toàn bộ gold_sql để chắc chắn câu chuẩn thực thi được (và xem kết quả để kiểm tay)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import run_sql

path = Path(sys.argv[1] if len(sys.argv) > 1 else "eval/questions_sample.jsonl")
for line in path.read_text(encoding="utf-8").splitlines():
    q = json.loads(line)
    print(f"[{q['id']}] {q['question']}")
    if not q.get("gold_sql"):
        print(f"   (không có SQL) expected={q['expected_behavior']}\n")
        continue
    cols, rows = run_sql(q["gold_sql"])
    print(f"   cols={cols}")
    for r in rows[:6]:
        print("  ", r)
    print()
