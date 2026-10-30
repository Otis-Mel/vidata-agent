"""Kiểm tra độ nhạy của bộ eval: nếu agent mắc đúng lỗi "ngây thơ" (quên đổi múi giờ, quên lọc trạng thái đơn,
bỏ sót cách viết tên tỉnh), bộ chấm có phát hiện ra không?

Cách làm: lấy gold SQL của mỗi câu có bẫy tương ứng, cố ý làm hỏng nó theo đúng kiểu lỗi đó, chạy, rồi chấm bằng chính bộ chấm.
  - Kết quả thay đổi  -> câu hỏi NHẠY với lỗi này (nếu agent mắc lỗi, sẽ bị bắt).
  - Kết quả y hệt     -> câu hỏi KHÔNG phân biệt được agent đúng với agent mắc lỗi (bẫy vô hiệu với câu này).
Không gọi LLM, chạy trong vài giây:  python scripts/trap_check.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.db import run_sql  # noqa: E402
from src.eval_utils import requires_order, results_match  # noqa: E402

HCM_FULL = "('TP. Hồ Chí Minh','HCM','TP.HCM','Sài Gòn','Ho Chi Minh')"
HN_FULL = "('Hà Nội','HN','Ha Noi','Hanoi')"


def m_timezone(sql):       # quên đổi múi giờ: UTC thay vì giờ Việt Nam
    return sql.replace("INTERVAL 7 HOUR", "INTERVAL 0 HOUR") if "INTERVAL 7 HOUR" in sql else None


def m_status(sql):         # quên lọc trạng thái đơn hoàn thành
    new = re.sub(r"(?:o\.)?status\s*=\s*'completed'", "1=1", sql)
    return new if new != sql else None


def m_province(sql):       # chỉ dùng cách viết chuẩn của tên tỉnh
    new = sql.replace("IN " + HCM_FULL, "IN ('TP. Hồ Chí Minh')").replace("IN " + HN_FULL, "IN ('Hà Nội')")
    new = new.replace("province IN ('HCM','TP.HCM','Sài Gòn','Ho Chi Minh','HN','Ha Noi','Hanoi')", "province IN ('HCM')")
    return new if new != sql else None


MUTATIONS = {"timezone": m_timezone, "status_filter": m_status, "province_variants": m_province}


def main():
    qs = [json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    stats = {k: {"sensitive": [], "blind": [], "error": []} for k in MUTATIONS}
    for q in qs:
        if q["type"] != "answerable":
            continue
        for trap, mut in MUTATIONS.items():
            if trap not in q.get("traps", []):
                continue
            bad_sql = mut(q["gold_sql"])
            if bad_sql is None:
                continue
            gold_rows = run_sql(q["gold_sql"])[1]
            try:
                bad_rows = run_sql(bad_sql)[1]
            except Exception:  # noqa: BLE001
                stats[trap]["error"].append(q["id"])
                continue
            same = results_match(gold_rows, bad_rows, requires_order(q["question"]))
            stats[trap]["blind" if same else "sensitive"].append(q["id"])

    print("ĐỘ NHẠY CỦA BỘ EVAL: nếu agent mắc lỗi ngây thơ, câu nào BẮT được?\n")
    for trap, s in stats.items():
        n = len(s["sensitive"]) + len(s["blind"]) + len(s["error"])
        print(f"- {trap}: {len(s['sensitive'])}/{n} câu bắt được lỗi")
        if s["blind"]:
            print(f"    KHÔNG bắt được (kết quả không đổi khi mắc lỗi): {', '.join(s['blind'])}")
        if s["error"]:
            print(f"    SQL hỏng bị lỗi khi chạy (agent sẽ bị tính là lỗi SQL): {', '.join(s['error'])}")


if __name__ == "__main__":
    main()
