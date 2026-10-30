"""Hồ sơ dữ liệu tự động: giá trị phân biệt của cột chữ ít giá trị + khoảng thời gian của cột ngày.
Tính từ chính DB (không viết tay) nên agent "nhìn thấy" dữ liệu thật, ví dụ tỉnh có nhiều cách viết."""
from functools import lru_cache

import duckdb

from src.db import DB_PATH

MAX_DISTINCT = 40


@lru_cache(maxsize=1)
def build_profile() -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    cols = con.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                       "WHERE table_schema='main' ORDER BY table_name, ordinal_position").fetchall()
    prof: dict[str, list[str]] = {}
    for t, c, dt in cols:
        if dt == "VARCHAR":
            n = con.execute(f'SELECT COUNT(DISTINCT "{c}") FROM "{t}"').fetchone()[0]
            if 0 < n <= MAX_DISTINCT:
                vals = [r[0] for r in con.execute(
                    f'SELECT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC, 1').fetchall()]
                prof.setdefault(t, []).append(f"{c} nhận các giá trị: " + ", ".join(repr(v) for v in vals))
        elif dt == "DATE" or dt.startswith("TIMESTAMP"):
            lo, hi = con.execute(f'SELECT MIN("{c}"), MAX("{c}") FROM "{t}"').fetchone()
            prof.setdefault(t, []).append(f"{c} từ {lo} đến {hi}")
    con.close()
    return prof


def profile_for(tables: list[str] | None = None) -> str:
    prof = build_profile()
    names = [t for t in prof if not tables or t in tables]
    return "\n".join(f"Bảng {t}:\n" + "\n".join(f"- {l}" for l in prof[t]) for t in names)
