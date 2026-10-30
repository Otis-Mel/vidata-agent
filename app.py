"""Demo UI: streamlit run app.py"""
import pandas as pd
import streamlit as st

from src.agents.multi import PRESETS, make_agent
from src.db import DB_PATH
from src.llm import LLM

st.set_page_config(page_title="ViDataAgent", page_icon="📊", layout="wide")
st.title(" ViDataAgent")
st.caption("Hỏi dữ liệu thương mại điện tử Việt Nam (dữ liệu giả lập) bằng tiếng Việt.")

if not DB_PATH.exists():
    st.error("Chưa có database. Chạy: `python scripts/generate_data.py`")
    st.stop()

EXAMPLES = [
    "Tổng giá trị hàng hóa của các đơn hoàn thành trong năm 2025 theo giờ Việt Nam là bao nhiêu?",
    "5 tỉnh/thành có nhiều đơn hoàn thành nhất?",
    "Tỉ lệ đơn bị hoàn trả của từng hãng vận chuyển?",
    "Doanh thu theo từng tháng năm 2025 và tăng trưởng so với tháng trước.",
    "Doanh thu tháng trước là bao nhiêu?",
    "Tỉ lệ khách hàng nữ là bao nhiêu?",
]

with st.sidebar:
    names = list(PRESETS)
    preset = st.selectbox("Cấu hình agent", names, index=names.index("p4_critic"))
    show_trace = st.checkbox("Hiện các bước của agent", value=True)
    st.caption("p0 = single-agent baseline; p4/p5 = multi-agent (router + critic...).")


@st.cache_resource
def get_agent(preset_name: str):
    return make_agent(preset_name, LLM(), explain=True)


example = st.selectbox("Câu hỏi mẫu", ["(tự nhập)"] + EXAMPLES)
question = st.text_input("Câu hỏi", value="" if example == "(tự nhập)" else example)

if st.button("Hỏi", type="primary") and question.strip():
    try:
        with st.spinner("Agent đang xử lý..."):
            res = get_agent(preset).answer(question.strip())
    except Exception as e:  # noqa: BLE001  (thiếu key, mất mạng...)
        st.error(f"Lỗi khi gọi agent: {e}")
        st.stop()

    if res.behavior == "clarify":
        st.info(f" Cần làm rõ thêm: {res.message}")
    elif res.behavior == "cannot_answer":
        st.warning(f" Dữ liệu hiện có không trả lời được: {res.message}")
    elif res.behavior == "error":
        st.error(f"Không tạo được truy vấn chạy được: {res.message}")
        if res.sql:
            st.code(res.sql, language="sql")
    else:
        if res.answer_text:
            st.success(res.answer_text)
        st.code(res.sql, language="sql")
        df = pd.DataFrame(res.rows, columns=res.cols)
        st.dataframe(df)
        if len(df.columns) == 2 and 2 <= len(df) <= 60 and pd.api.types.is_numeric_dtype(df.iloc[:, 1]):
            chart_df = df.set_index(df.columns[0])
            (st.line_chart if pd.api.types.is_datetime64_any_dtype(df.iloc[:, 0]) else st.bar_chart)(chart_df)

    c1, c2, c3 = st.columns(3)
    c1.metric("Lần gọi LLM", res.attempts)
    c2.metric("Token (vào/ra)", f"{res.in_tokens}/{res.out_tokens}")
    c3.metric("Độ trễ (s)", f"{res.latency_s:.1f}")
    if show_trace and res.trace:
        with st.expander("Các bước của agent"):
            for t in res.trace:
                st.markdown(f"**{t['step']}**  ·  {t['in_tokens']}/{t['out_tokens']} token")
                st.code(t["output"])
