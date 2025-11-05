import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import tempfile
import json
import bcrypt
import re
import os
import time
import pandas as pd
import random
import string

# ==========================================
# 🔹 Firebase 初期化
# ==========================================
def init_firestore():
    firebase_creds_dict = dict(st.secrets["firebase"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(firebase_creds_dict, f)
        f.flush()
        cred = credentials.Certificate(f.name)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        os.unlink(f.name)
    return firestore.client()

db = init_firestore()

# ==========================================
# 🔹 セッション初期化
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "page" not in st.session_state:
    st.session_state.page = 0
if "nickname" not in st.session_state:
    st.session_state.nickname = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# ==========================================
# 🔹 ログイン関連関数
# ==========================================
def go_to_main_page(nickname, user_id, is_admin):
    st.session_state.nickname = nickname.strip()
    st.session_state.user_id = user_id.strip()
    st.session_state.is_admin = is_admin
    st.session_state.logged_in = True
    st.session_state.page = 1
    time.sleep(0.1)
    st.rerun()

# ==========================================
# 🔹 ログインページ
# ==========================================
if st.session_state.page == 0:
    if st.session_state.logged_in:
        st.session_state.page = 1
        st.rerun()
        st.stop()

    st.title("ログインページ")
    nickname = st.text_input("ニックネーム", key="nickname_input")
    user_id_input = st.text_input("パスワード", type="password", key="user_id_input")

    if st.button("ログイン"):
        if not nickname:
            st.warning("ニックネームを入力してください。")
        elif not user_id_input:
            st.warning("パスワードを入力してください。")
        elif not re.fullmatch(r'[0-9a-zA-Z_\- ]+', nickname):
            st.error("ニックネームは半角英数字、_、-、スペースで入力してください。")
        elif not re.fullmatch(r'[0-9a-zA-Z]+', user_id_input):
            st.error("パスワードは半角英数字で入力してください。")
        else:
            admin_nickname = st.secrets.get("ADMIN_USERNAME")
            admin_hashed_password = st.secrets.get("ADMIN_PASSWORD")
            user_entered_password_bytes = user_id_input.strip().encode('utf-8')
            authenticated = False
            is_admin_user = False

            # 管理者チェック
            if nickname.strip() == admin_nickname:
                if admin_hashed_password and bcrypt.checkpw(user_entered_password_bytes, admin_hashed_password.encode('utf-8')):
                    authenticated = True
                    is_admin_user = True

            # 一般ユーザー認証
            if not authenticated:
                users_from_secrets = st.secrets.get("users", [])
                for user_info in users_from_secrets:
                    if nickname.strip() == user_info.get("nickname"):
                        stored_hashed_id = user_info.get("user_id")
                        if stored_hashed_id and bcrypt.checkpw(user_entered_password_bytes, stored_hashed_id.encode('utf-8')):
                            authenticated = True
                            break

            if authenticated:
                go_to_main_page(nickname, user_id_input, is_admin_user)
            else:
                st.error("ニックネームまたはパスワードが正しくありません。")

# ==========================================
# 🔹 ログイン後ページ（shuffleメイン）
# ==========================================
elif st.session_state.page == 1:
    # --- ログアウトボタン ---
    st.sidebar.title(f"👤 {st.session_state.nickname}")
    if st.sidebar.button("ログアウト"):
        st.session_state.clear()
        st.rerun()

    # --- 以下は shuffle.py の main() の内容 ---
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    QUESTIONS_SELECT_PATH = os.path.join(BASE_DIR, "shuffle_data", "questions_select.csv")
    PROPER_NOUNS_PATH = os.path.join(BASE_DIR, "shuffle_data", "proper_nouns.csv")
    AUDIO_CORRECT_PATH = os.path.join(BASE_DIR, "shuffle_data", "audio_correct.mp3")
    AUDIO_FALSE_PATH = os.path.join(BASE_DIR, "shuffle_data", "audio_false.mp3")

    # === キャッシュ関数 ===
    @st.cache_data
    def load_selection_data():
        try:
            if not os.path.exists(QUESTIONS_SELECT_PATH):
                st.error("❌ questions_select.csv が見つかりません。")
                return pd.DataFrame()
            return pd.read_csv(QUESTIONS_SELECT_PATH)
        except Exception as e:
            st.error(f"読み込みエラー: {e}")
            return pd.DataFrame()

    @st.cache_data
    def load_proper_nouns():
        try:
            if os.path.exists(PROPER_NOUNS_PATH):
                df = pd.read_csv(PROPER_NOUNS_PATH)
                proper_nouns = [str(x).strip() for x in df["proper_noun"].dropna()]
                if "I" not in proper_nouns:
                    proper_nouns.append("I")
                return proper_nouns
            else:
                return ["I", "Tokyo", "Osaka", "Japan"]
        except Exception:
            return ["I", "Tokyo", "Osaka", "Japan"]

    # === トークン化・シャッフル ===
    def tokenize(sentence, proper_nouns):
        temp = sentence
        for pn in sorted(proper_nouns, key=len, reverse=True):
            safe = re.escape(pn)
            temp = re.sub(rf"\b{safe}\b", pn.replace(" ", "_"), temp)
        return temp.split()

    def detokenize(tokens):
        return [t.replace("_", " ") for t in tokens]

    def shuffle_question(sentence, proper_nouns):
        punc_match = re.search(r"([\.\?!])$", sentence.strip())
        punctuation = punc_match.group(1) if punc_match else ""
        sentence_no_punct = sentence.rstrip(string.punctuation).strip()
        tokens = tokenize(sentence_no_punct, proper_nouns)
        if tokens:
            first = tokens[0]
            is_proper = first.upper() == "I" or any(pn.lower().replace(" ", "_") == first.lower() for pn in proper_nouns)
            if not is_proper:
                tokens[0] = first.lower()
        random.shuffle(tokens)
        words = detokenize(tokens)
        if punctuation:
            words.append(punctuation)
        return words

    # === クイズUI ===
    def show_selection_page():
        st.title("📚 問題セット選択")
        df_select = load_selection_data()
        if df_select.empty:
            return
        instructions = df_select['instruction'].tolist()
        selected = st.radio("セットを選んでください", options=instructions, key='instruction_selector')
        if selected:
            row = df_select[df_select['instruction'] == selected].iloc[0]
            csv_name = row['csv_name']
            st.caption(f"（ファイル: `{csv_name}`）")
            if st.button("開始 ▶", type="primary", use_container_width=True):
                st.session_state.selected_csv = csv_name
                st.session_state.app_mode = 'quiz'
                if 'index' in st.session_state:
                    del st.session_state.index
                st.rerun()

    def show_quiz_page(df, proper_nouns):
        st.subheader("🧩 英文並べ替えクイズ")
        total = len(df)
        idx = st.session_state.index % total
        row = df.iloc[idx]
        jp = row["japanese"]
        en = row["english"]

        st.info(jp)
        if "shuffled" not in st.session_state:
            st.session_state.shuffled = shuffle_question(en, proper_nouns)
            st.session_state.selected = []
            st.session_state.used = []
        col_ok, col_reset = st.columns(2)
        for i, word in enumerate(st.session_state.shuffled):
            if st.button(word, key=f"{word}_{i}"):
                st.session_state.selected.append(word)
                st.session_state.used.append(i)
                st.rerun()
        st.write(" ".join(st.session_state.selected))
        if len(st.session_state.selected) == len(st.session_state.shuffled):
            if " ".join(st.session_state.selected) == en:
                st.success("✅ 正解！")
            else:
                st.error("❌ 不正解。")
            if st.button("次へ ▶"):
                st.session_state.index += 1
                st.session_state.pop("shuffled", None)
                st.rerun()
        if col_reset.button("🔄 リセット"):
            st.session_state.pop("shuffled", None)
            st.rerun()

    # === メインアプリロジック ===
    if "app_mode" not in st.session_state:
        st.session_state.app_mode = 'selection'
        st.session_state.selected_csv = None

    if st.session_state.app_mode == 'selection':
        show_selection_page()
    elif st.session_state.app_mode == 'quiz':
        csv_path = os.path.join(BASE_DIR, "shuffle_data", st.session_state.selected_csv)
        if not os.path.exists(csv_path):
            st.error("問題ファイルが見つかりません。")
            st.session_state.app_mode = 'selection'
            st.rerun()
        else:
            df = pd.read_csv(csv_path)
            proper_nouns = load_proper_nouns()
            show_quiz_page(df, proper_nouns)
