import streamlit as st
import time

st.set_page_config(page_title="STOPWATCH", layout="centered")

# 💅 CSS（省略せずそのまま残してね）
st.markdown("""
<style>
.main { background-color: #f9f9f9 !important; }
body, .css-18e3th9 { color: #111111 !important; }
.big-time {
    font-size: 96px;
    font-weight: bold;
    color: #007acc !important;
    text-align: center;
    margin-top: 40px;
    margin-bottom: 40px;
}
.centered-title {
    text-align: center;
    font-size: 48px;
    font-weight: bold;
    color: #003366 !important;
    margin-bottom: 10px;
}
.stButton>button {
    width: 100%;
    height: 80px;
    font-size: 28px;
    font-weight: bold;
    background-color: #007acc !important;
    color: white !important;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

# 🏷️ タイトル
st.markdown("<div class='centered-title'>STOPWATCH ⏱️</div>", unsafe_allow_html=True)

# 🧠 セッションステート初期化
if 'start_time' not in st.session_state:
    st.session_state.start_time = None
    st.session_state.running = False
    st.session_state.elapsed = 0.0

# 🎛️ 操作ボタン
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("▶️ スタート"):
        if not st.session_state.running:
            st.session_state.start_time = time.time() - st.session_state.elapsed
            st.session_state.running = True

with col2:
    if st.button("⏹️ ストップ"):
        if st.session_state.running:
            st.session_state.elapsed = time.time() - st.session_state.start_time
            st.session_state.running = False

with col3:
    if st.button("🔄 リセット"):
        st.session_state.start_time = None
        st.session_state.running = False
        st.session_state.elapsed = 0.0

# ⏱️ 時間計算
if st.session_state.start_time is not None and st.session_state.running:
    st.session_state.elapsed = time.time() - st.session_state.start_time

# 表示用にフォーマット
minutes = int(st.session_state.elapsed // 60)
seconds = int(st.session_state.elapsed % 60)
formatted_time = f"{minutes:02d}m {seconds:02d}s"

# ⌛ 表示
st.markdown(f"<div class='big-time'>{formatted_time}</div>", unsafe_allow_html=True)

# 🔁 自動更新
if st.session_state.running:
    time.sleep(0.1)
    st.rerun()
