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
from typing import List

# ==========================================
# 🔹 Firebase 初期化
# ==========================================
# Streamlitのキャッシュ機能を利用して、アプリ実行中に一度だけ実行されるようにする
@st.cache_resource
def init_firestore():
    # Firebase secretsから認証情報を取得
    if "firebase" not in st.secrets:
        st.warning("⚠️ Streamlit Secretsに 'firebase' の設定が見つかりませんでした。", icon="🔒")
        # ダミーのクライアントを返す
        class DummyFirestoreClient:
            def collection(self, *args, **kwargs): return self
            def document(self, *args, **kwargs): return self
            def get(self, *args, **kwargs): return None
        return DummyFirestoreClient()
    
    firebase_creds_dict = dict(st.secrets["firebase"])
    
    # 認証情報を一時ファイルとして書き出し
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(firebase_creds_dict, f)
        f.flush()
        cred = credentials.Certificate(f.name)
        
        # アプリが未初期化の場合のみ初期化
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            
        # 一時ファイルを削除
        os.unlink(f.name)
    return firestore.client()

# ==========================================
# 🔹 ファイルパス設定
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
PROPER_NOUNS_PATH = os.path.join(BASE_DIR, "shuffle_data", "proper_nouns.csv")
QUESTIONS_SELECT_PATH = os.path.join(BASE_DIR, "shuffle_data", "questions_select.csv")
AUDIO_CORRECT_PATH = os.path.join(BASE_DIR, "shuffle_data", "audio_correct.mp3")
AUDIO_FALSE_PATH = os.path.join(BASE_DIR, "shuffle_data", "audio_false.mp3")


# ==========================================
# 🔹 ログイン関連関数
# ==========================================
def go_to_main_page(nickname, user_id, is_admin):
    """認証成功後、セッションステートを更新しメインページへ遷移"""
    st.session_state.nickname = nickname.strip()
    st.session_state.user_id = user_id.strip()
    st.session_state.is_admin = is_admin
    st.session_state.logged_in = True
    st.session_state.page = 1 # メインページ(クイズ選択)へ
    
    # ログイン後のクイズ初期状態をリセット
    st.session_state.app_mode = 'selection'
    st.session_state.selected_csv = None
    st.session_state.loaded_csv_name = None
    if 'index' in st.session_state:
        del st.session_state.index
        
    time.sleep(0.1)
    st.rerun()

def logout():
    """ログアウト処理"""
    st.session_state.logged_in = False
    st.session_state.page = 0
    # ログイン情報以外のセッションステートをクリア
    for key in list(st.session_state.keys()):
        if key not in ['page', 'logged_in']: 
            del st.session_state[key] 
    st.rerun()

# ==========================================
# 🔹 Firestore データ保存関数 (新規追加)
# ==========================================
def save_quiz_result(japanese, correct_english, user_answer, is_correct):
    """Firestoreにクイズ結果を保存する (コレクション名: shuffle_results)"""
    db = init_firestore() # キャッシュされたクライアントを取得
    
    # ダミークライアントの場合は保存をスキップ (Firebaseが初期化されていない場合)
    if not hasattr(db, 'collection'):
        # Streamlitが初期化の警告を表示するため、ここではst.errorをコメントアウト
        return

    # コレクション名を "shuffle_results" に設定
    collection_ref = db.collection("shuffle_results")
    
    data = {
        "user_id": st.session_state.user_id,
        "nickname": st.session_state.nickname,
        "quiz_set": st.session_state.selected_csv,
        "question_japanese": japanese,
        "question_english_correct": correct_english,
        "user_answer": user_answer,
        "is_correct": is_correct,
        "timestamp": firestore.SERVER_TIMESTAMP # サーバー側でタイムスタンプを記録
    }
    
    try:
        # ドキュメントIDは自動生成
        collection_ref.add(data)
    except Exception as e:
        # 開発中はエラーを表示
        st.error(f"⚠️ 結果の保存中にエラーが発生しました: {e}")

# ==========================================
# 🔹 クイズロジック: データロード・シャッフル (再定義と統合)
# (簡潔にするため、クイズ関連のヘルパー関数は省略せず含めます)
# ==========================================

@st.cache_data
def load_selection_data() -> pd.DataFrame:
    try:
        if not os.path.exists(QUESTIONS_SELECT_PATH):
            st.error(f"❌ questions_select.csv が見つかりません。")
            return pd.DataFrame()
        return pd.read_csv(QUESTIONS_SELECT_PATH)
    except Exception as e:
        st.error(f"問題セット選択リストの読み込み中にエラーが発生しました: {e}")
        return pd.DataFrame()

