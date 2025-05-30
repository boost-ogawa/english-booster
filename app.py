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

# --- Firestoreから設定を読み込む関数 ---
def load_config():
    try:
        doc_ref = db.collection("settings").document("app_config") # ドキュメントIDはあなたが設定したIDに
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            print("設定ドキュメントが存在しません。")
            return {}
    except Exception as e:
        print(f"設定の読み込みに失敗しました: {e}")
        return {}

# --- Firestoreに設定を保存する関数 ---
def save_config(fixed_row_index):
    try:
        doc_ref = db.collection("settings").document("app_config") # ドキュメントIDはあなたが設定したIDに
        doc_ref.set({"fixed_row_index": fixed_row_index})
        print(f"設定を保存しました: fixed_row_index = {fixed_row_index}")
        st.success(f"表示行番号を {fixed_row_index} に保存しました。")
    except Exception as e:
        st.error(f"設定の保存に失敗しました: {e}")

# --- Firestoreに結果を保存する関数 ---
def save_results(wpm, correct_answers, material_id, nickname, user_id):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "user_id": user_id,
        "nickname": nickname,
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
                fig = px.line(user_results, x='測定年月', y='WPM', title='WPM推移')
                fig.update_xaxes(tickangle=-45)
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
        font-size: 1.5rem;
    }

    /* スタートボタンのスタイル（高さ・フォントサイズ調整済み） */
    div.stButton > button:first-child {
        background-color: #28a745;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 20px 40px;           /* 高さと横幅UP */
        font-size: 1.8rem;            /* フォントサイズUP */
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
            return df.iloc[row_index].to_dict()
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
    config = load_config()
    st.session_state.fixed_row_index = config.get("fixed_row_index", 2) # Firestoreから読み込んだ値、なければデフォルトの2
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
if "nickname" not in st.session_state:
    st.session_state.nickname = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "show_full_graph" not in st.session_state:
    st.session_state.show_full_graph = False
if "set_page_key" not in st.session_state:
    st.session_state["set_page_key"] = "unique_key_speed" # 適当なユニークなキー
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False # 管理者権限の状態を保持する変数
    
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

# --- 管理者ユーザー名とパスワードの設定 ---
ADMIN_USERNAME = "admin" # 例：管理者ユーザー名
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "7nBTVRXi1ars") # Streamlit Secrets から取得

