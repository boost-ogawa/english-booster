import streamlit as st
import pandas as pd
import time
from datetime import datetime
from pytz import timezone
import firebase_admin
from firebase_admin import credentials, firestore
import json
import tempfile
import re
import os

GITHUB_DATA_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/data_j.csv"
GITHUB_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/results_j.csv"
GITHUB_USER_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/user_j.csv"
DATA_PATH = "data_j.csv"
GOOGLE_CLASSROOM_URL = "YOUR_GOOGLE_CLASSROOM_URL_HERE" # Google ClassroomのURLを設定してください
ADMIN_USERNAME = "admin" # 例：管理者ユーザー名
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "7nBTVRXi1ars") # Streamlit Secrets から取得

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

db = firestore.client()

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


# --- Firestoreに結果を保存する関数 (修正版 - 正誤判定のみ) ---
def save_results(wpm, correct_answers_comprehension, material_id, nickname, user_id,
                 is_correct_q1_text=None, is_correct_q2_text=None):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "user_id": user_id,
        "nickname": nickname,
        "timestamp": timestamp,
        "material_id": material_id,
        "wpm": round(wpm, 1),
        "comprehension_score": correct_answers_comprehension, # 読解問題の正答数
        "is_correct_q1_text": is_correct_q1_text,
        "is_correct_q2_text": is_correct_q2_text
    }

    try:
        db.collection("results_j").add(result_data)  # 保存先のコレクション名を "results_j" に変更
        print("結果が results_j に保存されました")
    except Exception as e:
        st.error(f"結果の保存に失敗しました: {e}")

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
        padding: 20px 40px;         /* 高さと横幅UP */
        font-size: 1.8rem;           /* フォントサイズUP */
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

# --- セッション変数の初期化 ---
config = load_config()
if "row_to_load" not in st.session_state:
    st.session_state.row_to_load = 0
if "fixed_row_index" not in st.session_state:
    st.session_state.fixed_row_index = config.get("fixed_row_index", 0)
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
if "stop_time_japanese" not in st.session_state:
    st.session_state.stop_time_japanese = None
if "q1_ja" not in st.session_state:
    st.session_state.q1_ja = None
if "q2_ja" not in st.session_state:
    st.session_state.q2_ja = None
if "word_count_japanese" not in st.session_state: # 日本語の単語数を保存
    st.session_state.word_count_japanese = 0
# --- ページ遷移関数 ---
def set_page(page_number):
    st.session_state.page = page_number

# --- 「スピード測定開始」ボタンが押されたときに実行する関数 ---
def start_reading(page_number):
    st.session_state.start_time = time.time()
    st.session_state.page = page_number

# --- 「国語の学習開始」ボタンが押されたときに実行する関数 ---
def start_japanese_reading():
    st.session_state.page = 7
    st.session_state.start_time = time.time()
    st.session_state.japanese_reading_started = True

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
                    else:
                        st.session_state.is_admin = False
                    st.session_state.page = 1
                    st.rerun()
                else:
                    st.error("ニックネームまたはIDが正しくありません。")

elif st.session_state.page == 1:
    st.title(f"こんにちは、{st.session_state.nickname}さん！")

    if st.session_state.is_admin:
        st.subheader("管理者設定")
        manual_index = st.number_input("表示する行番号 (0から始まる整数)", 0, value=st.session_state.get("fixed_row_index", 0))
        if st.button("表示行番号を保存"):
            st.session_state.fixed_row_index = manual_index
            save_config(manual_index) # Firestore に保存する関数を呼び出す

    if st.button("英語の学習開始（表示される英文を読んでStopをおしましょう）", key="english_start_button", use_container_width=True, on_click=start_reading, args=(2,)):
        pass
    if st.button("国語の学習開始（表示される文章を読んでStopをおしましょう）", key="japanese_start_button", use_container_width=True, on_click=start_japanese_reading):
        pass

elif st.session_state.page == 2:
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()
    st.info("読み終わったら「Stop」を押しましょう。")
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
            st.session_state.page = 3
            st.rerun()

