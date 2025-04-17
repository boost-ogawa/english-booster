import streamlit as st
import time
import pandas as pd

# Load CSV (always use the first row)
DATA_PATH = "data.csv"
df = pd.read_csv(DATA_PATH, sep='|')
data = df.iloc[0]  # Get the first row

# Initialize session state
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
        st.info("Click Start to see the passage. Try to read as quickly as possible.")
    elif st.session_state.page == 2:
        st.info("Click STOP when you've finished reading.")
    elif st.session_state.page == 3:
        st.info("Answer the questions and click Submit.")
    elif st.session_state.page == 4:
        st.success("Check your result and restart if you'd like.")

# Page 1: Start
if st.session_state.page == 1:
    with col1:
        if st.button("Start"):
            st.session_state.start_time = time.time()
            st.session_state.page = 2
            st.rerun()

# Page 2: Reading
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
            {data['main']}
            </div>
            """, unsafe_allow_html=True)
        if st.button("Stop"):
            st.session_state.stop_time = time.time()
            st.session_state.page = 3
            st.rerun()

# Page 3: Questions
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
            {data['main']}
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.subheader("Questions")
        st.radio(data['Q1'],
                 [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']],
                 key="q1")
        st.radio(data['Q2'],
                 [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']],
                 key="q2")

        if st.button("Submit"):
            if st.session_state.q1 is None or st.session_state.q2 is None:
                st.error("Please answer both questions.")
            else:
                st.session_state.page = 4
                st.rerun()

# Page 4: Result
elif st.session_state.page == 4:
    with col2:
        st.subheader("Result")

        total_time = st.session_state.stop_time - st.session_state.start_time
        word_count = len(data['main'].split())
        wpm = (word_count / total_time) * 60

        st.write(f"Words read: {word_count}")
        st.write(f"Time taken: {total_time:.2f} seconds")
        st.write(f"WPM: **{wpm:.2f}** words per minute")

        correct1 = st.session_state.q1 == data['A1']
        correct2 = st.session_state.q2 == data['A2']

        st.write(f"Q1: {'✅ Correct' if correct1 else '❌ Incorrect'}")
        st.write(f"Q2: {'✅ Correct' if correct2 else '❌ Incorrect'}")

        if st.button("Restart"):
            st.session_state.page = 1
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.q1 = None
            st.session_state.q2 = None
            st.rerun()
