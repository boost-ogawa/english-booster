import streamlit as st
import pandas as pd
import time
from datetime import datetime, date # datetime に加えて date もインポート
from pytz import timezone
import firebase_admin
from firebase_admin import credentials, firestore
import json
import tempfile
import re
import os
import bcrypt 

GITHUB_DATA_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/data_j.csv"
GITHUB_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/results_j.csv"
DATA_PATH = "data_j.csv"
GOOGLE_CLASSROOM_URL = "YOUR_GOOGLE_CLASSROOM_URL_HERE" 

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

db = firestore.client()

# --- データ読み込み関数 ---
def load_material(github_url, row_index):
    """GitHubのCSVファイルから指定された行のデータを読み込む関数"""
    try:
        df = pd.read_csv(github_url)
        if 0 <= row_index < len(df):
            return df.iloc[row_index]
        else:
            # st.error(f"指定された行番号 ({row_index + 1}) はファイルに存在しません。") # このエラーは不要になる
            return None
    except Exception as e:
        st.error(f"GitHubからのデータ読み込みに失敗しました: {e}")
        return None

# --- Firestoreに英語の結果を保存する関数 ---
def save_english_results(wpm, correct_answers_comprehension, material_id, nickname,
                          is_correct_q1_text=None, is_correct_q2_text=None):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "nickname": nickname,
        "timestamp": timestamp,
        "material_id": material_id,
        "wpm": round(wpm, 1),
        "comprehension_score": correct_answers_comprehension,
        "is_correct_q1_text": is_correct_q1_text,
        "is_correct_q2_text": is_correct_q2_text
    }

    try:
        db.collection("english_results").add(result_data)
        print("英語の結果が english_results に保存されました")
    except Exception as e:
        st.error(f"英語結果の保存に失敗しました: {e}")

# --- Firestoreに英語のテキスト理解問題の結果を保存する関数 ---
def save_english_text_comprehension_results(material_id, nickname,
                                            is_correct_q1_text, is_correct_q2_text,
                                            user_answer_q1, user_answer_q2,
                                            correct_answer_q1, correct_answer_q2):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "nickname": nickname,
        "timestamp": timestamp,
        "material_id": material_id,
        "is_correct_q1_text": is_correct_q1_text,
        "is_correct_q2_text": is_correct_q2_text,
        "user_answer_q1": user_answer_q1,
        "user_answer_q2": user_answer_q2,
    }

    try:
        # 新しいコレクション "english_text_results" に保存
        db.collection("english_text_results").add(result_data)
        print("英語のテキスト理解問題の結果が english_text_results に保存されました")
    except Exception as e:
        st.error(f"英語のテキスト理解問題結果の保存に失敗しました: {e}")

# --- Firestoreに日本語の結果を保存する関数 ---
def save_japanese_results(wpm_japanese, material_id, nickname,
                          is_correct_q1_ja=None, is_correct_q2_ja=None, is_correct_q3_ja=None):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        "nickname": nickname,
        "timestamp": timestamp,
        "material_id": material_id,
        "wpm_japanese": round(wpm_japanese, 1) if wpm_japanese is not None else None,
        "is_correct_q1_ja": is_correct_q1_ja,
        "is_correct_q2_ja": is_correct_q2_ja,
        "is_correct_q3_ja": is_correct_q3_ja 
    }

    try:
        db.collection("japanese_results").add(result_data) 
        print("日本語の結果が japanese_results に保存されました")
    except Exception as e:
        st.error(f"日本語結果の保存に失敗しました: {e}")

