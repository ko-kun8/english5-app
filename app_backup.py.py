# ==========================================
# Project Adventure
# Version 2.0
# Development Build
# ==========================================

import csv
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
import requests
import streamlit as st

# ============================================================
# ファイルの場所
# ============================================================
APP_DIR = Path(__file__).parent
CSV_FILE = APP_DIR / "words.csv"
HISTORY_FILE = APP_DIR / "learning_history.json"
PLAYER_DATA_FILE = APP_DIR / "player_data.json"


# ============================================================
# 単語データの読み込み（words.csv）
# ============================================================
def looks_english(text: str) -> bool:
    """英単語らしい文字列かどうかを判定する。"""
    return bool(re.match(r"^[A-Za-z][A-Za-z\s'\-]*$", text.strip()))


def looks_japanese(text: str) -> bool:
    """日本語らしい文字列かどうかを判定する。"""
    return any("\u3040" <= char <= "\u9fff" for char in text)


def normalize_column_name(name: str) -> str:
    """BOM や空白を除去して列名を正規化する。"""
    return name.strip().lstrip("\ufeff").lower()


def load_words():
    """words.csv から単語・熟語・文法を読み込む。"""
    if not CSV_FILE.exists():
        return None

    rows = []
    with CSV_FILE.open(encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            return None

        column_map = {
            normalize_column_name(name): name for name in reader.fieldnames
        }

        # 新しい形式: type, english, japanese
        type_key = column_map.get("type")
        english_key = column_map.get("english")
        japanese_key = column_map.get("japanese")

        if type_key and english_key and japanese_key:
            for row in reader:
                english = str(row.get(english_key) or "").strip()
                japanese = str(row.get(japanese_key) or "").strip()
                item_type = normalize_column_name(str(row.get(type_key) or "")).strip().lower()
                if english and japanese:
                    if item_type not in {"word", "phrase", "grammar"}:
                        item_type = "word"
                    rows.append({"type": item_type, "english": english, "japanese": japanese})
        else:
            # 旧形式の CSV でも読み込めるようにしておく
            english_key = column_map.get("english")
            japanese_key = column_map.get("japanese")
            if not english_key or not japanese_key:
                return None

            for row in reader:
                english = str(row.get(english_key) or "").strip()
                japanese = str(row.get(japanese_key) or "").strip()
                if english and japanese:
                    rows.append({"type": "word", "english": english, "japanese": japanese})

    if not rows:
        return None

    # 旧形式の CSV では列が逆になっていることがあるため、必要なら直す
    sample = rows[0]
    if looks_japanese(sample["english"]) and looks_english(sample["japanese"]):
        for row in rows:
            row["english"], row["japanese"] = row["japanese"], row["english"]

    words = {
        row["english"]: {"type": row["type"], "japanese": row["japanese"]}
        for row in rows
        if row.get("english") and row.get("japanese")
    }
    return words if words else None


# ============================================================
# 学習履歴の保存 / 読み込み
# ============================================================
WEAK_WORD_WEIGHT = 3.0
SRS_WRONG_WEIGHT = 0.75
LEARNED_WORD_WEIGHT = 0.5


def default_history():
    return {
        "learned_words": [],
        "not_learned_words": [],
        "quiz_correct": 0,
        "quiz_total": 0,
        "last_studied": None,
        "word_stats": {},
        "study_today_questions": 0,
        "study_today_date": None,
        "study_dates": [],
        "study_play_count": 0,
    }

# ============================================================
# Player Data
# ============================================================
def default_player_data():
    return {
        "level": 1,
        "exp": 0,
        "coin": 0,
    "login_days": 0,
    "streak": 0,
    "mission_word": 0,
    "mission_quiz": 0,
    "mission_completed": False
  }


def load_player_data():
    """player_data.json からプレイヤーデータを読み込む。存在しない場合は初期値を生成。"""
    default = default_player_data()
    
    if not PLAYER_DATA_FILE.exists():
        return default

    try:
        with PLAYER_DATA_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
            # 必要なキーが欠けている場合のためにデフォルトで補完
            for key, value in default.items():
                if key not in data:
                    data[key] = value
            return data
    except (json.JSONDecodeError, OSError):
        return default


def save_player_data():
    with PLAYER_DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(st.session_state.player_data, f, ensure_ascii=False, indent=2)


def add_player_exp_and_coin(exp_gain: int, coin_gain: int):
    """プレイヤーにEXPとコインを加算し、レベルアップ判定を行う。"""
    player = st.session_state.player_data
    
    player["exp"] = player.get("exp", 0) + exp_gain
    player["coin"] = player.get("coin", 0) + coin_gain
    
    leveled_up = False
    while player.get("exp", 0) >= 100:
        player["level"] = player.get("level", 1) + 1
        player["exp"] -= 100
        leveled_up = True
        
    if leveled_up:
        st.session_state.level_up_pending = player["level"]
        
    save_player_data()


def check_mission_completion():
    """今日のミッションが達成されたかチェックし、報酬を加算する。"""
    player = st.session_state.player_data
    m_word = player.get("mission_word", 0)
    m_quiz = player.get("mission_quiz", 0)
    
    if m_word >= 5 and m_quiz >= 5:
        if not player.get("mission_completed", False):
            player["mission_completed"] = True
            player["coin"] = player.get("coin", 0) + 30
            st.session_state.mission_just_completed = True
            save_player_data()

def load_history():
    if not HISTORY_FILE.exists():
        return default_history()

    try:
        with HISTORY_FILE.open(encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_history()

    base = default_history()
    base["learned_words"] = list(data.get("learned_words", []))
    base["not_learned_words"] = list(data.get("not_learned_words", []))
    base["quiz_correct"] = int(data.get("quiz_correct", 0))
    base["quiz_total"] = int(data.get("quiz_total", 0))
    base["last_studied"] = data.get("last_studied")
    base["word_stats"] = dict(data.get("word_stats", {}))
    base["study_today_questions"] = int(data.get("study_today_questions", 0))
    base["study_today_date"] = data.get("study_today_date")
    base["study_dates"] = list(data.get("study_dates", []))
    base["study_play_count"] = int(data.get("study_play_count", 0))
    return base


def save_history():
    history = {
        "learned_words": sorted(st.session_state.learned_words),
        "not_learned_words": sorted(st.session_state.not_learned_words),
        "quiz_correct": st.session_state.quiz_correct,
        "quiz_total": st.session_state.quiz_total,
        "last_studied": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "word_stats": st.session_state.word_stats,
        "study_today_questions": st.session_state.study_today_questions,
        "study_today_date": st.session_state.study_today_date,
        "study_dates": st.session_state.study_dates,
        "study_play_count": st.session_state.study_play_count,
    }
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


def persist_state():
    save_history()


# ============================================================
# ページの基本設定
# ============================================================
st.set_page_config(
    page_title="英検5級 単語帳",
    page_icon="📚",
    layout="centered",
)


# ============================================================
# かわいいデザイン（CSS）
# ============================================================
st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(
                160deg,
                #fff0f5 0%,
                #f0f8ff 45%,
                #f5fff0 100%
            );
        }

        h1 {
            color: #ff6b9d !important;
            text-align: center;
            font-weight: 800 !important;
        }

        .subtitle {
            text-align: center;
            color: #666;
            font-size: 1.1rem;
            margin-bottom: 0.5rem;
        }

        .stats-row {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            justify-content: center;
            margin: 0.75rem 0 1.5rem 0;
        }

        .stat-chip {
            background: white;
            border: 3px solid #ffd1dc;
            border-radius: 999px;
            padding: 0.45rem 1rem;
            font-size: 1rem;
            font-weight: 700;
            color: #555;
            box-shadow: 0 4px 12px rgba(255, 107, 157, 0.12);
        }

        .word-card {
            background: white;
            border: 4px solid #ffb6c1;
            border-radius: 28px;
            padding: 2rem 1.5rem;
            text-align: center;
            box-shadow: 0 8px 24px rgba(255, 107, 157, 0.15);
            margin: 1rem 0;
        }

        .word-card .label {
            color: #888;
            font-size: 1rem;
            margin-bottom: 0.5rem;
        }

        .word-card .english-word {
            color: #4a90d9;
            font-size: 3.5rem;
            font-weight: 800;
            letter-spacing: 2px;
        }

        .meaning-box {
            background: #e8fff0;
            border: 3px dashed #7dd87d;
            border-radius: 20px;
            padding: 1.2rem;
            text-align: center;
            font-size: 1.6rem;
            color: #2d8a2d;
            margin: 1rem 0;
        }

        .hint-box {
            background: #fff8e7;
            border: 3px dashed #ffc966;
            border-radius: 20px;
            padding: 1rem;
            text-align: center;
            font-size: 1.1rem;
            color: #b8860b;
            margin: 1rem 0;
        }

        .record-card {
            background: linear-gradient(135deg, #ffffff, #fff7fb);
            border: 3px solid #ffb6c1;
            border-radius: 24px;
            padding: 1rem 1.2rem;
            margin: 1rem 0 1.4rem 0;
            box-shadow: 0 6px 18px rgba(255, 107, 157, 0.12);
        }

        .record-card .record-title {
            font-size: 1.15rem;
            font-weight: 800;
            color: #ff6b9d;
            margin-bottom: 0.6rem;
        }

        .record-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.6rem;
        }

        .record-item {
            background: white;
            border-radius: 16px;
            padding: 0.7rem;
            border: 2px solid #f5d0dc;
            text-align: center;
            font-size: 0.95rem;
            line-height: 1.35;
        }

        .record-item strong {
            display: block;
            color: #4a90d9;
            font-size: 1.05rem;
            margin-top: 0.2rem;
        }

        /* プレイヤー情報カード用スタイル */
        .player-card {
            background: white;
            border: 3px solid #ffd1dc;
            border-radius: 24px;
            padding: 1.2rem;
            margin-bottom: 1.2rem;
            box-shadow: 0 6px 18px rgba(255, 107, 157, 0.1);
            text-align: center;
        }

        .player-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.5rem;
            align-items: center;
        }

        .player-stat-box {
            padding: 0.5rem;
        }

        .player-stat-label {
            font-size: 0.85rem;
            color: #888;
            margin-bottom: 0.2rem;
        }

        .player-stat-value {
            font-size: 1.2rem;
            font-weight: 800;
            color: #555;
        }

        .quiz-result-correct {
            background: #e8fff0;
            border: 3px solid #7dd87d;
            border-radius: 20px;
            padding: 1rem;
            text-align: center;
            font-size: 1.3rem;
            color: #2d8a2d;
            margin: 1rem 0;
        }

        .quiz-result-wrong {
            background: #fff0f0;
            border: 3px solid #ff8fab;
            border-radius: 20px;
            padding: 1rem;
            text-align: center;
            font-size: 1.3rem;
            color: #d64545;
            margin: 1rem 0;
        }

        div.stButton > button {
            height: 5.5rem !important;
            min-height: 5.5rem !important;
            font-size: 1.5rem !important;
            font-weight: 800 !important;
            border-radius: 28px !important;
            border: 3px solid transparent !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
            transition: transform 0.15s ease !important;
        }

        div.stButton > button:hover {
            transform: scale(1.03);
        }

        div.stButton > button:active {
            transform: scale(0.98);
        }

        /* ミッションカード用スタイル */
        .mission-card {
            background: white;
            border: 3px solid #ffd1dc;
            border-radius: 24px;
            padding: 1.2rem;
            margin-bottom: 1.2rem;
            box-shadow: 0 6px 18px rgba(255, 107, 157, 0.1);
        }

        .mission-title {
            font-size: 1.2rem;
            font-weight: 800;
            color: #ff6b9d;
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .mission-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0;
            border-bottom: 1px dashed #ffd1dc;
        }

        .mission-item:last-child {
            border-bottom: none;
        }

        .mission-label {
            font-weight: 600;
            color: #555;
        }

        .mission-status {
            font-weight: 800;
            color: #4a90d9;
        }

        .mission-complete {
            color: #2d8a2d;
            font-weight: 800;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 単語データを読み込む
# ============================================================
if "words_data" not in st.session_state:
    st.session_state.words_data = load_words()

# グローバル的に利用
WORDS = st.session_state.words_data

if WORDS is None:
    st.title("📚 英検5級 単語帳")
    if not CSV_FILE.exists():
        st.warning(f"⚠️ **words.csv が見つかりません。**\n\n`{CSV_FILE}` に配置してください。")
    else:
        st.warning("⚠️ **words.csv に有効な単語がありません。**")
    st.stop()


# ============================================================
# セッション状態の初期化
# ============================================================
if "history_loaded" not in st.session_state:
    saved = load_history()
    st.session_state.learned_words = set(saved["learned_words"])
    st.session_state.not_learned_words = set(saved["not_learned_words"])
    st.session_state.quiz_correct = saved["quiz_correct"]
    st.session_state.quiz_total = saved["quiz_total"]
    st.session_state.word_stats = saved["word_stats"]
    st.session_state.study_today_questions = saved["study_today_questions"]
    st.session_state.study_today_date = saved["study_today_date"]
    st.session_state.study_dates = list(saved["study_dates"])
    st.session_state.study_play_count = saved["study_play_count"]
    st.session_state.history_loaded = True
    
    
# ============================================================
# Player Data
# ============================================================

def increment_mission_word():
    """単語カードのミッションカウントを増やす。"""
    player = st.session_state.player_data
    if player.get("mission_word", 0) < 5:
        player["mission_word"] = player.get("mission_word", 0) + 1
        save_player_data()


def increment_mission_quiz():
    """クイズのミッションカウントを増やす。"""
    player = st.session_state.player_data
    if player.get("mission_quiz", 0) < 5:
        player["mission_quiz"] = player.get("mission_quiz", 0) + 1
        save_player_data()
def increment_mission_word():
    """単語カードのミッションカウントを増やす。"""
    player = st.session_state.player_data
    if player.get("mission_word", 0) < 5:
        player["mission_word"] = player.get("mission_word", 0) + 1
        check_mission_completion()
        save_player_data()


def increment_mission_quiz():
    """クイズのミッションカウントを増やす。"""
    player = st.session_state.player_data
    if player.get("mission_quiz", 0) < 5:
        player["mission_quiz"] = player.get("mission_quiz", 0) + 1
        check_mission_completion()
        save_player_data()
if "player_data" not in st.session_state:
    st.session_state.player_data = load_player_data()    
if "elementary_mode" not in st.session_state:
    st.session_state.elementary_mode = False
if "current_word" not in st.session_state:
    st.session_state.current_word = None
if "show_meaning" not in st.session_state:
    st.session_state.show_meaning = False
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "単語カード"
if "study_mode" not in st.session_state:
    st.session_state.study_mode = "通常モード"
if "quiz_choices" not in st.session_state:
    st.session_state.quiz_choices = []
if "quiz_answered" not in st.session_state:
    st.session_state.quiz_answered = False
if "quiz_was_correct" not in st.session_state:
    st.session_state.quiz_was_correct = None
if "quiz_selected" not in st.session_state:
    st.session_state.quiz_selected = None
if "used_words" not in st.session_state:
    st.session_state.used_words = []
if "pending_balloons" not in st.session_state:
    st.session_state.pending_balloons = False
if "last_picked_word" not in st.session_state:
    st.session_state.last_picked_word = None
if "quiz_score" not in st.session_state:
    st.session_state.quiz_score = 0
if "quiz_combo" not in st.session_state:
    st.session_state.quiz_combo = 0
if "quiz_best_combo" not in st.session_state:
    st.session_state.quiz_best_combo = 0
if "quiz_lives" not in st.session_state:
    st.session_state.quiz_lives = 3
if "quiz_question_index" not in st.session_state:
    st.session_state.quiz_question_index = 0
if "quiz_correct_count" not in st.session_state:
    st.session_state.quiz_correct_count = 0
if "quiz_game_finished" not in st.session_state:
    st.session_state.quiz_game_finished = False
if "quiz_result_summary" not in st.session_state:
    st.session_state.quiz_result_summary = None
if "pending_snow" not in st.session_state:
    st.session_state.pending_snow = False
if "pending_audio" not in st.session_state:
    st.session_state.pending_audio = None  # "correct" or "wrong" or None
if "praise_message" not in st.session_state:
    st.session_state.praise_message = ""
if "study_today_questions" not in st.session_state:
    st.session_state.study_today_questions = 0
if "study_today_date" not in st.session_state:
    st.session_state.study_today_date = None
if "study_dates" not in st.session_state:
    st.session_state.study_dates = []
if "study_play_count" not in st.session_state:
    st.session_state.study_play_count = 0


# ============================================================
# 小学生モード（ひらがな対応）
# ============================================================
def to_hiragana(text: str) -> str:
    """漢字をひらがなに変換する。エラーにならないことを最優先とする。"""
    if not text:
        return ""
    try:
        from pykakasi import kakasi
        kks = kakasi()
        result = kks.convert(text)
        return "".join([item['hira'] for item in result])
    except Exception:
        return text


def format_elementary_text(text: str, force: bool = False) -> str:
    """
    小学生モード用のテキスト整形を行う。
    - 常用漢字（低学年向け）はそのまま。
    - それ以外の漢字には（ふりがな）を付ける。
    """
    if not force and (not st.session_state.get("elementary_mode") or not text):
        return text
    if force and not text:
        return text

    # そのまま表示する簡単な漢字リスト
    simple_kanji_words = [
        "今日", "学校", "先生", "時間", "名前", "日本", "友達", "問題", "正解", "単語"
    ]

    # pykakasiを使用して形態素解析的に処理
    try:
        from pykakasi import kakasi
        kks = kakasi()
        result = kks.convert(text)
        
        formatted_text = ""
        for item in result:
            orig = item['orig']
            hira = item['hira']
            
            # 漢字を含まない場合はそのまま
            if not any("\u4e00" <= char <= "\u9fff" for char in orig):
                formatted_text += orig
                continue
            
            # 簡単な漢字リストに含まれる場合はそのまま
            if any(word in orig for word in simple_kanji_words):
                formatted_text += orig
                continue
                
            # それ以外の漢字は 漢字（ひらがな）形式
            # すでにひらがなのみの場合はそのまま（pykakasiの挙動に依存）
            if orig == hira:
                formatted_text += orig
            else:
                formatted_text += f"{orig}({hira})"
                
        return formatted_text
    except Exception:
        # エラー時は安全のためにひらがな変換を試みるか、そのまま返す
        return to_hiragana(text)


# ============================================================
# ヘルパー関数
# ============================================================
def get_word_entry(word: str | None) -> dict | None:
    """指定した英語に対応するデータを返す。古い形式の辞書にも対応する。"""
    if not word:
        return None

    entry = WORDS.get(word)
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, str):
        return {"type": "word", "japanese": entry}
    return None


