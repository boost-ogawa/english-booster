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
@st.cache_resource
def init_firestore():
    """Streamlitのキャッシュを利用し、Firestoreクライアントを一度だけ初期化する"""
    if "firebase" not in st.secrets:
        st.warning("⚠️ Streamlit Secretsに 'firebase' の設定が見つかりませんでした。", icon="🔒")
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
        
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            
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
    st.session_state.page = 1 
    
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
    for key in list(st.session_state.keys()):
        if key not in ['page', 'logged_in']: 
            del st.session_state[key] 
    st.rerun()

# ==========================================
# 🔹 Firestore データ保存関数
# ==========================================
def save_quiz_result(japanese, correct_english, user_answer, is_correct):
    """Firestoreにクイズ結果を保存する (コレクション名: shuffle_results)"""
    db = init_firestore()
    
    if not hasattr(db, 'collection'):
        return

    collection_ref = db.collection("shuffle_results")
    
    data = {
        "user_id": st.session_state.user_id,
        "nickname": st.session_state.nickname,
        "quiz_set": st.session_state.selected_csv,
        "question_japanese": japanese,
        "question_english_correct": correct_english,
        "user_answer": user_answer,
        "is_correct": is_correct,
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    
    try:
        collection_ref.add(data)
    except Exception as e:
        st.error(f"⚠️ 結果の保存中にエラーが発生しました: {e}")


# ==========================================
# 🔹 復習用データロード関数
# ==========================================
def load_review_data(user_id, quiz_set=None):
    """Firestoreから過去の不正解問題を抽出し、復習用DataFrameを返す"""
    db = init_firestore()
    if not hasattr(db, 'collection'):
        return pd.DataFrame({'japanese': [], 'english': []})

    review_questions = []
    
    try:
        # 1. クエリの作成: ユーザーIDと不正解でフィルタリング
        collection_ref = db.collection("shuffle_results")
        query = collection_ref.where("user_id", "==", user_id).where("is_correct", "==", False)
        
        # quiz_set が指定されていればクエリに追加
        if quiz_set and quiz_set != "復習モード": 
            query = query.where("quiz_set", "==", quiz_set) 
            
        results = query.get()
        
        # 2. 抽出した問題情報から重複を取り除き、復習リストを作成
        unique_mistakes = set()
        
        for doc in results:
            data = doc.to_dict()
            unique_key = (data['question_japanese'], data['question_english_correct'])
            
            if unique_key not in unique_mistakes:
                review_questions.append({
                    'japanese': data['question_japanese'],
                    'english': data['question_english_correct']
                })
                unique_mistakes.add(unique_key)
                
        # 3. DataFrameとして返す
        if not review_questions:
            return pd.DataFrame({'japanese': [], 'english': []})
        
        review_df = pd.DataFrame(review_questions).sample(frac=1).reset_index(drop=True)
        return review_df

    except Exception as e:
        st.error(f"⚠️ 復習問題のロード中にエラーが発生しました: {e}")
        return pd.DataFrame({'japanese': [], 'english': []})

# ==========================================
# 🔹 クイズロジック: データロード・シャッフル
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
    st.session_state.quiz_saved = False

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
    """次の問題へ進むためのロジック。最終問題なら結果画面へ遷移するフラグを立てる。"""
    current_index = st.session_state.index
    total_questions = len(df)
    
    if current_index + 1 >= total_questions:
        st.session_state.quiz_complete = True
        st.session_state.app_mode = 'quiz_result'
    else:
        st.session_state.index += 1
        init_session_state(df, proper_nouns) 
        
    st.session_state.quiz_saved = False 

def reset_question(df: pd.DataFrame, proper_nouns: List[str]):
    current_index = st.session_state.index
    st.session_state.index = current_index 
    init_session_state(df, proper_nouns)

# ==========================================
# 🔹 3. 結果表示ページ
# ==========================================
def show_result_page():
    """クイズセット終了後の結果表示ページ"""
    st.title("🎉 クイズセット完了！")
    
    total = st.session_state.get('total_questions', 0)
    correct = st.session_state.get('correct_count', 0)
    
    if total > 0:
        accuracy = (correct / total) * 100
        st.subheader(f"✅ 結果: {correct} / {total} 問 正解")
        st.success(f"**正答率: {accuracy:.1f}%**")
    else:
        st.subheader("結果は記録されていません。")
    
    st.markdown("---")
    
    if st.session_state.get('app_mode') == 'review_quiz':
        st.info("お疲れ様でした！復習クイズを完了しました。")
        if 'review_df' in st.session_state:
            del st.session_state.review_df
    
    if st.button("📚 問題セット選択に戻る", type="primary", use_container_width=True):
        
        for key in ['index', 'current_correct', 'shuffled', 'selected', 'used_indices', 'quiz_complete', 'quiz_saved', 'correct_count', 'total_questions', 'loaded_csv_name']:
            st.session_state.pop(key, None)
            
        st.session_state.app_mode = 'selection'
        st.rerun()

# ==========================================
# 🔹 1. 問題セット選択ページ
# ==========================================
def show_selection_page():
    st.title("📚 問題セット選択")
    st.caption("挑戦したいセットを選んでください。")

    df_select = load_selection_data()
    
    if df_select.empty:
        st.error("問題セットの選択リストが空です。`questions_select.csv` を確認してください。")
        return
        
    # 'grade' 列がない場合はエラーメッセージを表示して処理を中断
    if 'grade' not in df_select.columns:
        st.error("⚠️ エラー: 問題セットCSVに 'grade' 列が見つかりません。")
        return

    # DataFrameを 'grade' 列でグループ化
    df_grouped = df_select.groupby('grade')
    
    st.markdown("---") 
    
    # --- 👇 3カラムレイアウトの開始 (1:1:1) 👇 ---
    col_selector, col_start, col_review = st.columns(3)
    
    selected_instruction = None
    csv_name = None
    
    # 1. 問題セットの選択 (セレクトボックスで2段構成) - 左カラム
    with col_selector:
        st.subheader("セットを選択")
        
        # どのセレクトボックスが選ばれたかを示すための変数
        m2_selected_instruction = None
        m3_selected_instruction = None
        
        # 1-1. 中2コンテナの処理
        if '中2' in df_grouped.groups:
            df_m2 = df_grouped.get_group('中2')
            m2_instructions = df_m2['instruction'].tolist()
            m2_selected = st.selectbox(
                "中2_セレクター", # キーを変更
                options=["中学２年生（セットを選択してください）"] + m2_instructions, 
                key='m2_selector', 
                label_visibility="hidden"
            )
            if m2_selected != "中学２年生（セットを選択してください）":
                m2_selected_instruction = m2_selected
                
        # 1-2. 中3コンテナの処理
        if '中3' in df_grouped.groups:
            df_m3 = df_grouped.get_group('中3')
            m3_instructions = df_m3['instruction'].tolist()
            st.markdown("**🔹 中学3年生**")
            
            # 中2が選択されているかどうかで中3のセレクトボックスの有効/無効を切り替える
            is_m3_disabled = (m2_selected_instruction is not None)
            
            m3_selected = st.selectbox(
                "中3_セレクター", # キーを変更
                options=["中学３年生（セットを選択してください）"] + m3_instructions, 
                key='m3_selector', 
                label_visibility="hidden",
                disabled=is_m3_disabled
            )
            if not is_m3_disabled and m3_selected != "中学３年生（セットを選択してください）":
                 m3_selected_instruction = m3_selected

        # 最終的に選択された Instruction を決定
        selected_instruction = m2_selected_instruction if m2_selected_instruction else m3_selected_instruction


    # 2. 以降のロジックは 'selected_instruction' がセットされたかどうかで動く
    if selected_instruction:
        selected_row = df_select[df_select['instruction'] == selected_instruction].iloc[0]
        csv_name = selected_row['csv_name']
        
        st.caption(f"選択ファイル: `{csv_name}`")
        
        # 2. このセットで開始ボタン (中央カラム)
        with col_start:
            st.subheader("開始")
            if st.button("このセットで開始 ▶", key="start_quiz_set", type="primary", use_container_width=True):
                st.session_state.selected_csv = csv_name
                st.session_state.app_mode = 'quiz'
                st.session_state.pop('index', None)
                st.session_state.correct_count = 0 # カウンターリセット
                st.rerun()

        # 3. 間違えた問題に再挑戦ボタン (右カラム)
        with col_review:
            st.subheader("復習")
            if st.button("間違えた問題に再挑戦", key="start_review_quiz", type="secondary", use_container_width=True):
                review_df = load_review_data(st.session_state.user_id, quiz_set=csv_name)
                
                if review_df.empty:
                    st.warning(f"現在、**選択中のセット**には復習すべき問題はありません。")
                else:
                    for key in ['index', 'current_correct', 'shuffled', 'selected', 'used_indices', 'quiz_complete', 'quiz_saved', 'correct_count', 'total_questions', 'loaded_csv_name']:
                        st.session_state.pop(key, None)
                        
                    st.session_state.app_mode = 'review_quiz'
                    st.session_state.review_df = review_df
                    st.session_state.selected_csv = "復習モード"
                    st.rerun()
                    
    else: # どちらも選択されていない場合
        col_start.empty()
        col_review.empty()
        
    st.markdown("---") # 区切り線は最後に統一

# ==========================================
# 🔹 2. クイズ実行ページ
# ==========================================
def show_quiz_page(df: pd.DataFrame, proper_nouns: List[str]):
    
    total_questions = len(df)
    current_index = st.session_state.index % total_questions
    row = df.iloc[current_index]
    japanese = row["japanese"]
    english = row["english"]
    current_correct = english.strip()

    st.markdown(f"問題セット: `{st.session_state.selected_csv}`")
    
    st.info(f"**問題 {current_index + 1}**: {japanese}", icon="💬")

    # ----------------------------------------------------
    # 1. あなたの回答エリア (Selected Words)
    # ----------------------------------------------------
    # used_indicesの末尾2つが同じ（＝同じボタンが連続でクリックされた）場合をチェック
    if len(st.session_state.used_indices) >= 2 and st.session_state.used_indices[-1] == st.session_state.used_indices[-2]:
        # 2つ目の重複した単語だけを削除
        st.session_state.selected.pop() 
        st.session_state.used_indices.pop() 

    selected_words_html = ""
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

            if cols[col_index].button(
                label, 
                key=button_key, 
                disabled=is_picked, 
                use_container_width=True,
                on_click=handle_word_click,
                args=(i, word)
            ):
                st.rerun() 
                    
    # ----------------------------------------------------
    # 3. コントロールボタン (OK/Undo/Next)
    # ----------------------------------------------------
    
    col_undo, col_ok, col_next = st.columns([1, 1, 1])

    if col_undo.button("↩️ １語消去", on_click=undo_selection, disabled=not st.session_state.selected, use_container_width=True):
        st.rerun()

    if len(st.session_state.selected) == len(st.session_state.shuffled):
        st.session_state.quiz_complete = True
        
        user_answer_raw = " ".join(st.session_state.selected)
        user_answer_cleaned = re.sub(r'\s+([\.\?!])$', r'\1', user_answer_raw)
        
        if user_answer_cleaned and user_answer_cleaned[0].islower():
            user_answer_final = user_answer_cleaned[0].upper() + user_answer_cleaned[1:]
        else:
            user_answer_final = user_answer_cleaned

        is_correct = (user_answer_final == current_correct)

        if is_correct and not st.session_state.quiz_saved:
            st.session_state.correct_count += 1
                
        if not st.session_state.quiz_saved:
            save_quiz_result(japanese, current_correct, user_answer_final, is_correct)
            st.session_state.quiz_saved = True

        if is_correct:
            col_ok.success("✅ 正解！")
            st.balloons()
        else:
            col_ok.error("❌ 不正解。")
            
        st.markdown(f"**正解の英文:** `{current_correct}`")

        total_questions = len(df)
        current_index = st.session_state.index % total_questions
        is_last_question = (current_index + 1 >= total_questions)

        next_button_label = "結果を確認 ✅" if is_last_question else "次の問題へ ▶"
        next_button_type = "secondary" if is_last_question else "primary"
        
        if col_next.button(
            next_button_label,               # ラベルを動的に変更
            type=next_button_type,           # 最終問題ではボタンの色を変えて強調
            use_container_width=True, 
            on_click=next_question, 
            args=(df, proper_nouns)
        ):
            st.rerun()
                          
    else:
        col_ok.button("OK (未完成)", disabled=True, use_container_width=True)
        if col_next.button("🔄 リセット", on_click=reset_question, args=(df, proper_nouns), use_container_width=True):
            st.rerun()
            
    progress_ratio = (current_index + 1) / total_questions
    st.progress(progress_ratio, text=f"**進捗: {current_index + 1} / {total_questions} 問**")


def quiz_main():
    """Page 1 (メインコンテンツ) のロジックを管理"""
    
    st.markdown("""
    <style>
    /* ... (CSSの定義は省略) ... */
    </style>
    """, unsafe_allow_html=True)
    
    # --- メインコンテンツの表示 ---
    
    if st.session_state.app_mode == 'selection':
        show_selection_page()

    elif st.session_state.app_mode == 'quiz' or st.session_state.app_mode == 'review_quiz':
        
        if st.session_state.app_mode == 'review_quiz':
            if 'review_df' not in st.session_state or st.session_state.review_df.empty:
                st.error("復習データが見つからないか、空です。")
                st.session_state.app_mode = 'selection'
                st.rerun()
                return
            
            df = st.session_state.review_df
            proper_nouns = load_proper_nouns()
            header_text = "🔄 間違えた問題に再挑戦"

        else:
            header_text = "📝 英文並べかえ問題に挑戦"
            
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
            except Exception as e:
                st.error(f"問題データ読み込み中にエラーが発生しました: {e}")
                st.session_state.app_mode = 'selection'
                st.rerun()
                return

        if df.empty:
            st.error("問題データが空です。問題セット選択ページに戻ります。")
            st.session_state.app_mode = 'selection'
            st.rerun()
            return

        # 2カラムヘッダーの表示
        col_title_top, col_button_top = st.columns([4, 1])

        with col_title_top:
            st.title(header_text)
            
        with col_button_top:
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True) 
            if st.button("⬅️ 選択に戻る", key="back_to_selection_main", use_container_width=True):
                st.session_state.app_mode = 'selection'
                st.session_state.selected = []
                st.session_state.used_indices = []
                st.session_state.quiz_complete = False
                st.session_state.loaded_csv_name = None 
                st.rerun()
                return

        st.markdown("---")
        
        if st.session_state.selected_csv != st.session_state.get('loaded_csv_name') or "shuffled" not in st.session_state:
            st.session_state.index = 0
            init_session_state(df, proper_nouns)
            st.session_state.loaded_csv_name = st.session_state.selected_csv

            st.session_state.correct_count = 0
            st.session_state.total_questions = len(df) # 総問題数をここでセット
            

        show_quiz_page(df, proper_nouns)

    elif st.session_state.app_mode == 'quiz_result':
        show_result_page()
        
    # --- メインコンテンツ終了 ---
        
    st.markdown("---")
    
    # フッター
    footer_container = st.container()
    
    with footer_container:
        col_user, col_logout = st.columns([7, 3])

        with col_user:
            user_info = f"👤 **ログインユーザー:** {st.session_state.nickname} "
            if st.session_state.is_admin:
                user_info += " (管理者)"
            st.caption(user_info)

        with col_logout:
            st.button("ログアウト", on_click=logout, key="logout_button_footer", use_container_width=True)
            

# ==========================================
# 🔹 アプリケーション実行のメインロジック
# ==========================================
def run_app():
    st.set_page_config(layout="wide")

    # セッション初期化
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
        "quiz_saved": False,
        "correct_count": 0,
        "total_questions": 0,
        "duplicate_error": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    db = init_firestore()

    # ------------------------------------------
    # 🔹 Page 0: ログインページ 
    # ------------------------------------------
    if st.session_state.page == 0:
        if st.session_state.logged_in:
            st.session_state.page = 1
            st.rerun()
            st.stop()

        st.title("ログインページ")
        st.caption("管理者としてログインするには、secrets.tomlに設定したADMIN_USERNAMEとADMIN_PASSWORDを使用してください。")
        st.markdown("---")
        
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
        if not st.session_state.logged_in:
            st.session_state.page = 0
            st.rerun()
            st.stop()
            
        quiz_main()


# === 実行 ===
if __name__ == "__main__":
    run_app()