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
from typing import List, Tuple

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
VOCABOOSTER_URL = "https://filedn.com/lTkchLpf4Vo0aRMDYi0tvk5/VocaBooster/VocaBooster.html"

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
    for key in list(st.session_state.keys()):
        if key not in ['page', 'logged_in']:
            del st.session_state[key]
    st.session_state.logged_in = False
    st.session_state.page = 0

# ==========================================
# 🔹 Firestore データ保存関数
# ==========================================
# 💡 question_japanese, question_english_correct の保存を削除し、id を追加
def save_quiz_result(id, quiz_set, user_answer, is_correct, quiz_type):
    """Firestoreにクイズ結果を保存する (コレクション名: shuffle_results)"""
    db = init_firestore()
    
    if not hasattr(db, 'collection'):
        return

    collection_ref = db.collection("shuffle_results")
    
    data = {
        "user_id": st.session_state.user_id,
        "nickname": st.session_state.nickname,
        "quiz_set": quiz_set, # CSVファイル名
        "quiz_type": quiz_type, 
        "id": id, # 💡 問題特定用のIDのみを保存
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
@st.cache_data(show_spinner="復習問題を準備中...")
def load_quiz_data(csv_name):
    """指定されたCSVファイルをロードし、idが存在することを確認する"""
    quiz_file_path = os.path.join(BASE_DIR, "shuffle_data", csv_name)
    
    if not os.path.exists(quiz_file_path):
        st.error(f"❌ 問題ファイル (`{csv_name}`) が見つかりません。")
        return pd.DataFrame()
        
    try:
        df = pd.read_csv(quiz_file_path)
        if 'id' not in df.columns:
            st.error("❌ 問題CSVに 'id' 列がありません。この問題セットでは復習機能は利用できません。")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"問題データ読み込み中にエラーが発生しました: {e}")
        return pd.DataFrame()

def load_review_data(user_id, target_quiz_set=None):
    """Firestoreから過去の不正解問題を抽出し、復習用DataFrameを返す (アプローチA)"""
    db = init_firestore()
    if not hasattr(db, 'collection'):
        return pd.DataFrame()

    review_questions_list = []
    
    try:
        # 1. Firestoreから不正解記録 (id, quiz_set) を抽出
        collection_ref = db.collection("shuffle_results")
        query = collection_ref.where("user_id", "==", user_id).where("is_correct", "==", False)
        
        if target_quiz_set and target_quiz_set != "復習モード": 
            query = query.where("quiz_set", "==", target_quiz_set) 
            
        results = query.get()
        
        # 2. 不正解だった問題の (quiz_set, id) をユニークに抽出
        unique_mistakes = set()
        mistake_map = {} # {quiz_set: {id1, id2, ...}}
        
        for doc in results:
            data = doc.to_dict()
            q_set = data.get('quiz_set')
            q_id = data.get('id')
            
            if q_set and q_id is not None:
                key = (q_set, q_id)
                if key not in unique_mistakes:
                    unique_mistakes.add(key)
                    if q_set not in mistake_map:
                        mistake_map[q_set] = set()
                    mistake_map[q_set].add(q_id)
        
        if not unique_mistakes:
            return pd.DataFrame()

        # 3. 各CSVファイル (quiz_set) をロードし、不正解だった問題の行を抽出
        for csv_name, q_ids in mistake_map.items():
            df_original = load_quiz_data(csv_name)
            
            if not df_original.empty and 'id' in df_original.columns:
                # Firestoreに保存されているIDはint/strが混在する可能性があるため、型を統一してフィルタリング
                q_ids_safe = [str(qid) for qid in q_ids]
                
                df_filtered = df_original[df_original['id'].astype(str).isin(q_ids_safe)].copy()
                
                # 抽出したデータに quiz_set と quiz_type の情報を追加（復習画面で利用可能にするため）
                df_filtered['original_quiz_set'] = csv_name
                
                # df_select から quiz_type を取得して追加
                if 'df_select' in st.session_state:
                    type_row = st.session_state.df_select[st.session_state.df_select['csv_name'] == csv_name]
                    if not type_row.empty:
                        df_filtered['quiz_type_review'] = type_row.iloc[0]['type']
                    else:
                        df_filtered['quiz_type_review'] = 'shuffling' # 見つからなければ並べかえと仮定
                
                review_questions_list.append(df_filtered)
                
        if not review_questions_list:
            return pd.DataFrame()
            
        # 4. すべての不正解問題を結合し、シャッフルして返す
        review_df = pd.concat(review_questions_list, ignore_index=True)
        review_df = review_df.sample(frac=1).reset_index(drop=True)
        return review_df

    except Exception as e:
        st.error(f"⚠️ 復習問題のロード中にエラーが発生しました: {e}")
        return pd.DataFrame()