elif st.session_state.page == 3:
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()
    st.info("問題を解いて「次へ」を押しましょう。")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {data['main']}
            </div>
            """, unsafe_allow_html=True
        )

    with col2:
        st.subheader("Questions")
        st.radio(data['Q1'], [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']], key="q1")
        st.radio(data['Q2'], [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']], key="q2")
    if st.button("次へ"):
        if st.session_state.q1 is None or st.session_state.q2 is None:
            st.error("Please answer both questions.")
        else:
            st.session_state.page = 4
            st.rerun()

elif st.session_state.page == 4: # 結果表示ページ
    st.success("結果と意味を確認して「次へ」を押しましょう。") # メッセージを変更
    col1, col2 = st.columns([1, 4]) # 2カラムに分割、比率を 1:4 に設定
    with col1:
        data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
        if data is None:
            st.stop()
        st.subheader("Result")
        correct_answers_to_store = 0
        wpm = 0.0
        if st.session_state.start_time and st.session_state.stop_time and st.session_state.q1 is not None and st.session_state.q2 is not None:
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

            st.session_state["wpm"] = wpm
            st.session_state["correct_answers_to_store"] = correct_answers_to_store

        elif st.session_state.start_time and st.session_state.stop_time:
            st.info("回答の読み込み中です...") # 回答がまだ読み込まれていない場合のメッセージ
        if st.button("次へ"):
            st.session_state.page = 5
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.submitted = False
            st.rerun()
            
    with col2:
        japanese_text = data.get('japanese', 'データがありません')
        st.markdown(
            f"""
            <style>
                .japanese-translation {{
                    color: white;
                    background-color: #333;
                    font-size: 1.1em;
                    padding: 10px;
                    border-radius: 5px;
                    white-space: pre-wrap;
                }}
            </style>
            <div class="japanese-translation">{japanese_text}</div>
            """,
            unsafe_allow_html=True
        )

elif st.session_state.page == 5: # 並べ替え・複数選択問題ページ
    st.title("テキストの問題を解きましょう")
    st.info("問題を解いたら答えをチェックして「提出」を押しましょう。")
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is not None and not data.empty:
        page_number = data.get('page', '不明') # 'id' を 'page' に変更
        st.subheader(f"ページ: {page_number}")

        st.subheader("問１：１番目から順にクリック")
        col_q1_1, col_q1_2, col_q1_3, col_q1_4 = st.columns(4)
        options_q1 = ['ア', 'イ', 'ウ', 'エ']
        selected_q1_1 = col_q1_1.radio("1番目", options_q1, key="q1_1")
        selected_q1_2 = col_q1_2.radio("2番目", [o for o in options_q1 if o != selected_q1_1], key="q1_2")
        selected_q1_3 = col_q1_3.radio("3番目", [o for o in options_q1 if o != selected_q1_1 and o != selected_q1_2], key="q1_3")
        remaining_options_q1_4 = [o for o in options_q1 if o != selected_q1_1 and o != selected_q1_2 and o != selected_q1_3]
        selected_q1_4 = col_q1_4.radio("4番目", remaining_options_q1_4, key="q1_4")
        selected_order_q1 = [selected_q1_1, selected_q1_2, selected_q1_3, selected_q1_4]
        is_q1_answered = len(set(selected_order_q1)) == 4

        st.subheader("問２：正しいものをすべてクリック")
        options_q2 = ["ア", "イ", "ウ", "エ", "オ"] # 固定の選択肢
        selected_options_q2 = []
        cols_q2 = st.columns(len(options_q2))
        for i, option in enumerate(options_q2):
            with cols_q2[i]:
                if st.checkbox(option, key=f"q2_{i}"):
                    selected_options_q2.append(option)

        is_q2_answered = len(selected_options_q2) > 0

        if st.button("提出"):
            if is_q1_answered and is_q2_answered:
                correct_order_q1_str = data.get('correct_order_q1', '')
                correct_order_q1 = [item.strip() for item in correct_order_q1_str.split(',')]
                is_correct_q1 = selected_order_q1 == correct_order_q1

                correct_answers_q2_str = data.get('correct_answers_q2', '')
                correct_answers_q2 = [item.strip() for item in correct_answers_q2_str.split(',')]
                is_correct_q2 = set(selected_options_q2) == set(correct_answers_q2)

                st.session_state["is_correct_q1"] = is_correct_q1
                st.session_state["is_correct_q2"] = is_correct_q2
                st.session_state["user_answer_q1"] = selected_order_q1
                st.session_state["user_answer_q2"] = selected_options_q2
                st.session_state["correct_answer_q1"] = correct_order_q1
                st.session_state["correct_answer_q2"] = correct_answers_q2

                # ① ここで Firebase への転送を行う
                user_id = st.session_state.get("user_id")
                row_index = st.session_state.get("fixed_row_index")
                wpm = st.session_state.get("wpm", 0.0)
                correct_answers_comprehension = st.session_state.get("correct_answers_to_store", 0)
                is_correct_q1_text = st.session_state.get("is_correct_q1")
                is_correct_q2_text = st.session_state.get("is_correct_q2")

                material_id = str(data.get("id", f"row_{st.session_state.row_to_load}")) if data is not None else "unknown"

                save_results(wpm, correct_answers_comprehension, material_id,
                             st.session_state.nickname, st.session_state.user_id,
                             is_correct_q1_text=is_correct_q1_text, is_correct_q2_text=is_correct_q2_text)

                st.session_state.page = 6 # 解答確認ページへ遷移
                st.rerun()
            else:
                st.error("両方の問題に答えてから「解答」を押してください。")

    else:
        st.error("問題データの読み込みに失敗しました。")

elif st.session_state.page == 6:
    st.subheader("丸付けしましょう。別冊（全訳と解説）を見て復習しましょう。")

    if "user_answer_q1" in st.session_state and "correct_answer_q1" in st.session_state and "is_correct_q1" in st.session_state:
        formatted_user_answer_q1 = ' → '.join(st.session_state.user_answer_q1)
        formatted_correct_answer_q1 = ' → '.join(st.session_state.correct_answer_q1)
        is_correct_q1 = st.session_state.is_correct_q1
        if is_correct_q1:
            st.success("問１：正解！")
            st.write(f"あなたの解答: {formatted_user_answer_q1}")
            st.write(f"正しい順番　: {formatted_correct_answer_q1}")
        else:
            st.error("問２：不正解...")
            st.write(f"あなたの解答: {formatted_user_answer_q1}")
            st.write(f"正しい順番　: {formatted_correct_answer_q1}")
    else:
        st.info("問１の解答データがありません")

    if "user_answer_q2" in st.session_state and "correct_answer_q2" in st.session_state and "is_correct_q2" in st.session_state:
        formatted_user_answer_q2 = ', '.join(st.session_state.user_answer_q2)
        formatted_correct_answer_q2 = ', '.join(st.session_state.correct_answer_q2)
        is_correct_q2 = st.session_state.is_correct_q2
        if is_correct_q2:
            st.success("問１：正解！")
            st.write(f"あなたの解答: {formatted_user_answer_q2}")
            st.write(f"正しい選択肢: {formatted_correct_answer_q2}")
        else:
            st.error("問２：不正解...")
            st.write(f"あなたの解答: {formatted_user_answer_q2}")
            st.write(f"正しい選択肢: {formatted_correct_answer_q2}")
    else:
        st.info("問２の解答データがありません")

    if st.button("ホームへ戻る"):
        st.session_state.page = 1
        st.session_state.start_time = None
        st.session_state.stop_time = None
        st.session_state.q1 = None
        st.session_state.q2 = None
        st.session_state.submitted = False
        st.session_state.wpm = 0.0
        st.session_state.correct_answers_to_store = 0
        st.session_state.is_correct_q1 = None
        st.session_state.is_correct_q2 = None
        st.session_state.user_answer_q1 = None
        st.session_state.user_answer_q2 = None
        st.session_state.correct_answer_q1 = None
        st.session_state.correct_answer_q2 = None
        st.rerun()
    # --- ここに日本語速読への遷移ボタンを追加 ---
    if st.button("国語の学習開始（表示される文章を読んでStopをおしましょう）", key="japanese_reading_from_page6", on_click=start_japanese_reading):
        pass

elif st.session_state.page == 7:
    col1, col2 = st.columns([1, 9]) # 幅を1:9に分割

    with col1:
        # 左カラムにStopボタンを配置
        if st.button("Stop", key="stop_japanese_reading_button"):
            st.session_state.stop_time_japanese = time.time()
            st.session_state.page = 8 # ページ8へ遷移
            st.rerun()

    with col2:
        # 右カラムに日本語縦書き画像を配置
        data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
        if data is not None:
            japanese_image_url = data.get('japanese_image_url')
            if japanese_image_url:
                st.image(japanese_image_url)
                # ★ここから追加★
                # 日本語の単語数をセッションステートに保存
                # 'word_count_ja' 列がCSVに存在することを前提としています
                st.session_state.word_count_japanese = data.get('word_count_ja', 0)
                # ★ここまで追加★
            else:
                st.error("対応する画像のURLが見つかりませんでした。")
        else:
            st.error("コンテンツデータの読み込みに失敗しました。")

elif st.session_state.page == 8: # 日本語読解問題ページ
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()

    st.info("問題を解いて「次へ」を押しましょう。")
    st.subheader("日本語読解問題")

    # 所要時間の表示
    if st.session_state.get("start_time") and st.session_state.get("stop_time_japanese"):
        total_time_japanese = st.session_state.stop_time_japanese - st.session_state.start_time
        st.write(f"所要時間: {total_time_japanese:.2f} 秒")
        # 日本語WPMの計算と表示 (word_count_japaneseが0でないことを確認)
        if st.session_state.word_count_japanese > 0:
            wpm_japanese = (st.session_state.word_count_japanese / total_time_japanese) * 60
            st.write(f"日本語単語数/分: **{wpm_japanese:.1f}** WPM")
        else:
            st.info("日本語の単語数データがありません。")
    else:
        st.info("まだ日本語速読が開始されていないか、停止されていません。")

    st.markdown("---") # 区切り線

    # 日本語問題 問1
    st.subheader("問１")
    st.write(data['q1_ja']) # q1_ja列のテキストを表示
    st.radio("問１の回答", ["正しい", "正しくない"], key="q1_ja")

    # 日本語問題 問2
    st.subheader("問２")
    st.write(data['q2_ja']) # q2_ja列のテキストを表示
    st.radio("問２の回答", ["正しい", "正しくない"], key="q2_ja")

    if st.button("次へ"):
        if st.session_state.q1_ja is None or st.session_state.q2_ja is None:
            st.error("両方の問題に答えてから「次へ」を押してください。")
        else:
            # 回答の正誤判定（表示はしないが、セッションステートに保持は可能）
            is_correct_q1_ja = (st.session_state.q1_ja == data['correct_answer_q1_ja'])
            is_correct_q2_ja = (st.session_state.q2_ja == data['correct_answer_q2_ja'])

            # ★Firebaseへの保存処理は一旦削除
            # save_results(...) はここには呼び出さない

            st.session_state.page = 9 # ページ9へ遷移
            st.rerun()

elif st.session_state.page == 9: # 日本語学習の最終ページ
    st.title("日本語学習 完了")
    st.success("本日の日本語学習お疲れ様でした！")
    st.write("結果は記録されました。（※現在、結果は送信されていません）") # メッセージを追加

    if st.button("ホームへ戻る"):
        # セッションステートをリセットしてページ1へ
        st.session_state.page = 1
        st.session_state.start_time = None
        st.session_state.stop_time = None # 英語用
        st.session_state.stop_time_japanese = None # 日本語用
        st.session_state.q1 = None # 英語Q1
        st.session_state.q2 = None # 英語Q2
        st.session_state.q1_ja = None # 日本語Q1
        st.session_state.q2_ja = None # 日本語Q2
        st.session_state.submitted = False
        st.session_state.wpm = 0.0
        st.session_state.correct_answers_to_store = 0
        st.session_state.is_correct_q1 = None
        st.session_state.is_correct_q2 = None
        st.session_state.user_answer_q1 = None
        st.session_state.user_answer_q2 = None
        st.session_state.correct_answer_q1 = None
        st.session_state.correct_answer_q2 = None
        st.session_state.word_count_japanese = 0 # 日本語単語数もリセット
        st.rerun()