# --- メインの処理 ---
if st.session_state.page == 0:
    st.title("ニックネームとIDを入力してください")
    col1, _ = st.columns(2)
    with col1:
        nickname = st.text_input("ニックネーム (半角英数字)", key="nickname_input", value=st.session_state.nickname)
        user_id = st.text_input("ID (半角英数字)", key="user_id_input", value=st.session_state.user_id)
        if st.button("次へ"):
            if not nickname:
                st.warning("ニックネームを入力してください。")
            elif not user_id:
                st.warning("IDを入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z_\- ]+', nickname):
                st.error("ニックネームは半角英数字で入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z]+', user_id):
                st.error("IDは半角英数字で入力してください。")
            else:
                user_data = get_user_data(GITHUB_USER_CSV_URL, nickname.strip(), user_id.strip())
                if user_data:
                    st.session_state.nickname = nickname.strip()
                    st.session_state.user_id = user_id.strip()
                    # 管理者としてログインしたかを判定
                    if nickname.strip() == ADMIN_USERNAME and user_id.strip() == ADMIN_PASSWORD:
                        st.session_state.is_admin = True
                        st.session_state.page = 5 # 管理者画面へ遷移
                        st.rerun()
                    else:
                        st.session_state.page = 10 # 一般ユーザー用のページへ遷移 (新しいページ番号)
                        st.rerun()
                else:
                    st.error("ニックネームまたはIDが正しくありません。")
elif st.session_state.page == 10: # 一般ユーザー用のページ
    sidebar_content()
    st.title(f"こんにちは、{st.session_state.nickname}さん！")
    if st.button("スピード測定開始（このボタンをクリックすると英文が表示されます）", key="main_start_button", use_container_width=True, on_click=start_reading, args=(1,)):
        pass
    st.markdown("---")
    st.subheader(f"{st.session_state.nickname}さんのWPM推移")
    current_user_id = st.session_state.get('user_id')
    display_wpm_history(current_user_id) # 関数を呼び出す
    st.markdown("---")
    st.markdown("© 2025 英文速解English Booster", unsafe_allow_html=True)
elif st.session_state.page == 5:
    sidebar_content()
    st.title(f"こんにちは、{st.session_state.nickname}さん！")

    if st.session_state.is_admin:
        st.subheader("管理者設定")
        manual_index = st.number_input("表示する行番号 (0から始まる整数)", 0, value=st.session_state.get("fixed_row_index", 0))
        if st.button("表示行番号を保存"):
            st.session_state.fixed_row_index = manual_index
            save_config(manual_index) # Firestore に保存する関数を呼び出す

    if st.session_state.is_admin: # 管理者も測定できるように
        if st.button("スピード測定開始（このボタンをクリックすると英文が表示されます）", key="admin_start_button", use_container_width=True, on_click=start_reading, args=(1,)):
            pass
        st.markdown("---")
        st.subheader(f"{st.session_state.nickname}さんのWPM推移")
        current_user_id = st.session_state.get('user_id')
        display_wpm_history(current_user_id) # 関数を呼び出す
        st.markdown("---")
        st.markdown("© 2025 英文速解English Booster", unsafe_allow_html=True)
    else: # 一般ユーザーの場合は測定開始ボタンのみ
        if st.button("スピード測定開始（このボタンをクリックすると英文が表示されます）", key="main_start_button", use_container_width=True, on_click=start_reading, args=(1,)):
            pass
        st.markdown("---")
        st.subheader(f"{st.session_state.nickname}さんのWPM推移")
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
        st.markdown(f'<div class="custom-paragraph">{data["main"]}</div>', unsafe_allow_html=True)

    with col2:
        st.subheader("Questions")
        q1_choice = st.radio(data['Q1'], [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']], key="q1")
        q2_choice = st.radio(data['Q2'], [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']], key="q2")

    if st.button("Submit"): # ← col1 の外に移動
        if st.session_state.q1 is not None and st.session_state.q2 is not None:
            st.session_state.page = 3
            st.rerun()
        else:
            st.error("両方の質問に答えてください。")

elif st.session_state.page == 3:
    sidebar_content()
    st.success("結果を記録しました。") # メッセージを変更
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

            # Q1 の結果表示
            correct1 = st.session_state.q1 == data['A1']
            st.write(f"Q1: {'✅ 正解' if correct1 else '❌ 不正解'}")
            st.write(f"あなたの解答 {st.session_state.q1}")
            st.write(f"正しい答え: {data['A1']}")

            # Q2 の結果表示
            correct2 = st.session_state.q2 == data['A2']
            st.write(f"Q2: {'✅ 正解' if correct2 else '❌ 不正解'}")
            st.write(f"あなたの解答: {st.session_state.q2}")
            st.write(f"正しい答え: {data['A2']}")

            correct_answers_to_store = int(correct1) + int(correct2)

            if not st.session_state.submitted:
                save_results(wpm, correct_answers_to_store, str(data.get("id", f"row_{st.session_state.row_to_load}")),
                             st.session_state.nickname, st.session_state.user_id)
                st.session_state.submitted = True

        # 「Restart」ボタンを削除し、「意味を確認」ボタンを追加
        if st.button("意味を確認"):
            st.session_state.page = 4
            st.rerun()

elif st.session_state.page == 4:
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()
    st.title("英文と日本語訳")
    col_en, col_ja = st.columns(2)
    with col_en:
        st.subheader("英文")
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {data['main']}
            </div>
            """, unsafe_allow_html=True
        )
    with col_ja:
        st.subheader("日本語訳")
        if 'japanese' in data:
            # 英文と同じスタイルを適用
            st.markdown(
                f"""
                <div style="font-family: Georgia, serif; line-height: 1.8; font-size: 1.5rem;">
                {data['japanese']}
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.error("CSVファイルに'japanese'列が存在しません。")
            st.stop()

    if st.button("終了"):
        st.session_state.page = 5 # トップページに戻るように変更
        st.session_state.start_time = None
        st.session_state.stop_time = None
        st.session_state.submitted = False
        st.rerun()
