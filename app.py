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

GITHUB_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/results.csv"

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

GITHUB_USER_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/user.csv"

# --- セッション変数の初期化 読み込みデータの変更---
if "row_to_load" not in st.session_state:
    st.session_state.row_to_load = 0

if "fixed_row_index" not in st.session_state:
    st.session_state.fixed_row_index = 1  # ← 固定の行番号を 1 に設定（2行目）

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


# --- page == 0: ニックネームとIDの入力フォーム ---
if st.session_state.page == 0:
    st.title("ニックネームとIDを入力してください")
    col1, _ = st.columns(2)
    with col1:
        nickname = st.text_input("ニックネーム (半角英数字)", key="nickname_input", value=st.session_state.first_name)
        user_id = st.text_input("ID (半角英数字)", key="user_id_input", value=st.session_state.user_id)
        if st.button("次へ"):
            if nickname and user_id:
                if not re.fullmatch(r'[0-9a-zA-Z]+', nickname):
                    st.error("ニックネームは半角英数字で入力してください。")
                elif not re.fullmatch(r'[0-9a-zA-Z]+', user_id):
                    st.error("IDは半角英数字で入力してください。")
                else:
                    user_data = get_user_data(GITHUB_USER_CSV_URL, nickname.strip(), user_id.strip())
                    if user_data:
                        st.session_state.first_name = nickname.strip()
                        st.session_state.last_name = ""
                        st.session_state.user_id = user_id.strip()
                        st.session_state.page = 1
                        st.rerun()
                    else:
                        st.error("ニックネームまたはIDが正しくありません。")
            else:
                st.warning("ニックネームとIDを入力してください。")
                
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
    data = load_material(DATA_PATH, st.session_state.fixed_row_index)  # ← 変更

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
    data = load_material(DATA_PATH, st.session_state.fixed_row_index)  # ← 変更

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
    st.success("結果を記録しましょう。Restartを押すともう一度できます。")
    col1, col2 = st.columns([2, 1])
    with col2:
        st.subheader(f"{st.session_state.first_name}さんのWPM推移")

        current_user_id = st.session_state.get('user_id')

        if current_user_id:
            try:
                df_results = pd.read_csv(GITHUB_CSV_URL)
                user_results = df_results[df_results['user_id'] == current_user_id]

                if not user_results.empty:
                    past_data = user_results.drop(columns=['user_id'])
                    if not past_data.empty:
                        past_data_transposed = past_data.T
                        if not past_data_transposed.empty:
                            # 最初の行をヘッダーとして扱う
                            new_header = past_data_transposed.iloc[0]
                            past_data_transposed = past_data_transposed[1:]
                            past_data_transposed.columns = new_header

                            # 列の幅を自動調整する設定
                            column_config = {}
                            for col in past_data_transposed.columns:
                                column_config[col] = st.column_config.Column(width="auto")

                            st.dataframe(past_data_transposed, column_config=column_config)
                        else:
                            st.info("まだ学習履歴がありません。")
                    else:
                        st.info("まだ学習履歴がありません。")

            except Exception as e:
                st.error(f"過去データの読み込みまたは処理に失敗しました: {e}")
        else:
            st.info("ユーザーIDがありません。")  
    with col2:
        DATA_PATH = "data.csv"
    data = load_material(DATA_PATH, st.session_state.fixed_row_index)  # ← 変更

    if data is None:
        st.stop()

    with col1:
        st.subheader("Result")
        correct_answers_to_store = 0  # 初期値を設定
        wpm = 0.0  # wpm の初期値を設定

        # 開始時間と停止時間が記録されているか確認
        if st.session_state.start_time and st.session_state.stop_time:
            total_time = st.session_state.stop_time - st.session_state.start_time
            word_count = len(data['main'].split())
            wpm = (word_count / total_time) * 60
            st.write(f"今回の文章の総単語数: {word_count}")
            st.write(f"文章を読んだ所要時間: {total_time:.2f} seconds")
            st.write(f"１分間あたりの単語数: **{wpm:.1f}** words per minute")
            correct1 = st.session_state.q1 == data['A1']
            correct2 = st.session_state.q2 == data['A2']
            st.write(f"Q1: {'✅ 正解' if correct1 else '❌ 不正解'}")
            st.write(f"Q2: {'✅ 正解' if correct2 else '❌ 不正解'}")
            correct_answers_to_store = int(correct1) + int(correct2)

            # Firestoreに結果を保存
            if not st.session_state.submitted:
                save_results(wpm, correct_answers_to_store, str(data.get("id", f"row_{st.session_state.row_to_load}")),
                             st.session_state.first_name, st.session_state.last_name, st.session_state.user_id)
                st.session_state.submitted = True
        else:
            st.error("測定時間が記録されていません。もう一度お試しください。")

        if st.button("Restart"):
            st.session_state.page = 1  # ページ 1 から再開
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.q1 = None
            st.session_state.q2 = None
            st.session_state.submitted = False
            st.rerun()