# ==========================================
# 🔹 クイズロジック: データロード・シャッフル
# ==========================================
# (省略: load_selection_data, load_proper_nouns, tokenize, detokenize, shuffle_question, generate_shuffling_data は変更なし)

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

def generate_shuffling_data(english_sentence: str, proper_nouns: List[str]) -> Tuple[List[str], List[str]]:
    """並べ替えに必要な単語リストと正解の順序付き単語リストを生成する"""
    correct_sentence = english_sentence.strip()
    
    shuffled_words = shuffle_question(correct_sentence, proper_nouns)
    
    punctuation_match = re.search(r"([\.\?!])$", correct_sentence)
    sentence_no_punct = correct_sentence.rstrip(string.punctuation).strip()
    correct_tokens = detokenize(tokenize(sentence_no_punct, proper_nouns))
    if punctuation_match:
        correct_tokens.append(punctuation_match.group(1))
        
    return shuffled_words, correct_tokens

# 💡 問題形式に応じてセッションステートを初期化する関数
def init_session_state(df: pd.DataFrame, proper_nouns: List[str]):
    if "index" not in st.session_state:
        st.session_state.index = 0
    
    current_index = st.session_state.index % len(df)
    row = df.iloc[current_index]
    
    # 💡 [修正点 A] 復習モードの場合は 'quiz_type_review' を優先して問題タイプを決定
    if st.session_state.get('app_mode') == 'review_quiz':
        quiz_type = row.get('quiz_type_review', 'shuffling')
    else:
        quiz_type = st.session_state.get('quiz_type', 'shuffling') 
    
    # 共通の初期化
    st.session_state.current_correct = row.get("english", "").strip()
    st.session_state.current_id = row.get("id")
    st.session_state.selected = [] 
    st.session_state.used_indices = []
    st.session_state.quiz_complete = False
    st.session_state.quiz_saved = False
    
    # 💡 [新規] 現在の問題タイプをセッションに保存
    st.session_state.quiz_type_current = quiz_type

    if quiz_type == 'shuffling':
        english_sentence = st.session_state.current_correct
        
        shuffled_words, correct_tokens = generate_shuffling_data(english_sentence, proper_nouns)
        
        st.session_state.shuffled = shuffled_words
        st.session_state.correct_tokens = correct_tokens 

    elif quiz_type == 'multiple':
        # 択一問題用の初期化
        options_raw = row.get("word_options", "")
        if isinstance(options_raw, str):
            # 択一問題の正解は current_correct ではなく correct_answer を使用する
            st.session_state.mc_options = [opt.strip() for opt in options_raw.split(',')]
            
            # 💡 [追加] 択一問題の選択肢がない場合に表示
            if not st.session_state.mc_options:
                st.session_state.mc_options = ["No options to select."] 
                
        else:
            st.session_state.mc_options = ["No options to select."]
            
        st.session_state.mc_correct_answer = row.get("correct_answer", "").strip()
        st.session_state.multiple_choice_selection = None

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
    # (省略: 変更なし)
    st.subheader("🎉 クイズセット完了！")
    
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
        
        # 💡 削除するキーに id 関連を追加
        for key in ['index', 'current_correct', 'current_id', 'shuffled', 'selected', 'used_indices', 'quiz_complete', 'quiz_saved', 'correct_count', 'total_questions', 'loaded_csv_name', 'quiz_type', 'mc_options', 'mc_correct_answer', 'multiple_choice_selection', 'correct_tokens']:
            st.session_state.pop(key, None)
            
        st.session_state.app_mode = 'selection'
        st.rerun()

