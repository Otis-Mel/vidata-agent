"""Chạy nhiều preset trên cùng bộ câu hỏi và xuất bảng ablation.

    python scripts/run_ablation.py                         # tất cả preset, split dev
    python scripts/run_ablation.py --presets p0_baseline p4_critic
    python scripts/run_ablation.py --split test            # CHỈ chạy 1 lần khi đã chốt cấu hình cuối

Kết quả: eval/results/ablation_<split>.md (+ file chi tiết cho từng preset).
Cache LLM dùng chung nên chạy lại rất rẻ. Nếu bị rate limit: đặt LLM_MIN_INTERVAL trong .env.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_eval  # noqa: E402
from src.agents.multi import PRESETS, make_agent  # noqa: E402
from src.llm import LLM  # noqa: E402

DESC = {
    "p0_baseline": "Single-agent, 1 prompt",
    "p0b_baseline_retry2": "Single-agent + tự sửa lỗi SQL (2 lần)",
    "p1_router": "+ Router (hỏi lại / từ chối)",
    "p2_profile": "+ Hồ sơ giá trị dữ liệu",
    "p3_selfcorrect": "+ Tự sửa lỗi SQL (2 lần)",
    "p4_critic": "+ Critic (1 vòng)",
    "p5_full": "+ Chọn bảng (schema selector)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(ROOT / "eval" / "questions.jsonl"))
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--presets", nargs="+", default=list(PRESETS), choices=list(PRESETS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "results"), help="thư mục lưu kết quả, vd eval/results/lite khi đổi model")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    qs = run_eval.load_questions(args.questions)
    if args.split != "all":
        qs = [q for q in qs if q.get("split", "dev") == args.split]
    qs = qs[: args.limit]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for preset in args.presets:
        print(f"\n=== {preset} ({len(qs)} câu, split={args.split}) ===")
        llm = LLM(use_cache=not args.no_cache)
        records = run_eval.run(make_agent(preset, llm), qs)
        s = run_eval.summarize(records, f"{preset}_{args.split}", llm.model, preset, llm.stats)
        (out / f"{preset}_{args.split}.json").write_text(
            json.dumps({"summary": s, "records": records}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (out / f"{preset}_{args.split}.md").write_text(run_eval.to_markdown(s, records), encoding="utf-8")
        rows.append(s)

    pct = lambda x: "n/a" if x != x else f"{x:.1%}"  # noqa: E731
    L = [f"# Ablation (split={args.split}, {len(qs)} câu, model `{rows[0]['model']}`)", "",
         "| Cấu hình | Mô tả | Exec acc | Lỗi SQL | Sai kết quả | Hỏi lại đúng | Từ chối đúng | Lần gọi LLM/câu | Độ trễ/câu (s) | Token vào+ra/câu |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for s in rows:
        L.append(f"| `{s['preset']}` | {DESC.get(s['preset'], '')} | **{pct(s['execution_accuracy'])}** | "
                 f"{pct(s['exec_error_rate'])} | {pct(s['wrong_result_rate'])} | {pct(s['ambiguous_accuracy'])} | "
                 f"{pct(s['out_of_scope_accuracy'])} | {s['avg_attempts']:.2f} | {s['avg_latency_s']:.1f} | "
                 f"{s['avg_in_tokens'] + s['avg_out_tokens']:.0f} |")
    L += ["", "_Độ trễ lấy từ lần gọi thật đầu tiên (cache lưu lại độ trễ gốc)._"]
    (out / f"ablation_{args.split}.md").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))


if __name__ == "__main__":
    main()
