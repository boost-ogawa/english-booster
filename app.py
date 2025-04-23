import streamlit as st
import pandas as pd
import time
from datetime import datetime
from pytz import timezone  # ← これは最初の方、他のimportの並びに追加
import firebase_admin
from firebase_admin import credentials, firestore
import json
import tempfile

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:  # ← すでに初期化されていないか確認
        firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Firestoreに結果を保存する関数 ---
def save_results(wpm, correct_answers, material_id, first_name, last_name, user_id):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "timestamp": timestamp,           # 時間
        "material_id": material_id,       # 素材ID（何を読んだか）
        "wpm": round(wpm, 1),             # WPM（1分間の単語数）小数第1位まで
        "correct_answers": correct_answers,  # 正解数
        "first_name": first_name,         # 名前（姓）
        "last_name": last_name,           # 名前（名）
        "user_id": user_id                # ユーザーID
    }

    try:
        # Firestoreの"results"コレクションに保存
        db.collection("results").add(result_data)
        print("結果が保存されました")
    except Exception as e:
        # エラーハンドリング（保存に失敗した場合）
        st.error(f"結果の保存に失敗しました: {e}")

    # Firestoreの"results"コレクションに保存
    db.collection("results").add(result_data)
    print("結果が保存されました")

# --- ページ設定（最初に書く必要あり） ---
st.set_page_config(page_title="Speed Reading App", layout="wide")

# --- データ読み込み関数 ---
def load_material(data_path, row_index):
    """CSVファイルから指定された行のデータを読み込む関数"""
    try:
        df = pd.read_csv(data_path)
        if row_index < len(df):
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

# セッション変数の初期化
if "row_to_load" not in st.session_state:
    st.session_state.row_to_load = 1

if "page" not in st.session_state:
    st.session_state.page = 0  # 初期ページを0に設定

# その他のセッション変数
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "stop_time" not in st.session_state:
    st.session_state.stop_time = None
if "q1" not in st.session_state:
    st.session_state.q1 = None
if "q2" not in st.session_state:
    st.session_state.q2 = None

# --- セッションに名前・IDの初期化 ---
if "last_name" not in st.session_state:
    st.session_state.last_name = ""
if "first_name" not in st.session_state:
    st.session_state.first_name = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""

# --- page == 0: 名前とIDの入力フォーム ---
if st.session_state.page == 0:
    st.title("English Booster へようこそ")

    st.write("以下の情報を入力してください：")

    st.session_state.last_name = st.text_input("姓（例：山田）", value=st.session_state.last_name)
    st.session_state.first_name = st.text_input("名（例：太郎）", value=st.session_state.first_name)
    st.session_state.user_id = st.text_input("ID（例：abc123）", value=st.session_state.user_id)

    if st.button("学習をはじめる"):
        if st.session_state.last_name and st.session_state.first_name and st.session_state.user_id:
            st.session_state.page = 1
            st.rerun()
        else:
            st.warning("すべての項目を入力してください。")

# --- page == 1: 学習内容の表示とスタートボタンの処理 ---
if st.session_state.page == 1:
    # 学習者の名前を挨拶
    st.title(f"こんにちは、{st.session_state.first_name}さん！")

    # 学習内容を表示（データが存在すれば）
    data = load_material(DATA_PATH, int(st.session_state.row_to_load))
    if data is None:
        st.stop()

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

    st.info("Startボタンを押して英文を読みましょう.")
    if st.button("Start", key="start_button"):
        st.session_state.start_time = time.time()
        st.session_state.page = 2
        st.rerun()

# --- page == 2: 読書時間の計測 ---
if st.session_state.page == 2:
    st.info("読み終わったらStopボタンを押しましょう")
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

# --- page == 3: クイズの表示と解答処理 ---
if st.session_state.page == 3:
    st.info("問題を解いてSubmitボタンを押しましょう")
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

    # クイズの表示
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

# --- page == 4: 結果の表示と保存 ---
if st.session_state.page == 4:
    st.success("結果を記録しましょう。Restartを押すともう一度できます。")

    with col2:
        st.subheader("Result")
        total_time = st.session_state.stop_time - st.session_state.start_time
        word_count = len(data['main'].split())
        wpm = (word_count / total_time) * 60
        st.write(f"Words read: {word_count}")
        st.write(f"Time taken: {total_time:.2f} seconds")
        st.write(f"WPM: **{wpm:.1f}** words per minute")  # ← 小数第1位まで
        correct1 = st.session_state.q1 == data['A1']
        correct2 = st.session_state.q2 == data['A2']
        st.write(f"Q1: {'✅ Correct' if correct1 else '❌ Incorrect'}")
        st.write(f"Q2: {'✅ Correct' if correct2 else '❌ Incorrect'}")
        timestamp = datetime.now().isoformat()
        correct_answers_to_store = int(correct1) + int(correct2)

        # 結果を表示
        st.write(f"Timestamp: {timestamp}")
        st.write(f"Correct Answers: {correct_answers_to_store}")

        # Firestoreに結果を保存
        if "submitted" not in st.session_state:
            st.session_state.submitted = False
        if not st.session_state.submitted:
            result_data = {
                "timestamp": timestamp,
                "material_id": str(data.get("id", f"row_{st.session_state.row_to_load}")),
                "wpm": round(wpm, 1),
                "correct_answers": correct_answers_to_store,
                "first_name": st.session_state.first_name,
                "last_name": st.session_state.last_name,
                "user_id": st.session_state.user_id
            }
            save_results(wpm, correct_answers_to_store, str(data.get("id", f"row_{st.session_state.row_to_load}")),
                         st.session_state.first_name, st.session_state.last_name, st.session_state.user_id)
            st.session_state.submitted = True

        if st.button("Restart"):
            st.session_state.page = 1
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.q1 = None
            st.session_state.q2 = None
            st.session_state.submitted = False
            st.rerun()
