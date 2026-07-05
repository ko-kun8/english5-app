
# ============================================================
# 英検5級 単語帳アプリ
# ============================================================
# app.py と words.csv を同じフォルダに置いて使います。
# 実行方法: ターミナルで「streamlit run app.py」と入力
# ============================================================

import csv
import json
import random
import re
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# ファイルの場所
# ============================================================
APP_DIR = Path(__file__).parent
CSV_FILE = APP_DIR / "words.csv"
HISTORY_FILE = APP_DIR / "learning_history.json"


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
    """
    words.csv から単語を読み込む。

    返り値:
        dict | None
        - 成功: {"apple": "りんご", ...}
        - 失敗: None
    """
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
        english_key = column_map.get("english")
        japanese_key = column_map.get("japanese")

        if not english_key or not japanese_key:
            return None

        for row in reader:
            english = row.get(english_key, "").strip()
            japanese = row.get(japanese_key, "").strip()
            if english and japanese:
                rows.append((english, japanese))

    if not rows:
        return None

    # 列が逆になっている CSV を自動で直す
    sample_english, sample_japanese = rows[0]
    columns_swapped = looks_japanese(sample_english) and looks_english(sample_japanese)
    if columns_swapped:
        rows = [(japanese, english) for english, japanese in rows]

    words = {english: japanese for english, japanese in rows}
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
    }


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
    return base