@st.cache_data
def load_proper_nouns() -> List[str]:
    try:
        if os.path.exists(PROPER_NOUNS_PATH):
            df = pd.read_csv(PROPER_NOUNS_PATH)
            proper_nouns = [str(x).strip() for x in df["proper_noun"].dropna()]
            if "I" not in proper_nouns:
                proper_nouns.append("I")
            return proper_nouns
        else:
            return ["New York", "Osaka", "Tokyo", "Sunday", "Monday", "Japan", "America", "I"]
    except Exception as e:
        st.error(f"固有名詞の読み込みエラー: {e}")
        return ["New York", "Osaka", "Tokyo", "Sunday", "Monday", "Japan", "America", "I"]

def tokenize(sentence: str, proper_nouns: List[str]) -> List[str]:
    temp_sentence = sentence
    for pn in sorted(proper_nouns, key=len, reverse=True):
        safe_pn = re.escape(pn)
        temp_sentence = re.sub(rf"\b{safe_pn}\b", pn.replace(" ", "_"), temp_sentence)
    return temp_sentence.split()

def detokenize(tokens: List[str]) -> List[str]:
    return [t.replace("_", " ") for t in tokens]

def shuffle_question(sentence: str, proper_nouns: List[str]) -> List[str]:
    punctuation_match = re.search(r"([\.\?!])$", sentence.strip())
    punctuation = punctuation_match.group(1) if punctuation_match else ""
    sentence_no_punct = sentence.rstrip(string.punctuation).strip()
    tokens = tokenize(sentence_no_punct, proper_nouns)
    
    if tokens:
        first_token = tokens[0]
        is_proper_or_i = first_token.upper() == 'I' or any(pn.lower().replace(" ", "_") == first_token.lower() for pn in proper_nouns)
        if not is_proper_or_i:
            tokens[0] = first_token[0].lower() + first_token[1:] if len(first_token) > 1 else first_token.lower()
            
    random.shuffle(tokens)
    shuffled_words = detokenize(tokens)
    
    if punctuation:
        shuffled_words.append(punctuation)
    return shuffled_words

def init_session_state(df: pd.DataFrame, proper_nouns: List[str]):
    if "index" not in st.session_state:
        st.session_state.index = 0
    
    current_index = st.session_state.index % len(df)
    english_sentence = df.iloc[current_index]["english"]
    
    st.session_state.current_correct = english_sentence.strip()
    st.session_state.shuffled = shuffle_question(english_sentence, proper_nouns)
    st.session_state.selected = [] 
    st.session_state.used_indices = []
    st.session_state.quiz_complete = False
    st.session_state.quiz_saved = False # 【追記】問題が切り替わったらリセット

def handle_word_click(i: int, word: str):
    if st.session_state.quiz_complete:
        return

    word_to_append = word
    if not st.session_state.selected: 
        if not re.match(r"[\.\?!]$", word):
            if word[0].islower():
                word_to_append = word[0].upper() + word[1:] if len(word) > 1 else word.upper()
    
    st.session_state.selected.append(word_to_append)
    st.session_state.used_indices.append(i) 

def undo_selection():
    if st.session_state.selected:
        st.session_state.selected.pop()
        st.session_state.used_indices.pop() 

def next_question(df: pd.DataFrame, proper_nouns: List[str]):
    st.session_state.index = (st.session_state.index + 1) % len(df)
    init_session_state(df, proper_nouns) 

def reset_question(df: pd.DataFrame, proper_nouns: List[str]):
    current_index = st.session_state.index
    st.session_state.index = current_index 
    init_session_state(df, proper_nouns)

def play_audio_trick(is_correct: bool):
    audio_path = AUDIO_CORRECT_PATH if is_correct else AUDIO_FALSE_PATH
    if not os.path.exists(audio_path):
        return
    st.audio(str(audio_path), format="audio/mp3", autoplay=True, loop=False)

# ==========================================
# 🔹 1. 問題セット選択ページ (Page 1 の 'selection' モード)
# ==========================================
def show_selection_page():
    st.title("📚 問題セット選択")
    st.caption("挑戦したい英文並べ替えセットを選んでください。")

    df_select = load_selection_data()

    if df_select.empty:
        st.warning("問題セットの選択データがありません。")
        return

    st.markdown("---")
    
    instructions = df_select['instruction'].tolist()
    
    selected_instruction = st.radio(
        "**セットを選択してください**",
        options=instructions,
        key='instruction_selector',
    )

    if selected_instruction:
        selected_row = df_select[df_select['instruction'] == selected_instruction].iloc[0]
        csv_name = selected_row['csv_name']
        
        st.caption(f"（ファイル: `{csv_name}`）")
        
        st.markdown("---")
        
        if st.button("このセットで開始 ▶", key="start_quiz_set", type="primary", use_container_width=True):
            st.session_state.selected_csv = csv_name
            st.session_state.app_mode = 'quiz'
            if 'index' in st.session_state:
                 del st.session_state.index
            st.rerun()

