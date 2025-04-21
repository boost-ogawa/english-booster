import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
import pandas as pd
import time
from datetime import datetime

# --- ページ設定 ---
st.set_page_config(page_title="Speed Reading App", layout="wide")

# --- Firebase 初期化 ---
def initialize_firebase():
     if not firebase_admin._apps:
        try:
             cred = credentials.Certificate({
                 "type": st.secrets["firebase"]["type"],
                 "project_id": st.secrets["firebase"]["project_id"],
                 "private_key_id": st.secrets["firebase"]["private_key_id"],
                 "private_key": st.secrets["firebase"]["private_key"].replace('\\n', '\n'),
                 "client_email": st.secrets["firebase"]["client_email"],
                 "client_id": st.secrets["firebase"]["client_id"],
                 "auth_uri": st.secrets["firebase"]["auth_uri"],
                 "token_uri": st.secrets["firebase"]["token_uri"],
                 "auth_provider_x509_cert_url": st.secrets["firebase"]["auth_provider_x509_cert_url"],
                 "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"],
                 "universe_domain": st.secrets["firebase"]["universe_domain"]
             })
             firebase_admin.initialize_app(cred)
        except Exception as e:
             st.error(f"Firebase 初期化エラー: {e}")
             st.stop()

initialize_firebase()
db = firestore.client()

# --- 認証ユーザー取得 ---
def get_authenticated_user():
    token = st.query_params.get("token")  # ✅ 新しい書き方（リストじゃなく文字列で返る）
    if not token:
        return None
    try:
        return auth.verify_id_token(token)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

user = get_authenticated_user()
if user:
    user_data = get_user_data(user["uid"])

    if user_data is None:
        st.error("ユーザーデータが見つかりません。管理者に連絡してください。")
        st.stop()

    role = user_data.get("role", "student")  # デフォルトは student

    if role == "admin":
        st.success("ようこそ、管理者モードです 👑")
        # 管理者向け画面ここに追加
        st.write("ここは管理者専用ページです。")
    else:
        st.success("ようこそ、学習者モードです 📚")
        # 学習者向け画面ここに追加
        st.write("ここは学習者ページです。")

# --- Firestore関連 ---
def get_user_data(uid):
    try:
        doc = db.collection("users").document(uid).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        st.error(f"ユーザーデータ取得失敗: {e}")
        return None

def save_user_data(uid, data):
    try:
        db.collection("users").document(uid).set(data, merge=True)
        st.success("ユーザーデータを保存しました。")
    except Exception as e:
        st.error(f"保存失敗: {e}")

def is_admin(user):
    try:
        return db.collection("admins").document(user["uid"]).get().exists
    except Exception as e:
        st.warning(f"管理者チェック失敗: {e}")
        return False

# --- セッション初期化 ---
for key, default in {
    "page": 1,
    "start_time": None,
    "stop_time": None,
    "q1": None,
    "q2": None,
    "row_to_load": 1,
    "submitted": False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- CSVデータ読み込み関数 ---
def load_material(data_path, row_index):
    try:
        df = pd.read_csv(data_path)
        return df.iloc[row_index]
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return None

# --- ユーザー処理 ---
if user:
    uid = user["uid"]
    user_data = get_user_data(uid)

    st.sidebar.success(f"認証成功: {uid}")
    if user_data:
        st.sidebar.write(f"ようこそ、{user_data.get('name', 'ユーザー')} さん！")
    else:
        name = st.sidebar.text_input("はじめての方は名前を登録してください")
        if st.sidebar.button("登録"):
            save_user_data(uid, {"name": name})

    # --- 管理者モード ---
    admin_mode = is_admin(user)
    if admin_mode:
        st.sidebar.subheader("管理者モード")
        row_index = st.sidebar.number_input("表示する課題番号", 0, step=1, value=st.session_state.row_to_load)
        st.session_state.row_to_load = row_index

        st.subheader("📊 学習履歴")
        try:
            results = db.collection("results").order_by("timestamp").get()
            df_results = pd.DataFrame([doc.to_dict() for doc in results])
            if not df_results.empty:
                st.dataframe(df_results)
            else:
                st.info("履歴がまだありません。")
        except:
            st.error("履歴の取得に失敗しました。")

    # --- データ読み込み ---
    DATA_PATH = "data.csv"
    data = load_material(DATA_PATH, int(st.session_state.row_to_load))
    if data is None:
        st.stop()

    col1, col2 = st.columns([2, 1])

    # --- ステップ1: 読む前 ---
    if st.session_state.page == 1:
        with col1:
            st.info("Startを押して英文を読みましょう")
            if st.button("Start"):
                st.session_state.start_time = time.time()
                st.session_state.page = 2
                st.rerun()

    # --- ステップ2: 読書中 ---
    elif st.session_state.page == 2:
        with col1:
            st.info("読み終わったらStopを押してください")
            st.markdown(f"<div style='font-size: 1.3rem; line-height: 1.8;'>{data['main']}</div>", unsafe_allow_html=True)
            if st.button("Stop"):
                st.session_state.stop_time = time.time()
                st.session_state.page = 3
                st.rerun()

    # --- ステップ3: 質問 ---
    elif st.session_state.page == 3:
        with col1:
            st.info("問題に答えてください")
            st.markdown(f"<div style='font-size: 1.3rem; line-height: 1.8;'>{data['main']}</div>", unsafe_allow_html=True)

        with col2:
            st.radio(data["Q1"], [data["Q1A"], data["Q1B"], data["Q1C"], data["Q1D"]], key="q1")
            st.radio(data["Q2"], [data["Q2A"], data["Q2B"], data["Q2C"], data["Q2D"]], key="q2")
            if st.button("Submit"):
                if st.session_state.q1 and st.session_state.q2:
                    st.session_state.page = 4
                    st.rerun()
                else:
                    st.error("2問とも答えてください。")

    # --- ステップ4: 結果表示 ---
    elif st.session_state.page == 4:
        with col2:
            total_time = st.session_state.stop_time - st.session_state.start_time
            word_count = len(data["main"].split())
            wpm = (word_count / total_time) * 60
            correct1 = st.session_state.q1 == data["A1"]
            correct2 = st.session_state.q2 == data["A2"]
            correct_count = int(correct1) + int(correct2)

            st.success("結果")
            st.write(f"Words: {word_count}")
            st.write(f"Time: {total_time:.2f}s")
            st.write(f"WPM: **{wpm:.2f}**")
            st.write(f"Q1: {'✅' if correct1 else '❌'}")
            st.write(f"Q2: {'✅' if correct2 else '❌'}")

            # Firestoreに保存
            if not st.session_state.submitted:
                db.collection("results").add({
                    "uid": uid,
                    "timestamp": datetime.now().isoformat(),
                    "material_id": str(data.get("id", f"row_{st.session_state.row_to_load}")),
                    "wpm": round(wpm, 2),
                    "correct_answers": correct_count
                })
                st.session_state.submitted = True

            if st.button("Restart"):
                for key in ["page", "start_time", "stop_time", "q1", "q2", "submitted"]:
                    st.session_state[key] = 1 if key == "page" else None
                st.rerun()

else:
    st.warning("ログインが必要です。URLに '?token=...' を付けてアクセスしてください。")