def get_display_label(word: str | None) -> str:
    """画面表示用に、単語・熟語・文法の見出しを返す。"""
    entry = get_word_entry(word)
    if not entry:
        return "英語"
    return {"word": "英単語", "phrase": "熟語", "grammar": "文法"}.get(entry.get("type", "word"), "英語")


def english_to_japanese(word: str) -> str:
    """指定した英語の日本語意味を返す。"""
    entry = get_word_entry(word)
    return entry.get("japanese", "") if entry else ""


def normalize_english_word(word: str | None) -> str | None:
    """英単語・熟語・文法の表示文を、内部キーに正規化する。"""
    if not word:
        return None
    if word in WORDS:
        return word
    for english, raw_entry in WORDS.items():
        entry = raw_entry if isinstance(raw_entry, dict) else {"type": "word", "japanese": raw_entry}
        if entry.get("japanese") == word:
            st.session_state.current_word = english
            return english
    return None


def sanitize_word_sets():
    """学習履歴に残っている単語を、今のデータに合わせて整える。"""
    valid_english = set(WORDS.keys())
    st.session_state.learned_words = {
        normalize_english_word(word) or word for word in st.session_state.learned_words
    } & valid_english
    st.session_state.not_learned_words = {
        normalize_english_word(word) or word for word in st.session_state.not_learned_words
    } & valid_english
    st.session_state.word_stats = {
        word: stats for word, stats in st.session_state.word_stats.items() if word in valid_english
    }
    st.session_state.used_words = [
        word for word in st.session_state.used_words if word in valid_english
    ]