# ==========================================
# 🔹 2. クイズ実行ページ (Page 1 の 'quiz' モード)
# ==========================================
def show_quiz_page(df: pd.DataFrame, proper_nouns: List[str]):
    # (中略: CSSの定義は run_app または quiz_main で一括で呼び出すのが望ましい)
    
    col_title, col_button = st.columns([4, 1])

    with col_title:
        st.subheader("🧩 英文並べ替えトレーニング")
        st.markdown(f"問題セット: `{st.session_state.selected_csv}`")
    
    with col_button:
        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True) 
        if st.button("⬅️ 選択に戻る", key="back_to_selection", use_container_width=True):
            st.session_state.app_mode = 'selection'
            # 状態をクリア
            st.session_state.selected = []
            st.session_state.used_indices = []
            st.session_state.quiz_complete = False
            st.session_state.loaded_csv_name = None 
            st.rerun()
            
    st.markdown("---")

    # 現在の問題情報
    total_questions = len(df)
    current_index = st.session_state.index % total_questions
    row = df.iloc[current_index]
    japanese = row["japanese"]
    english = row["english"]
    current_correct = english.strip()

    st.info(f"**問題 {current_index + 1}**: {japanese}", icon="💬")
    
    # ----------------------------------------------------
    # 1. あなたの回答エリア (Selected Words)
    # ----------------------------------------------------
    
    selected_words_html = ""
    # (HTML生成ロジックは省略せずにそのまま保持。文字数のためここでは省略します)
    if not st.session_state.selected:
        selected_words_html = "<div style='border: 2px dashed #9ca3af; padding: 12px; border-radius: 8px; text-align: center; color: #9ca3af; font-style: italic; min-height: 50px;'>下の語句を順番にタップしてください</div>"
    else:
        selected_words_html = "<div style='display: flex; flex-wrap: wrap; gap: 8px; padding: 10px; border: 2px solid #3b82f6; background-color: #f7fbff; border-radius: 8px; min-height: 50px;'>"
        for word in st.session_state.selected:
            is_punctuation = re.match(r"[\.\?!]$", word)
            color_style = "background-color: #fca5a5; color: #7f1d1d; box-shadow: 0 2px #fecaca;" if is_punctuation else "background-color: #dbeafe; color: #1e40af; box-shadow: 0 2px #93c5fd;"
            selected_words_html += f"<span class='selected-word-chip' style='{color_style} padding: 6px 10px; border-radius: 6px; font-weight: bold;'>{word}</span>"
        selected_words_html += "</div>"
    
    st.markdown(selected_words_html, unsafe_allow_html=True)
    
    # ----------------------------------------------------
    # 2. 選択肢エリア (Shuffled Words)
    # ----------------------------------------------------
    shuffled_container = st.container()
    with shuffled_container:
        num_words = len(st.session_state.shuffled)
        max_cols = min(num_words, 8) 
        cols = st.columns([1] * max_cols)
        
        for i, word in enumerate(st.session_state.shuffled):
            is_picked = i in st.session_state.used_indices
            label = word 
            button_key = f"word_{st.session_state.selected_csv}_{st.session_state.index}_{i}"
            col_index = i % max_cols
            
            if cols[col_index].button(label, key=button_key, disabled=is_picked, use_container_width=True):
                handle_word_click(i, word)
                st.rerun()

    # ----------------------------------------------------
    # 3. コントロールボタン (OK/Undo/Next)
    # ----------------------------------------------------
  
    col_undo, col_ok, col_next = st.columns([1, 1, 1])

    if col_undo.button("↩️ やり直し", on_click=undo_selection, disabled=not st.session_state.selected, use_container_width=True):
        st.rerun()

    if len(st.session_state.selected) == len(st.session_state.shuffled):
        st.session_state.quiz_complete = True
        
        user_answer_raw = " ".join(st.session_state.selected)
        user_answer_cleaned = re.sub(r'\s+([\.\?!])$', r'\1', user_answer_raw)
        
        if user_answer_cleaned and user_answer_cleaned[0].islower():
            user_answer_final = user_answer_cleaned[0].upper() + user_answer_cleaned[1:]
        else:
            user_answer_final = user_answer_cleaned

        # 正誤判定
        is_correct = (user_answer_final == current_correct)

        # 【結果の保存ロジック】
        if not st.session_state.quiz_saved:
            # Firestoreに結果を保存
            save_quiz_result(japanese, current_correct, user_answer_final, is_correct)
            st.session_state.quiz_saved = True # 保存フラグを立てて二重保存を防ぐ

        if is_correct:
            col_ok.success("✅ 正解！")
            st.balloons()
            play_audio_trick(True)
        else:
            col_ok.error("❌ 不正解。")
            play_audio_trick(False)
            
        st.markdown(f"**正解の英文:** `{current_correct}`")
        
        if col_next.button("次の問題へ ▶", type="primary", use_container_width=True, on_click=next_question, args=(df, proper_nouns)):
            st.rerun()
            
    else: # if len(...) == len(...) の else に対応
        col_ok.button("OK (未完成)", disabled=True, use_container_width=True)
        if col_next.button("🔄 リセット", on_click=reset_question, args=(df, proper_nouns), use_container_width=True):
            st.rerun()
            
    progress_ratio = (current_index + 1) / total_questions
    st.progress(progress_ratio, text=f"**進捗: {current_index + 1} / {total_questions} 問**")

