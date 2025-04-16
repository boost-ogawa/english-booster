import streamlit as st
import time
import pandas as pd

# CSVの読み込み（毎回1行目を使う）
DATA_PATH = "C:/Users/ogawa/Streamlit_apps/data.csv"
df = pd.read_csv(DATA_PATH, sep='|')
data = df.iloc[0]  # 1行目を取得

# ページ状態を初期化
if "page" not in st.session_state:
    st.session_state.page = 1
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "stop_time" not in st.session_state:
    st.session_state.stop_time = None
if "q1" not in st.session_state:
    st.session_state.q1 = None
if "q2" not in st.session_state:
    st.session_state.q2 = None

st.set_page_config(page_title="Speed Reading App", layout="wide")
st.title("Speed Reading App")

col1, col2 = st.columns([2, 1])

with col1:
    if st.session_state.page == 1:
        st.info("スタートボタンを押すと課題文が表示されます。できるだけ速く読みましょう。")
    elif st.session_state.page == 2:
        st.info("読み終わったらSTOPボタンを押しましょう。")
    elif st.session_state.page == 3:
        st.info("以下の問題に答えて、Submitを押しましょう。")
    elif st.session_state.page == 4:
        st.success("結果を確認して、最初に戻りましょう。")

if st.session_state.page == 1:
    with col1:
        if st.button("Start"):
            st.session_state.start_time = time.time()
            st.session_state.page = 2
            st.rerun()

elif st.session_state.page == 2:
    with col1:
        st.markdown(
            f"""
            <style>
            .custom-paragraph {{
                font-family: Georgia, serif;
                line-height: 1.8;
                font-size: 1.3rem;
            }}
            </style>
            <div class="custom-paragraph">
            {data['課題文']}
            </div>
            """, unsafe_allow_html=True)
        if st.button("Stop"):
            st.session_state.stop_time = time.time()
            st.session_state.page = 3
            st.rerun()

elif st.session_state.page == 3:
    with col1:
        st.markdown(
            f"""
            <style>
            .custom-paragraph {{
                font-family: Georgia, serif;
                line-height: 1.8;
                font-size: 1.3rem;
            }}
            </style>
            <div class="custom-paragraph">
            {data['課題文']}
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.subheader("質問")
        st.radio(data['質問1'],
                 [data['選択肢1A'], data['選択肢1B'], data['選択肢1C'], data['選択肢1D']],
                 key="q1")
        st.radio(data['質問2'],
                 [data['選択肢2A'], data['選択肢2B'], data['選択肢2C'], data['選択肢2D']],
                 key="q2")

        if st.button("Submit"):
            if st.session_state.q1 is None or st.session_state.q2 is None:
                st.error("すべての質問に答えてください。")
            else:
                st.session_state.page = 4
                st.rerun()

elif st.session_state.page == 4:
    with col2:
        st.subheader("結果")

        total_time = st.session_state.stop_time - st.session_state.start_time
        word_count = len(data['課題文'].split())
        wpm = (word_count / total_time) * 60

        st.write(f"読んだ語数: {word_count}語")
        st.write(f"かかった時間: {total_time:.2f}秒")
        st.write(f"WPM: **{wpm:.2f}** 語/分")

        correct1 = st.session_state.q1 == data['解答1']
        correct2 = st.session_state.q2 == data['解答2']

        st.write(f"Q1: {'✅ 正解' if correct1 else '❌ 不正解'}")
        st.write(f"Q2: {'✅ 正解' if correct2 else '❌ 不正解'}")

        if st.button("最初に戻る"):
            st.session_state.page = 1
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.q1 = None
            st.session_state.q2 = None
            st.rerun()
