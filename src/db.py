"""Thực thi SQL an toàn cho agent: read-only, chỉ SELECT/WITH, giới hạn dòng, có timeout."""
import re
import threading
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "ecommerce.duckdb"
MAX_ROWS = 1000
TIMEOUT_S = 10
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|install|load|export|call)\b", re.I)


class UnsafeSQL(Exception):
    pass


def validate(sql: str) -> str:
    s = sql.strip().rstrip(";")
    if ";" in s:
        raise UnsafeSQL("Chỉ cho phép 1 câu lệnh.")
    if not re.match(r"^\s*(select|with)\b", s, re.I):
        raise UnsafeSQL("Chỉ cho phép SELECT/WITH.")
    if _FORBIDDEN.search(s):
        raise UnsafeSQL("Phát hiện từ khoá không được phép.")
    return s


def run_sql(sql: str, max_rows: int = MAX_ROWS, timeout: int = TIMEOUT_S):
    """Trả về (columns, rows). Ném UnsafeSQL / duckdb.Error / TimeoutError."""
    s = validate(sql)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    out = {}

    def _work():
        try:
            cur = con.execute(s)
            out["cols"] = [d[0] for d in cur.description]
            out["rows"] = cur.fetchmany(max_rows)
        except Exception as e:  # noqa: BLE001
            out["err"] = e

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        con.interrupt()
        con.close()
        raise TimeoutError(f"SQL chạy quá {timeout}s")
    con.close()
    if "err" in out:
        raise out["err"]
    return out["cols"], out["rows"]
