import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from pytz import timezone
import firebase_admin
from firebase_admin import credentials, firestore
import json
import tempfile
import re

GITHUB_DATA_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/data.csv"
GITHUB_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/results.csv"
HEADER_IMAGE_URL = "https://github.com/boost-ogawa/english-booster/blob/main/English%20Booster_header.jpg?raw=true"
GITHUB_USER_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/user.csv"
DATA_PATH = "data.csv"
GOOGLE_CLASSROOM_URL = "YOUR_GOOGLE_CLASSROOM_URL_HERE" # Google ClassroomのURLを設定してください

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Firestoreに結果を保存する関数 ---
def save_results(wpm, correct_answers, material_id, first_name, last_name, user_id):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "user_id": user_id,
        "last_name": last_name,
        "first_name": first_name,
        "timestamp": timestamp,
        "material_id": material_id,
        "wpm": round(wpm, 1),
        "correct_answers": correct_answers
    }

    try:
        db.collection("results").add(result_data)
        print("結果が保存されました")
    except Exception as e:
        st.error(f"結果の保存に失敗しました: {e}")

# --- WPM推移グラフ表示関数 ---
def display_wpm_history(user_id):
    if user_id:
        try:
            df_results = pd.read_csv(GITHUB_CSV_URL)
            user_results = df_results[df_results['user_id'] == user_id].copy()
            if not user_results.empty:
                fig = px.line(user_results.tail(5), x='測定年月', y='WPM', title='WPM推移')
                fig.update_xaxes(tickangle=0)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("まだ学習履歴がありません。")
        except Exception as e:
            st.error(f"過去データの読み込みまたは処理に失敗しました: {e}")
    else:
        st.info("ユーザーIDがありません。")

# --- ページ設定（最初に書く必要あり） ---
st.set_page_config(page_title="Speed Reading App", layout="wide", initial_sidebar_state="collapsed")