def get_word_pool():
    if st.session_state.study_mode == "苦手復習モード":
        return [word for word in st.session_state.not_learned_words if word in WORDS]
    # 通常モードでは、苦手リスト（not_learned_words）に入っていない通常単語だけを出題対象とする
    return [word for word in WORDS.keys() if word not in st.session_state.not_learned_words]


def get_current_word() -> str | None:
    """現在の単語（正規化された英語キー）を検証・取得し、存在しない場合は新しく選ぶ。"""
    word_pool = get_word_pool()
    if not word_pool:
        st.session_state.current_word = None
        return None

    # 回答済みの場合は、現在の単語を絶対に維持する
    if st.session_state.get("quiz_answered"):
        return normalize_english_word(st.session_state.current_word)

    current = normalize_english_word(st.session_state.current_word)
    
    # すでに単語が選ばれているならそれを返す（ここで pick_random_word を呼ばない）
    if current:
        return current

    # まだ単語がない場合のみ新しく選ぶ
    pick_random_word()
    return normalize_english_word(st.session_state.current_word)


def get_word_stat(english: str) -> dict:
    stats = st.session_state.word_stats.setdefault(english, {"wrong": 0, "correct": 0})
    stats.setdefault("wrong", 0)
    stats.setdefault("correct", 0)
    return stats


def compute_word_weight(english: str) -> float:
    weight = 1.0
    if english in st.session_state.not_learned_words:
        weight *= WEAK_WORD_WEIGHT
    stats = get_word_stat(english)
    weight *= 1.0 + stats["wrong"] * SRS_WRONG_WEIGHT
    if english in st.session_state.learned_words:
        weight *= LEARNED_WORD_WEIGHT

    total = stats["correct"] + stats["wrong"]
    if total >= 3:
        accuracy = stats["correct"] / total
        if accuracy >= 0.8:
            weight *= 0.7
        elif accuracy <= 0.4:
            weight *= 1.4
    return max(weight, 0.1)


def get_available_words(word_pool: list[str], exclude: str | None = None) -> list[str]:
    used = set(st.session_state.used_words)
    available = [word for word in word_pool if word not in used]
    if not available:
        st.session_state.used_words = []
        available = list(word_pool)
    if exclude and len(available) > 1:
        available = [word for word in available if word != exclude]
    return available


