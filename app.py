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

# --- 定数設定 ---
GITHUB_DATA_URL = "https://raw.githubusercontent.com/boost-ogawa/english-booster/refs/heads/main/data.csv"
# GITHUB_CSV_URL は未使用のようですので、ここでは記載しません
HEADER_IMAGE_URL = "https://github.com/boost-ogawa/english-booster/blob/main/English%20Booster_header.jpg?raw=true"
# DATA_PATH も未使用のようですので、ここでは記載しません

# --- Firebaseの初期化 ---
firebase_creds_dict = dict(st.secrets["firebase"])
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
    json.dump(firebase_creds_dict, f)
    f.flush()
    cred = credentials.Certificate(f.name)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    os.unlink(f.name) # tempfileを削除

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
        "nickname": nickname,
        "timestamp": timestamp,
        "material_id": material_id,
        "wpm": round(wpm, 1),
        "correct_answers": correct_answers
    }

    try:
        db.collection("results").add(result_data)
        print("結果が保存されました")

        # 視聴履歴の更新（video_idではなく、material_idをそのまま記録）
        # material_idはdata.csvの行番号なので、動画視聴とは直接紐付かない点に注意
        # ここはあくまで「スピード測定を完了した教材ID」を記録する場所として残します
        user_profile_ref = db.collection("user_profiles").document(nickname)
        # FirestoreのArrayUnionを使って、重複なく追加
        user_profile_ref.update({
            "watched_materials": firestore.ArrayUnion([material_id])
        })
        print(f"ユーザー {nickname} の教材完了履歴が更新されました: {material_id}")

    except Exception as e:
        st.error(f"結果の保存に失敗しました: {e}")