def save_history():
    history = {
        "learned_words": sorted(st.session_state.learned_words),
        "not_learned_words": sorted(st.session_state.not_learned_words),
        "quiz_correct": st.session_state.quiz_correct,
        "quiz_total": st.session_state.quiz_total,
        "last_studied": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "word_stats": st.session_state.word_stats,
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
            margin: 0.75rem 0 1rem 0;
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
            font-size: 3rem;
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
            height: 4.5rem !important;
            min-height: 4.5rem !important;
            font-size: 1.2rem !important;
            font-weight: 700 !important;
            border-radius: 24px !important;
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

        div[data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
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

WORDS = st.session_state.words_data


if WORDS is None:
    st.title("📚 英検5級 単語帳")
    if not CSV_FILE.exists():
        st.warning(
            f"⚠️ **words.csv が見つかりません。**\n\n"
            f"`{CSV_FILE}` に words.csv を置いてください。\n\n"
            f"列は `english`, `japanese` だけにしてください。"
        )
    else:
        st.warning(
            "⚠️ **words.csv に有効な単語がありません。**\n\n"
            "english と japanese の列に、1行以上の単語を書いてください。"
        )
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
    st.session_state.history_loaded = True

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

if "word_stats" not in st.session_state:
    st.session_state.word_stats = {}

if "pending_balloons" not in st.session_state:
    st.session_state.pending_balloons = False

if "last_picked_word" not in st.session_state:
    st.session_state.last_picked_word = None


# ============================================================
# ヘルパー関数
# ============================================================
def english_to_japanese(word: str) -> str:
    return WORDS.get(word, "")


def normalize_english_word(word: str | None) -> str | None:
    """
    表示用の英単語を必ず返す。
    セッションに日本語が入っていた場合も自動で直す。
    """
    if not word:
        return None

    if word in WORDS:
        return word

    for english, japanese in WORDS.items():
        if japanese == word:
            st.session_state.current_word = english
            return english

    return None


def sanitize_word_sets():
    """学習記録から、存在しない単語や日本語だけの記録を除去する。"""
    valid_english = set(WORDS.keys())
    st.session_state.learned_words = {
        normalize_english_word(word) or word
        for word in st.session_state.learned_words
    } & valid_english
    st.session_state.not_learned_words = {
        normalize_english_word(word) or word
        for word in st.session_state.not_learned_words
    } & valid_english
    st.session_state.word_stats = {
        word: stats
        for word, stats in st.session_state.word_stats.items()
        if word in valid_english
    }
    st.session_state.used_words = [
        word for word in st.session_state.used_words if word in valid_english
    ]


def get_word_pool():
    if st.session_state.study_mode == "苦手復習モード":
        return [
            word
            for word in st.session_state.not_learned_words
            if word in WORDS
        ]
    return list(WORDS.keys())


def get_word_stat(english: str) -> dict:
    stats = st.session_state.word_stats.setdefault(
        english,
        {"wrong": 0, "correct": 0},
    )
    stats.setdefault("wrong", 0)
    stats.setdefault("correct", 0)
    return stats


def compute_word_weight(english: str) -> float:
    """苦手単語・SRS・正解率に応じた出題重みを計算する。"""
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
    """出題履歴を考慮し、まだ出ていない単語リストを返す。"""
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


def pick_random_word():
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


def build_quiz_distractors(english: str, correct_japanese: str, count: int = 3) -> list[str]:
    """不正解選択肢を苦手・未学習・覚えた単語からバランスよく選ぶ。"""
    others = [
        (key, value)
        for key, value in WORDS.items()
        if key != english and value and value != correct_japanese
    ]
    if not others:
        return []

    weak = [(k, v) for k, v in others if k in st.session_state.not_learned_words]
    learned = [(k, v) for k, v in others if k in st.session_state.learned_words]
    neutral = [
        (k, v)
        for k, v in others
        if k not in st.session_state.not_learned_words
        and k not in st.session_state.learned_words
    ]

    selected: list[str] = []
    seen: set[str] = set()

    def take_from(pool: list[tuple[str, str]], limit: int):
        random.shuffle(pool)
        for _, meaning in pool:
            if len(selected) >= count or len(selected) >= limit:
                break
            if meaning not in seen:
                selected.append(meaning)
                seen.add(meaning)

    take_from(weak, count)
    take_from(neutral, count)
    take_from(learned, count)
    take_from(others, count)

    if len(selected) < count:
        remaining = [v for _, v in others if v not in seen]
        random.shuffle(remaining)
        for meaning in remaining:
            if len(selected) >= count:
                break
            selected.append(meaning)
            seen.add(meaning)

    return selected[:count]


def setup_quiz_choices():
    english = normalize_english_word(st.session_state.current_word)
    if not english:
        st.session_state.quiz_choices = []
        return

    correct = english_to_japanese(english)
    wrong_answers = build_quiz_distractors(english, correct, count=3)

    if len(wrong_answers) < 3:
        fallback = [
            value
            for key, value in WORDS.items()
            if key != english and value != correct and value not in wrong_answers
        ]
        random.shuffle(fallback)
        for meaning in fallback:
            if len(wrong_answers) >= 3:
                break
            if meaning not in wrong_answers:
                wrong_answers.append(meaning)

    choices = list(dict.fromkeys(wrong_answers + [correct]))
    random.shuffle(choices)
    st.session_state.quiz_choices = choices


def reload_words_from_csv():
    new_words = load_words()
    if new_words is None:
        return False
    st.session_state.words_data = new_words
    st.session_state.used_words = []
    sanitize_word_sets()
    pick_random_word()
    return True


import urllib.parse
import streamlit.components.v1 as components

import requests
import streamlit as st

def speak_word(word):
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&q={word}&tl=en"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        st.audio(response.content, format="audio/mp3")
    else:
        st.error("音声の取得に失敗しました")


def quiz_accuracy_text():
    total = st.session_state.quiz_total
    correct = st.session_state.quiz_correct
    if total == 0:
        return "0.0"
    return f"{(correct / total) * 100:.1f}"


def record_quiz_answer(selected_japanese: str):
    english = normalize_english_word(st.session_state.current_word)
    if not english or st.session_state.quiz_answered:
        return

    correct_japanese = english_to_japanese(english)
    is_correct = selected_japanese == correct_japanese
    stats = get_word_stat(english)

    st.session_state.quiz_selected = selected_japanese
    st.session_state.quiz_answered = True
    st.session_state.quiz_was_correct = is_correct
    st.session_state.quiz_total += 1

    if is_correct:
        st.session_state.quiz_correct += 1
        stats["correct"] += 1
        st.session_state.pending_balloons = True
        mark_as_learned(english)
    else:
        stats["wrong"] += 1
        mark_as_not_learned(english)

    persist_state()


def go_to_next_question():
    """回答後の状態を完全にリセットして次の問題へ進む。"""
    reset_quiz_state()
    pick_random_word()


# ============================================================
# 起動時のデータ整備
# ============================================================
sanitize_word_sets()

if normalize_english_word(st.session_state.current_word) is None:
    st.session_state.current_word = None

if st.session_state.current_word is None:
    pick_random_word()

if "previous_study_mode" not in st.session_state:
    st.session_state.previous_study_mode = st.session_state.study_mode

if "previous_app_mode" not in st.session_state:
    st.session_state.previous_app_mode = st.session_state.app_mode

if st.session_state.previous_study_mode != st.session_state.study_mode:
    st.session_state.previous_study_mode = st.session_state.study_mode
    st.session_state.used_words = []
    pick_random_word()

if st.session_state.previous_app_mode != st.session_state.app_mode:
    st.session_state.previous_app_mode = st.session_state.app_mode
    st.session_state.show_meaning = False
    reset_quiz_state()
    if current_english := normalize_english_word(st.session_state.current_word):
        setup_quiz_choices()

if st.session_state.study_mode == "苦手復習モード":
    word_pool = get_word_pool()
    if not word_pool:
        st.session_state.current_word = None
    elif normalize_english_word(st.session_state.current_word) not in word_pool:
        pick_random_word()

current_english = normalize_english_word(st.session_state.current_word)
if current_english and not st.session_state.quiz_choices:
    setup_quiz_choices()


# ============================================================
# 画面の表示
# ============================================================
st.title("📚 英検5級 単語帳")

st.markdown(
    '<p class="subtitle">🌟 英単語の意味を当ててみよう！ 🌟</p>',
    unsafe_allow_html=True,
)

mode_col1, mode_col2 = st.columns(2)
with mode_col1:
    st.radio(
        "アプリのモード",
        ["単語カード", "4択クイズ"],
        horizontal=True,
        key="app_mode",
        label_visibility="collapsed",
    )
with mode_col2:
    st.radio(
        "出題モード",
        ["通常モード", "苦手復習モード"],
        horizontal=True,
        key="study_mode",
        label_visibility="collapsed",
    )

reload_col, count_col = st.columns([1, 2])
with reload_col:
    if st.button("🔄 単語を再読み込み", use_container_width=True):
        if reload_words_from_csv():
            st.success("words.csv を読み込み直しました！")
        else:
            st.error("words.csv を読み込めませんでした。")
with count_col:
    st.caption(f"📝 登録単語数: {len(WORDS)} 語")

st.markdown(
    f"""
    <div class="stats-row">
        <div class="stat-chip">😊 覚えた {len(st.session_state.learned_words)} 語</div>
        <div class="stat-chip">😅 まだ {len(st.session_state.not_learned_words)} 語</div>
        <div class="stat-chip">🎯 正解率 {quiz_accuracy_text()}%</div>
        <div class="stat-chip">✅ {st.session_state.quiz_correct} / {st.session_state.quiz_total} 問</div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_col1, metric_col2, metric_col3 = st.columns(3)
with metric_col1:
    st.metric("😊 覚えた", f"{len(st.session_state.learned_words)} 語")
with metric_col2:
    st.metric("😅 まだ", f"{len(st.session_state.not_learned_words)} 語")
with metric_col3:
    st.metric("🎯 正解率", f"{quiz_accuracy_text()}%")

review_mode_empty = (
    st.session_state.study_mode == "苦手復習モード"
    and len(get_word_pool()) == 0
)

if review_mode_empty:
    st.info("苦手単語はありません😊 通常モードで学習を続けましょう！")
elif current_english is None:
    st.warning("出題できる単語がありません。words.csv を確認してください。")
elif st.session_state.app_mode == "単語カード":
    st.markdown(
        f"""
        <div class="word-card">
            <div class="label">✨ 今日の単語 ✨</div>
            <div class="english-word">{current_english}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.show_meaning:
        meaning = english_to_japanese(current_english)
        st.markdown(
            f'<div class="meaning-box">🎉 意味: <strong>{meaning}</strong></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="hint-box">👆 意味がわかったら「意味を見る」を押してね！</div>',
            unsafe_allow_html=True,
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔊 発音", use_container_width=True):
            speak_word(current_english)
    with col2:
        if st.button("📖 意味を見る", use_container_width=True):
            st.session_state.show_meaning = True
    with col3:
        if st.button("➡️ 次へ", use_container_width=True):
            pick_random_word()
            st.rerun()

    learn_col1, learn_col2 = st.columns(2)
    with learn_col1:
        if st.button("😊 覚えた", use_container_width=True):
            mark_as_learned(current_english)
            if st.session_state.study_mode == "苦手復習モード":
                pick_random_word()
            st.rerun()
    with learn_col2:
        if st.button("😅 まだ", use_container_width=True):
            mark_as_not_learned(current_english)
            st.rerun()

else:
    st.markdown(
        f"""
        <div class="word-card">
            <div class="label">🎯 4択クイズ</div>
            <div class="english-word">{current_english}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hint-box">🤔 この英単語の意味はどれかな？</div>',
        unsafe_allow_html=True,
    )

    if st.button("🔊 発音", use_container_width=True):
        speak_word(current_english)

    if len(st.session_state.quiz_choices) < 4:
        st.warning("4択クイズには最低5語以上の単語が必要です。words.csv に単語を追加してください。")
    else:
        choice_cols = st.columns(2)
        for index, choice in enumerate(st.session_state.quiz_choices):
            with choice_cols[index % 2]:
                if st.button(
                    choice,
                    key=f"quiz_choice_{current_english}_{index}_{choice}",
                    use_container_width=True,
                    disabled=st.session_state.quiz_answered,
                ):
                    record_quiz_answer(choice)
                    st.rerun()

    if st.session_state.quiz_answered:
        correct_answer = english_to_japanese(current_english)

        if st.session_state.quiz_was_correct:
            if st.session_state.pending_balloons:
                st.balloons()
                st.session_state.pending_balloons = False
            st.markdown(
                '<div class="quiz-result-correct">🎉 正解！すごいね！</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="quiz-result-wrong">😅 不正解… もう一度覚えよう！</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="meaning-box">📌 正しい意味: <strong>{correct_answer}</strong></div>',
                unsafe_allow_html=True,
            )
            if st.session_state.quiz_selected:
                st.markdown(
                    f'<div class="hint-box">選んだ答え: {st.session_state.quiz_selected}</div>',
                    unsafe_allow_html=True,
                )

        if st.button("➡️ 次の問題", use_container_width=True, key="quiz_next_button"):
            go_to_next_question()
            st.rerun()

with st.expander("📖 使い方"):
    st.markdown(
        """
        ### 単語カードモード
        1. 画面に表示された **英単語** の意味を考えます  
        2. **「🔊 発音」** で読み方を聞けます  
        3. **「📖 意味を見る」** で答え合わせ  
        4. **「➡️ 次へ」** で次の単語へ  
        5. **「😊 覚えた」** / **「😅 まだ」** で記録できます  

        ### 4択クイズモード
        1. 英単語を見て、4つの日本語から正しい意味を選びます  
        2. 正解すると **🎈 バルーン** が飛び、**正解率** が更新されます  
        3. 不正解のときは **正しい意味** が強調表示されます  
        4. **「➡️ 次の問題」** で次へ進みます（同じ問題は連続しません）  

        ### 学習の仕組み
        - **出題履歴:** 一度出た単語は全単語を一周するまで再出題されません  
        - **苦手優先:** 「😅 まだ」の単語は通常より **3倍** 出やすくなります  
        - **SRS（簡易版）:** 間違えた回数が多い単語ほど、優先的に出題されます  
        - **苦手復習モード** では「😅 まだ」の単語だけ出題されます  
        - 学習記録は `learning_history.json` に自動保存されます  
        - **単語の追加方法:** `words.csv` に行を追加して「🔄 単語を再読み込み」を押すだけです  

        **実行方法:** `streamlit run app.py`
        """
    )
