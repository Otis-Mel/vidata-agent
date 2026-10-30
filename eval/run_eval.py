"""Chạy agent trên bộ câu hỏi, chấm điểm, xuất báo cáo.

Ví dụ:
    python eval/run_eval.py --preset p0_baseline                  # baseline thuần (split dev)
    python eval/run_eval.py --preset p4_critic --split dev
    python eval/run_eval.py --preset p5_full --split test         # chỉ chạy test khi đã chốt cấu hình!
    python eval/run_eval.py --preset p0_baseline --limit 3 --no-cache
Preset: xem PRESETS trong src/agents/multi.py

Kết quả: eval/results/<name>.json (chi tiết từng câu) và eval/results/<name>.md (bảng tóm tắt).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.multi import PRESETS, make_agent  # noqa: E402
from src.db import run_sql  # noqa: E402
from src.eval_utils import judge  # noqa: E402
from src.llm import LLM  # noqa: E402


def load_questions(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def run(agent, questions, llm=None, verbose=True):
    records = []
    for i, q in enumerate(questions, 1):
        gold_rows = None
        if q.get("gold_sql"):
            _, gold_rows = run_sql(q["gold_sql"])
        try:
            res = agent.answer(q["question"])
        except Exception as e:  # lỗi hạ tầng (key sai, mất mạng...) -> ghi lại, không làm sập cả lượt eval
            from src.agents.baseline import AgentResult
            res = AgentResult(behavior="error", message=f"AGENT_CRASH {type(e).__name__}: {e}")
        ok, reason = judge(q, res, gold_rows)
        records.append({
            "id": q["id"], "type": q["type"], "difficulty": q["difficulty"], "traps": q.get("traps", []),
            "question": q["question"], "correct": ok, "reason": reason, "behavior": res.behavior,
            "pred_sql": res.sql, "gold_sql": q.get("gold_sql"), "message": res.message,
            "attempts": res.attempts, "in_tokens": res.in_tokens, "out_tokens": res.out_tokens,
            "latency_s": round(res.latency_s, 2),
        })
        if verbose:
            print(f"[{i}/{len(questions)}] {q['id']:<5} {'PASS' if ok else 'FAIL'}  {reason[:90]}")
    return records


def _acc(rs):
    return (sum(r["correct"] for r in rs) / len(rs)) if rs else float("nan")


def summarize(records, name, model, preset, llm_stats=None):
    ans = [r for r in records if r["type"] == "answerable"]
    summary = {
        "name": name, "model": model, "preset": preset, "n": len(records),
        "execution_accuracy": _acc(ans),
        "exec_error_rate": (sum(r["behavior"] == "error" for r in ans) / len(ans)) if ans else float("nan"),
        "wrong_result_rate": (sum(r["reason"] == "wrong_result" for r in ans) / len(ans)) if ans else float("nan"),
        "ambiguous_accuracy": _acc([r for r in records if r["type"] == "ambiguous"]),
        "out_of_scope_accuracy": _acc([r for r in records if r["type"] == "out_of_scope"]),
        "avg_attempts": sum(r["attempts"] for r in records) / len(records),
        "avg_latency_s": sum(r["latency_s"] for r in records) / len(records),
        "avg_in_tokens": sum(r["in_tokens"] for r in records) / len(records),
        "avg_out_tokens": sum(r["out_tokens"] for r in records) / len(records),
        "llm_stats": llm_stats or {},
    }
    by_diff, by_trap = defaultdict(list), defaultdict(list)
    for r in ans:
        by_diff[r["difficulty"]].append(r)
        for t in r["traps"]:
            by_trap[t].append(r)
    summary["by_difficulty"] = {k: {"acc": _acc(v), "n": len(v)} for k, v in by_diff.items()}
    summary["by_trap"] = {k: {"acc": _acc(v), "n": len(v)} for k, v in by_trap.items()}
    return summary


def to_markdown(s, records):
    pct = lambda x: "n/a" if x != x else f"{x:.1%}"  # noqa: E731
    L = [f"# Báo cáo eval: {s['name']}", "",
         f"- Model: `{s['model']}` | preset: `{s['preset']}` | số câu: {s['n']}", "",
         "## Tổng quan", "", "| Metric | Giá trị |", "|---|---|",
         f"| Execution accuracy (câu trả lời được) | **{pct(s['execution_accuracy'])}** |",
         f"| Tỉ lệ lỗi SQL | {pct(s['exec_error_rate'])} |",
         f"| Tỉ lệ SQL chạy được nhưng sai kết quả | {pct(s['wrong_result_rate'])} |",
         f"| Hỏi làm rõ đúng (câu mơ hồ) | {pct(s['ambiguous_accuracy'])} |",
         f"| Từ chối đúng (câu ngoài phạm vi) | {pct(s['out_of_scope_accuracy'])} |",
         f"| Số lần gọi LLM / câu (TB) | {s['avg_attempts']:.2f} |",
         f"| Độ trễ / câu (TB, giây) | {s['avg_latency_s']:.2f} |",
         f"| Token vào / ra mỗi câu (TB) | {s['avg_in_tokens']:.0f} / {s['avg_out_tokens']:.0f} |", "",
         "## Theo độ khó", "", "| Độ khó | Accuracy | Số câu |", "|---|---|---|"]
    L += [f"| {k} | {pct(v['acc'])} | {v['n']} |" for k, v in s["by_difficulty"].items()]
    L += ["", "## Theo loại bẫy", "", "| Bẫy | Accuracy | Số câu |", "|---|---|---|"]
    L += [f"| {k} | {pct(v['acc'])} | {v['n']} |" for k, v in sorted(s["by_trap"].items())]
    fails = [r for r in records if not r["correct"]]
    L += ["", f"## Câu sai ({len(fails)})", ""]
    for r in fails:
        L += [f"**{r['id']}** ({r['type']}, {r['difficulty']}) — {r['question']}", f"- Lý do: {r['reason']}"]
        if r["pred_sql"]:
            L += ["- SQL agent:", "```sql", r["pred_sql"], "```"]
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(ROOT / "eval" / "questions.jsonl"))
    ap.add_argument("--preset", default="p0_baseline", choices=list(PRESETS))
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--name", default=None, help="tên file kết quả (mặc định: <preset>_<split>)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "results"), help="thư mục lưu kết quả (dùng khi so sánh nhiều model)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    if args.split != "all":
        questions = [q for q in questions if q.get("split", "dev") == args.split]
    questions = questions[: args.limit]
    name = args.name or f"{args.preset}_{args.split}"
    llm = LLM(use_cache=not args.no_cache)
    agent = make_agent(args.preset, llm)
    records = run(agent, questions)
    summary = summarize(records, name, llm.model, args.preset, llm.stats)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps({"summary": summary, "records": records},
                                                     ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / f"{name}.md").write_text(to_markdown(summary, records), encoding="utf-8")
    print(f"\nExecution accuracy: {summary['execution_accuracy']:.1%} | báo cáo: {out / (name + '.md')}")


if __name__ == "__main__":
    main()
