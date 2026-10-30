"""Test pipeline bằng LLM giả (không cần API key). Chạy: python tests/test_pipeline.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import src.llm as llm_mod  # noqa: E402
from src.agents.baseline import BaselineAgent, parse_response  # noqa: E402
from src.eval_utils import results_match  # noqa: E402
from src.llm import LLM  # noqa: E402
from src.schema_text import load_schema_for_prompt  # noqa: E402
import run_eval  # noqa: E402

llm_mod.CACHE_DIR = Path(tempfile.mkdtemp())  # không làm bẩn cache thật
qs = {q["id"]: q for q in run_eval.load_questions(ROOT / "eval" / "questions_sample.jsonl")}


def fake_provider(prompt, system, temperature, model):
    """Mỗi câu hỏi có 1 'hành vi' giả lập khác nhau."""
    def fenced(sql):
        return f"```sql\n{sql}\n```"
    q = next(i for i, x in qs.items() if x["question"] in prompt)
    retry = "bị lỗi khi chạy" in prompt
    if q == "e01":
        out = fenced(qs[q]["gold_sql"])
    elif q == "e02":
        out = fenced("SELECT COUNT(*) FROM orders WHERE status = 'returned'")      # sai kết quả
    elif q == "m01":
        out = fenced(qs[q]["gold_sql"]) if retry else fenced("SELEC SUM(x) FROM orders")  # lỗi, retry thì sửa được
    elif q == "m02":
        out = fenced(qs[q]["gold_sql"].replace("so_don", "n_orders"))               # khác tên cột -> vẫn đúng
    elif q == "m03":
        out = fenced("DROP TABLE orders")                                           # bị chặn
    elif q == "h01":
        out = qs[q]["gold_sql"]                                                     # SQL trần không có fence
    elif q == "h02":
        out = "CANNOT_ANSWER: không có dữ liệu"                                     # từ chối nhầm
    elif q == "a01":
        out = "CLARIFY: Bạn muốn doanh thu gộp hay thuần?"
    elif q == "o01":
        out = "CANNOT_ANSWER: bảng customers không có cột giới tính"
    return out, 100, 20


# --- unit tests nhỏ ---
assert parse_response("```sql\nSELECT 1\n```")[0] == "sql"
assert parse_response("CLARIFY: hỏi lại gì đó")[0] == "clarify"
assert parse_response("`CANNOT_ANSWER: thiếu cột`")[0] == "cannot"
assert parse_response("xin lỗi tôi không biết")[0] == "none"
assert results_match([(1.0, "a")], [(1.004, "a")], ordered=True)
assert not results_match([(1,), (2,)], [(1,), (3,)], ordered=False)
assert results_match([(1,), (2,)], [(2,), (1,)], ordered=False)
assert not results_match([(1,), (2,)], [(2,), (1,)], ordered=True)
schema = load_schema_for_prompt()
assert "BẪY" not in schema and "CREATE TABLE payments" in schema and "UTC" in schema
print("unit tests OK")

# --- baseline thuần (retries=0) ---
llm0 = LLM(provider=fake_provider, model="fake")
recs0 = run_eval.run(BaselineAgent(llm0, max_retries=0), list(qs.values()), verbose=False)
r0 = {r["id"]: r for r in recs0}
expect0 = {"e01": True, "e02": False, "m01": False, "m02": True, "m03": False, "h01": True, "h02": False, "a01": True, "o01": True}
assert {k: v["correct"] for k, v in r0.items()} == expect0, {k: (v["correct"], v["reason"]) for k, v in r0.items()}
assert r0["e02"]["reason"] == "wrong_result" and r0["m01"]["reason"].startswith("exec_error")
assert "UnsafeSQL" in r0["m03"]["reason"] and r0["h02"]["reason"].startswith("từ chối nhầm")
s0 = run_eval.summarize(recs0, "t0", "fake", 0, llm0.stats)
assert abs(s0["execution_accuracy"] - 3 / 7) < 1e-9, s0["execution_accuracy"]   # e01,m02,h01 / 7 câu answerable
assert s0["ambiguous_accuracy"] == 1.0 and s0["out_of_scope_accuracy"] == 1.0
print("baseline (retries=0) OK  acc =", f"{s0['execution_accuracy']:.1%}")

# --- self-correction (retries=1): m01 phải được cứu ---
llm1 = LLM(provider=fake_provider, model="fake2")
recs1 = run_eval.run(BaselineAgent(llm1, max_retries=1), list(qs.values()), verbose=False)
r1 = {r["id"]: r for r in recs1}
assert r1["m01"]["correct"] and r1["m01"]["attempts"] == 2
s1 = run_eval.summarize(recs1, "t1", "fake2", 1, llm1.stats)
assert abs(s1["execution_accuracy"] - 4 / 7) < 1e-9
print("self-correction OK       acc =", f"{s1['execution_accuracy']:.1%}")

# --- cache: chạy lại cùng cấu hình -> 100% cache hit, 0 token mới ---
calls = {"n": 0}
def counting(*a):
    calls["n"] += 1
    return fake_provider(*a)
llm2 = LLM(provider=counting, model="fake3")
run_eval.run(BaselineAgent(llm2), list(qs.values()), verbose=False)
n1 = calls["n"]
llm3 = LLM(provider=counting, model="fake3")
run_eval.run(BaselineAgent(llm3), list(qs.values()), verbose=False)
assert calls["n"] == n1 and llm3.stats["cache_hits"] == len(qs)
print("cache OK")

# --- retry khi lỗi tạm thời (429/503), không retry lỗi khác ---
llm_mod.time.sleep = lambda s: None
seq = {"n": 0}
def flaky(*a):
    seq["n"] += 1
    if seq["n"] <= 2:
        raise RuntimeError("503 UNAVAILABLE: model overloaded")
    return "ok", 1, 1
l = LLM(provider=flaky, model="fake4", use_cache=False)
assert l.generate("x").text == "ok" and l.stats["retries"] == 2
def bad(*a):
    raise ValueError("API key not valid")
try:
    LLM(provider=bad, model="fake5", use_cache=False).generate("x")
    raise SystemExit("lẽ ra phải ném lỗi")
except ValueError:
    pass
print("retry OK")

# --- báo cáo markdown sinh được ---
md = run_eval.to_markdown(s0, recs0)
assert "Execution accuracy" in md and "Câu sai (" in md
# --- regression: GEMINI_MODEL để trống trong .env phải dùng model mặc định (lỗi "model is required") ---
import os
os.environ["GEMINI_MODEL"] = ""
assert LLM(provider=lambda *a: ("", 0, 0)).model == llm_mod.DEFAULT_MODEL
os.environ["GEMINI_MODEL"] = "gemini-x"
assert LLM(provider=lambda *a: ("", 0, 0)).model == "gemini-x"
del os.environ["GEMINI_MODEL"]
print("model env OK")

print("report OK\n\nTẤT CẢ TEST ĐỀU PASS")