def pick_weighted_word(candidates: list[str]) -> str:
    weights = [compute_word_weight(word) for word in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def mark_word_as_used(english: str):
    if english not in st.session_state.used_words:
        st.session_state.used_words.append(english)


def reset_quiz_state():
    st.session_state.quiz_answered = False
    st.session_state.quiz_was_correct = None
    st.session_state.quiz_selected = None
    st.session_state.quiz_choices = []
    st.session_state.pending_balloons = False
    st.session_state.pending_snow = False
    st.session_state.pending_audio = None
    st.session_state.praise_message = ""


def format_lives(lives: int) -> str:
    hearts = "❤️" * max(lives, 0)
    empty_hearts = "🤍" * max(3 - max(lives, 0), 0)
    return hearts + empty_hearts


def get_today_key() -> str:
    """今日の日付を YYYY-MM-DD 形式で返す。"""
    return datetime.now().strftime("%Y-%m-%d")


def record_study_activity():
    """今日の学習記録を増やして、学習日一覧を更新する。"""
    today = get_today_key()
    if st.session_state.study_today_date != today:
        st.session_state.study_today_date = today
        st.session_state.study_today_questions = 0
        # 日付が変わったらミッションもリセット
        st.session_state.player_data["mission_word"] = 0
        st.session_state.player_data["mission_quiz"] = 0
        st.session_state.player_data["mission_completed"] = False

    st.session_state.study_today_questions += 1
    if today not in st.session_state.study_dates:
        st.session_state.study_dates.append(today)
    persist_state()


def increment_mission_word():
    """単語カードのミッションカウントを増やす。"""
    player = st.session_state.player_data
    if player.get("mission_word", 0) < 5:
        player["mission_word"] = player.get("mission_word", 0) + 1
        save_player_data()


def increment_mission_quiz():
    """クイズのミッションカウントを増やす。"""
    player = st.session_state.player_data
    if player.get("mission_quiz", 0) < 5:
        player["mission_quiz"] = player.get("mission_quiz", 0) + 1
        save_player_data()


def get_learning_record_summary() -> dict:
    """ホーム画面に表示する学習記録の要約を作る。"""
    total_questions = int(st.session_state.quiz_total)
    correct = int(st.session_state.quiz_correct)
    wrong = max(total_questions - correct, 0)
    accuracy = round((correct / total_questions) * 100, 1) if total_questions else 0.0

    study_dates = sorted(set(st.session_state.study_dates))
    total_study_days = len(study_dates)

    streak = 0
    current_day = datetime.now().date()
    while True:
        key = current_day.strftime("%Y-%m-%d")
        if key in study_dates:
            streak += 1
            current_day = current_day.fromordinal(current_day.toordinal() - 1)
        else:
            break

    return {
        "today_questions": int(st.session_state.study_today_questions),
        "total_questions": total_questions,
        "correct": correct,
        "wrong": wrong,
        "accuracy": accuracy,
        "best_combo": int(st.session_state.quiz_best_combo),
        "total_study_days": total_study_days,
        "consecutive_study_days": streak,
        "play_count": int(st.session_state.study_play_count),
    }


def build_quiz_result_summary(score: int, correct_count: int, total_questions: int, best_combo: int) -> dict:
    accuracy = round((correct_count / total_questions) * 100, 1) if total_questions else 0.0
    return {
        "score": score,
        "correct_count": correct_count,
        "accuracy": accuracy,
        "best_combo": best_combo,
        "total_questions": total_questions,
    }


def should_finish_quiz_game(question_index: int, lives: int, max_questions: int = 10) -> bool:
    return question_index >= max_questions or lives <= 0


def reset_quiz_game_state():
    st.session_state.quiz_score = 0
    st.session_state.quiz_combo = 0
    st.session_state.quiz_best_combo = 0
    st.session_state.quiz_lives = 3
    st.session_state.quiz_question_index = 0
    st.session_state.quiz_correct_count = 0
    st.session_state.quiz_game_finished = False
    st.session_state.quiz_result_summary = None
    reset_quiz_state()


def start_new_quiz_game():
    reset_quiz_game_state()
    st.session_state.used_words = []
    st.session_state.study_play_count += 1
    persist_state()
    pick_random_word()


def mark_as_learned(word):
    english = normalize_english_word(word)
    if not english:
        return
    st.session_state.learned_words.add(english)
    st.session_state.not_learned_words.discard(english)
    persist_state()


def mark_as_not_learned(word):
    english = normalize_english_word(word)
    if not english:
        return
    st.session_state.not_learned_words.add(english)
    st.session_state.learned_words.discard(english)
    persist_state()


def add_word_to_weak_list(word):
    """間違えた単語を苦手リストに追加する。重複は防ぐ。"""
    english = normalize_english_word(word)
    if not english:
        return
    st.session_state.not_learned_words.add(english)
    st.session_state.learned_words.discard(english)
    persist_state()


def remove_word_from_weak_list(word):
    """苦手リストから単語を取り除く。"""
    english = normalize_english_word(word)
    if not english:
        return
    st.session_state.not_learned_words.discard(english)
    persist_state()


def ensure_current_word_for_mode():
    """現在のモードに応じて current_word を必ずセットする。"""
    get_current_word()


def pick_random_word():
    """現在のモードに合わせて、次に出す単語を選ぶ。"""
    # 回答済みの場合は新しい単語を選ばない
    if st.session_state.get("quiz_answered"):
        return False

    if "level_up_pending" in st.session_state:
        st.session_state.level_up_pending = None

    word_pool = get_word_pool()
    if not word_pool:
        st.session_state.current_word = None
        st.session_state.show_meaning = False
        reset_quiz_state()
        return False

    previous = normalize_english_word(st.session_state.last_picked_word)
    available = get_available_words(word_pool, exclude=previous)
    if not available:
        st.session_state.used_words = []
        available = get_available_words(word_pool, exclude=previous)
    if not available:
        available = list(word_pool)

    chosen = pick_weighted_word(available)
    st.session_state.current_word = chosen
    st.session_state.last_picked_word = chosen
    mark_word_as_used(chosen)
    st.session_state.show_meaning = False
    reset_quiz_state()
    setup_quiz_choices()
    return True


def get_word_category(english: str, japanese: str) -> str | None:
    """単語のカテゴリを推定する。"""
    categories = {
        "動物": ["dog", "cat", "bird", "fish", "rabbit", "horse", "cow", "pig", "monkey", "lion", "tiger", "elephant", "bear", "duck", "chicken", "sheep", "goat", "mouse", "frog", "pet", "犬", "猫", "鳥", "魚", "うさぎ", "馬", "牛", "豚", "猿", "ライオン", "トラ", "象", "くま", "アヒル", "にわとり", "羊", "ヤギ", "ねずみ", "カエル"],
        "色": ["red", "blue", "yellow", "green", "black", "white", "brown", "pink", "color", "赤", "青", "黄色", "緑", "黒", "白", "茶色", "ピンク", "色"],
        "数字": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "number", "番号"],
        "曜日": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "日曜日", "月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日"],
        "月": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
        "家族": ["father", "mother", "brother", "sister", "grandfather", "grandmother", "family", "baby", "parent", "cousin", "uncle", "aunt", "父", "母", "兄", "弟", "姉", "妹", "祖父", "祖母", "家族", "赤ちゃん", "親", "いとこ", "おじ", "おば"],
        "学校": ["teacher", "student", "class", "classroom", "school", "desk", "chair", "book", "notebook", "pen", "pencil", "eraser", "bag", "homework", "test", "blackboard", "page", "lesson", "先生", "生徒", "授業", "教室", "学校", "机", "いす", "本", "ノート", "ペン", "鉛筆", "消しゴム", "かばん", "宿題", "テスト", "黒板", "ページ"],
        "食べ物": ["apple", "banana", "orange", "grape", "peach", "melon", "lemon", "strawberry", "bread", "rice", "cake", "egg", "meat", "chicken", "fish", "breakfast", "lunch", "dinner", "sandwich", "salad", "soup", "ice cream", "cookie", "chocolate", "candy", "sugar", "salt", "vegetable", "fruit", "りんご", "バナナ", "オレンジ", "ぶどう", "もも", "メロン", "レモン", "いちご", "パン", "ご飯", "ケーキ", "卵", "肉", "鶏肉", "魚", "朝食", "昼食", "夕食", "サンドイッチ", "サラダ", "スープ", "アイスクリーム", "クッキー", "チョコレート", "あめ", "砂糖", "塩", "野菜", "果物"],
        "飲み物": ["milk", "water", "juice", "tea", "coffee", "牛乳", "水", "ジュース", "お茶", "コーヒー"],
        "体": ["head", "face", "eye", "ear", "nose", "mouth", "tooth", "neck", "shoulder", "arm", "hand", "finger", "leg", "foot", "toe", "hair", "body", "back", "heart", "頭", "顔", "目", "耳", "鼻", "口", "歯", "首", "肩", "腕", "手", "指", "脚", "足", "足の指", "髪", "体", "背中", "心臓"],
        "衣服": ["eyeglass", "shirt", "T-shirt", "coat", "jacket", "cap", "hat", "dress", "skirt", "pants", "shoe", "sock", "umbrella", "眼鏡", "シャツ", "Tシャツ", "コート", "上着", "帽子", "ドレス", "スカート", "ズボン", "靴", "靴下", "傘"],
        "場所": ["park", "library", "hospital", "station", "store", "shop", "restaurant", "hotel", "bank", "post office", "city", "town", "country", "house", "home", "room", "kitchen", "bathroom", "bedroom", "garden", "road", "street", "river", "lake", "sea", "mountain", "zoo", "airport", "supermarket", "bakery", "building", "公園", "図書館", "病院", "駅", "店", "レストラン", "ホテル", "銀行", "郵便局", "町", "市", "国", "家", "部屋", "台所", "浴室", "寝室", "庭", "道", "通り", "川", "湖", "海", "山", "動物園", "空港", "スーパー", "パン屋", "建物"],
        "スポーツ": ["soccer", "baseball", "tennis", "basketball", "volleyball", "game", "ball", "サッカー", "野球", "テニス", "バスケットボール", "バレーボール", "ゲーム", "ボール"],
        "形容詞": ["beautiful", "big", "small", "long", "short", "new", "old", "young", "fast", "slow", "easy", "difficult", "happy", "sad", "busy", "free", "strong", "weak", "clean", "dirty", "kind", "famous", "fine", "interesting", "fun", "careful", "ready", "same", "different", "美しい", "大きい", "小さい", "長い", "短い", "新しい", "古い", "若い", "速い", "遅い", "やさしい", "難しい", "幸せな", "悲しい", "忙しい", "暇な", "強い", "弱い", "きれいな", "汚れた", "親切な", "有名な", "元気な", "すばらしい", "面白い", "楽しい", "注意深い", "準備ができた", "同じ", "違う"],
        "副詞": ["always", "often", "sometimes", "never", "usually", "really", "very", "well", "now", "then", "soon", "together", "again", "too", "いつも", "よく", "ときどき", "決して", "たいてい", "本当に", "とても", "上手に", "今", "その時", "すぐに", "一緒に", "もう一度"],
        "熟語": ["a lot of", "be from", "get up", "go to bed", "go home", "go to school", "come from", "look at", "listen to", "talk to", "speak to", "wait for", "write to", "thank you for", "help with", "have breakfast", "have lunch", "have dinner", "take a picture", "have a good time", "see you tomorrow", "come in", "sit down", "stand up", "of course", "all right", "good job", "how much", "how many", "what time", "after school", "at home", "at school", "every day", "every week", "every month", "every year", "in the morning", "in the afternoon", "in the evening", "on Sunday", "next week", "last week", "this morning", "this afternoon", "this evening", "over there", "right now", "for example", "a little", "come here", "go away", "be careful", "hurry up", "of all", "in front of", "in the park", "on the desk", "under the table", "next to"]
    }
    
    eng_lower = english.lower()
    for cat, keywords in categories.items():
        if any(kw.lower() == eng_lower for kw in keywords) or any(kw in japanese for kw in keywords):
            return cat
    return None


