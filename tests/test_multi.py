"""Test multi-agent pipeline bằng LLM giả. Chạy: python tests/test_multi.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import src.llm as llm_mod  # noqa: E402
from src.agents.multi import PRESETS, PipelineAgent, PipelineConfig, make_agent  # noqa: E402
from src.llm import LLM  # noqa: E402
import run_eval  # noqa: E402

llm_mod.CACHE_DIR = Path(tempfile.mkdtemp())
Q = {q["id"]: q for q in run_eval.load_questions(ROOT / "eval" / "questions.jsonl")}
assert len(Q) == 101 and {q["split"] for q in Q.values()} == {"dev", "test"}
GOLD = lambda i: f"```sql\n{Q[i]['gold_sql']}\n```"  # noqa: E731
WRONG = "```sql\nSELECT COUNT(*) FROM products WHERE price < 0\n```"


def make_llm(script, log):
    """script: dict marker->callable(qid, prompt)->text. Ghi lại mọi prompt vào log."""
    def prov(prompt, system, temperature, model):
        qid = next(i for i, q in Q.items() if q["question"] in prompt)
        step = ("router" if "Nhiệm vụ: phân loại" in prompt else "selector" if "Nhiệm vụ: chọn bảng" in prompt
                else "critic" if "Nhiệm vụ: kiểm tra" in prompt else "explain" if "Nhiệm vụ: diễn giải" in prompt
                else "sql_retry" if "bị lỗi khi chạy" in prompt else "sql_revise" if "Người kiểm tra chỉ ra" in prompt else "sql")
        log.append((step, prompt))
        return script[step](qid, prompt), 10, 5
    return LLM(provider=prov, model=f"fake-{id(log)}")


steps = lambda r: [t["step"] for t in r.trace]  # noqa: E731

# 1) Router: clarify / cannot_answer / answer (và JSON hỏng -> mặc định answer)
log = []
route = {"a02": '{"type":"clarify","message":"Doanh thu gộp hay thuần?"}',
         "o02": 'Đây là kết quả: {"type":"cannot_answer","message":"không có dữ liệu truy cập"}',
         "e01": "not json at all"}
llm = make_llm({"router": lambda q, p: route[q], "sql": lambda q, p: GOLD(q)}, log)
ag = PipelineAgent(llm, PipelineConfig(max_retries=0, critic_rounds=0))
r = ag.answer(Q["a02"]["question"]); assert r.behavior == "clarify" and steps(r) == ["router"]
r = ag.answer(Q["o02"]["question"]); assert r.behavior == "cannot_answer"
r = ag.answer(Q["e01"]["question"]); assert r.behavior == "answer" and r.rows == [(6000,)]
print("router OK")

# 2) Hồ sơ giá trị: có/không có trong prompt SQL
log = []
llm = make_llm({"router": lambda q, p: '{"type":"answer"}', "sql": lambda q, p: GOLD(q)}, log)
PipelineAgent(llm, PipelineConfig(value_profile=True, max_retries=0, critic_rounds=0)).answer(Q["m08"]["question"])
sql_prompt = [p for s, p in log if s == "sql"][0]
assert "'Sài Gòn'" in sql_prompt and "'HCM'" in sql_prompt
log2 = []
llm = make_llm({"router": lambda q, p: '{"type":"answer"}', "sql": lambda q, p: GOLD(q)}, log2)
PipelineAgent(llm, PipelineConfig(value_profile=False, max_retries=0, critic_rounds=0)).answer(Q["m08"]["question"])
assert "'Sài Gòn'" not in [p for s, p in log2 if s == "sql"][0]
print("value profile OK")

# 3) Schema selector: chỉ giữ bảng hợp lệ, prompt SQL chỉ chứa bảng đã chọn
log = []
llm = make_llm({"router": lambda q, p: '{"type":"answer"}', "selector": lambda q, p: '{"tables":["customers","bogus"]}',
                "sql": lambda q, p: GOLD(q)}, log)
PipelineAgent(llm, PipelineConfig(schema_select=True, max_retries=0, critic_rounds=0)).answer(Q["m08"]["question"])
sp = [p for s, p in log if s == "sql"][0]
assert "CREATE TABLE customers" in sp and "CREATE TABLE reviews" not in sp and "bogus" not in sp
print("schema selector OK")

# 4) Self-correction: SQL lỗi -> gửi lỗi lại -> sửa được; hết lượt thì báo lỗi
log = []
bad = "```sql\nSELECT COUNT(*) FORM customers\n```"
llm = make_llm({"router": lambda q, p: '{"type":"answer"}',
                "sql": lambda q, p: bad, "sql_retry": lambda q, p: GOLD(q)}, log)
r = PipelineAgent(llm, PipelineConfig(max_retries=2, critic_rounds=0)).answer(Q["e01"]["question"])
assert r.behavior == "answer" and steps(r) == ["router", "sql", "sql_fix"], steps(r)
retry_prompt = [p for s, p in log if s == "sql_retry"][0]
assert "FORM customers" in retry_prompt and "Error" in retry_prompt   # SQL cũ + thông báo lỗi được gửi lại
llm = make_llm({"router": lambda q, p: '{"type":"answer"}', "sql": lambda q, p: bad, "sql_retry": lambda q, p: bad}, [])
r = PipelineAgent(llm, PipelineConfig(max_retries=2, critic_rounds=0)).answer(Q["e01"]["question"])
assert r.behavior == "error" and r.attempts == 4   # router + sql + 2 lần sửa
print("self-correction OK")

# 5) Critic: sửa sai -> đúng; critic trả rác -> giữ kết quả; bản sửa lỗi -> giữ kết quả cũ
cfg = PipelineConfig(max_retries=0, critic_rounds=1)
base = {"router": lambda q, p: '{"type":"answer"}', "sql": lambda q, p: WRONG}
llm = make_llm({**base, "critic": lambda q, p: '{"verdict":"revise","issues":"sai điều kiện"}', "sql_revise": lambda q, p: GOLD("e01")}, [])
r = PipelineAgent(llm, cfg).answer(Q["e01"]["question"])
assert steps(r) == ["router", "sql", "critic", "sql_revise"] and r.rows == [(6000,)]
llm = make_llm({**base, "critic": lambda q, p: "blah blah"}, [])
r = PipelineAgent(llm, cfg).answer(Q["e01"]["question"]); assert r.rows == [(0,)] and steps(r)[-1] == "critic"
llm = make_llm({**base, "critic": lambda q, p: '{"verdict":"revise","issues":"x"}', "sql_revise": lambda q, p: "```sql\nSELECT 1 FORM x\n```"}, [])
r = PipelineAgent(llm, cfg).answer(Q["e01"]["question"]); assert r.rows == [(0,)] and r.behavior == "answer"
# critic ok -> không sửa; kết quả rỗng được gắn cờ trong prompt critic
log = []
llm = make_llm({**base, "sql": lambda q, p: "```sql\nSELECT * FROM products WHERE price < 0\n```",
                "critic": lambda q, p: '{"verdict":"ok","issues":""}'}, log)
PipelineAgent(llm, cfg).answer(Q["e01"]["question"])
assert "kết quả rỗng" in [p for s, p in log if s == "critic"][0]
print("critic OK")

# 6) Explainer + khi router tắt thì SQL agent vẫn có thể CLARIFY/CANNOT_ANSWER
llm = make_llm({"router": lambda q, p: '{"type":"answer"}', "sql": lambda q, p: GOLD(q), "explain": lambda q, p: "Có 6000 khách."}, [])
r = PipelineAgent(llm, PipelineConfig(max_retries=0, critic_rounds=0, explain=True)).answer(Q["e01"]["question"])
assert r.answer_text == "Có 6000 khách." and steps(r)[-1] == "explain"
llm = make_llm({"sql": lambda q, p: "CLARIFY: bạn muốn quý nào?"}, [])
r = PipelineAgent(llm, PipelineConfig(router=False, max_retries=0, critic_rounds=0)).answer(Q["a02"]["question"])
assert r.behavior == "clarify" and steps(r) == ["sql"]
print("explainer / no-router OK")

# 7) Mọi preset dựng được; chạy cả bộ eval 53 câu bằng LLM giả "oracle" và chấm điểm
for name in PRESETS:
    make_agent(name, LLM(provider=lambda *a: ("", 0, 0), model="x"))
def oracle(prompt, system, temperature, model):
    qid = next(i for i, q in Q.items() if q["question"] in prompt)
    q = Q[qid]
    if "Nhiệm vụ: phân loại" in prompt:
        t = {"answerable": "answer", "ambiguous": "clarify", "out_of_scope": "cannot_answer"}[q["type"]]
        return json.dumps({"type": t, "message": "m"}), 1, 1
    if "Nhiệm vụ: kiểm tra" in prompt:
        return '{"verdict":"ok","issues":""}', 1, 1
    return GOLD(qid), 1, 1
llm = LLM(provider=oracle, model="oracle")
recs = run_eval.run(make_agent("p4_critic", llm), list(Q.values()), verbose=False)
s = run_eval.summarize(recs, "oracle", "oracle", "p4_critic", llm.stats)
bad = [(r["id"], r["reason"]) for r in recs if not r["correct"]]
assert not bad, bad                       # gold SQL tự chấm đúng 100% -> bộ chấm không có lỗi
assert s["execution_accuracy"] == 1.0 and s["ambiguous_accuracy"] == 1.0 and s["out_of_scope_accuracy"] == 1.0
print(f"oracle full-eval OK ({len(recs)} câu, tự chấm 100%)")
print("\nTẤT CẢ TEST MULTI-AGENT PASS")
