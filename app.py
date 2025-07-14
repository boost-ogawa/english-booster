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
import os
import bcrypt # bcryptをインポート

GITHUB_DATA_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/data.csv"
GITHUB_CSV_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/results.csv"
HEADER_IMAGE_URL = "https://github.com/boost-ogawa/english-booster/blob/main/English%20Booster_header.jpg?raw=true"
DATA_PATH = "data.csv"

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    # tempfileを削除
    os.unlink(f.name)

db = firestore.client()

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

# --- Firestoreに結果を保存する関数 ---
# user_idを引数と保存データから削除
def save_results(wpm, correct_answers, material_id, nickname): 
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()

    result_data = {
        # "user_id": user_id, # user_idを削除
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
# user_idではなくnicknameでフィルタリングするように変更
def display_wpm_history(nickname): # 引数をnicknameに変更
    if nickname: # nicknameが存在するか確認
        try:
            # Firestoreから直接データを読み込む
            # nicknameでフィルタリング
            results_ref = db.collection("results").where("nickname", "==", nickname).order_by("timestamp")
            docs = results_ref.stream()
            
            data_list = []
            for doc in docs:
                data = doc.to_dict()
                # 'timestamp'をdatetimeオブジェクトに変換し、JSTに変換
                dt_object = datetime.fromisoformat(data['timestamp'])
                jst = timezone('Asia/Tokyo')
                dt_object_jst = dt_object.astimezone(jst)
                data['測定年月'] = dt_object_jst.strftime('%Y-%m-%d %H:%M') # グラフ表示用にフォーマット
                data_list.append(data)

            if data_list:
                df_results = pd.DataFrame(data_list)
                # WPMが数値であることを確認
                df_results['wpm'] = pd.to_numeric(df_results['wpm'], errors='coerce')
                df_results.dropna(subset=['wpm'], inplace=True) # NaNを削除

                fig = px.line(df_results, x='測定年月', y='wpm', title='WPM推移')
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("まだ学習履歴がありません。")
        except Exception as e:
            st.error(f"過去データの読み込みまたは処理に失敗しました: {e}")
    else:
        st.info("ニックネームがありません。") # メッセージを調整

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
        padding: 20px 40px;
        font-size: 1.8rem;
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
@st.cache_data(ttl=3600) # 1時間キャッシュ
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
        
# --- Secrets からニックネームとIDでユーザー情報をロードする関数 (未使用だが残す) ---
def get_user_data(nickname, user_id):
    try:
        users = st.secrets.get("users", [])
        for user in users:
            if user["nickname"] == nickname and user["user_id"] == user_id:
                return user
        return None
    except Exception as e:
        print(f"ユーザーデータ取得エラー: {e}")
        return None

# --- セッション変数の初期化 ---
if "row_to_load" not in st.session_state:
    st.session_state.row_to_load = 0
if "fixed_row_index" not in st.session_state:
    config = load_config()
    st.session_state.fixed_row_index = config.get("fixed_row_index", 2)
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
    st.session_state.user_id = "" # ここに平文のID（パスワード）が一時的に保存される
if "show_full_graph" not in st.session_state:
    st.session_state.show_full_graph = False
if "set_page_key" not in st.session_state:
    st.session_state["set_page_key"] = "unique_key_speed"
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
    
# --- ページ遷移関数 ---
def set_page(page_number):
    st.session_state.page = page_number

# --- 「スピード測定開始」ボタンが押されたときに実行する関数 ---
def start_reading(page_number):
    st.session_state.start_time = time.time()
    st.session_state.page = page_number

# --- サイドバーのコンテンツ（コメントアウトされていますが、残しておきます） ---
#def sidebar_content():
#    st.sidebar.header("メニュー")
#    st.sidebar.markdown(f"[Google Classroom]({GOOGLE_CLASSROOM_URL})")
#    st.sidebar.markdown("[利用規約](#利用規約)")
#    st.sidebar.markdown("[プライバシーポリシー](#プライバシーポリシー)")
#    st.sidebar.markdown("---")
#    st.sidebar.subheader("その他")
#    st.sidebar.write("English Booster")
#    st.sidebar.write("Ver.1_01")

# --- 認証ページ（page 0） ---
if st.session_state.page == 0:
    st.title("ニックネームとIDを入力してください")
    col1, _ = st.columns(2)
    with col1:
        # 入力フォーム
        nickname = st.text_input("ニックネーム (半角英数字、_、-、半角スペース可)", key="nickname_input", value=st.session_state.get("nickname", ""))
        # IDはパスワードとして機能するため、初期値は空にするべき
        user_id_input = st.text_input("ID (パスワードとして機能します。半角英数字)", type="password", key="user_id_input", value="") 
        
        if st.button("次へ"):
            # 入力チェック
            if not nickname:
                st.warning("ニックネームを入力してください。")
            elif not user_id_input:
                st.warning("IDを入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z_\- ]+', nickname):
                st.error("ニックネームは半角英数字、_、-、半角スペースで入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z]+', user_id_input):
                st.error("IDは半角英数字で入力してください。")
            else:
                # 管理者情報をSecretsから取得
                admin_nickname = st.secrets.get("ADMIN_USERNAME")
                admin_hashed_password = st.secrets.get("ADMIN_PASSWORD") # ハッシュ化されたパスワードを取得

                # ユーザーが入力したID（パスワード）をバイト文字列に変換
                user_entered_password_bytes = user_id_input.strip().encode('utf-8')

                authenticated = False
                is_admin_user = False

                # 管理者認証
                if nickname.strip() == admin_nickname:
                    # secretsにハッシュ化パスワードがあるか確認
                    if admin_hashed_password:
                        try:
                            # 入力されたパスワードとsecretsから取得したハッシュ値を比較
                            if bcrypt.checkpw(user_entered_password_bytes, admin_hashed_password.encode('utf-8')):
                                authenticated = True
                                is_admin_user = True
                        except ValueError: # ハッシュ値の形式が不正な場合など
                            pass # 認証失敗として扱う
                    
                # 管理者として認証されなかった場合のみ、一般ユーザー認証を試みる
                if not authenticated: 
                    # 一般ユーザー認証（Secretsのusersリストから確認）
                    users_from_secrets = st.secrets.get("users", [])
                    for user_info in users_from_secrets:
                        if nickname.strip() == user_info.get("nickname"):
                            stored_hashed_id = user_info.get("user_id") # ハッシュ化されたIDを取得
                            if stored_hashed_id: # 存在する場合のみ比較
                                try:
                                    if bcrypt.checkpw(user_entered_password_bytes, stored_hashed_id.encode('utf-8')):
                                        authenticated = True
                                        is_admin_user = False
                                        break
                                except ValueError: # ハッシュ値の形式が不正な場合など
                                    pass # 認証失敗として扱う
                            break # ニックネームが一致するユーザーが見つかったらループを抜ける

                if authenticated:
                    st.session_state.nickname = nickname.strip()
                    st.session_state.user_id = user_id_input.strip() # セッションには入力されたパスワード（平文）を保存
                    st.session_state.is_admin = is_admin_user
                    st.session_state.page = 1 # 認証後、メインメニューページへ
                    st.rerun() # ページ遷移を即時実行
                else:
                    st.error("ニックネームまたはIDが正しくありません。")

# --- 認証後のメインメニューページ（page 1） ---
elif st.session_state.page == 1:
    # sidebar_content() # コメントアウトされたサイドバー関数
    st.title(f"こんにちは、{st.session_state.nickname}さん！")

    # 管理者設定は一旦ここに残します
    if st.session_state.is_admin:
        st.subheader("管理者設定")
        manual_index = st.number_input("表示する行番号 (0から始まる整数)", 0, value=st.session_state.get("fixed_row_index", 0))
        if st.button("表示行番号を保存"):
            st.session_state.fixed_row_index = manual_index
            save_config(manual_index) # Firestore に保存する関数を呼び出す (コメントアウトを外しました)

    # --- ここから2カラムレイアウトの開始 ---
    col1, col2 = st.columns([0.6, 0.4]) # 左を広め（6割）、右を狭め（4割）に調整

    with col1:
        st.header("授業動画")
        st.markdown("毎日更新！新しい動画をチェックしましょう！")

        try:
            video_data = pd.read_csv("videos.csv")
            video_data["date"] = pd.to_datetime(video_data["date"])
            video_data = video_data.sort_values(by="date", ascending=False).reset_index(drop=True)

            if not video_data.empty:
                for index, row in video_data.iterrows():
                    expander_header = f"{row['title']} （公開日: {row['date'].strftime('%Y年%m月%d日')}）"
                    
                    with st.expander(expander_header):
                        st.write(row["description"])
                        if "type" in row and row["type"] == "embed":
                            st.markdown(f'<iframe width="100%" height="315" src="{row["url"]}" frameborder="0" allowfullscreen></iframe>', unsafe_allow_html=True)
                        elif "type" in row and row["type"] == "link":
                            st.markdown(f"[動画を見る]({row['url']})")
                        else:
                            st.markdown(f'<iframe width="100%" height="315" src="{row["url"]}" frameborder="0" allowfullscreen></iframe>', unsafe_allow_html=True)
            else:
                st.info("現在、表示できる動画はありません。")

        except FileNotFoundError:
            st.error("動画情報ファイル (videos.csv) が見つかりません。")
            st.info("videos.csvを作成してアップロードしてください。")
        except Exception as e:
            st.error(f"動画情報の読み込み中にエラーが発生しました: {e}")

    with col2:
        st.header("スピード測定")
        st.write("ボタンを押して英文を読みましょう！")
        st.write("　※　文章は毎月更新されます")
        st.write("　※　測定は何回でもできます")
        st.write("　※　各月初回の結果が保存されます")
        if st.button("スピード測定開始", key="start_reading_button", use_container_width=True, on_click=start_reading, args=(2,)):
            pass

    # --- 2カラムレイアウトの終了 ---
    st.subheader(f"{st.session_state.nickname}さんのWPM推移")
    current_nickname = st.session_state.get('nickname') # nicknameを取得
    display_wpm_history(current_nickname) # nicknameを渡す
    # st.info("月次WPM推移グラフは後日表示されます。") # 代替メッセージは不要

    st.markdown("---")
    st.markdown("© 2025 英文速解English Booster", unsafe_allow_html=True)

# --- 英文表示ページ（旧 page 1、現在は page 2 に相当） ---
elif st.session_state.page == 2:
    # sidebar_content() # コメントアウトされたサイドバー関数
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
        st.session_state.page = 3
        st.rerun()

# 問題ページ（旧 page 2）
elif st.session_state.page == 3:
    # sidebar_content() # コメントアウトされたサイドバー関数
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

    if st.button("Submit"):
        if st.session_state.q1 is not None and st.session_state.q2 is not None:
            st.session_state.page = 4
            st.rerun()
        else:
            st.error("両方の質問に答えてください。")

# 結果表示ページ（旧 page 3）
elif st.session_state.page == 4:
    # sidebar_content() # コメントアウトされたサイドバー関数
    st.success("結果を記録しました。")
    col1, col2 = st.columns([1, 2])
    with col2:
        current_nickname = st.session_state.get('nickname') # nicknameを取得
        display_wpm_history(current_nickname) # nicknameを渡す
        # st.info("月次WPM推移グラフは後日表示されます。") # 代替メッセージは不要

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
                # user_idを削除してsave_resultsを呼び出し
                save_results(wpm, correct_answers_to_store, str(data.get("id", f"row_{st.session_state.row_to_load}")),
                                st.session_state.nickname)
                st.session_state.submitted = True

        if st.button("意味を確認"):
            st.session_state.page = 5
            st.rerun()

# --- 意味確認ページ（旧 page 4） ---
elif st.session_state.page == 5:
    # sidebar_content() # コメントアウトされたサイドバー関数
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
        st.session_state.page = 1
        st.session_state.start_time = None
        st.session_state.stop_time = None
        st.session_state.submitted = False
        st.session_state.q1 = None
        st.session_state.q2 = None
        st.rerun()