# ==========================================
# 🔹 1. 問題セット選択ページ (インデックス計算・完全永続化版)
# ==========================================
def show_selection_page():
    col_head, col_voca = st.columns([3, 1])
    with col_head:
        st.markdown("## 📚 問題セット選択 <small>(左から順に項目を選択)</small>", unsafe_allow_html=True)
    with col_voca:
        st.link_button("📖 VocaBooster", VOCABOOSTER_URL, use_container_width=True)

    df_select = load_selection_data()
    st.session_state.df_select = df_select

    if df_select.empty:
        st.error("問題セットの選択リストが空です。")
        return
    if 'grade' not in df_select.columns or 'lesson' not in df_select.columns or 'type' not in df_select.columns:
        st.error("⚠️ エラー: CSVに 'grade', 'lesson', または 'type' 列が見つかりません。")
        return

    # -------------------------------------------------------
    # 💾 1. 「保存用変数（金庫）」の初期化
    # -------------------------------------------------------
    if "saved_grade" not in st.session_state:
        st.session_state.saved_grade = None
    if "saved_lesson" not in st.session_state:
        st.session_state.saved_lesson = None
    if "saved_instruction" not in st.session_state:
        st.session_state.saved_instruction = None

    # -------------------------------------------------------
    # ⚡ 2. コールバック関数
    # -------------------------------------------------------
    def on_grade_change():
        st.session_state.saved_grade = st.session_state.dd_grade
        st.session_state.saved_lesson = None
        st.session_state.dd_lesson = None
        st.session_state.saved_instruction = None
        st.session_state.dd_set_instruction = None

    def on_lesson_change():
        st.session_state.saved_lesson = st.session_state.dd_lesson
        st.session_state.saved_instruction = None
        st.session_state.dd_set_instruction = None

    def on_instruction_change():
        st.session_state.saved_instruction = st.session_state.dd_set_instruction

    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns([2, 2, 3, 4])
    
    # Col 1: 学年選択 (省略: 変更なし)
    with col1:
        st.subheader("① 学年")
        grade_options = ['中2', '中3'] 
        grade_index = None
        if st.session_state.saved_grade in grade_options:
            grade_index = grade_options.index(st.session_state.saved_grade)

        st.radio(
            "学年を選択",
            options=grade_options,
            key="dd_grade",
            index=grade_index,
            on_change=on_grade_change
        )
    
    # Col 2: Lesson選択 (省略: 変更なし)
    with col2:
        st.subheader("② Lesson")
        current_grade = st.session_state.saved_grade
        
        if current_grade:
            df_grade = df_select[df_select['grade'] == current_grade]
            lesson_options = sorted(df_grade['lesson'].unique().tolist())
            
            lesson_index = None
            if st.session_state.saved_lesson in lesson_options:
                lesson_index = lesson_options.index(st.session_state.saved_lesson)
            
            st.radio(
                "Lessonを選択",
                options=lesson_options,
                key="dd_lesson",
                index=lesson_index,
                on_change=on_lesson_change
            )
        else:
            st.info("👈 学年を選択してください")
            
    # Col 3: 問題セット選択 (省略: 変更なし)
    csv_name = None
    quiz_type = None 

    with col3:
        st.subheader("③ 問題")
        current_lesson = st.session_state.saved_lesson
        
        if current_grade and current_lesson:
            df_target = df_select[
                (df_select['grade'] == current_grade) & 
                (df_select['lesson'] == current_lesson)
            ]
            
            if not df_target.empty:
                instruction_options = df_target['instruction'].tolist()
                
                instr_index = None
                if st.session_state.saved_instruction in instruction_options:
                    instr_index = instruction_options.index(st.session_state.saved_instruction)

                st.radio(
                    "問題セットを選択",
                    options=instruction_options,
                    key="dd_set_instruction",
                    index=instr_index,
                    on_change=on_instruction_change
                )
                
                if st.session_state.saved_instruction:
                    selected_row = df_target[df_target['instruction'] == st.session_state.saved_instruction]
                    if not selected_row.empty:
                        csv_name = selected_row.iloc[0]['csv_name']
                        quiz_type = selected_row.iloc[0]['type'] 
            else:
                st.warning("該当する問題がありません")
        elif current_grade:
            st.info("👈 Lessonを選択してください")


    # ==========================================
    # 🟢 Col 4: ボタン配置
    # ==========================================
    with col4:
        if csv_name:
            st.markdown(f"**選択中:** > `{st.session_state.saved_grade}` > `{st.session_state.saved_lesson}` > `{st.session_state.saved_instruction}`")
            st.caption(f"形式: **{quiz_type.upper()}**") 
            
            st.markdown("---")
            
            # --- 開始ボタン ---
            if st.button("開始 ▶", key="start_quiz_new", type="primary", use_container_width=True):
                st.session_state.selected_lesson = st.session_state.saved_lesson
                st.session_state.grade = st.session_state.saved_grade
                st.session_state.selected_csv = csv_name
                st.session_state.quiz_type = quiz_type 
                
                st.session_state.app_mode = 'quiz'
                st.session_state.pop('index', None)
                st.session_state.correct_count = 0
                st.rerun()
            
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

            # --- 復習ボタン ---
            # 💡 択一も復習可能にするために quiz_type のチェックを削除
            if st.button("復習 ↺", key="review_quiz_new", type="secondary", use_container_width=True):
                # 💡 選択されたCSVに関連する不正解データをロード
                review_df = load_review_data(st.session_state.user_id, target_quiz_set=csv_name)
                
                if review_df.empty:
                    st.toast("🎉 このセットに復習すべき問題はありません！", icon="✅")
                else:
                    # 💡 削除するキーに id 関連を追加
                    for key in ['index', 'current_correct', 'current_id', 'shuffled', 'selected', 'used_indices', 'quiz_complete', 'quiz_saved', 'correct_count', 'total_questions', 'loaded_csv_name', 'mc_options', 'mc_correct_answer', 'multiple_choice_selection']:
                        st.session_state.pop(key, None)
                        
                    st.session_state.app_mode = 'review_quiz'
                    st.session_state.review_df = review_df
                    st.session_state.selected_csv = "復習モード" # 特殊なCSV名を設定
                    # 💡 復習モードでは、問題を解くたびに quiz_type を設定し直す
                    st.rerun()
        else:
            if current_grade and current_lesson:
                st.info("👈 問題を選択してください")

    st.markdown("---")

