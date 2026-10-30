"""Tạo mô tả schema để đưa vào prompt.

Chú ý công bằng khi eval: các ghi chú "BẪY" trong schema.sql là ghi chú của người thiết kế dữ liệu,
KHÔNG đưa cho agent (nếu không baseline sẽ được gợi ý đáp án). Các comment mô tả bình thường
(đơn vị, múi giờ UTC, ý nghĩa cột) vẫn được giữ như tài liệu của một DB thật.
"""
import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "schema.sql"
_BLOCK = re.compile(r"CREATE TABLE (\w+) \(.*?\n\);", re.S)


def _clean() -> str:
    out = []
    for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*--\s*BẪY", line):
            continue                                   # dòng comment thuần là gợi ý bẫy
        line = re.sub(r"\s*--\s*BẪY.*$", "", line)     # comment BẪY ở cuối dòng
        out.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def all_tables() -> list[str]:
    return _BLOCK.findall(_clean()) and [m.group(1) for m in _BLOCK.finditer(_clean())]


def load_schema_for_prompt(tables: list[str] | None = None) -> str:
    text = _clean()
    if not tables:
        return text
    keep = [m.group(0) for m in _BLOCK.finditer(text) if m.group(1) in set(tables)]
    header = "\n".join(l for l in text.splitlines() if l.startswith("--") and "CREATE" not in l)[:300]
    return (header + "\n\n" if header else "") + "\n\n".join(keep)
