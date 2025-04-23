import streamlit as st
import pandas as pd
import time
from datetime import datetime
from pytz import timezone
import firebase_admin
from firebase_admin import credentials, firestore
import json
import tempfile
import re  # 正規表現ライブラリ

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

# --- ページ設定（最初に書く必要あり） ---
st.set_page_config(page_title="Speed Reading App", layout="wide")

# --- データ読み込み関数 ---
def load_material(data_path, row_index):
    """CSVファイルから指定された行のデータを読み込む関数"""
    try:
        df = pd.read_csv(data_path)
        if 0 <= row_index < len(df):
            return df.iloc[row_index]
        else:
            st.error(f"指定された行番号 ({row_index + 1}) はファイルに存在しません。")
            return None
    except FileNotFoundError:
        st.error(f"ファイル '{data_path}' が見つかりません。")
        return None
    except Exception as e:
        st.error(f"予期しないエラーが発生しました: {e}")
        return None

# --- GitHubからユーザーIDリストをロードし、セッションステートに格納 ---
@st.cache_data
def load_user_ids_from_github(github_raw_url):
    try:
        df = pd.read_csv(github_raw_url)
        if 'user_id' in df.columns:
            return df['user_id'].tolist()
        else:
            st.error("CSVファイルに 'user_id' カラムが存在しません。")
            return []
    except Exception as e:
        st.error(f"GitHubからのユーザーIDリストの読み込みに失敗しました: {e}")
        return []

GITHUB_USER_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/user.csv"

# --- セッション変数の初期化 ---
if "row_to_load" not in st.session_state:
    st.session_state.row_to_load = 0
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
if 'valid_user_ids' not in st.session_state:
    st.session_state['valid_user_ids'] = load_user_ids_from_github(GITHUB_USER_CSV_URL)

# --- page == 0: 名前とIDの入力フォーム ---
if st.session_state.page == 0:
    st.title("名前とIDを入力してください")
    col1, _ = st.columns(2)
    with col1:
        last_name = st.text_input("姓", key="last_name_input", value=st.session_state.last_name)
        first_name = st.text_input("名", key="first_name_input", value=st.session_state.first_name)
        user_id = st.text_input("ID", key="user_id_input", value=st.session_state.user_id)
        if st.button("次へ"):
            if last_name and first_name and user_id:
                if not re.fullmatch(r'[0-9a-zA-Z]+', user_id):
                    st.error("IDは半角英数字で入力してください。")
                elif user_id.strip() in st.session_state.get('valid_user_ids', []):
                    st.session_state.last_name = last_name
                    st.session_state.first_name = first_name
                    st.session_state.user_id = user_id.strip()
                    st.session_state.page = 1
                    st.rerun()
                else:
                    st.error(f"入力されたID '{user_id}' は登録されていません。")
            else:
                st.warning("すべての項目を入力してください。")
# --- page == 1: 挨拶とスタートボタン ---
elif st.session_state.page == 1:
    st.title("English Booster スピード測定")
    if st.session_state.first_name:
        st.subheader(f"こんにちは、{st.session_state.first_name}さん！")
    st.info("下のStartボタンを押して英文を読みましょう.")
    if st.button("Start"):
        st.session_state.start_time = time.time()
        st.session_state.page = 2
        st.rerun()

# --- page == 2: 英文表示とStopボタン (2カラム) ---
elif st.session_state.page == 2:
    # CSVデータの読み込み
    DATA_PATH = "data.csv"
    data = load_material(DATA_PATH, int(st.session_state.row_to_load))

    if data is None:
        st.stop()

    st.info("読み終わったらStopボタンを押しましょう")
    col1, _ = st.columns([2, 1])
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
            """, unsafe_allow_html=True
        )
        if st.button("Stop"):
            st.session_state.stop_time = time.time()
            st.session_state.page = 3
            st.rerun()

# --- page == 3: クイズの表示と解答処理 (2カラム) ---
elif st.session_state.page == 3:
    # CSVデータの読み込み
    DATA_PATH = "data.csv"
    data = load_material(DATA_PATH, int(st.session_state.row_to_load))

    if data is None:
        st.stop()

    st.info("問題を解いてSubmitボタンを押しましょう")
    col1, col2 = st.columns([2, 1])
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
            """, unsafe_allow_html=True
        )
    with col2:
        st.subheader("Questions")
        st.radio(data['Q1'], [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']], key="q1")
        st.radio(data['Q2'], [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']], key="q2")

        if st.button("Submit"):
            if st.session_state.q1 is None or st.session_state.q2 is None:
                st.error("Please answer both questions.")
            else:
                st.session_state.page = 4
                st.rerun()

# --- page == 4: 結果の表示と保存 (2カラム) ---
elif st.session_state.page == 4:
    # CSVデータの読み込み
    DATA_PATH = "data.csv"
    data = load_material(DATA_PATH, int(st.session_state.row_to_load))

    if data is None:
        st.stop()

    st.success("結果を記録しました。Restartを押すともう一度できます。")

    col1, col2 = st.columns([2, 1])
    with col2:
        st.subheader("Result")
        correct_answers_to_store = 0
        wpm = 0.0

        if st.session_state.start_time and st.session_state.stop_time:
            total_time = st.session_state.stop_time - st.session_state.start_time
            word_count = len(data['main'].split())
            wpm = (word_count / total_time) * 60
            st.write(f"Words read: {word_count}")
            st.write(f"Time taken: {total_time:.2f} seconds")
            st.write(f"WPM: **{wpm:.1f}** words per minute")
            correct1 = st.session_state.q1 == data['A1']
            correct2 = st.session_state.q2 == data['A2']
            st.write(f"Q1: {'✅ Correct' if correct1 else '❌ Incorrect'}")
            st.write(f"Q2: {'✅ Correct' if correct2 else '❌ Incorrect'}")
            correct_answers_to_store = int(correct1) + int(correct2)

            if not st.session_state.submitted:
                save_results(wpm, correct_answers_to_store, str(data.get("id", f"row_{st.session_state.row_to_load}")),
                             st.session_state.first_name, st.session_state.last_name, st.session_state.user_id)
                st.session_state.submitted = True
        else:
            st.error("測定時間が記録されていません。もう一度お試しください。")

        if st.button("Restart"):
            st.session_state.page = 1
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.q1 = None
            st.session_state.q2 = None
            st.session_state.submitted = False
            st.rerun()

    with col1:
        st.subheader(f"{st.session_state.first_name}さんのWPM推移")
        # Firestoreから該当ユーザーの履歴データを取得
        results_ref = db.collection("results")
        query = results_ref.where("user_id", "==", st.session_state.user_id).order_by("timestamp")
        user_history = query.get()

        if user_history:
            history_data = [doc.to_dict() for doc in user_history]
            df_history = pd.DataFrame(history_data)

            # timestampをdatetime型に変換し、時刻部分までを表示
            df_history['datetime'] = pd.to_datetime(df_history['timestamp']).dt.strftime('%Y-%m-%d %H:%M')

            # 折れ線グラフの作成
            fig = px.line(df_history, x='datetime', y='wpm', title='WPMの推移')
            fig.update_layout(xaxis_title='時間', yaxis_title='WPM', yaxis_range=[0, 300])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("まだ履歴データがありません。")