# ==========================================
# 🔹 2. クイズ実行ページ
# ==========================================
def show_quiz_page(df: pd.DataFrame, proper_nouns: List[str]):
    
    total_questions = len(df)
    current_index = st.session_state.index % total_questions
    row = df.iloc[current_index]
    quiz_type = st.session_state.get('quiz_type_current', 'shuffling')
    japanese = row["japanese"]
    id = row["id"]
    current_quiz_set = st.session_state.selected_csv
    # 💡 復習モードの場合、quiz_typeを上書きする
    if st.session_state.app_mode == 'review_quiz':
        quiz_type = row.get('quiz_type_review', 'shuffling')
    else:
        quiz_type = st.session_state.quiz_type
    
    # 💡問題特定に必要な情報を取得
    japanese = row["japanese"]
    id = row["id"]
    current_quiz_set = st.session_state.selected_csv
    
    current_correct = st.session_state.current_correct # init_session_stateで設定済み

    st.info(f"**問題 {current_index + 1}**: {japanese}")

    # ----------------------------------------------------
    # 1. 回答エリアと選択肢エリアの分岐
    # ----------------------------------------------------
    if quiz_type == 'shuffling':
        # (省略: 並べかえロジックは変更なし)
        # ... 1-A. 並べかえ：あなたの回答エリア ...
        if len(st.session_state.used_indices) >= 2 and st.session_state.used_indices[-1] == st.session_state.used_indices[-2]:
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
        
        # ... 1-B. 並べかえ：選択肢エリア ...
        shuffled_container = st.container()
        with shuffled_container:
            num_words = len(st.session_state.shuffled)
            max_cols = min(num_words, 8) 
            cols = st.columns([1] * max_cols)

            for i, word in enumerate(st.session_state.shuffled):
                is_picked = i in st.session_state.used_indices
                label = word 
                # 💡 復習モードかどうかでキーを調整
                key_prefix = "review" if st.session_state.app_mode == 'review_quiz' else "quiz"
                button_key = f"word_{key_prefix}_{st.session_state.index}_{i}"
                col_index = i % max_cols

                # 修正: ifブロックを削除し、buttonの呼び出しを直接行う
                cols[col_index].button(
                    label, 
                    key=button_key, 
                    disabled=is_picked, 
                    use_container_width=True,
                    on_click=handle_word_click,
                    args=(i, word)
                )

    elif quiz_type == 'multiple':
        # ... 1-C. 択一：ボタンの表示 (ラジオボタンから置き換え)
        st.subheader(row.get('english', '英文が設定されていません')) 
        
        # 💡 init_session_stateでロードされた選択肢データを使用
        options_to_display = st.session_state.get('mc_options', ["Error: No options loaded"])

        # 💡 [描画] 列数を8に固定し、横並びボタンを表示
        num_cols = 6 
        cols = st.columns(num_cols) 
        
        # ボタンが押されたときのコールバック関数
        def select_option(val):
            st.session_state.multiple_choice_selection = val

        for i, option in enumerate(options_to_display):
            
            # 現在選択されているオプションであればハイライトする
            is_selected = (option == st.session_state.get('multiple_choice_selection'))
            
            # 判定済み、または現在選択されている場合は disabled にする
            # st.session_state.quiz_complete は判定ボタン押下後に True になる
            is_disabled = st.session_state.quiz_complete or is_selected
            
            button_type = "primary" if is_selected else "secondary"
            
            # 現在のインデックスを列数(8)で割った余りが、ボタンを配置する列のインデックスになる
            col_index = i % num_cols 
            
            # 💡 8列のコンテナを循環して使用
            with cols[col_index]:
                label = f"{option}" 
                
                # キーを現在の問題 index に紐づけることで、問題が変わるとリセットされる
                button_key = f"mc_option_{st.session_state.index}_{i}" 

                if st.button(
                    label,
                    key=button_key, 
                    type=button_type,
                    use_container_width=True,
                    disabled=is_disabled,
                    on_click=select_option,
                    args=(option,)
                ):
                    pass
        
        st.markdown("---")
    # ----------------------------------------------------
    # 2. コントロールボタン (判定/リセット/次へ)
    # ----------------------------------------------------

    col_undo, col_ok, col_next = st.columns([1, 1, 1])

    if quiz_type == 'shuffling':
        # 修正: ifブロックを削除し、buttonの呼び出しを直接行う
        col_undo.button(
            "↩️ １語消去", 
            on_click=undo_selection, 
            disabled=not st.session_state.selected, 
            use_container_width=True
        )
    elif quiz_type == 'multiple':
        col_undo.markdown("")

    # ----------------------------------------------------
    # 3. 判定ロジックの分岐
    # ----------------------------------------------------
    is_ready_to_check = False
    
    if quiz_type == 'shuffling':
        if len(st.session_state.selected) == len(st.session_state.shuffled):
            is_ready_to_check = True
            
            user_answer_raw = " ".join(st.session_state.selected)
            user_answer_cleaned = re.sub(r'\s+([\.\?!])$', r'\1', user_answer_raw)
            if user_answer_cleaned and user_answer_cleaned[0].islower():
                user_answer_final = user_answer_cleaned[0].upper() + user_answer_cleaned[1:]
            else:
                user_answer_final = user_answer_cleaned
                
            is_correct = (user_answer_final == current_correct)

            
    elif quiz_type == 'multiple':
        if st.session_state.get('multiple_choice_selection') is not None:
            is_ready_to_check = True
            user_answer_final = st.session_state.multiple_choice_selection
            correct_answer = st.session_state.mc_correct_answer
            is_correct = (user_answer_final == correct_answer)
            current_correct = correct_answer # 正解表示用に更新
            
            
    if is_ready_to_check:
        st.session_state.quiz_complete = True
        
        # 判定後の処理 (保存とカウント)
        if is_correct and not st.session_state.quiz_saved:
            st.session_state.correct_count += 1



        if not st.session_state.quiz_saved:
            # 💡 id と current_quiz_set を渡して保存
            save_quiz_result(int(id), current_quiz_set, user_answer_final, is_correct, quiz_type)
            st.session_state.quiz_saved = True

        if is_correct:
            col_ok.success("✅ 正解！")
            st.balloons()
        else:
            col_ok.error("❌ 不正解。")
        st.markdown(
            f"**正解の英文/語句:** <span style='font-size: 24px; font-weight: bold; color: #ef4444;'>{current_correct}</span>", 
            unsafe_allow_html=True
        )

        total_questions = len(df)
        current_index = st.session_state.index % total_questions
        is_last_question = (current_index + 1 >= total_questions)

        next_button_label = "結果を確認 ✅" if is_last_question else "次の問題へ ▶"
        next_button_type = "secondary" if is_last_question else "primary"

        col_next.button( # if を削除
            next_button_label, 
            type=next_button_type, 
            use_container_width=True, 
            on_click=next_question, 
            args=(df, proper_nouns)
        )
            
    else:
        # 準備ができていない場合、リセットボタンを表示
        if col_next.button("🔄 リセット(すべてクリア)", on_click=reset_question, args=(df, proper_nouns), use_container_width=True):
            st.rerun()

    current_index = st.session_state.index % len(df)
    total_questions = len(df)

    progress_ratio = (current_index + 1) / total_questions
    st.progress(progress_ratio, text=f"**進捗: {current_index + 1} / {total_questions} 問**")