def build_quiz_distractors(english: str, correct_japanese: str, count: int = 3) -> list[str]:
    """4択クイズ用に、正解と同じタイプの、意味の近い日本語選択肢を作る。"""
    entry_main = get_word_entry(english)
    target_type = entry_main.get("type", "word")
    target_category = get_word_category(english, correct_japanese)
    
    # 候補の収集
    same_type_same_cat = []
    same_type_other = []
    other_type = []
    
    for key, raw_entry in WORDS.items():
        if key == english:
            continue
            
        entry = raw_entry if isinstance(raw_entry, dict) else {"type": "word", "japanese": raw_entry}
        item_type = entry.get("type", "word")
        japanese = entry.get("japanese", "")
        
        if not japanese or japanese == correct_japanese:
            continue
            
        if item_type == target_type:
            item_category = get_word_category(key, japanese)
            if target_category and item_category == target_category:
                same_type_same_cat.append(japanese)
            else:
                same_type_other.append(japanese)
        else:
            other_type.append(japanese)

    # 重複を排除してシャッフル
    same_type_same_cat = list(dict.fromkeys(same_type_same_cat))
    same_type_other = list(dict.fromkeys(same_type_other))
    other_type = list(dict.fromkeys(other_type))
    random.shuffle(same_type_same_cat)
    random.shuffle(same_type_other)
    random.shuffle(other_type)
    
    # 選択肢の組み立て
    selected = []
    
    # 1. 同じタイプかつ同じカテゴリを優先
    for meaning in same_type_same_cat:
        if len(selected) < count:
            selected.append(meaning)
            
    # 2. 足りない場合は同じタイプから補充
    for meaning in same_type_other:
        if len(selected) < count:
            selected.append(meaning)
            
    # 3. それでも足りない場合は別のタイプから補充
    for meaning in other_type:
        if len(selected) < count:
            selected.append(meaning)
            
    return selected


def setup_quiz_choices():
    """現在の問題に合わせて、4択の選択肢を作る。"""
    english = normalize_english_word(st.session_state.current_word)
    if not english:
        st.session_state.quiz_choices = []
        return

    entry = get_word_entry(english)
    correct = entry.get("japanese", "") if entry else ""
    
    # 1. 仕様に基づいた誤選択肢を生成
    wrong_answers = build_quiz_distractors(english, correct, count=3)

    # 最終的な選択肢の統合（重複禁止・シャッフル）
    choices = list(dict.fromkeys([correct] + wrong_answers))
    
    # 4つに満たない場合（単語数が極端に少ない場合など）の補充
    if len(choices) < 4:
        for key, raw_entry in WORDS.items():
            e = raw_entry if isinstance(raw_entry, dict) else {"type": "word", "japanese": raw_entry}
            japanese = e.get("japanese", "")
            if japanese and japanese not in choices:
                choices.append(japanese)
            if len(choices) >= 4:
                break

    # テスト環境など、極端に単語が少ない場合にダミーを追加
    dummy_count = 1
    while len(choices) < 4:
        choices.append(f"ダミー選択肢{dummy_count}")
        dummy_count += 1
                
    random.shuffle(choices)
    st.session_state.quiz_choices = choices[:4]


def reload_words_from_csv():
    new_words = load_words()
    if new_words is None:
        return False
    st.session_state.words_data = new_words
    st.session_state.used_words = []
    sanitize_word_sets()
    pick_random_word()
    return True


def speak_word(word):
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={word}&tl=en"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            st.audio(response.content, format="audio/mp3")
        else:
            st.error("音声の取得に失敗しました")
    except Exception:
        st.error("通信エラーが発生しました")


def build_quiz_prompt_markup(english: str, elementary_mode: bool) -> str:
    """4択クイズ画面に英単語を表示するためのHTMLを返す。"""
    prompt_label = "📝 英単語"
    if elementary_mode:
        prompt_label = to_hiragana(prompt_label)
    return (
        f'<div class="word-card">'
        f'<div class="label">{prompt_label}</div>'
        f'<div class="english-word">{english}</div>'
        f'</div>'
    )


def quiz_accuracy_text():
    total = st.session_state.quiz_total
    correct = st.session_state.quiz_correct
    if total == 0:
        return "0.0"
    return f"{(correct / total) * 100:.1f}"


def record_quiz_answer(selected_japanese: str):
    english = normalize_english_word(st.session_state.current_word)
    if not english or st.session_state.quiz_answered or st.session_state.quiz_game_finished:
        return

    # 回答時の情報を即座に固定（再描画によるズレを防ぐ）
    st.session_state.quiz_answered = True
    st.session_state.quiz_selected = selected_japanese
    st.session_state.current_word = english # 確実に現在の英語をセット

    correct_japanese = english_to_japanese(english)
    is_correct = selected_japanese == correct_japanese
    stats = get_word_stat(english)

    st.session_state.quiz_was_correct = is_correct
    st.session_state.quiz_total += 1
    st.session_state.quiz_question_index += 1
    record_study_activity()
    increment_mission_quiz()

    if is_correct:
        st.session_state.quiz_correct += 1
        st.session_state.quiz_correct_count += 1
        st.session_state.quiz_score += 10
        st.session_state.quiz_combo += 1
        st.session_state.quiz_best_combo = max(st.session_state.quiz_best_combo, st.session_state.quiz_combo)
        stats["correct"] += 1
        st.session_state.pending_balloons = True
        st.session_state.pending_snow = True
        st.session_state.pending_audio = "correct"
        praise_messages = ["Great!", "Excellent!", "Amazing!", "Wonderful!", "Perfect!", "Awesome!", "Good job!", "Fantastic!"]
        st.session_state.praise_message = random.choice(praise_messages)
        remove_word_from_weak_list(english)
        mark_as_learned(english)
        add_player_exp_and_coin(5, 2)
    else:
        st.session_state.quiz_combo = 0
        st.session_state.quiz_lives -= 1
        stats["wrong"] += 1
        st.session_state.pending_audio = "wrong"
        st.session_state.pending_snow = False
        st.session_state.praise_message = ""
        add_word_to_weak_list(english)
        mark_as_not_learned(english)
        add_player_exp_and_coin(1, 0)

    persist_state()