# --- Firestoreから設定を読み込む関数 ---
def load_config():
    try:
        doc_ref = db.collection("settings").document("app_config") 
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
        doc_ref = db.collection("settings").document("app_config") 
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

    /* 英文・日本語訳表示用の共通段落スタイル */
    .custom-paragraph {
        font-family: Georgia, serif;
        line-height: 1.6;
        font-size: 1.5rem;
        padding: 10px !important;
        border-radius: 5px;
        /* ここでは margin-top を設定せず、h2 との連携で調整 */
    }

    /* 日本語訳の特定の背景色 */
    .japanese-translation {
        color: white;
        background-color: #333;
        font-size: 1.3rem !important;
    }

    /* サブヘッダー (h2) のマージン調整 - これが最重要！ */
    /* h2要素全体の上と下のマージンを調整し、要素間の隙間を制御 */
    h2 {
        margin-top: 0.5rem;    /* 必要に応じてサブヘッダーの上に少し余白を持たせる */
        margin-bottom: 0.2rem; /* ★ここがポイント！下にわずかな余白を残すか、0にする★ */
                                /* 0rem で完全にくっつくはず。または負の値を少し試す */
    }

    /* スタートボタンのスタイル（高さ・フォントサイズ調整済み） */
    div.stButton > button:first-child {
        background-color: #28a745;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 20px 40px;
        font-size: 1.8rem;
    }

    div.stButton > button:first-child:hover {
        background-color: #218838;
    }

    div[data-testid="stRadio"] label p {
        font-size: 1.2rem !important; /* ★変更したいフォントサイズ★ */
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
    div[data-testid="stLinkButton"] a {
        background-color: #28a745;
        color: white !important;
        font-weight: bold;
        border-radius: 8px;
        padding: 20px 40px;
        font-size: 1.8rem;
        text-decoration: none;
        display: block;
        text-align: center;
    }
    div[data-testid="stLinkButton"] a:hover {
        background-color: #218838;
    }
        /* Streamlitの画像を対象 */
    img {
        max-height: 80vh; /* 画面の高さの80%を最大高さとする */
        object-fit: contain; /* アスペクト比を維持しつつ、要素内に収まるように調整 */
        display: block; /* 中央寄せのためにブロック要素に */
        margin-left: auto; /* 中央寄せ */
        margin-right: auto; /* 中央寄せ */
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
    st.session_state["set_page_key"] = "unique_key_speed" 
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False 
if "stop_time_japanese" not in st.session_state:
    st.session_state.stop_time_japanese = None
if "q1_ja" not in st.session_state:
    st.session_state.q1_ja = None
if "q2_ja" not in st.session_state:
    st.session_state.q2_ja = None
if "q3_ja" not in st.session_state: # ★追加: 4択問題用のセッションステート
    st.session_state.q3_ja = None
if "word_count_japanese" not in st.session_state: 
    st.session_state.word_count_japanese = 0
if "selected_material_info" not in st.session_state: # ★追加: 選択された教材情報（インデックスと有無）
    st.session_state.selected_material_info = {"index": 0, "found": False}
if "selected_date" not in st.session_state: # ★追加: 日付ピッカー用
    st.session_state.selected_date = date.today()

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
    st.title("ニックネームとパスワードを入力してください")
    col1, _ = st.columns(2)
    with col1:
        nickname = st.text_input("ニックネーム (半角英数字)", key="nickname_input", value=st.session_state.nickname)
        password = st.text_input("パスワード", type="password", key="password_input", value=st.session_state.user_id)
        if st.button("次へ"):
            if not nickname:
                st.warning("ニックネームを入力してください。")
            elif not password:
                st.warning("パスワードを入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z_\- ]+', nickname):
                st.error("ニックネームは半角英数字で入力してください。")
            else:
                admin_nickname = st.secrets.get("ADMIN_USERNAME")
                admin_hashed_password = st.secrets.get("ADMIN_PASSWORD") 

                users_from_secrets = st.secrets.get("users", [])

                user_entered_password_bytes = password.strip().encode('utf-8') 

                authenticated = False
                is_admin_user = False

                if nickname.strip() == admin_nickname:
                    if admin_hashed_password:
                        try:
                            if bcrypt.checkpw(user_entered_password_bytes, admin_hashed_password.encode('utf-8')):
                                authenticated = True
                                is_admin_user = True
                        except ValueError:
                            pass 
                
                if not authenticated:
                    for user_info in users_from_secrets:
                        if nickname.strip() == user_info.get("nickname"):
                            stored_hashed_id = user_info.get("user_id") 
                            if stored_hashed_id:
                                try:
                                    if bcrypt.checkpw(user_entered_password_bytes, stored_hashed_id.encode('utf-8')):
                                        authenticated = True
                                        is_admin_user = False
                                        break 
                                except ValueError:
                                    pass
                            break 
                
                if authenticated:
                    st.session_state.nickname = nickname.strip()
                    st.session_state.user_id = nickname.strip() 
                    st.session_state.is_admin = is_admin_user
                    st.session_state.page = 1
                    st.rerun()
                else:
                    st.error("ニックネームまたはパスワードが正しくありません。")
elif st.session_state.page == 1:
    st.title(f"こんにちは、{st.session_state.nickname}さん！")

    if st.session_state.is_admin:
        st.subheader("管理者設定")
        manual_index = st.number_input("表示する行番号 (0から始まる整数)", 0, value=st.session_state.get("fixed_row_index", 0))
        if st.button("表示行番号を保存"):
            st.session_state.fixed_row_index = manual_index
            save_config(manual_index) 
        st.markdown("---") # 管理者設定とユーザー向け選択を区切る

    st.subheader("学習する教材を選びましょう")

    # 日付選択ピッカーの表示
    # default値を st.session_state.selected_date に設定し、ユーザーの選択で更新
    selected_date_from_picker = st.date_input(
        "学習する日付を選択してください",
        value=st.session_state.selected_date,
        key="date_picker"
    )
    # 選択された日付をセッションステートに保存（次回ロード時にも保持するため）
    st.session_state.selected_date = selected_date_from_picker

    # CSVデータを読み込み、選択された日付に一致する教材を検索
    try:
        df_data = pd.read_csv(GITHUB_DATA_URL)
        
        # 'date'列が存在するか確認
        if 'date' in df_data.columns:
            # CSVの'date'列をdatetimeオブジェクトに変換し、日付部分のみを比較
            # エラーになる日付データがある場合はcoerceでNoneにする
            df_data['date'] = pd.to_datetime(df_data['date'], errors='coerce').dt.date
            
            # 選択された日付に一致する行を検索
            # df_data['date'].notna() で、変換に失敗した行（NaTになった行）を除外
            matching_rows = df_data[(df_data['date'].notna()) & (df_data['date'] == st.session_state.selected_date)]
            
            if not matching_rows.empty:
                # 見つかった最初の行のインデックス（0から始まる行番号）をセット
                # 複数ある場合は最初のものを使用
                st.session_state.row_to_load = matching_rows.index[0]
                st.session_state.selected_material_info = {"index": st.session_state.row_to_load, "found": True}
                st.success(f"🗓️ **{st.session_state.selected_date.strftime('%Y年%m月%d日')}** の教材が見つかりました！")
            else:
                # 教材が見つからない場合
                st.session_state.row_to_load = st.session_state.get("fixed_row_index", 0) # デフォルトは管理者設定の行番号か0
                st.session_state.selected_material_info = {"index": st.session_state.row_to_load, "found": False}
                st.warning(f"⚠️ **{st.session_state.selected_date.strftime('%Y年%m月%d日')}** の教材はありません。現在選択中の教材を使用します。")
        else:
            # 'date'列が存在しない場合のエラーハンドリング
            st.error("データファイルに日付 ('date') 列が見つかりません。教材の選択は管理者設定に依存します。")
            st.session_state.row_to_load = st.session_state.get("fixed_row_index", 0)
            st.session_state.selected_material_info = {"index": st.session_state.row_to_load, "found": True} # デフォルト教材は「ある」と見なす
    except Exception as e:
        st.error(f"教材データの読み込みまたは処理に失敗しました: {e}")
        st.session_state.row_to_load = st.session_state.get("fixed_row_index", 0)
        st.session_state.selected_material_info = {"index": st.session_state.row_to_load, "found": False} # エラー時は教材は「ない」と見なす

    # 英語の学習開始ボタン
    # load_material関数に st.session_state.fixed_row_index の代わりに st.session_state.row_to_load を渡すように変更
    if st.button("英語の学習開始（表示される英文を読んでStopをおきましょう）", key="english_start_button", use_container_width=True, on_click=start_reading, args=(2,)):
        pass
    
    # 国語の学習開始ボタン
    # こちらも st.session_state.row_to_load を利用
    if st.button("国語の学習開始（表示される文章を読んでStopをおきましょう）", key="japanese_start_button", use_container_width=True, on_click=start_japanese_reading):
        pass
    st.link_button(
        "📚 VocaBoosterで単語トレーニング",
        "https://filedn.com/lTkchLpf4Vo0aRMDYi0tvk5/VocaBooster/VocaBooster.html",
        use_container_width=True
    )

elif st.session_state.page == 2:
    # ここから load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is None:
        st.error("教材の読み込みに失敗しました。ホームに戻ってください。")
        if st.button("ホームへ戻る", key="back_to_home_page2"):
            st.session_state.page = 1
            st.rerun()
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
    # ここも load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is None:
        st.error("教材の読み込みに失敗しました。ホームに戻ってください。")
        if st.button("ホームへ戻る", key="back_to_home_page3"):
            st.session_state.page = 1
            st.rerun()
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
    st.success("結果と意味を確認して「次へ」を押しましょう。") 

    col1, col2, col3 = st.columns([1, 2, 2])

    # ここも load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is None:
        st.error("教材の読み込みに失敗しました。ホームに戻ってください。")
        if st.button("ホームへ戻る", key="back_to_home_page4"):
            st.session_state.page = 1
            st.rerun()
        st.stop()

    with col1: # 左カラム: 結果表示
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
            st.info("回答の読み込み中です...") 
        
        if st.button("次へ"):
            st.session_state.page = 45
            st.session_state.start_time = None
            st.session_state.stop_time = None
            st.session_state.submitted = False
            st.rerun()

    with col2: 
        english_text = data.get('main', '原文がありません')
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {english_text}
            </div>
            """, unsafe_allow_html=True
        )

    with col3: 
        japanese_text = data.get('japanese', 'データがありません')
        st.markdown(
            f"""
            <div class="custom-paragraph japanese-translation">
            {japanese_text}
            </div>
            """,
            unsafe_allow_html=True
        )

elif st.session_state.page == 45: 
    st.title("復習：音声を聞いてみましょう")
    st.info("英文の音声を聞いて内容を確認しましょう。")

    # ここも load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is None:
        st.error("教材の読み込みに失敗しました。ホームに戻ってください。")
        if st.button("ホームへ戻る", key="back_to_home_page45"):
            st.session_state.page = 1
            st.rerun()
        st.stop()

    audio_url = data.get('audio_url') 
    main_text = data.get('main') 

    if isinstance(audio_url, str) and audio_url.strip() != "":
        st.subheader("💡 音声を聞く")
        try:
            st.audio(audio_url, format="audio/mp3") 
        except Exception as e:
            st.warning(f"音声ファイルの再生に失敗しました。URL: {audio_url} エラー: {e}")
            st.subheader("原文")
            st.markdown(
                f"""
                <div class="custom-paragraph">
                {main_text}
                </div>
                """, unsafe_allow_html=True
            )
            st.markdown("---")
            if st.button("次の問題へ進む"):
                st.session_state.page = 5
                st.rerun()

        st.subheader("原文")
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {main_text}
            </div>
            """, unsafe_allow_html=True
        )
    else:
        st.warning("この英文には音声データがありません。")
        st.markdown(
            f"""
            <div class="custom-paragraph">
            {main_text}
            </div>
            """, unsafe_allow_html=True
        )

    st.markdown("---")
    if st.button("次の問題へ進む"):
        st.session_state.page = 5
        st.rerun()

elif st.session_state.page == 5: 
    st.title("テキストの問題を解きましょう")
    st.info("問題を解いたら答えをチェックして「提出」を押しましょう。")
    # ここも load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is not None and not data.empty:
        page_number = data.get('page', '不明') 
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
        options_q2 = ["ア", "イ", "ウ", "エ", "オ"] 
        selected_options_q2 = []
        cols_q2 = st.columns(len(options_q2))
        for i, option in enumerate(options_q2):
            with cols_q2[i]:
                if st.checkbox(option, key=f"q2_{i}"):
                    selected_options_q2.append(option)

        is_q2_answered = len(selected_options_q2) > 0

        if st.button("提出"):
            if is_q1_answered and is_q2_answered:
                # --- ここからが「正誤判定とセッションステートへの保存」の具体的な内容です ---
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
                # --- 「正誤判定とセッションステートへの保存」ここまで ---

                material_id = str(data.get("id", f"row_{st.session_state.row_to_load}")) if data is not None else "unknown"

                # ここで新しく定義した save_english_text_comprehension_results 関数を呼び出す
                save_english_text_comprehension_results(
                    material_id=material_id,
                    nickname=st.session_state.nickname,
                    is_correct_q1_text=st.session_state.is_correct_q1,
                    is_correct_q2_text=st.session_state.is_correct_q2,
                    user_answer_q1=st.session_state.user_answer_q1,
                    user_answer_q2=st.session_state.user_answer_q2,
                    correct_answer_q1=st.session_state.correct_answer_q1,
                    correct_answer_q2=st.session_state.correct_answer_q2
                )

                st.session_state.page = 6
                st.rerun()
            else:
                st.error("両方の問題に答えてから「解答」を押してください。")

    else:
        st.error("問題データの読み込みに失敗しました。ホームに戻ってください。")
        if st.button("ホームへ戻る", key="back_to_home_page5"):
            st.session_state.page = 1
            st.rerun()
        st.stop()


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
            st.success("問２：正解！")
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
    if st.button("国語の学習開始（表示される文章を読んでStopをおきましょう）", key="japanese_reading_from_page6", on_click=start_japanese_reading):
        pass

elif st.session_state.page == 7:
    col1, col2 = st.columns([1, 8]) 

    with col1:
        if st.button("Stop", key="stop_japanese_reading_button"):
            st.session_state.stop_time_japanese = time.time()
            st.session_state.page = 8 
            st.rerun()

    with col2:
        # ここも load_material 関数の引数を st.session_state.row_to_load に変更
        data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
        if data is not None:
            japanese_image_url = data.get('japanese_image_url')
            if japanese_image_url:
                st.image(japanese_image_url, use_container_width=True)
                st.session_state.word_count_japanese = data.get('word_count_ja', 0)
            else:
                st.error("対応する画像のURLが見つかりませんでした。")
        else:
            st.error("コンテンツデータの読み込みに失敗しました。ホームに戻ってください。")
            if st.button("ホームへ戻る", key="back_to_home_page7"):
                st.session_state.page = 1
                st.rerun()
            st.stop()

elif st.session_state.page == 8: # 日本語読解問題ページ
    # ここも load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is None:
        st.error("教材の読み込みに失敗しました。ホームに戻ってください。")
        if st.button("ホームへ戻る", key="back_to_home_page8"):
            st.session_state.page = 1
            st.rerun()
        st.stop()

    st.info("問題を解いて「次へ」を押しましょう。")
    
    question_type_ja = data.get('question_type_ja', 'binary_double') 

    if question_type_ja == 'binary_double':
        st.session_state.q3_ja = None 
    elif question_type_ja == 'multiple_single':
        st.session_state.q1_ja = None 
        st.session_state.q2_ja = None


    if data.get('ja_intro_text'): 
        st.subheader(data['ja_intro_text'])
    st.markdown("---") 

    wpm_japanese_calculated = 0.0 

    if question_type_ja == 'binary_double':
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("問１")
            st.write(data['q1_ja']) 
            st.radio("問１の解答", ["正しい", "正しくない"], key="q1_ja")
        with col2:
            st.subheader("問２")
            st.write(data['q2_ja']) 
            st.radio("問２の解答", ["正しい", "正しくない"], key="q2_ja")
        
        if st.button("次へ"):
            if st.session_state.q1_ja is None or st.session_state.q2_ja is None:
                st.error("両方の問題に答えてから「次へ」を押してください。")
            else:
                st.session_state.is_correct_q1_ja = (st.session_state.q1_ja == data['correct_answer_q1_ja'])
                st.session_state.is_correct_q2_ja = (st.session_state.q2_ja == data['correct_answer_q2_ja'])
                st.session_state.is_correct_q3_ja = None 

                if st.session_state.get("start_time") and st.session_state.get("stop_time_japanese") and st.session_state.word_count_japanese > 0:
                    total_time_japanese = st.session_state.stop_time_japanese - st.session_state.start_time
                    wpm_japanese_calculated = (st.session_state.word_count_japanese / total_time_japanese) * 60

                material_id_ja = str(data.get("id", f"row_{st.session_state.row_to_load}_ja")) if data is not None else "unknown_ja" # material_idも変更
                save_japanese_results(wpm_japanese_calculated, material_id_ja,
                                      st.session_state.nickname,
                                      is_correct_q1_ja=st.session_state.is_correct_q1_ja,
                                      is_correct_q2_ja=st.session_state.is_correct_q2_ja,
                                      is_correct_q3_ja=st.session_state.is_correct_q3_ja) 
                st.session_state.page = 9 
                st.rerun()

    elif question_type_ja == 'multiple_single':
        st.subheader("問題") 
        st.write(data['q3_ja']) 
        st.radio("解答", [data['q3a_ja'], data['q3b_ja'], data['q3c_ja'], data['q3d_ja']], key="q3_ja")

        if st.button("次へ"):
            if st.session_state.q3_ja is None:
                st.error("問題に答えてから「次へ」を押してください。")
            else:
                st.session_state.is_correct_q3_ja = (st.session_state.q3_ja == data['correct_answer_q3_ja'])
                st.session_state.is_correct_q1_ja = None 
                st.session_state.is_correct_q2_ja = None

                if st.session_state.get("start_time") and st.session_state.get("stop_time_japanese") and st.session_state.word_count_japanese > 0:
                    total_time_japanese = st.session_state.stop_time_japanese - st.session_state.start_time
                    wpm_japanese_calculated = (st.session_state.word_count_japanese / total_time_japanese) * 60

                material_id_ja = str(data.get("id", f"row_{st.session_state.row_to_load}_ja")) if data is not None else "unknown_ja" # material_idも変更
                save_japanese_results(wpm_japanese_calculated, material_id_ja,
                                      st.session_state.nickname,
                                      is_correct_q1_ja=st.session_state.is_correct_q1_ja, 
                                      is_correct_q2_ja=st.session_state.is_correct_q2_ja, 
                                      is_correct_q3_ja=st.session_state.is_correct_q3_ja)
                st.session_state.page = 9
                st.rerun()

elif st.session_state.page == 9: # 日本語学習の最終結果表示ページ
    st.success("もう一度文章を読んで答えの根拠を考えましょう")
    # ここも load_material 関数の引数を st.session_state.row_to_load に変更
    data = load_material(GITHUB_DATA_URL, st.session_state.row_to_load)
    if data is None:
        st.error("コンテンツデータの読み込みに失敗しました。ホームに戻ってください。") 
        if st.button("ホームへ戻る", key="back_to_home_page9_error"):
            st.session_state.page = 1
            st.rerun()
        st.stop()

    col1, col2 = st.columns([1, 3]) 

    with col1:
        st.subheader("📖 読書データ")
        if st.session_state.get("start_time") and st.session_state.get("stop_time_japanese"):
            total_time_japanese = st.session_state.stop_time_japanese - st.session_state.start_time
            st.write(f"読書時間: **{total_time_japanese:.2f} 秒**")

            if st.session_state.word_count_japanese > 0:
                wpm_japanese = (st.session_state.word_count_japanese / total_time_japanese) * 60
                st.write(f"1分あたりの文字数: **{wpm_japanese:.1f} WPM**") 
            else:
                st.info("日本語の文字数データがありませんでした。")
        else:
            st.info("日本語速読の計測データがありません。")

        st.subheader("📝 問題結果")
        
        question_type_ja = data.get('question_type_ja', 'binary_double')

        if question_type_ja == 'binary_double':
            if "is_correct_q1_ja" in st.session_state and st.session_state.is_correct_q1_ja is not None:
                if st.session_state.is_correct_q1_ja:
                    st.write("問１: ✅ **正解**")
                else:
                    st.write("問１: ❌ **不正解**")
                st.write(data['q1_ja']) 
                st.write(f"あなたの回答: **{st.session_state.q1_ja}**")
                st.write(f"正解: **{data['correct_answer_q1_ja']}**")
            else:
                st.info("問１の解答データがありません。")

            if "is_correct_q2_ja" in st.session_state and st.session_state.is_correct_q2_ja is not None:
                if st.session_state.is_correct_q2_ja:
                    st.write("問２: ✅ **正解**")
                else:
                    st.write("問２: ❌ **不正解**")
                st.write(data['q2_ja']) 
                st.write(f"あなたの回答: **{st.session_state.q2_ja}**")
                st.write(f"正解: **{data['correct_answer_q2_ja']}**")
            else:
                st.info("問２の解答データがありません。")

        elif question_type_ja == 'multiple_single':
            if "is_correct_q3_ja" in st.session_state and st.session_state.is_correct_q3_ja is not None:
                if st.session_state.is_correct_q3_ja:
                    st.write("問３: ✅ **正解**")
                else:
                    st.write("問３: ❌ **不正解**")
                st.write(data['q3_ja']) 
                st.write(f"あなたの回答: **{st.session_state.q3_ja}**")
                st.write(f"正解: **{data['correct_answer_q3_ja']}**")
            else:
                st.info("問３の解答データがありません。")

    with col2:
        japanese_image_url = data.get('japanese_image_url')
        if japanese_image_url:
            st.image(japanese_image_url)
            st.session_state.word_count_japanese = data.get('word_count_ja', 0)
        else:
            st.error("対応する画像のURLが見つかりませんでした。")

    st.markdown("---")
    video_url = data.get('japanese_explanation_video_url')

    if video_url:
        st.subheader("解説動画へのリンク")
        # st.markdown で直接リンクを貼るだけ
        st.markdown(f"[クリックして解説動画を見る]({video_url})")
        st.info("上記のリンクをクリックすると、動画が新しいタブで開きます。")
        st.markdown("---")
    else:
            st.info("この教材には関連する解説動画がありません。")
            st.markdown("---") # 区切り線は残す

    if st.button("ホームへ戻る"):
        st.session_state.page = 1
        st.session_state.start_time = None
        st.session_state.stop_time = None 
        st.session_state.stop_time_japanese = None 
        st.session_state.q1 = None 
        st.session_state.q2 = None 
        st.session_state.q1_ja = None 
        st.session_state.q2_ja = None 
        st.session_state.q3_ja = None 
        st.session_state.submitted = False
        st.session_state.wpm = 0.0
        st.session_state.correct_answers_to_store = 0
        st.session_state.is_correct_q1 = None
        st.session_state.is_correct_q2 = None
        st.session_state.user_answer_q1 = None
        st.session_state.user_answer_q2 = None
        st.session_state.correct_answer_q1 = None
        st.session_state.correct_answer_q2 = None
        st.session_state.word_count_japanese = 0 
        st.rerun()
