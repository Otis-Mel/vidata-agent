"""So sánh từng câu giữa hai cấu hình: câu nào được cứu, câu nào bị làm hỏng.

    python scripts/compare_runs.py p0_baseline p2_profile
    python scripts/compare_runs.py p2_profile p4_critic --split dev

Đọc eval/results/<preset>_<split>.json (do run_eval/run_ablation ghi). Kèm kiểm định dấu (sign test) cho các câu
khác nhau giữa hai cấu hình, để biết chênh lệch có đáng tin hay chỉ là nhiễu của bộ eval nhỏ.
"""
import argparse
import json
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sign_test_p(fixed: int, broken: int) -> float:
    """p-value hai phía (đúng) của kiểm định dấu: giả thuyết không = hai cấu hình như nhau."""
    n = fixed + broken
    if n == 0:
        return 1.0
    k = min(fixed, broken)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def load(results_dir: Path, preset: str, split: str):
    path = results_dir / f"{preset}_{split}.json"
    if not path.exists():
        sys.exit(f"Không thấy {path}. Chạy run_eval/run_ablation cho preset này trước.")
    return {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["records"]}


def compare(a: dict, b: dict):
    ids = [i for i in a if i in b]
    fixed = [i for i in ids if not a[i]["correct"] and b[i]["correct"]]
    broken = [i for i in ids if a[i]["correct"] and not b[i]["correct"]]
    both_ok = [i for i in ids if a[i]["correct"] and b[i]["correct"]]
    both_bad = [i for i in ids if not a[i]["correct"] and not b[i]["correct"]]
    return ids, fixed, broken, both_ok, both_bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", help="cấu hình gốc, vd p0_baseline")
    ap.add_argument("b", help="cấu hình so sánh, vd p2_profile")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--results-dir", default=str(ROOT / "eval" / "results"))
    args = ap.parse_args()

    ra, rb = load(Path(args.results_dir), args.a, args.split), load(Path(args.results_dir), args.b, args.split)
    ids, fixed, broken, both_ok, both_bad = compare(ra, rb)
    print(f"{args.a} -> {args.b}  (split={args.split}, {len(ids)} câu)")
    print(f"  đúng ở cả hai: {len(both_ok)} | sai ở cả hai: {len(both_bad)}")
    print(f"  ĐƯỢC CỨU (sai -> đúng): {len(fixed)} | BỊ LÀM HỎNG (đúng -> sai): {len(broken)}")
    print(f"  kiểm định dấu: p = {sign_test_p(len(fixed), len(broken)):.3f}"
          f"  ({'có ý nghĩa' if sign_test_p(len(fixed), len(broken)) < 0.05 else 'CHƯA đủ bằng chứng, có thể chỉ là nhiễu'})")
    for title, group, src in (("Được cứu", fixed, ra), ("Bị làm hỏng", broken, rb)):
        if group:
            print(f"\n{title}:")
            for i in group:
                r = src[i]
                print(f"  {i:<4} ({r['type']}, {r['difficulty']}) lý do khi sai: {r['reason'][:90]}")
    if both_bad:
        print("\nVẫn sai ở cả hai (đáng đọc nhất):")
        for i in both_bad:
            print(f"  {i:<4} {rb[i]['reason'][:100]}")


if __name__ == "__main__":
    main()