def go_to_next_question():
    # 「▶ 次へ」が押されたタイミングで終了判定を行う
    if should_finish_quiz_game(st.session_state.quiz_question_index, st.session_state.quiz_lives):
        st.session_state.quiz_game_finished = True
        st.session_state.quiz_result_summary = build_quiz_result_summary(
            score=st.session_state.quiz_score,
            correct_count=st.session_state.quiz_correct_count,
            total_questions=st.session_state.quiz_question_index,
            best_combo=st.session_state.quiz_best_combo,
        )
        persist_state()
        return

    reset_quiz_state()
    if "level_up_pending" in st.session_state:
        st.session_state.level_up_pending = None
    pick_random_word()


# ============================================================
# 起動時のデータ整備とモード監視
# ============================================================
sanitize_word_sets()

if "previous_study_mode" not in st.session_state:
    st.session_state.previous_study_mode = st.session_state.study_mode
if "previous_app_mode" not in st.session_state:
    st.session_state.previous_app_mode = st.session_state.app_mode

# 出題モード（通常 / 苦手復習）が切り替わった場合
if st.session_state.previous_study_mode != st.session_state.study_mode:
    st.session_state.previous_study_mode = st.session_state.study_mode
    st.session_state.used_words = []
    st.session_state.current_word = None
    st.session_state.show_meaning = False
    reset_quiz_state()

# アプリのモード（単語カード / 4択クイズ）が切り替わった場合
if st.session_state.previous_app_mode != st.session_state.app_mode:
    st.session_state.previous_app_mode = st.session_state.app_mode
    st.session_state.show_meaning = False
    reset_quiz_state()

# 共通出題関数から現在の単語を保証・取得する
# pick_random_word() はこの中で必要な時だけ呼ばれる
current_english = get_current_word()


# ============================================================
# 画面の表示
# ============================================================
title_text = "📚 英検シリーズ 単語帳"
subtitle_text = "🌟 英単語・熟語・文法をまとめて学習しよう！ 🌟"
if st.session_state.elementary_mode:
    title_text = to_hiragana(title_text)
    subtitle_text = to_hiragana(subtitle_text)

st.title(title_text)
st.markdown(f'<p class="subtitle">{subtitle_text}</p>', unsafe_allow_html=True)

# ============================================================
# レベルアップ演出・ミッション完了通知
# ============================================================
if st.session_state.get("level_up_pending"):
    lv = st.session_state.level_up_pending
    st.success(f"🎉 LEVEL UP!\n\nLv.{lv}になった！")

if st.session_state.get("mission_just_completed"):
    st.toast("🎯 今日のミッションをすべてクリア！ 🪙+30 Coin ゲット！", icon="🎉")
    st.session_state.mission_just_completed = False

# ============================================================
# 今日のミッション
# ============================================================
player = st.session_state.player_data
m_word = player.get("mission_word", 0)
m_quiz = player.get("mission_quiz", 0)
m_word_status = "✅ COMPLETE" if m_word >= 5 else f"{m_word} / 5"
m_quiz_status = "✅ COMPLETE" if m_quiz >= 5 else f"{m_quiz} / 5"

# COMPLETE 表示のロジック
m_word_display = f'<span class="mission-complete">✅ COMPLETE</span>' if m_word >= 5 else f"{m_word} / 5"
m_quiz_display = f'<span class="mission-complete">✅ COMPLETE</span>' if m_quiz >= 5 else f"{m_quiz} / 5"