def quiz_main():
    """Page 1 (メインコンテンツ) のロジックを管理"""
    
    # CSSの定義 (省略、簡潔化のため)
    st.markdown("""
    <style>
    /* ... (CSSの定義は省略) ... */
    </style>
    """, unsafe_allow_html=True)
    
    # --- メインコンテンツの表示 ---
    if st.session_state.app_mode == 'selection':
        show_selection_page()

    elif st.session_state.app_mode == 'quiz':
        if st.session_state.selected_csv is None:
            st.session_state.app_mode = 'selection'
            st.rerun()
            return
            
        quiz_file_path = os.path.join(BASE_DIR, "shuffle_data", st.session_state.selected_csv)
        
        if not os.path.exists(quiz_file_path):
            st.error(f"❌ 問題ファイル (`{st.session_state.selected_csv}`) が見つかりません。")
            st.session_state.app_mode = 'selection'
            st.rerun()
            return
            
        try:
            df = pd.read_csv(quiz_file_path)
            proper_nouns = load_proper_nouns()
            
            # 問題セットが切り替わった場合、セッションを初期化
            if st.session_state.selected_csv != st.session_state.get('loaded_csv_name') or "shuffled" not in st.session_state:
                st.session_state.index = 0
                init_session_state(df, proper_nouns)
                st.session_state.loaded_csv_name = st.session_state.selected_csv
                
            show_quiz_page(df, proper_nouns)
            
        except Exception as e:
            st.error(f"問題データ読み込み中にエラーが発生しました: {e}")
            st.session_state.app_mode = 'selection'
            st.rerun()
    # --- メインコンテンツ終了 ---
    
    st.markdown("---") # フッターとの区切り線
    
    # フッター用のコンテナを作成し、セクションを分ける
    footer_container = st.container()
    
    with footer_container:
        col_user, col_logout = st.columns([7, 3])

        with col_user:
            user_info = f"👤 **ログインユーザー:** {st.session_state.nickname} "
            if st.session_state.is_admin:
                user_info += " (管理者)"
            st.caption(user_info) # captionで控えめに表示

        with col_logout:
            # ログアウトボタンを右側に配置
            st.button("ログアウト", on_click=logout, key="logout_button_footer", use_container_width=True)
            


# ==========================================
# 🔹 アプリケーション実行のメインロジック
# ==========================================
def run_app():
    st.set_page_config(layout="wide")

    # セッション初期化 (Streamlitアプリの実行開始時に一度だけ実行される)
    defaults = {
        "logged_in": False,
        "page": 0,
        "nickname": "",
        "user_id": "",
        "is_admin": False,
        "index": 0,
        "app_mode": 'selection',
        "selected_csv": None,
        "loaded_csv_name": None,
        "current_correct": "",
        "shuffled": [],
        "selected": [], 
        "used_indices": [],
        "quiz_complete": False,
        "selected": [], 
        "quiz_saved": False, # 【追記】結果保存済みフラグ
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    db = init_firestore() # Firebase 初期化はここで実行

    # ------------------------------------------
    # 🔹 Page 0: ログインページ 
    # ------------------------------------------

    if st.session_state.page == 0:
        # ログイン済みならメインへ
        if st.session_state.logged_in:
            st.session_state.page = 1
            st.rerun()
            st.stop()

        st.title("ログインページ")
        st.caption("管理者としてログインするには、secrets.tomlに設定したADMIN_USERNAMEとADMIN_PASSWORDを使用してください。")
        st.markdown("---")
        
        # ユーザー入力
        nickname = st.text_input("ニックネーム", key="nickname_input")
        user_id_input = st.text_input("パスワード", type="password", key="user_id_input")

        if st.button("ログイン", type="primary"):
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

    # ------------------------------------------
    # 🔹 Page 1: メインコンテンツ (問題セット選択/クイズ実行)
    # ------------------------------------------
    elif st.session_state.page == 1:
        # 未ログインならログインページへリダイレクト
        if not st.session_state.logged_in:
            st.session_state.page = 0
            st.rerun()
            st.stop()
            
        quiz_main()


# === 実行 ===
if __name__ == "__main__":
    run_app()