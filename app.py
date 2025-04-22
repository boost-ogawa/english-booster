# --- ページ設定 ---
import streamlit as st
st.set_page_config(page_title="Speed Reading App", layout="wide")

# --- ライブラリ ---
import time
import pandas as pd
from datetime import datetime
from firebase_admin import auth, credentials, firestore, initialize_app
import firebase_admin

# --- Firebase 初期化 ---
import json  # ← 追加！
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            if "firebase" in st.secrets:
                # Streamlit Cloud 用：AttrDict → dict に変換
                firebase_dict = dict(st.secrets["firebase"])
                cred = credentials.Certificate(firebase_dict)
            else:
                # ローカル用
                cred = credentials.Certificate("serviceAccountKey.json")

            initialize_app(cred)

        except Exception as e:
            st.error(f"Firebase初期化エラー: {e}")
            st.stop()

# 初期化と Firestore クライアントの取得
initialize_firebase()
db = firestore.client()

# --- トークンからユーザー情報を取得 ---
def get_authenticated_user():
    token = st.query_params.get("token", [None])[0]  # 修正箇所
    if not token:
        return None
    try:
        return auth.verify_id_token(token)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

# --- Firestore 関連関数 ---
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
    uid = user["uid"]
    data = get_user_data(uid)
    return data and data.get("role") == "admin"

# --- ユーザー管理機能 ---
def manage_users():
    st.title("ユーザー管理画面")

    email = st.text_input("メールアドレス")
    role = st.selectbox("ロール", ["student", "admin"])

    if st.button("ユーザーを追加"):
        if email:
            db.collection("users").document(email).set({"role": role})
            st.success(f"{email} を {role} として追加しました。")
        else:
            st.warning("メールアドレスを入力してください。")

    if st.button("ユーザーを削除"):
        if email:
            db.collection("users").document(email).delete()
            st.success(f"{email} を削除しました。")

    st.subheader("登録済みユーザー一覧")
    for user in db.collection("users").stream():
        data = user.to_dict()
        st.write(f"- {user.id}（role: {data.get('role', 'N/A')}）")

# --- CSV読込関数 ---
def load_material(path, index):
    try:
        df = pd.read_csv(path)
        return df.iloc[index]
    except Exception as e:
        st.error(f"CSV読み込み失敗: {e}")
        return None

# --- Speed Reading App 本体 ---
def speed_reading_app(user):
    uid = user["uid"]
    user_data = get_user_data(uid)

    if user_data is None:
        st.error("ユーザーデータが見つかりません。管理者に連絡してください。")
        st.stop()

    st.sidebar.success(f"認証成功: {uid}")
    st.sidebar.write(f"ようこそ、{user_data.get('name', 'ユーザー')} さん")

    # 学習者登録
    if "name" not in user_data:
        name = st.sidebar.text_input("名前を登録してください")
        if st.sidebar.button("登録"):
            save_user_data(uid, {"name": name})

    admin_mode = user_data.get("role") == "admin"

    if admin_mode:
        st.success("👑 管理者モード")
        st.sidebar.subheader("管理者モード")
        manage_users()

        row_index = st.sidebar.number_input("課題番号", 0, step=1, value=st.session_state.get("row_to_load", 1))
        st.session_state.row_to_load = row_index

        st.subheader("📊 学習履歴")
        try:
            results = db.collection("results").order_by("timestamp").get()
            df = pd.DataFrame([r.to_dict() for r in results])
            if not df.empty:
                st.dataframe(df)
            else:
                st.info("履歴がまだありません。")
        except:
            st.error("履歴の取得失敗")

    # --- 課題読込 ---
    DATA_PATH = "data.csv"
    data = load_material(DATA_PATH, int(st.session_state.get("row_to_load", 0)))
    if data is None:
        st.stop()

    col1, col2 = st.columns([2, 1])

    # --- セッション初期化 ---
    for key, val in {
        "page": 1, "start_time": None, "stop_time": None,
        "q1": None, "q2": None, "submitted": False
    }.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # --- 読解ステップ ---
    if st.session_state.page == 1:
        with col1:
            st.info("Startを押して英文を読みましょう")
            if st.button("Start"):
                st.session_state.start_time = time.time()
                st.session_state.page = 2
                st.rerun()

    elif st.session_state.page == 2:
        with col1:
            st.info("読み終えたらStopを押してください")
            st.markdown(f"<div style='font-size:1.3rem; line-height:1.8;'>{data['main']}</div>", unsafe_allow_html=True)
            if st.button("Stop"):
                st.session_state.stop_time = time.time()
                st.session_state.page = 3
                st.rerun()

    elif st.session_state.page == 3:
        with col1:
            st.info("問題に答えてください")
            st.markdown(f"<div style='font-size:1.3rem; line-height:1.8;'>{data['main']}</div>", unsafe_allow_html=True)

        with col2:
            st.radio(data["Q1"], [data["Q1A"], data["Q1B"], data["Q1C"], data["Q1D"]], key="q1")
            st.radio(data["Q2"], [data["Q2A"], data["Q2B"], data["Q2C"], data["Q2D"]], key="q2")
            if st.button("Submit"):
                if st.session_state.q1 and st.session_state.q2:
                    st.session_state.submitted = True
                    st.session_state.page = 4
                    st.rerun()

    elif st.session_state.page == 4:
        with col1:
            st.success("結果")
            correct1 = st.session_state.q1 == data["Answer1"]
            correct2 = st.session_state.q2 == data["Answer2"]
            duration = round(st.session_state.stop_time - st.session_state.start_time, 2)
            wpm = round(len(data["main"].split()) / duration * 60, 2)

            st.write("問題1:", "✅ 正解" if correct1 else "❌ 不正解")
            st.write("問題2:", "✅ 正解" if correct2 else "❌ 不正解")
            st.write(f"読み時間: {duration} 秒")
            st.write(f"WPM: {wpm}")

            if st.session_state.submitted:
                db.collection("results").add({
                    "uid": uid,
                    "timestamp": datetime.now(),
                    "wpm": wpm,
                    "q1": correct1,
                    "q2": correct2
                })
                st.success("記録を保存しました")
                st.session_state.page = 1
                st.rerun()

# --- 実行 ---
user = get_authenticated_user()
if user:
    speed_reading_app(user)
else:
    st.warning("ログインが必要です。URLに '?token=...' を付けてアクセスしてください。")