# 全ミッション達成時の全体 COMPLETE 表示
if m_word >= 5 and m_quiz >= 5:
    st.markdown(
        f"""
        <div class="mission-card" style="border-color: #7dd87d; background-color: #f0fff0;">
            <div class="mission-title" style="color: #2d8a2d;">🎯 今日のミッション <span style="margin-left: auto;">✅ COMPLETE</span></div>
            <div class="mission-item" style="border-bottom-color: #7dd87d;">
                <div class="mission-label">単語カード</div>
                <div class="mission-status">{m_word_display}</div>
            </div>
            <div class="mission-item">
                <div class="mission-label">4択クイズ</div>
                <div class="mission-status">{m_quiz_display}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"""
        <div class="mission-card">
            <div class="mission-title">🎯 今日のミッション</div>
            <div class="mission-item">
                <div class="mission-label">単語カード</div>
                <div class="mission-status">{m_word_display}</div>
            </div>
            <div class="mission-item">
                <div class="mission-label">4択クイズ</div>
                <div class="mission-status">{m_quiz_display}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# Player Status
# ============================================================
player = st.session_state.player_data

player_label = "👤 プレイヤー"
level_label = "⭐ レベル"
exp_label = "✨ EXP"
coin_label = "🪙 コイン"
if st.session_state.elementary_mode:
    player_label = to_hiragana(player_label)
    level_label = to_hiragana(level_label)
    exp_label = to_hiragana(exp_label)
    coin_label = to_hiragana(coin_label)

st.subheader(player_label)
p_col1, p_col2, p_col3 = st.columns(3)
with p_col1:
    st.metric(level_label, f"Lv.{player.get('level', 1)}")
with p_col2:
    st.metric(exp_label, f"{player.get('exp', 0)} / 100")
with p_col3:
    st.metric(coin_label, player.get("coin", 0))

st.markdown("---")

# モード選択
mode_col1, mode_col2 = st.columns(2)
app_modes = ["単語カード", "4択クイズ"]
study_modes = ["通常モード", "苦手復習モード"]
if st.session_state.elementary_mode:
    app_modes = [to_hiragana(m) for m in app_modes]
    study_modes = [to_hiragana(m) for m in study_modes]

with mode_col1:
    st.radio("アプリのモード", app_modes, horizontal=True, key="app_mode_radio", label_visibility="collapsed")
    # 選択値を内部用の英語/漢字キーに変換
    if st.session_state.app_mode_radio in app_modes:
        idx = app_modes.index(st.session_state.app_mode_radio)
        st.session_state.app_mode = ["単語カード", "4択クイズ"][idx]

with mode_col2:
    st.radio("出題モード", study_modes, horizontal=True, key="study_mode_radio", label_visibility="collapsed")
    if st.session_state.study_mode_radio in study_modes:
        idx = study_modes.index(st.session_state.study_mode_radio)
        st.session_state.study_mode = ["通常モード", "苦手復習モード"][idx]

# 小学生モードON/OFF追加
elem_label = "🎒 小学生モード（ひらがな表示）"
if st.session_state.elementary_mode:
    elem_label = to_hiragana(elem_label)
st.checkbox(elem_label, key="elementary_mode")

record_summary = get_learning_record_summary()

def fmt_rec(text):
    return to_hiragana(text) if st.session_state.elementary_mode else text

st.markdown(
    f"""
    <div class="record-card">
        <div class="record-title">{fmt_rec('📈 学習記録')}</div>
        <div class="record-grid">
            <div class="record-item">{fmt_rec('今日解いた問題数')}<strong>{record_summary['today_questions']}{fmt_rec('問')}</strong></div>
            <div class="record-item">{fmt_rec('総問題数')}<strong>{record_summary['total_questions']}{fmt_rec('問')}</strong></div>
            <div class="record-item">{fmt_rec('正解数')}<strong>{record_summary['correct']}{fmt_rec('問')}</strong></div>
            <div class="record-item">{fmt_rec('不正解数')}<strong>{record_summary['wrong']}{fmt_rec('問')}</strong></div>
            <div class="record-item">{fmt_rec('正解率')}<strong>{record_summary['accuracy']}%</strong></div>
            <div class="record-item">{fmt_rec('最高コンボ')}<strong>{record_summary['best_combo']}{fmt_rec('連続')}</strong></div>
            <div class="record-item">{fmt_rec('総学習日数')}<strong>{record_summary['total_study_days']}{fmt_rec('日')}</strong></div>
            <div class="record-item">{fmt_rec('連続学習日数')}<strong>{record_summary['consecutive_study_days']}{fmt_rec('日')}</strong></div>
            <div class="record-item">{fmt_rec('総プレイ回数')}<strong>{record_summary['play_count']}{fmt_rec('回')}</strong></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 再読み込みと単語数
reload_col, count_col = st.columns([1, 1])
reload_btn_label = "🔄 単語を再読み込み"
reload_success_msg = "words.csv を読み込み直しました！"
reload_error_msg = "words.csv を読み込めませんでした。"
word_count_label = f"📝 登録単語数: {len(WORDS)} 語"

if st.session_state.elementary_mode:
    reload_btn_label = to_hiragana(reload_btn_label)
    reload_success_msg = to_hiragana(reload_success_msg)
    reload_error_msg = to_hiragana(reload_error_msg)
    word_count_label = to_hiragana(word_count_label)

with reload_col:
    if st.button(reload_btn_label, use_container_width=True):
        if reload_words_from_csv():
            st.success(reload_success_msg)
        else:
            st.error(reload_error_msg)

with count_col:
    st.markdown(f"<div style='padding-top:1.2rem; font-size:1rem; color:#666;'>{word_count_label}</div>", unsafe_allow_html=True)

# すっきりさせた統一メトリクスチップ
learned_label = f"😊 覚えた {len(st.session_state.learned_words)} 語"
not_learned_label = f"😅 まだ {len(st.session_state.not_learned_words)} 語"
accuracy_label = f"🎯 正解率 {quiz_accuracy_text()}%"
progress_label = f"✅ {st.session_state.quiz_correct} / {st.session_state.quiz_total} 問"

if st.session_state.elementary_mode:
    learned_label = to_hiragana(learned_label)
    not_learned_label = to_hiragana(not_learned_label)
    accuracy_label = to_hiragana(accuracy_label)
    progress_label = to_hiragana(progress_label)

st.markdown(
    f"""
    <div class="stats-row">
        <div class="stat-chip">{learned_label}</div>
        <div class="stat-chip">{not_learned_label}</div>
        <div class="stat-chip">{accuracy_label}</div>
        <div class="stat-chip">{progress_label}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

review_mode_empty = st.session_state.study_mode == "苦手復習モード" and len(get_word_pool()) == 0

if review_mode_empty:
    msg = "苦手単語はありません😊 通常モードで学習を続けましょう！"
    if st.session_state.elementary_mode:
        msg = to_hiragana(msg)
    st.info(msg)
else:
    if st.session_state.study_mode == "苦手復習モード":
        msg = "🔁 苦手復習モードです。間違えた単語だけをじっくり出題します。"
        if st.session_state.elementary_mode:
            msg = to_hiragana(msg)
        st.markdown(
            f'<div class="hint-box">{msg}</div>',
            unsafe_allow_html=True,
        )

    if current_english is None:
        st.warning("出題できる単語がありません。words.csv を確認してください。")
    elif st.session_state.app_mode == "単語カード":
        current_label = get_display_label(current_english)
        card_label = f"✨ 今日の{current_label} ✨"
        if st.session_state.elementary_mode:
            card_label = to_hiragana(card_label)

        st.markdown(
            f"""
            <div class="word-card">
                <div class="label">{card_label}</div>
                <div class="english-word">{current_english}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.show_meaning:
            meaning = english_to_japanese(current_english)
            meaning_label = "🎉 意味"
            if st.session_state.elementary_mode:
                meaning = to_hiragana(meaning)
                meaning_label = to_hiragana(meaning_label)
            st.markdown(
                f'<div class="meaning-box">{meaning_label}: <strong>{meaning}</strong></div>',
                unsafe_allow_html=True,
            )
        else:
            hint_box_text = "👆 意味がわかったら「意味を見る」を押してね！"
            if st.session_state.elementary_mode:
                hint_box_text = to_hiragana(hint_box_text)
            st.markdown(
                f'<div class="hint-box">{hint_box_text}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        audio_label = "🔊 発音"
        meaning_btn_label = "📖 意味を見る"
        next_btn_label = "➡️ 次へ"
        if st.session_state.elementary_mode:
            audio_label = to_hiragana(audio_label)
            meaning_btn_label = to_hiragana(meaning_btn_label)
            next_btn_label = to_hiragana(next_btn_label)

        with col1:
            if st.button(audio_label, use_container_width=True):
                speak_word(current_english)
        with col2:
            if st.button(meaning_btn_label, use_container_width=True):
                if not st.session_state.show_meaning:
                    add_player_exp_and_coin(2, 0)
                st.session_state.show_meaning = True
                increment_mission_word()
                st.rerun()
        with col3:
            if st.button(next_btn_label, use_container_width=True):
                pick_random_word()
                st.rerun()

        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

        learn_col1, learn_col2 = st.columns(2)
        learned_btn_label = "😊 覚えた！"
        not_learned_btn_label = "😅 まだかな"
        if st.session_state.elementary_mode:
            learned_btn_label = to_hiragana(learned_btn_label)
            not_learned_btn_label = to_hiragana(not_learned_btn_label)

        with learn_col1:
            if st.button(learned_btn_label, use_container_width=True):
                mark_as_learned(current_english)
                pick_random_word()
                st.rerun()
        with learn_col2:
            if st.button(not_learned_btn_label, use_container_width=True):
                mark_as_not_learned(current_english)
                pick_random_word()
                st.rerun()
    else:
        current_label = get_display_label(current_english)
        if st.session_state.quiz_game_finished and st.session_state.quiz_result_summary:
            summary = st.session_state.quiz_result_summary
            finish_msg = "🎉 ゲーム終了！ 10問チャレンジおつかれさま！"
            score_label = "🏆 スコア"
            correct_label = "✅ 正解数"
            accuracy_summary_label = "📊 正解率"
            combo_summary_label = "🔥 最高コンボ"
            retry_btn_label = "🔁 もう一度遊ぶ"
            
            if st.session_state.elementary_mode:
                finish_msg = to_hiragana(finish_msg)
                score_label = to_hiragana(score_label)
                correct_label = to_hiragana(correct_label)
                accuracy_summary_label = to_hiragana(accuracy_summary_label)
                combo_summary_label = to_hiragana(combo_summary_label)
                retry_btn_label = to_hiragana(retry_btn_label)

            st.markdown(
                f'<div class="quiz-result-correct">{finish_msg}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class="meaning-box">
                    <div>{score_label}: <strong>{summary['score']}点</strong></div>
                    <div>{correct_label}: <strong>{summary['correct_count']} / {summary['total_questions']}問</strong></div>
                    <div>{accuracy_summary_label}: <strong>{summary['accuracy']}%</strong></div>
                    <div>{combo_summary_label}: <strong>{summary['best_combo']}連続</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(retry_btn_label, use_container_width=True, key="play_again_button"):
                start_new_quiz_game()
                st.rerun()
        else:
            # クイズ回答中または回答直後、英単語が必ず表示されるようにする
            if current_english:
                st.markdown(build_quiz_prompt_markup(current_english, st.session_state.elementary_mode), unsafe_allow_html=True)
            
            hint_msg = f"🤔 この{current_label}の意味はどれかな？"
            audio_btn_label = "🔊 発音を聞く"
            if st.session_state.elementary_mode:
                hint_msg = to_hiragana(hint_msg)
                audio_btn_label = to_hiragana(audio_btn_label)

            st.markdown(f'<div class="hint-box">{hint_msg}</div>', unsafe_allow_html=True)

            if st.button(audio_btn_label, use_container_width=True):
                speak_word(current_english)

            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

            if len(st.session_state.quiz_choices) < 4:
                warning_msg = "4択クイズには最低5語以上の単語が必要です。"
                if st.session_state.elementary_mode:
                    warning_msg = to_hiragana(warning_msg)
                st.warning(warning_msg)
            else:
                choice_cols = st.columns(2)
                for index, choice in enumerate(st.session_state.quiz_choices):
                    with choice_cols[index % 2]:
                        display_choice = format_elementary_text(choice) if st.session_state.elementary_mode else choice
                        
                        # ボタンクリック時にJSで音を鳴らすための仕掛け
                        correct_japanese = english_to_japanese(current_english)
                        is_correct_choice = (choice == correct_japanese)
                        audio_type_to_play = "correct" if is_correct_choice else "wrong"
                        
                        # ユニークなIDを生成
                        btn_key = f"real_btn_{current_english}_{index}_{choice}"

                        # HTML/JSで音を鳴らしてからStreamlitのボタンをクリックさせる
                        # Streamlitボタンの見た目を完全に模倣したHTMLボタンを作成
                        st.markdown(
                            f"""
                            <div id="wrapper_{index}">
                                <button id="custom_btn_{index}" 
                                    style="
                                        width: 100%; 
                                        height: 5.5rem; 
                                        font-size: 1.5rem; 
                                        font-weight: 800; 
                                        border-radius: 28px; 
                                        border: 3px solid transparent; 
                                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); 
                                        background-color: white; 
                                        color: rgb(49, 51, 63); 
                                        cursor: pointer;
                                        transition: transform 0.15s ease;
                                        margin-bottom: 1rem;
                                    "
                                    onmouseover="this.style.transform='scale(1.03)'"
                                    onmouseout="this.style.transform='scale(1)'"
                                    onclick="
                                        (async () => {{
                                            try {{
                                                const AudioContext = window.AudioContext || window.webkitAudioContext;
                                                const audioCtx = new AudioContext();
                                                if (audioCtx.state === 'suspended') await audioCtx.resume();
                                                
                                                if ('{audio_type_to_play}' === 'correct') {{
                                                    const osc1 = audioCtx.createOscillator();
                                                    const gain1 = audioCtx.createGain();
                                                    osc1.type = 'sine';
                                                    osc1.frequency.setValueAtTime(523.25, audioCtx.currentTime);
                                                    gain1.gain.setValueAtTime(0.15, audioCtx.currentTime);
                                                    gain1.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.15);
                                                    osc1.connect(gain1); gain1.connect(audioCtx.destination);
                                                    osc1.start(); osc1.stop(audioCtx.currentTime + 0.15);
                                                    
                                                    setTimeout(() => {{
                                                        const osc2 = audioCtx.createOscillator();
                                                        const gain2 = audioCtx.createGain();
                                                        osc2.type = 'sine';
                                                        osc2.frequency.setValueAtTime(659.25, audioCtx.currentTime);
                                                        gain2.gain.setValueAtTime(0.15, audioCtx.currentTime);
                                                        gain2.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25);
                                                        osc2.connect(gain2); gain2.connect(audioCtx.destination);
                                                        osc2.start(); osc2.stop(audioCtx.currentTime + 0.25);
                                                    }}, 80);
                                                }} else {{
                                                    const t = audioCtx.currentTime;
                                                    const osc1 = audioCtx.createOscillator();
                                                    const osc2 = audioCtx.createOscillator();
                                                    const gainNode = audioCtx.createGain();
                                                    osc1.type = 'sawtooth'; osc1.frequency.setValueAtTime(150, t);
                                                    osc1.frequency.linearRampToValueAtTime(100, t + 0.3);
                                                    osc2.type = 'sawtooth'; osc2.frequency.setValueAtTime(146, t);
                                                    osc2.frequency.linearRampToValueAtTime(96, t + 0.3);
                                                    gainNode.gain.setValueAtTime(0.12, t);
                                                    gainNode.gain.exponentialRampToValueAtTime(0.01, t + 0.3);
                                                    osc1.connect(gainNode); osc2.connect(gainNode);
                                                    gainNode.connect(audioCtx.destination);
                                                    osc1.start(); osc2.start();
                                                    osc1.stop(t + 0.3); osc2.stop(t + 0.3);
                                                }}
                                            }} catch (e) {{ console.error(e); }}
                                            
                                            // 本物のStreamlitボタンをクリック
                                            // 少し遅延させて音を先に出す
                                            setTimeout(() => {{
                                                const buttons = window.parent.document.querySelectorAll('button');
                                                for (const btn of buttons) {{
                                                    if (btn.innerText.trim() === '{display_choice}') {{
                                                        btn.click();
                                                        break;
                                                    }}
                                                }}
                                            }}, 150);
                                        }})();
                                    "
                                >
                                    {display_choice}
                                </button>
                            </div>
                            <style>
                                /* 本物のStreamlitボタンは物理的に存在させるが、非表示にする */
                                div[data-testid="stButton"]:has(button[aria-label="{display_choice}"]) {{
                                    display: none;
                                }}
                            </style>
                            """,
                            unsafe_allow_html=True
                        )

                        # 本物のボタン（ロジック用）
                        if st.button(
                            display_choice,
                            key=btn_key,
                            use_container_width=True,
                            disabled=st.session_state.quiz_answered,
                        ):
                            record_quiz_answer(choice)
                            st.rerun()

            if st.session_state.quiz_answered:
                correct_answer = english_to_japanese(current_english)
                # 小学生モードに関わらず「漢字（ひらがな）」形式を強制する (force=True)
                display_meaning = format_elementary_text(correct_answer, force=True)

                if st.session_state.quiz_was_correct:
                    # 風船 (1回だけ)
                    if st.session_state.pending_balloons:
                        st.balloons()
                        st.session_state.pending_balloons = False
                    
                    st.markdown('<div class="quiz-result-correct" style="font-size: 2.2rem; font-weight: 800; text-align: center;">⭕ せいかい！</div>', unsafe_allow_html=True)
                    
                    # 褒めメッセージ付き緑色正解カード
                    praise_msg = st.session_state.praise_message
                    st.markdown(
                        f"""
                        <div style="background: #e8fff0; border: 4px solid #7dd87d; border-radius: 28px; padding: 2rem 1.5rem; text-align: center; box-shadow: 0 8px 24px rgba(125, 216, 125, 0.15); margin: 1rem 0;">
                            <div style="color: #2d8a2d; font-size: 1.4rem; font-weight: 800; margin-bottom: 0.5rem;">🎉 {praise_msg}</div>
                            <div style="color: #4a90d9; font-size: 3.5rem; font-weight: 800; letter-spacing: 2px;">{current_english}</div>
                            <div style="background: white; border: 3px dashed #7dd87d; border-radius: 20px; padding: 1.2rem; text-align: center; font-size: 1.8rem; color: #2d8a2d; margin: 1rem 0;"><strong>{display_meaning}</strong></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    
                    st.markdown('<div style="text-align: center; color: #666; font-weight: 700;">EXP +5</div>', unsafe_allow_html=True)
                    st.markdown('<div style="text-align: center; color: #666; font-weight: 700; margin-bottom: 1.5rem;">Coin +2</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="quiz-result-wrong" style="font-size: 2rem; font-weight: 800;">❌ ざんねん！</div>', unsafe_allow_html=True)
                    
                    # あなたの答え (グレー表示)
                    display_selected = format_elementary_text(st.session_state.quiz_selected)
                    st.markdown('<div style="text-align: center; color: #888; font-size: 0.9rem;">あなたの答え</div>', unsafe_allow_html=True)
                    st.markdown(f'<div style="text-align: center; font-size: 1.2rem; font-weight: 700; color: #888888; margin-bottom: 0.5rem;">{display_selected}</div>', unsafe_allow_html=True)
                    
                    st.markdown('<div style="text-align: center; color: #ccc;">────────────</div>', unsafe_allow_html=True)
                    
                    # 正解 (緑カード & ⭕付き)
                    st.markdown(
                        f"""
                        <div style="background: #e8fff0; border: 4px solid #7dd87d; border-radius: 28px; padding: 1.5rem; text-align: center; box-shadow: 0 8px 24px rgba(125, 216, 125, 0.15); margin: 1rem 0;">
                            <div style="color: #2d8a2d; font-size: 1.2rem; font-weight: 800; margin-bottom: 0.5rem;">⭕ 正解</div>
                            <div style="color: #4a90d9; font-size: 2.2rem; font-weight: 800; letter-spacing: 1px; margin-bottom: 0.5rem;">{current_english}</div>
                            <div style="background: white; border: 2px dashed #7dd87d; border-radius: 15px; padding: 0.8rem; text-align: center; font-size: 1.4rem; color: #2d8a2d;"><strong>{display_meaning}</strong></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                if st.button("▶ 次へ", use_container_width=True, key="quiz_next_button"):
                    go_to_next_question()
                    st.rerun()

# 使い方アコーディオン
how_to_label = "📖 使い方"
how_to_content = """
### 単語カードモード
1. 画面に表示された **英単語** の意味を考えます  
2. **「🔊 発音」** で読み方を聞けます  
3. **「📖 意味を見る」** で答え合わせ  
4. **「😊 覚えた！」** / **「😅 まだかな」** を押すと記録されて自動で次の単語へ進みます  

### 4択クイズモード
1. 英単語を見て、4つの日本語から正しい意味を選びます  
2. 正解すると **🎈 バルーン** が飛び、**正解率** が更新されます  
3. **「➡️ 次の問題へ進む」** で次へ進みます
"""
if st.session_state.elementary_mode:
    how_to_label = to_hiragana(how_to_label)
    how_to_content = to_hiragana(how_to_content)

with st.expander(how_to_label):
    st.markdown(how_to_content)
