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
import bcrypt
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
from matplotlib import rcParams

# --- 定数設定 ---
GITHUB_DATA_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/main/data.csv"
HEADER_IMAGE_URL = "https://github.com/boost-ogawa/english-booster/blob/main/English%20Booster_header.jpg?raw=true"

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
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
def save_results(wpm, correct_answers, material_id, nickname):
    jst = timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).isoformat()
    result_data = {
        "nickname": nickname,
        "timestamp": timestamp,
        "material_id": material_id,
        "wpm": round(wpm, 1),
        "correct_answers": correct_answers
    }
    try:
        db.collection("results").add(result_data)
        print("結果が保存されました")
        user_profile_ref = db.collection("user_profiles").document(nickname)
        user_profile_ref.update({
            "watched_materials": firestore.ArrayUnion([material_id])
        })
        print(f"ユーザー {nickname} の教材完了履歴が更新されました: {material_id}")
    except Exception as e:
        st.error(f"結果の保存に失敗しました: {e}")

# --- ページ設定（最初に書く必要あり） ---
st.set_page_config(page_title="Speed Reading App", layout="wide", initial_sidebar_state="collapsed")

# --- スタイル設定 ---
st.markdown(
    """
    <style>
    .stApp {
        background-color: #000D36;
        color: #ffffff;
    }
    .custom-paragraph {
        font-family: Georgia, serif;
        line-height: 1.8;
        font-size: 1.5rem;
    }
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
        font-size: 1.2rem !important;
        line-height: 1.4 !important;
        color: #FFFFFF !important;
        margin-bottom: 0.3rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- ヘッダー画像の表示 ---
st.image(HEADER_IMAGE_URL, use_container_width=True)

# --- データ読み込み関数 ---
@st.cache_data(ttl=3600)
def load_material(github_url, row_index):
    try:
        df = pd.read_csv(github_url)
        if 0 <= row_index < len(df):
            material_data = df.iloc[row_index].to_dict()
            material_data['material_id_for_save'] = str(row_index)
            return material_data
        else:
            st.error(f"指定された行番号 ({row_index + 1}) はファイルに存在しません。")
            return None
    except Exception as e:
        st.error(f"GitHubからのデータ読み込みに失敗しました: {e}")
        return None

# --- セッション変数の初期化 ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
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
    st.session_state.user_id = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- ページ遷移関数 ---
def go_to_main_page(nickname, user_id, is_admin):
    st.session_state.nickname = nickname.strip()
    st.session_state.user_id = user_id.strip()
    st.session_state.is_admin = is_admin
    st.session_state.logged_in = True
    st.session_state.page = 1
    time.sleep(0.1)
    st.rerun()
# --- YouTube URLを埋め込み形式に正規化する関数 ---
def normalize_youtube_url(url: str) -> str:
    """
    YouTubeの共有リンク（youtu.be/形式）から動画IDを抽出し、
    埋め込み可能なURL形式に変換します。
    """
    
    # 共有リンク（youtu.be/）が含まれているか確認
    if "youtu.be/" in url:
        # スラッシュで分割し、末尾の要素を取得
        video_id_with_params = url.split("/")[-1]
        
        # クエリパラメータ（例: ?t=100）がある場合に、それを削除して純粋な動画IDを抽出
        # クエリパラメータがない場合は、video_id_with_params全体が動画IDになります
        video_id = video_id_with_params.split("?")[0].split("#")[0] 
        
        return f"https://www.youtube.com/embed/{video_id}"
        
    # それ以外の形式、または既に使用可能な埋め込みURLの場合はそのまま返す
    return url

# --- 「スピード測定開始」ボタンが押されたときに実行する関数 ---
def start_reading(page_number):
    st.session_state.start_time = time.time()
    st.session_state.page = page_number

# --- 認証ページ（page 0） ---
if st.session_state.page == 0:
    if st.session_state.logged_in:
        st.session_state.page = 1
        st.rerun()
        st.stop()

    st.title("ニックネームとIDを入力してください")
    col1, _ = st.columns(2)
    with col1:
        nickname = st.text_input("ニックネーム (半角英数字、_、-、半角スペース可)", key="nickname_input", value=st.session_state.get("nickname", ""))
        user_id_input = st.text_input("パスワード（お伝えしているパスワードを入力してください。半角英数字)", type="password", key="user_id_input", value="")
        if st.button("次へ"):
            if not nickname:
                st.warning("ニックネームを入力してください。")
            elif not user_id_input:
                st.warning("IDを入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z_\- ]+', nickname):
                st.error("ニックネームは半角英数字、_、-、半角スペースで入力してください。")
            elif not re.fullmatch(r'[0-9a-zA-Z]+', user_id_input):
                st.error("IDは半角英数字で入力してください。")
            else:
                admin_nickname = st.secrets.get("ADMIN_USERNAME")
                admin_hashed_password = st.secrets.get("ADMIN_PASSWORD")
                user_entered_password_bytes = user_id_input.strip().encode('utf-8')
                authenticated = False
                is_admin_user = False
                if nickname.strip() == admin_nickname:
                    if admin_hashed_password and bcrypt.checkpw(user_entered_password_bytes, admin_hashed_password.encode('utf-8')):
                        authenticated = True
                        is_admin_user = True
                if not authenticated:
                    users_from_secrets = st.secrets.get("users", [])
                    for user_info in users_from_secrets:
                        if nickname.strip() == user_info.get("nickname"):
                            stored_hashed_id = user_info.get("user_id")
                            if stored_hashed_id and bcrypt.checkpw(user_entered_password_bytes, stored_hashed_id.encode('utf-8')):
                                authenticated = True
                                is_admin_user = False
                                break
                if authenticated:
                    go_to_main_page(nickname, user_id_input, is_admin_user)
                else:
                    st.error("ニックネームまたはIDが正しくありません。")

# --- 認証後のメインメニューページ（page 1） ---
elif st.session_state.page == 1:
    col1, col2 = st.columns([0.4, 0.1])
    with col1:
        st.title(f"こんにちは、{st.session_state.nickname}さん！")
        st.markdown("---")
    with col2:
        if st.button("ログアウト"):
            st.session_state.clear()
            st.rerun()
        stopwatch_url = "https://english-booster-mlzrmgb7mftcynzupjqkyn.streamlit.app/"
        st.markdown(f"[⏱️ STOPWATCH]({stopwatch_url})", unsafe_allow_html=True)
        st.markdown("<small>（別ウィンドウで開きます）</small>", unsafe_allow_html=True)

    if st.session_state.is_admin:
        st.subheader("管理者設定")
        manual_index = st.number_input("表示する行番号 (0から始まる整数)", 0, value=st.session_state.get("fixed_row_index", 0), key="admin_fixed_row_index")
        if st.button("表示行番号を保存", key="save_fixed_row_index"):
            st.session_state.fixed_row_index = manual_index
            save_config(manual_index)
        st.markdown("---")
        st.subheader("ユーザー登録日設定 (管理者のみ)")
        target_nickname = st.text_input("登録日を設定するユーザーのニックネーム", key="target_nickname_input")
        today_jst_date = datetime.now(timezone('Asia/Tokyo')).date()
        selected_enrollment_date = st.date_input("登録日を選択", value=today_jst_date, key="enrollment_date_picker")
        if st.button("登録日を設定", key="set_enrollment_date_button"):
            if target_nickname:
                target_user_profile_ref = db.collection("user_profiles").document(target_nickname)
                enrollment_date_str = selected_enrollment_date.strftime('%Y-%m-%d')
                target_user_profile_ref.set(
                    {"enrollment_date": enrollment_date_str},
                    merge=True
                )
                st.success(f"ユーザー **{target_nickname}** の登録日を **{enrollment_date_str}** に設定しました。")
            else:
                st.warning("登録日を設定するユーザーのニックネームを入力してください。")

    col1, col2 = st.columns([0.6, 0.4])
    with col1:
        st.header("授業動画")
        st.markdown("新しい動画をチェックしましょう！")
        
        user_profile_ref = db.collection("user_profiles").document(st.session_state.nickname)
        user_profile_doc = user_profile_ref.get()
        user_profile_data = user_profile_doc.to_dict() if user_profile_doc.exists else {}
        enrollment_date_str = user_profile_data.get("enrollment_date")
        
        if enrollment_date_str is None:
            st.info("あなたの動画視聴開始日はまだ設定されていません。管理者に連絡してください。")
        else:
            today_jst = datetime.now(timezone('Asia/Tokyo')).date()
            enrollment_dt = datetime.strptime(enrollment_date_str, '%Y-%m-%d').date()
            days_since_enrollment = (today_jst - enrollment_dt).days + 1
            
            try:
                video_data = pd.read_csv("videos.csv")
                video_data["date"] = pd.to_datetime(video_data["date"])
                video_data = video_data.sort_values(by="release_day", ascending=False).reset_index(drop=True)
                
                watched_videos = user_profile_data.get("watched_videos", [])
                
                if not video_data.empty:
                    for _, row in video_data.iterrows():
                        video_id = row.get('video_id')
                        release_day = row.get('release_day')
                        
                        if video_id is None or release_day is None:
                            continue
                        
                        if release_day <= days_since_enrollment:
                            expander_header = f"{row['title']} （公開日: {row['date'].strftime('%Y年%m月%d日')}）"
                            if video_id in watched_videos:
                                expander_header = f"✅ {expander_header} （視聴済み）"
                            
                            with st.expander(expander_header):
                                st.write(row["description"])
                                st.markdown(f"📺 **[YouTubeでこの動画を直接開く]({row['url']})**")
                                st.video(normalize_youtube_url(row["url"]))
                else:
                    st.info("現在、表示できる動画はありません。")
            except FileNotFoundError:
                st.error("動画情報ファイル (videos.csv) が見つかりません。")
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

        st.markdown("---")
        st.subheader(f"{st.session_state.nickname}さんの測定結果")

        try:
            # GitHub 上の CSV を読み込む
            GITHUB_USER_CSV = "https://raw.githubusercontent.com/boost-ogawa/english-booster/main/user.csv"
            df_wpm = pd.read_csv(GITHUB_USER_CSV)
            df_user = df_wpm[df_wpm["nickname"] == st.session_state.nickname]

            if not df_user.empty:
                # 日付順に降順ソート（最新が上）
                df_user["date"] = pd.to_datetime(df_user["date"])
                df_user = df_user.sort_values("date", ascending=False)

                # 表示列を WPM グラフ用に合わせる
                df_display = df_user[["date", "wpm"]]
                df_display = df_display.rename(columns={
                    "date": "測定年月日",
                    "wpm": "WPM"
                })
                # 日付を文字列に変換
                df_display["測定年月日"] = df_display["測定年月日"].dt.strftime('%Y/%m/%d')
                st.dataframe(df_display.reset_index(drop=True), hide_index=True)
            else:
                st.info("過去の結果データはまだありません。")
        except FileNotFoundError:
            st.error("user.csv が見つかりません。")
        except Exception as e:
            st.error(f"結果表表示中にエラーが発生しました: {e}")

        st.markdown("---")

    st.markdown("© 2025 英文速解English Booster", unsafe_allow_html=True)
    
# --- 英文読解ページ（page 2） ---
elif st.session_state.page == 2:
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

# --- 問題解答ページ（page 3） ---
elif st.session_state.page == 3:
    data = load_material(GITHUB_DATA_URL, st.session_state.fixed_row_index)
    if data is None:
        st.stop()
    st.info("問題を解いてSubmitボタンを押しましょう")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f'<div class="custom-paragraph">{data["main"]}</div>', unsafe_allow_html=True)
    with col2:
        st.subheader("Questions")
        q1_choice = st.radio(data["Q1"], [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']], key="q1",
                             index=([data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']].index(st.session_state.q1)
                                    if st.session_state.get('q1') in [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']] else None))
        q2_choice = st.radio(data["Q2"], [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']], key="q2",
                             index=([data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']].index(st.session_state.q2)
                                    if st.session_state.get('q2') in [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']] else None))
    if st.button("Submit"):
        if st.session_state.q1 is not None and st.session_state.q2 is not None:
            st.session_state.page = 4
            st.rerun()
        else:
            st.error("両方の質問に答えてください。")
# --- 結果表示ページ（page 4） ---
elif st.session_state.page == 4:
    st.success("結果を記録しました。")
    col1, col2 = st.columns([1, 2])

    # --- 右カラム: WPM推移グラフ ---
    with col2:
        st.subheader(f"{st.session_state.nickname}さんのWPM推移（過去の結果）")

        try:
            GITHUB_USER_CSV = "https://raw.githubusercontent.com/boost-ogawa/english-booster/main/user.csv"
            df_wpm = pd.read_csv(GITHUB_USER_CSV)
            df_user = df_wpm[df_wpm["nickname"] == st.session_state.nickname]

            if not df_user.empty:
                # 日付順に並べ替え、文字列として扱う
                df_user = df_user.sort_values("date")
                df_user["date"] = df_user["date"].astype(str)

                # グラフ描画
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(df_user["date"], df_user["wpm"], marker='o', linestyle='-')

                # 縦軸固定
                ax.set_ylim(0, 400)
                ax.set_yticks(range(0, 401, 50))
                ax.set_ylabel("WPM")
                ax.set_xlabel("Measurement Date")
                plt.xticks(rotation=45)
                plt.grid(axis='y', linestyle='--', alpha=0.7)

                st.pyplot(fig)
            else:
                st.info("WPMデータがまだありません。")
        except FileNotFoundError:
            st.error("user.csv が見つかりません。")
        except Exception as e:
            st.error(f"WPMグラフ描画中にエラーが発生しました: {e}")

    # --- 左カラム: 今回の結果表示 ---
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

            # --- 判定と記録 ---
            correct1 = st.session_state.q1 == data['A1']
            correct2 = st.session_state.q2 == data['A2']

            # 判定を固定しておく（訳ページ遷移時に一瞬Falseになるのを防ぐ）
            st.session_state["final_correct1"] = correct1
            st.session_state["final_correct2"] = correct2

            st.write(f"Q1: {'✅ 正解' if correct1 else '❌ 不正解'}")
            st.write(f"あなたの解答: {st.session_state.q1}")
            st.write(f"正しい答え: {data['A1']}")

            st.write(f"Q2: {'✅ 正解' if correct2 else '❌ 不正解'}")
            st.write(f"あなたの解答: {st.session_state.q2}")
            st.write(f"正しい答え: {data['A2']}")

            correct_answers_to_store = int(correct1) + int(correct2)
            if not st.session_state.submitted:
                material_id_to_save = data.get('material_id_for_save', str(st.session_state.fixed_row_index))
                save_results(wpm, correct_answers_to_store, material_id_to_save, st.session_state.nickname)
                st.session_state.submitted = True

        if st.button("意味を確認"):
            # 遷移時に判定結果を保持したままpage変更
            st.session_state.page = 5
            st.rerun()


# --- 意味確認ページ（page 5） ---
elif st.session_state.page == 5:
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

    # --- （必要に応じて結果を再確認表示）---
    if "final_correct1" in st.session_state and "final_correct2" in st.session_state:
        st.subheader("あなたの解答結果")
        st.write(f"Q1: {'✅ 正解' if st.session_state.final_correct1 else '❌ 不正解'}")
        st.write(f"Q2: {'✅ 正解' if st.session_state.final_correct2 else '❌ 不正解'}")

    if st.button("終了"):
        # 終了時に状態をクリア
        for key in ["page", "start_time", "stop_time", "submitted",
                    "q1", "q2", "final_correct1", "final_correct2"]:
            st.session_state[key] = None
        st.session_state.page = 1
        st.rerun()
