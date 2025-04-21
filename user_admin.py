import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# Firebase Admin SDKの初期化（1回だけ）
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")  # ←ファイル名を調整！
    firebase_admin.initialize_app(cred)

# Firestoreクライアント取得
db = firestore.client()

st.title("ユーザー管理画面")

# 入力欄
email = st.text_input("ユーザーのメールアドレスを入力")
role = st.selectbox("ユーザーのロールを選択", ["student", "admin"], index=0)

# Firestoreのコレクション名
USER_COLLECTION = "users"

# 追加ボタン
if st.button("ユーザーを追加"):
    if email:
        doc_ref = db.collection(USER_COLLECTION).document(email)
        doc_ref.set({"role": role})
        st.success(f"{email} を {role} として追加しました。")
    else:
        st.warning("メールアドレスを入力してください。")

# 削除ボタン
if st.button("ユーザーを削除"):
    if email:
        db.collection(USER_COLLECTION).document(email).delete()
        st.success(f"{email} を削除しました。")
    else:
        st.warning("メールアドレスを入力してください。")

# 登録済みユーザー一覧表示
st.subheader("登録済みユーザー一覧")
users = db.collection(USER_COLLECTION).stream()
for user in users:
    data = user.to_dict()
    st.write(f"- {user.id}（role: {data.get('role', 'N/A')}）")