def quiz_main():
    st.markdown("""
    <style>
    /* ==========================================
       Streamlit 標準の primary ボタン（水色）
       ========================================== */
    .stButton button[data-testid="baseButton-primary"] {
        background-color: #38bdf8;
        color: #164e63;
        border: none;
        transition: background-color 0.1s;
    }
    .stButton button[data-testid="baseButton-primary"]:hover {
        background-color: #0ea5e9;
    }
 
    /* Dark Mode */
    .stApp.stApp.stApp > div > section > div > button[data-testid="baseButton-primary"] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: none !important;
    }
    .stApp.stApp.stApp > div > section > div > button[data-testid="baseButton-primary"]:hover {
        background-color: #0284c7 !important;
    }
 
    /* ==========================================
       VocaBooster リンクボタン
       ブランドカラー（山吹 #ffcc00 → #ff9900）に合わせた立体ボタン
       ========================================== */
    .stLinkButton a,
    a[data-testid="stBaseLinkButton-secondary"],
    a[data-testid="baseLinkButton-secondary"],
    a[data-testid^="stBaseLinkButton"],
    a[data-testid^="baseLinkButton"] {
        background: linear-gradient(180deg, #ffd94d 0%, #ffcc00 45%, #ff9900 100%) !important;
        color: #5c3d00 !important;
        border: 2px solid #e68a00 !important;
        min-height: 60px !important;
        padding: 18px 12px !important;
        border-radius: 14px !important;
        box-shadow: 0 4px 0 #d97706, 0 7px 14px rgba(217, 119, 6, 0.28) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-decoration: none !important;
        letter-spacing: 0.02em !important;
        transition: transform 0.1s ease, box-shadow 0.1s ease, background 0.15s ease !important;
    }
 
    /* Streamlit はラベルを内側の p に入れるため、そちらにもサイズ指定が必要 */
    .stLinkButton a p,
    .stLinkButton a div,
    .stLinkButton a span,
    a[data-testid^="stBaseLinkButton"] p,
    a[data-testid^="baseLinkButton"] p {
        font-size: 22px !important;
        font-weight: 800 !important;
        color: #5c3d00 !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.25 !important;
        white-space: nowrap !important;
    }
 
    /* ホバー：少し沈ませる */
    .stLinkButton a:hover,
    a[data-testid^="stBaseLinkButton"]:hover,
    a[data-testid^="baseLinkButton"]:hover {
        background: linear-gradient(180deg, #ffcc00 0%, #ffb300 45%, #f57c00 100%) !important;
        color: #4a3000 !important;
        transform: translateY(2px) !important;
        box-shadow: 0 2px 0 #d97706, 0 4px 8px rgba(217, 119, 6, 0.25) !important;
    }
 
    /* クリック中：完全に沈む */
    .stLinkButton a:active,
    a[data-testid^="stBaseLinkButton"]:active,
    a[data-testid^="baseLinkButton"]:active {
        transform: translateY(4px) !important;
        box-shadow: 0 0 0 #d97706 !important;
    }
 
    /* キーボード操作時のフォーカスリング */
    .stLinkButton a:focus-visible,
    a[data-testid^="stBaseLinkButton"]:focus-visible {
        outline: 3px solid #1e40af !important;
        outline-offset: 3px !important;
    }
 
    /* ダークモードでも黄色地＋濃茶文字を維持 */
    @media (prefers-color-scheme: dark) {
        .stLinkButton a,
        a[data-testid^="stBaseLinkButton"],
        a[data-testid^="baseLinkButton"] {
            background: linear-gradient(180deg, #ffd94d 0%, #ffc400 45%, #ff9000 100%) !important;
            color: #4a3000 !important;
            border-color: #b45309 !important;
        }
        .stLinkButton a p,
        a[data-testid^="stBaseLinkButton"] p {
            color: #4a3000 !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    if st.session_state.app_mode == 'selection':
        show_selection_page()

    elif st.session_state.app_mode == 'quiz' or st.session_state.app_mode == 'review_quiz':
        
        # 💡 quiz_type の初期値設定
        if st.session_state.app_mode == 'review_quiz':
            if 'review_df' not in st.session_state or st.session_state.review_df.empty:
                st.error("復習データが見つからないか、空です。")
                st.session_state.app_mode = 'selection'
                st.rerun()
                return
            
            df = st.session_state.review_df
            proper_nouns = load_proper_nouns()
            header_text = "🔄 不正解問題に再挑戦"
            # 💡 復習モードでは、問題ごとの quiz_type_review を使用するため、ここでは特に設定しない

        else:
            quiz_type = st.session_state.get('quiz_type', 'shuffling') 
            header_text = f"📝 {quiz_type.upper()} 問題に挑戦" 
            
            if st.session_state.selected_csv is None:
                st.session_state.app_mode = 'selection'
                st.rerun()
                return
                
            # 💡 load_quiz_data を使用してCSVファイルをロード
            df = load_quiz_data(st.session_state.selected_csv)
            proper_nouns = load_proper_nouns()

        if df.empty:
            st.error("問題データが空です。問題セット選択ページに戻ります。")
            st.session_state.app_mode = 'selection'
            st.rerun()
            return

        col_title_top, col_button_top = st.columns([4, 1])

        with col_title_top:
            st.subheader(header_text)
            
        with col_button_top:
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True) 
            if st.button("⬅️ 選択に戻る", key="back_to_selection_main", use_container_width=True):
                st.session_state.app_mode = 'selection'
                # 💡 削除するキーに id 関連を追加
                for key in ['index', 'current_correct', 'current_id', 'shuffled', 'selected', 'used_indices', 'quiz_complete', 'quiz_saved', 'loaded_csv_name', 'quiz_type', 'mc_options', 'mc_correct_answer', 'multiple_choice_selection', 'correct_tokens', 'review_df']:
                    st.session_state.pop(key, None)
                st.rerun()
                return

        
        # 💡 ロードされたCSV名が変更されたか、問題のタイプが変わった、または復習モードに移行した場合は初期化
        is_review_mode_changed = st.session_state.app_mode == 'review_quiz' and st.session_state.selected_csv != st.session_state.get('loaded_csv_name')
        
        if st.session_state.selected_csv != st.session_state.get('loaded_csv_name') or "shuffled" not in st.session_state or is_review_mode_changed:
            st.session_state.index = 0
            init_session_state(df, proper_nouns)
            st.session_state.loaded_csv_name = st.session_state.selected_csv
            st.session_state.quiz_type_loaded = st.session_state.get('quiz_type', 'shuffling') 

            st.session_state.correct_count = 0
            st.session_state.total_questions = len(df) 
            

        show_quiz_page(df, proper_nouns)

    elif st.session_state.app_mode == 'quiz_result':
        show_result_page()
        
    st.markdown("---")
    
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

    # セッション初期化 (💡 id 関連を追加)
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
        "current_id": None, # 💡 新規追加
        "shuffled": [],
        "selected": [], 
        "used_indices": [],
        "quiz_complete": False,
        "quiz_saved": False,
        "correct_count": 0,
        "total_questions": 0,
        "duplicate_error": False,
        
        "quiz_type": 'shuffling', 
        "quiz_type_loaded": 'shuffling', 
        "mc_options": [],
        "mc_correct_answer": "",
        "multiple_choice_selection": None,
        "correct_tokens": [],
        "df_select": None, 
        "review_df": pd.DataFrame(), # 💡 新規追加
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    db = init_firestore()

    # (省略: ログインページのロジック)
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