# --- スタイル設定 ---
st.markdown(
    """
    <style>
    /* アプリ全体の背景と文字色設定 */
    .stApp {
        background-color: #000D36;
        color: #ffffff;
    }

    /* 英文表示用のカスタム段落スタイル */
    .custom-paragraph {
        font-family: Georgia, serif;
        line-height: 1.8;
        font-size: 1.3rem;
    }

    /* スタートボタンのスタイル（高さ・フォントサイズ調整済み） */
    div.stButton > button:first-child {
        background-color: #28a745;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 20px 40px;           /* 高さと横幅UP */
        font-size: 1.5rem;            /* フォントサイズUP */
    }

    div.stButton > button:first-child:hover {
        background-color: #218838;
    }

    /* Google Classroom風のボタン */
    .google-classroom-button {
        display: inline-block;
        padding: 10px 20px;
        margin-top: 10px;
        background-color: #4285F4;
        color: white !important;
        text-decoration: none;
        border-radius: 5px;
    }

    .google-classroom-button:hover {
        background-color: #357AE8;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- ヘッダー画像の表示 ---
st.image(HEADER_IMAGE_URL, use_container_width=True)

# --- データ読み込み関数 ---
def load_material(github_url, row_index):
    """GitHubのCSVファイルから指定された行のデータを読み込む関数"""
    try:
        df = pd.read_csv(github_url)
        if 0 <= row_index < len(df):
            return df.iloc[row_index]
        else:
            st.error(f"指定された行番号 ({row_index + 1}) はファイルに存在しません。")
            return None
    except Exception as e:
        st.error(f"GitHubからのデータ読み込みに失敗しました: {e}")
        return None

# --- GitHubからニックネームとIDでユーザー情報をロードする関数 ---
@st.cache_data
def get_user_data(github_raw_url, nickname, user_id):
    try:
        df = pd.read_csv(github_raw_url)
        user = df[(df['nickname'] == nickname) & (df['user_id'] == user_id)].iloc[0].to_dict()
        return user
    except (IndexError, FileNotFoundError, KeyError) as e:
        print(f"ユーザーデータ取得エラー: {e}")
        return None

# --- セッション変数の初期化 ---
if "row_to_load" not in st.session_state:
    st.session_state.row_to_load = 0
if "fixed_row_index" not in st.session_state:
    st.session_state.fixed_row_index = 1
if "page" not in st.session_state:
    st.session_state.page = 0
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "stop_time" not in st.session_state:
    st.session_state.stop_time = None
if "q1" not in st.session_state:
    st.session_state.q1 = None
if "q2" not in st.session_state:
    st.session_state.q2 = None
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "last_name" not in st.session_state:
    st.session_state.last_name = ""
if "first_name" not in st.session_state:
    st.session_state.first_name = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "show_full_graph" not in st.session_state:
    st.session_state.show_full_graph = False
if "set_page_key" not in st.session_state:
    st.session_state["set_page_key"] = "unique_key_speed" # 適当なユニークなキー
# --- ページ遷移関数 ---
def set_page(page_number):
    st.session_state.page = page_number

# --- 「スピード測定開始」ボタンが押されたときに実行する関数 ---
def start_reading(page_number):
    st.session_state.start_time = time.time()
    st.session_state.page = page_number

# --- サイドバーのコンテンツ ---
def sidebar_content():
    st.sidebar.header("メニュー")
    st.sidebar.markdown(f"[Google Classroom]({GOOGLE_CLASSROOM_URL})")
    st.sidebar.markdown("[利用規約](#利用規約)")
    st.sidebar.markdown("[プライバシーポリシー](#プライバシーポリシー)")
    st.sidebar.markdown("---")
    st.sidebar.subheader("その他")
    st.sidebar.write("English Booster")
    st.sidebar.write("Ver.1_01")
    
# --- メインの処理 ---
if st.session_state.page == 0:
    st.title("ニックネームとIDを入力してください")
    col1, _ = st.columns(2)
    with col1:
        nickname = st.text_input("ニックネーム (半角英数字)", key="nickname_input", value=st.session_state.first_name)
        user_id = st.text_input("ID (半角英数字)", key="user_id_input", value=st.session_state.user_id)
        if st.button("次へ"):
            if not nickname:
                st.warning("ニックネームを入力してください。")
            elif not user_id:
                st.warning("IDを入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z]+', nickname):
                st.error("ニックネームは半角英数字で入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z]+', user_id):
                st.error("IDは半角英数字で入力してください。")
            else:
                user_data = get_user_data(GITHUB_USER_CSV_URL, nickname.strip(), user_id.strip())
                if user_data:
                    st.session_state.first_name = nickname.strip()
                    st.session_state.last_name = ""
                    st.session_state.user_id = user_id.strip()
                    st.session_state.page = 5
                    st.rerun()
                else:
                    st.error("ニックネームまたはIDが正しくありません。")
elif st.session_state.page == 5:
    sidebar_content()
    st.title(f"こんにちは、{st.session_state.first_name}さん！")
    if st.button("スピード測定開始（このボタンをクリックすると英文が表示されます）", key="main_start_button", use_container_width=True, on_click=start_reading, args=(1,)):
        pass
    st.markdown("---")
    st.subheader(f"{st.session_state.first_name}さんのWPM推移")
    current_user_id = st.session_state.get('user_id')
    display_wpm_history(current_user_id) # 関数を呼び出す
    st.markdown("---")
    st.markdown("© 2025 英文速解English Booster", unsafe_allow_html=True)

elif st.session_state.page == 1:
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()
    st.info("読み終わったらStopボタンを押しましょう")
    col1, _ = st.columns([2, 1])
    with col1:
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {data['main']}
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Stop"):
            st.session_state.stop_time = time.time()
            st.session_state.page = 2
            st.rerun()

elif st.session_state.page == 2:
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()
    st.info("問題を解いてSubmitボタンを押しましょう")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {data['main']}
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Submit"):
            if st.session_state.q1 is None or st.session_state.q2 is None:
                st.error("Please answer both questions.")
            else:
                st.session_state.page = 3
                st.rerun()

    with col2:
        st.subheader("Questions")
        st.radio(data['Q1'], [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']], key="q1")
        st.radio(data['Q2'], [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']], key="q2")

elif st.session_state.page == 3:
    sidebar_content()
    st.success("結果を記録しましょう。Restartを押すともう一度できます。")
    col1, col2 = st.columns([1, 2])
    with col2:
        current_user_id = st.session_state.get('user_id')
        display_wpm_history(current_user_id) # 関数を呼び出す

    with col1:
        data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
        if data is None:
            st.stop()
        st.subheader("Result")
        correct_answers_to_store = 0
        wpm = 0.0

        if st.session_state.start_time and st.session_state.stop_time:
            total_time = st.session_state.stop_time - st.session_state.start_time
            word_count = len(data['main'].split())
            wpm = (word_count / total_time) * 60
            st.write(f"総単語数: {word_count} 語")
            st.write(f"所要時間: {total_time:.2f} 秒")
            st.write(f"単語数/分: **{wpm:.1f}** WPM")
            correct1 = st.session_state.q1 == data['A1']
            correct2 = st.session_state.q2 == data['A2']
            st.write(f"Q1: {'✅ 正解' if correct1 else '❌ 不正解'}")
            st.write(f"Q2: {'✅ 正解' if correct2 else '❌ 不正解'}")
            correct_answers_to_store = int(correct1) + int(correct2)

            if not st.session_state.submitted:
                save_results(wpm, correct_answers_to_store, str(data.get("id", f"row_{st.session_state.row_to_load}")),
                             st.session_state.first_name, st.session_state.last_name, st.session_state.user_id)
                st.session_state.submitted = True

        if st.button("Restart"):
            st.session_state.page = 5
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.submitted = False
            st.rerun()