# --- WPM推移グラフ表示関数 ---
# user_idではなくnicknameでフィルタリングするように変更
def display_wpm_history(nickname):
    if nickname:
        try:
            results_ref = db.collection("results").where("nickname", "==", nickname).order_by("timestamp")
            docs = results_ref.stream()

            data_list = []
            for doc in docs:
                data = doc.to_dict()
                dt_object = datetime.fromisoformat(data['timestamp'])
                jst = timezone('Asia/Tokyo')
                dt_object_jst = dt_object.astimezone(jst)
                data['測定年月'] = dt_object_jst.strftime('%Y-%m-%d %H:%M')
                data_list.append(data)

            if data_list:
                df_results = pd.DataFrame(data_list)
                df_results['wpm'] = pd.to_numeric(df_results['wpm'], errors='coerce')
                df_results.dropna(subset=['wpm'], inplace=True)

                fig = px.line(df_results, x='測定年月', y='wpm', title='WPM推移')
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("まだ学習履歴がありません。")
        except Exception as e:
            st.error(f"過去データの読み込みまたは処理に失敗しました: {e}")
    else:
        st.info("ニックネームがありません。")

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
    .google-classroom-button {
        display: inline-block;
        padding: 10px 20px;
        margin-top: 10px;
        background-color: #4285F4;
        color: white !important;
        text-decoration: none;
        border-radius: 5px;
    }

    div[data-testid="stRadio"] label p {
        font-size: 1.2rem !important; /* 質問文も選択肢も同じフォントサイズに設定 */
        line-height: 1.4 !important; /* 行間も確実に適用 */
        color: #FFFFFF !important;
        margin-bottom: 0.3rem !important; /* 各ラベル（質問文、選択肢）の下に適切な余白を確保 */
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
            material_data = df.iloc[row_index].to_dict()
            # material_id_for_save は data.csvの行番号をそのまま使用
            material_data['material_id_for_save'] = str(row_index)
            return material_data
        else:
            st.error(f"指定された行番号 ({row_index + 1}) はファイルに存在しません。")
            return None
    except Exception as e:
        st.error(f"GitHubからのデータ読み込みに失敗しました: {e}")
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
    st.session_state.user_id = ""
if "show_full_graph" not in st.session_state:
    st.session_state.show_full_graph = False
if "set_page_key" not in st.session_state:
    st.session_state["set_page_key"] = "unique_key_speed"
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "enrollment_date" not in st.session_state: # enrollment_date をセッションに追加
    st.session_state.enrollment_date = None

# --- ページ遷移関数 ---
def set_page(page_number):
    st.session_state.page = page_number

# --- 「スピード測定開始」ボタンが押されたときに実行する関数 ---
def start_reading(page_number):
    st.session_state.start_time = time.time()
    st.session_state.page = page_number

# --- 認証ページ（page 0） ---
if st.session_state.page == 0:
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
                    if admin_hashed_password:
                        try:
                            if bcrypt.checkpw(user_entered_password_bytes, admin_hashed_password.encode('utf-8')):
                                authenticated = True
                                is_admin_user = True
                        except ValueError:
                            pass

                if not authenticated:
                    users_from_secrets = st.secrets.get("users", [])
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
                    st.session_state.user_id = user_id_input.strip()
                    st.session_state.is_admin = is_admin_user
                    st.session_state.page = 1
                    st.rerun()
                else:
                    st.error("ニックネームまたはIDが正しくありません。")

# --- 認証後のメインメニューページ（page 1） ---
elif st.session_state.page == 1:
    col1, col2 = st.columns([0.4, 0.1])

    with col1:
        st.title(f"こんにちは、{st.session_state.nickname}さん！")
        st.markdown("---")
    with col2:
        stopwatch_url = "https://english-booster-mlzrmgb7mftcynzupjqkyn.streamlit.app/"
        st.markdown(f"[⏱️ STOPWATCH]({stopwatch_url})", unsafe_allow_html=True)

    # ユーザーのenrollment_dateをFirestoreから取得し、セッションに保存
    current_nickname = st.session_state.nickname
    user_profile_ref = db.collection("user_profiles").document(current_nickname)
    user_profile_doc = user_profile_ref.get()

    if user_profile_doc.exists:
        user_profile_data = user_profile_doc.to_dict()
        st.session_state.enrollment_date = user_profile_data.get("enrollment_date")
    else:
        # ドキュメントがない場合は、enrollment_dateはNoneのままにする
        # 管理者が設定するのを待つ
        st.session_state.enrollment_date = None


    # 管理者設定
    if st.session_state.is_admin:
        st.subheader("管理者設定")
        
        # 固定行インデックス設定
        manual_index = st.number_input("表示する行番号 (0から始まる整数)", 0, value=st.session_state.get("fixed_row_index", 0), key="admin_fixed_row_index")
        if st.button("表示行番号を保存", key="save_fixed_row_index"):
            st.session_state.fixed_row_index = manual_index
            save_config(manual_index)

        st.markdown("---")
        st.subheader("ユーザー登録日設定 (管理者のみ)")

        target_nickname = st.text_input("登録日を設定するユーザーのニックネーム", key="target_nickname_input")
        today_jst_date = datetime.now(timezone('Asia/Tokyo')).date() # default value for date_input
        selected_enrollment_date = st.date_input("登録日を選択", value=today_jst_date, key="enrollment_date_picker")

        if st.button("登録日を設定", key="set_enrollment_date_button"):
            if target_nickname:
                target_user_profile_ref = db.collection("user_profiles").document(target_nickname)
                enrollment_date_str = selected_enrollment_date.strftime('%Y-%m-%d')
                
                # Firestoreに保存 (watched_videosが未設定なら空配列で初期化も兼ねる)
                target_user_profile_ref.set(
                    {"enrollment_date": enrollment_date_str, "watched_videos": []},
                    merge=True # 既存のフィールド（例: 既に存在するwatched_videos）を上書きしない
                )
                st.success(f"ユーザー **{target_nickname}** の登録日を **{enrollment_date_str}** に設定しました。")
                # もし設定したユーザーが自分自身の場合、セッション変数も更新
                if target_nickname == st.session_state.nickname:
                    st.session_state.enrollment_date = enrollment_date_str
            else:
                st.warning("登録日を設定するユーザーのニックネームを入力してください。")

    # --- ここから2カラムレイアウトの開始 ---
    col1, col2 = st.columns([0.6, 0.4])

    with col1:
        st.header("授業動画")
        st.markdown("新しい動画をチェックしましょう！")

        # enrollment_dateが設定されていない場合は動画を表示しない
        if st.session_state.enrollment_date is None:
            st.info("あなたの動画視聴開始日はまだ設定されていません。管理者に連絡してください。")
        else:
            # 現在の日付を取得 (日本時間)
            today_jst = datetime.now(timezone('Asia/Tokyo')).date()
            # ユーザーの登録日をdatetimeオブジェクトに変換
            enrollment_dt = datetime.strptime(st.session_state.enrollment_date, '%Y-%m-%d').date()

            # 登録日からの経過日数を計算 (+1は登録日を1日目とするため)
            days_since_enrollment = (today_jst - enrollment_dt).days + 1

            try:
                # videos.csvを読み込む
                video_data = pd.read_csv("videos.csv")
                video_data["date"] = pd.to_datetime(video_data["date"])
                # ★変更点1: release_dayで降順にソート（新しい解放日が上に来るように）
                video_data = video_data.sort_values(by="release_day", ascending=False).reset_index(drop=True)

                # ユーザーの視聴済み動画リストをFirestoreから取得
                # user_profile_doc はこのコードスニペットには含まれていませんが、
                # 実際のアプリでは定義されていると仮定します。
                # 例: user_profile_doc = db.collection("users").document(st.session_state.user_id).get()
                # user_profile_data = user_profile_doc.to_dict()
                # 以下の行は、user_profile_docとuser_profile_dataが適切に定義されていることを前提としています。
                user_profile_data = {} # 仮の定義
                watched_videos = user_profile_data.get("watched_videos", [])


                if not video_data.empty:
                    for index, row in video_data.iterrows():
                        video_id = row.get('video_id')
                        release_day = row.get('release_day')

                        if video_id is None or release_day is None:
                            st.warning(f"動画データに 'video_id' または 'release_day' がありません: {row.get('title', '不明な動画')}")
                            continue

                        # ★変更点2: 動画が解放されているかチェックし、解放されていない場合は何も表示しない
                        if release_day <= days_since_enrollment:
                            expander_header = f"{row['title']} （公開日: {row['date'].strftime('%Y年%m月%d日')}）"
                            if video_id in watched_videos:
                                expander_header = f"✅ {expander_header} （視聴済み）"
                            
                            with st.expander(expander_header):
                                st.write(row["description"])
                                # MP4ファイルの場合はvideoタグを使用
                                if ".mp4" in row["url"].lower():
                                    st.markdown(f'<video width="100%" height="315" controls><source src="{row["url"]}" type="video/mp4"></video>', unsafe_allow_html=True)
                                # YouTube動画の場合はst.videoを使用
                                elif "youtube.com" in row["url"] or "youtu.be" in row["url"]:
                                    st.video(row["url"])
                                # その他の埋め込みタイプ
                                elif "type" in row and row["type"] == "embed":
                                    # YouTube以外の埋め込み動画（もしあれば）
                                    st.markdown(f'<iframe width="100%" height="315" src="{row["url"]}" frameborder="0" allowfullscreen></iframe>', unsafe_allow_html=True)
                                # リンクタイプ
                                elif "type" in row and row["type"] == "link":
                                    st.markdown(f"[動画を見る]({row['url']})", unsafe_allow_html=True)
                                # デフォルトの処理（YouTube動画を想定）
                                else:
                                    st.video(row["url"]) # ここもst.videoを使用

                else:
                    st.info("現在、表示できる動画はありません。")

            except FileNotFoundError:
                st.error("動画情報ファイル (videos.csv) が見つかりません。")
                st.info("`videos.csv`を作成してアプリのルートディレクトリにアップロードしてください。")
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

    st.subheader(f"{st.session_state.nickname}さんのWPM推移")
    current_nickname = st.session_state.get('nickname')
    # display_wpm_history(current_nickname) # ← この行はコメントアウトを維持
    st.info("月次WPM推移グラフは後日表示されます。") # ← この行はコメントアウトを維持

    st.markdown("---")
    st.markdown("© 2025 英文速解English Booster", unsafe_allow_html=True)

# --- 英文表示ページ（旧 page 1、現在は page 2 に相当） ---
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

## ... 既存のコード ...
# 問題ページ（旧 page 2, 現在の app.py の page 3 に相当）
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
        
        # Q1の質問文をst.radioのラベルとして直接渡す
        # label_visibility="hidden" を削除し、質問文をラベルにする
        q1_choice = st.radio(data["Q1"], [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']], key="q1",
                             index=([data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']].index(st.session_state.q1)
                                    if st.session_state.get('q1') in [data['Q1A'], data['Q1B'], data['Q1C'], data['Q1D']] else None))
        
        # Q2の質問文をst.radioのラベルとして直接渡す
        # label_visibility="hidden" を削除し、質問文をラベルにする
        q2_choice = st.radio(data["Q2"], [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']], key="q2",
                             index=([data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']].index(st.session_state.q2)
                                    if st.session_state.get('q2') in [data['Q2A'], data['Q2B'], data['Q2C'], data['Q2D']] else None))


    if st.button("Submit"):
        if st.session_state.q1 is not None and st.session_state.q2 is not None:
            st.session_state.page = 4
            st.rerun()
        else:
            st.error("両方の質問に答えてください。")


# 結果表示ページ（旧 page 3）
elif st.session_state.page == 4:
    st.success("結果を記録しました。")
    col1, col2 = st.columns([1, 2])
    with col2:
        current_nickname = st.session_state.get('nickname')
        # display_wpm_history(current_nickname) # ← この行はコメントアウトを維持
        st.info("月次WPM推移グラフは後日表示されます。") # ← この行はコメントアウトを維持

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
            st.write(f"Q1: {'✅ 正解' if correct1 else '❌ 不正解'}")
            st.write(f"あなたの解答 {st.session_state.q1}")
            st.write(f"正しい答え: {data['A1']}")

            correct2 = st.session_state.q2 == data['A2']
            st.write(f"Q2: {'✅ 正解' if correct2 else '❌ 不正解'}")
            st.write(f"あなたの解答: {st.session_state.q2}")
            st.write(f"正しい答え: {data['A2']}")

            correct_answers_to_store = int(correct1) + int(correct2)

            if not st.session_state.submitted:
                # material_id_for_save を取得してsave_resultsに渡す
                material_id_to_save = data.get('material_id_for_save', str(st.session_state.fixed_row_index))
                save_results(wpm, correct_answers_to_store, material_id_to_save,
                                st.session_state.nickname)
                st.session_state.submitted = True

        if st.button("意味を確認"):
            st.session_state.page = 5
            st.rerun()

# --- 意味確認ページ（旧 page 4） ---
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

    if st.button("終了"):
        st.session_state.page = 1
        st.session_state.start_time = None
        st.session_state.stop_time = None
        st.session_state.submitted = False
        st.session_state.q1 = None
        st.session_state.q2 = None
        st.rerun()