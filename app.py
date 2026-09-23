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
import base64
import streamlit as st

# ============================================================
# ファイルの場所 & パス解決
# ============================================================
APP_DIR = Path(__file__).parent
CSV_FILE = APP_DIR / "words.csv"
HISTORY_FILE = APP_DIR / "learning_history.json"
PLAYER_DATA_FILE = APP_DIR / "player_data.json"
LAST_USER_FILE = APP_DIR / "last_user.json"

USERS_DIR = APP_DIR / "users"
USERS_DIR.mkdir(exist_ok=True)

# 既存の learning_history.json のバックアップ
LEGACY_HISTORY_FILE = APP_DIR / "learning_history.json"
BACKUP_HISTORY_FILE = APP_DIR / "learning_history_backup.json"
if LEGACY_HISTORY_FILE.exists() and not BACKUP_HISTORY_FILE.exists():
    try:
        import shutil
        shutil.copy2(LEGACY_HISTORY_FILE, BACKUP_HISTORY_FILE)
    except Exception:
        pass



import uuid

def migrate_old_users():
    """旧形式（ユーザー名フォルダ）のデータを新形式（UUID形式）へ安全に移行する。
    1つの旧フォルダに対してマイグレーションは1度だけ実行し、再生成を完全に防止する。
    """
    if not USERS_DIR.exists():
        return

    # まず、既存のUUIDフォルダとその表示名のマップを作成
    existing_uuid_names = {}
    for p in USERS_DIR.iterdir():
        if p.is_dir():
            name = p.name
            try:
                uuid.UUID(name)
                # UUID フォルダの場合、user_data.json を読む
                ud_file = p / "user_data.json"
                if ud_file.exists():
                    with ud_file.open(encoding="utf-8") as f:
                        data = json.load(f)
                        dname = data.get("display_name")
                        if dname:
                            existing_uuid_names[dname] = name
            except ValueError:
                pass

    for p in USERS_DIR.iterdir():
        if p.is_dir():
            name = p.name
            is_uuid = False
            try:
                uuid.UUID(name)
                is_uuid = True
            except ValueError:
                is_uuid = False
            
            # 非UUID形式（旧ユーザー名フォルダ）の場合
            if not is_uuid:
                migrated_flag = p / ".migrated"
                # すでにマイグレーション完了マークがある場合は完全にスキップ
                if migrated_flag.exists():
                    continue

                # 旧フォルダ内に user_data.json または既存情報があるか確認
                target_user_id = None
                user_data_file = p / "user_data.json"
                if user_data_file.exists():
                    try:
                        with user_data_file.open(encoding="utf-8") as f:
                            data = json.load(f)
                            target_user_id = data.get("user_id")
                    except Exception:
                        pass

                # 既存のUUIDフォルダで同じ表示名のものがあればそれを使用（新規発行しない）
                if not target_user_id and name in existing_uuid_names:
                    target_user_id = existing_uuid_names[name]

                # それでもなければ新しいUUIDを一度だけ生成
                if not target_user_id:
                    target_user_id = str(uuid.uuid4())

                new_dir = USERS_DIR / target_user_id
                new_dir.mkdir(parents=True, exist_ok=True)
                
                # 新UUIDフォルダに user_data.json を保存
                new_user_data_file = new_dir / "user_data.json"
                if not new_user_data_file.exists():
                    user_data = {
                        "user_id": target_user_id,
                        "display_name": name
                    }
                    with new_user_data_file.open("w", encoding="utf-8") as f:
                        json.dump(user_data, f, ensure_ascii=False, indent=2)
                        
                # 旧フォルダから学習履歴とプレイヤーデータをコピー
                for fname in ["learning_history.json", "player_data.json"]:
                    old_f = p / fname
                    new_f = new_dir / fname
                    if old_f.exists() and not new_f.exists():
                        try:
                            import shutil
                            shutil.copy2(old_f, new_f)
                        except Exception:
                            pass

                # 旧フォルダ内に .migrated フラグファイルおよび user_data.json を作成して次回以降の自動生成を阻止
                try:
                    with migrated_flag.open("w", encoding="utf-8") as f:
                        f.write(target_user_id)
                    if not user_data_file.exists():
                        with user_data_file.open("w", encoding="utf-8") as f:
                            json.dump({"user_id": target_user_id, "display_name": name}, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass





# アプリ起動時にマイグレーションを実行
migrate_old_users()


def sanitize_username(name: str) -> str:
    """表示名からファイルシステムで安全な文字列を生成する。"""
    cleaned = re.sub(r'[\\/:*?"<>|]+', '_', name).strip()
    return cleaned if cleaned else "default_user"


def get_user_dir(user_id: str | None) -> Path:
    safe_id = user_id if user_id else "default_user"
    user_dir = USERS_DIR / safe_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir



def get_user_history_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "learning_history.json"


def get_user_player_data_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "player_data.json"


def get_user_data_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "user_data.json"


def get_existing_users() -> list[dict]:
    """users フォルダ内にある既存のユーザー情報一覧（user_id, display_name）を取得する。
    同じ user_id が重複してリストアップされないよう一意にユニーク化する。
    """
    if not USERS_DIR.exists():
        return []
    users_map = {}
    for p in USERS_DIR.iterdir():
        if p.is_dir():
            data = load_user_profile(p.name)
            if data and data.get("user_id") and "display_name" in data:
                uid = data["user_id"]
                if uid not in users_map:
                    users_map[uid] = data
            else:
                # 万が一 user_data.json がないフォルダの場合
                uid = p.name
                if uid not in users_map:
                    users_map[uid] = {"user_id": uid, "display_name": uid}
                    
    # display_name または user_id でソートしてリスト化
    return sorted(list(users_map.values()), key=lambda x: x.get("display_name", x.get("user_id", "")))



def get_display_name(user_id: str) -> str:
    """user_id から表示名を取得する。"""
    if not user_id:
        return "ゲスト"
    data = load_user_profile(user_id)
    if data and "display_name" in data:
        return data["display_name"]
    return user_id


def load_user_profile(user_id: str) -> dict | None:
    """ユーザープロファイル（user_id, display_name等）を読み込む。"""
    if not user_id:
        return None
    user_data_file = get_user_data_file(user_id)
    if user_data_file.exists():
        try:
            with user_data_file.open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_user_profile(user_id: str, profile_data: dict) -> None:
    """ユーザープロファイルを保存する。"""
    user_data_file = get_user_data_file(user_id)
    with user_data_file.open("w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)


def create_user_profile(user_id: str, display_name: str) -> dict:
    """新規ユーザーのプロファイルおよび初期データを生成・保存する（UI分離・クラウド移行容易化）。"""
    profile_data = {
        "user_id": user_id,
        "display_name": display_name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_user_profile(user_id, profile_data)
    
    # 初期プレイヤーデータと初期学習履歴も作成して保存
    init_player = default_player_data()
    save_player_data(user_id=user_id, player_data=init_player)
    
    init_history = default_history()
    save_history(user_id=user_id, history_data=init_history)
    
    return profile_data


def delete_user_data(user_id: str):
    """指定されたユーザーのUUIDフォルダを削除し、バックアップを作成する。"""
    # 1. バックアップ
    backup_dir = APP_DIR / "users_backup" / datetime.now().strftime("%Y%m%d")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    source = USERS_DIR / user_id
    if source.exists():
        destination = backup_dir / user_id
        import shutil
        shutil.copytree(source, destination)
        
        # 2. ユーザーフォルダ削除
        shutil.rmtree(source)
    
    # 3. last_user.json の解除
    if LAST_USER_FILE.exists():
        try:
            with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("last_user_id") == user_id:
                LAST_USER_FILE.unlink()
        except Exception:
            pass



# ============================================================
# ユーザー管理 & 切替ロジック
# ============================================================
def reset_user_session():
    """ユーザー切り替え時に旧ユーザーのセッションデータを完全にクリアする。"""
    keys_to_remove = [
        "history_loaded", "player_data", "learned_words", "not_learned_words",
        "quiz_correct", "quiz_total", "word_stats", "study_today_questions",
        "study_today_date", "study_dates", "study_play_count", "current_word",
        "quiz_choices", "quiz_answered", "quiz_was_correct", "quiz_selected",
        "used_words", "level_up_pending", "daily_mission_claimed", "praise_message",
        "pending_balloons", "pending_snow", "pending_audio"
    ]
    for key in keys_to_remove:
        st.session_state.pop(key, None)


def load_last_user_id() -> str | None:
    """端末側に保存された最後に使用したユーザーUUIDを読み込む。"""
    try:
        if LAST_USER_FILE.exists():
            with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                uid = data.get("last_user_id")
                if uid and isinstance(uid, str):
                    if (USERS_DIR / uid / "user_data.json").exists():
                        return uid
    except Exception:
        pass
    return None


def save_last_user_id(user_id: str | None) -> None:
    """端末側に最後に使用したユーザーUUIDを保存する（None の場合は保存ファイルを削除）。"""
    try:
        if user_id:
            with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
                json.dump({"last_user_id": user_id}, f, ensure_ascii=False, indent=2)
        else:
            if LAST_USER_FILE.exists():
                LAST_USER_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def set_active_user(user_id: str | None):
    """アクティブなユーザー（UUID）をセットし、セッションをクリアして再ロードの準備をする。"""
    reset_user_session()
    st.session_state.current_user_id = user_id
    st.session_state.current_user = user_id  # 互換性維持
    if user_id:
        save_last_user_id(user_id)


if "current_user_id" not in st.session_state:
    # 端末側に保存された前回のユーザーUUIDを復元
    last_id = load_last_user_id()
    if last_id:
        st.session_state.current_user_id = last_id
    elif "current_user" in st.session_state and st.session_state.current_user:
        st.session_state.current_user_id = st.session_state.current_user
    else:
        st.session_state.current_user_id = None

if "current_user" not in st.session_state:
    st.session_state.current_user = st.session_state.current_user_id

if "show_new_user_form" not in st.session_state:
    st.session_state.show_new_user_form = False

if not st.session_state.current_user_id:
    st.title("🎉 だれが勉強する？")
    existing_users = get_existing_users()

    if existing_users and not st.session_state.show_new_user_form:
        st.write("つかう なまえ を えらんでね！")
        
        # ユーザー選択ボタンを表示
        for idx, u in enumerate(existing_users):
            u_id = u["user_id"]
            u_name = u["display_name"]
            
            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                if st.button(f"👤 {u_name}", key=f"user_select_btn_{u_id}", use_container_width=True):
                    set_active_user(u_id)
                    st.rerun()
            with c2:
                if st.button("🗑️", key=f"delete_btn_{u_id}", help="削除"):
                    st.session_state[f"confirm_delete_{u_id}"] = True
            
            if st.session_state.get(f"confirm_delete_{u_id}"):
                st.warning(f"{u_name} を削除しますか？（バックアップは作成されます）")
                col_y, col_n = st.columns(2)
                if col_y.button("はい", key=f"yes_delete_{u_id}"):
                    delete_user_data(u_id)
                    st.session_state[f"confirm_delete_{u_id}"] = False
                    st.rerun()
                if col_n.button("いいえ", key=f"no_delete_{u_id}"):
                    st.session_state[f"confirm_delete_{u_id}"] = False
                    st.rerun()

        st.markdown("---")
        if st.button("➕ 新しいユーザー", key="btn_toggle_new_user", use_container_width=True):
            st.session_state.show_new_user_form = True
            st.rerun()

    else:
        st.subheader("新しいユーザーの登録")
        st.markdown("名前を入力してください")
        new_name_input = st.text_input("名前：", key="input_new_username_val")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("はじめる", key="btn_create_and_start", use_container_width=True):
                clean_name = new_name_input.strip()
                if not clean_name:
                    st.warning("名前を入力してください。")
                else:
                    new_id = str(uuid.uuid4())
                    create_user_profile(new_id, clean_name)
                    
                    st.session_state.show_new_user_form = False
                    set_active_user(new_id)
                    st.rerun()
        with c2:
            if existing_users:
                if st.button("戻る", key="btn_cancel_new_user", use_container_width=True):
                    st.session_state.show_new_user_form = False
                    st.rerun()

    st.stop()







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
        "mission_completed": False,
        "daily_date": "",
        "daily_correct": 0,
        "daily_clear": 0,
        "daily_claimed": [False, False, False],
        "badges": [],
        "purchased_items": []
    }


def load_player_data(user_id: str | None = None):
    """プレイヤーデータを読み込む。存在しない場合は初期値を生成（必ずLv.1）。"""
    default = default_player_data()
    target_id = user_id or st.session_state.get("current_user_id", "default_user")
    player_file = get_user_player_data_file(target_id)
    
    if not player_file.exists():
        return default

    try:
        with player_file.open(encoding="utf-8") as f:
            data = json.load(f)
            # 欠けているキーがあればデフォルト値で埋める
            for key, value in default.items():
                if key not in data:
                    data[key] = value
            return data
    except (json.JSONDecodeError, OSError):
        return default


def save_player_data(user_id: str | None = None, player_data: dict | None = None):
    """プレイヤーデータを保存する。"""
    target_id = user_id or st.session_state.get("current_user_id", "default_user")
    data_to_save = player_data if player_data is not None else st.session_state.get("player_data")
    
    if data_to_save is None:
        return
        
    player_file = get_user_player_data_file(target_id)
    with player_file.open("w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)


def add_player_exp_and_coin(exp_gain: int, coin_gain: int):
    """プレイヤーにEXPとコインを加算し、レベルアップ判定を行う。"""
    player = st.session_state.player_data
    
    old_level = player.get("level", 1)
    player["exp"] = player.get("exp", 0) + exp_gain
    player["coin"] = player.get("coin", 0) + coin_gain
    
    leveled_up = False
    while player.get("exp", 0) >= 100:
        player["level"] = player.get("level", 1) + 1
        player["exp"] -= 100
        player["coin"] = player.get("coin", 0) + 50 # レベルアップボーナス
        leveled_up = True
        
    if leveled_up:
        st.session_state.level_up_pending = {
            "old": old_level,
            "new": player["level"]
        }
        
    check_badges()
    save_player_data()


def check_daily_reset():
    """日付が変わっていたらデイリーミッションをリセットする。"""
    player = st.session_state.player_data
    today = datetime.now().strftime("%Y-%m-%d")
    
    if player.get("daily_date") != today:
        player["daily_date"] = today
        player["daily_correct"] = 0
        player["daily_clear"] = 0
        player["daily_claimed"] = [False, False, False]
        # 既存の古いミッションキーも念のためリセット
        player["mission_word"] = 0
        player["mission_quiz"] = 0
        player["mission_completed"] = False
        save_player_data()


def update_daily_mission(is_correct: bool):
    """デイリーミッションの進捗を更新し、達成報酬を付与する。"""
    # まずリセットチェック
    check_daily_reset()
    
    player = st.session_state.player_data
    player["daily_clear"] += 1
    if is_correct:
        player["daily_correct"] += 1
    
    # 報酬判定
    # 1. 5問正解 (20Coin)
    if player["daily_correct"] >= 5 and not player["daily_claimed"][0]:
        player["daily_claimed"][0] = True
        player["coin"] += 20
        st.session_state.daily_mission_claimed = "🎯 5問正解達成！ 🪙+20 Coin ゲット！"
        
    # 2. 10問クリア (30Coin)
    if player["daily_clear"] >= 10 and not player["daily_claimed"][1]:
        player["daily_claimed"][1] = True
        player["coin"] += 30
        st.session_state.daily_mission_claimed = "🎯 10問クリア達成！ 🪙+30 Coin ゲット！"

    # 3. 20問クリア (50Coin)
    if player["daily_clear"] >= 20 and not player["daily_claimed"][2]:
        player["daily_claimed"][2] = True
        player["coin"] += 50
        st.session_state.daily_mission_claimed = "🎯 20問クリア達成！ 🪙+50 Coin ゲット！"
        
    save_player_data()


def check_mission_completion():
    """(互換性のために残す) 今日のミッションが達成されたかチェックする。"""
    pass

def load_history(user_id: str | None = None):
    """学習履歴を読み込む。"""
    target_id = user_id or st.session_state.get("current_user_id", "default_user")
    history_file = get_user_history_file(target_id)
    if not history_file.exists():
        return default_history()

    try:
        with history_file.open(encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_history()

    base = default_history()
    # 読み込んだデータで上書き
    for key in base.keys():
        if key in data:
            if key in ["learned_words", "not_learned_words", "study_dates"]:
                base[key] = list(data[key])
            elif key == "word_stats":
                base[key] = dict(data[key])
            else:
                base[key] = data[key]
    return base


def save_history(user_id: str | None = None, history_data: dict | None = None):
    """学習履歴を保存する。"""
    target_id = user_id or st.session_state.get("current_user_id", "default_user")
    history_file = get_user_history_file(target_id)
    
    if history_data is not None:
        history = history_data
    else:
        # セッション状態から取得
        history = {
            "learned_words": sorted(list(st.session_state.get("learned_words", []))),
            "not_learned_words": sorted(list(st.session_state.get("not_learned_words", []))),
            "quiz_correct": st.session_state.get("quiz_correct", 0),
            "quiz_total": st.session_state.get("quiz_total", 0),
            "last_studied": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "word_stats": st.session_state.get("word_stats", {}),
            "study_today_questions": st.session_state.get("study_today_questions", 0),
            "study_today_date": st.session_state.get("study_today_date"),
            "study_dates": list(st.session_state.get("study_dates", [])),
            "study_play_count": st.session_state.get("study_play_count", 0),
        }
        
    with history_file.open("w", encoding="utf-8") as file:
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
if not st.session_state.get("history_loaded", False):
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
    
# セッション変数の安全な初期化
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
    st.session_state.pending_audio = None
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
    if "learned_words" not in st.session_state:
        st.session_state.learned_words = set()
    if "not_learned_words" not in st.session_state:
        st.session_state.not_learned_words = set()
    if "word_stats" not in st.session_state:
        st.session_state.word_stats = {}
    if "used_words" not in st.session_state:
        st.session_state.used_words = []

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
        current = normalize_english_word(st.session_state.current_word)
        if current and not st.session_state.quiz_choices:
            setup_quiz_choices()
        return current

    current = normalize_english_word(st.session_state.current_word)
    
    # すでに単語が選ばれているならそれを返す（ここで pick_random_word を呼ばない）
    if current:
        if st.session_state.app_mode == "4択クイズ" and not st.session_state.quiz_choices:
             setup_quiz_choices()
        return current

    # ま化単語がない場合のみ新しく選ぶ
    pick_random_word()
    current = normalize_english_word(st.session_state.current_word)
    if current and st.session_state.app_mode == "4択クイズ" and not st.session_state.quiz_choices:
        setup_quiz_choices()
    return current


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
    # デイリーミッションのリセットチェックもここで行う
    check_daily_reset()
    
    today = get_today_key()
    if st.session_state.study_today_date != today:
        st.session_state.study_today_date = today
        st.session_state.study_today_questions = 0

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


# ============================================================
# ショップ機能
# ============================================================
def show_shop():
    """ショップ画面を表示する。"""
    player = st.session_state.player_data
    if "purchased_items" not in player:
        player["purchased_items"] = []

    shop_title = "🛒 ショップ"
    coin_label = f"Coin：{player.get('coin', 0)}"

    if st.session_state.elementary_mode:
        shop_title = to_hiragana(shop_title)
        coin_label = to_hiragana(coin_label)

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #fff5f8 0%, #fff0f5 100%);
            border: 3px solid #ffb6c1;
            border-radius: 24px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 6px 18px rgba(255, 107, 157, 0.15);
            text-align: center;
        ">
            <div style="font-size: 2rem; font-weight: 800; color: #ff6b9d; margin-bottom: 0.5rem;">{shop_title}</div>
            <div style="font-size: 1.5rem; font-weight: 800; color: #ff9900; background: white; display: inline-block; padding: 0.4rem 1.2rem; border-radius: 20px; border: 2px dashed #ffc966;">🪙 {coin_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    items = [
        {"id": "hat", "name": "🎩 帽子", "price": 100},
        {"id": "rainbow", "name": "🌈 にじ背景", "price": 200},
        {"id": "crown", "name": "👑 王冠", "price": 300},
    ]

    purchased = player.get("purchased_items", [])

    cols = st.columns(3)
    for idx, item in enumerate(items):
        item_id = item["id"]
        item_name = item["name"]
        item_price = item["price"]
        is_bought = item_id in purchased or item_name in purchased

        display_name = to_hiragana(item_name) if st.session_state.elementary_mode else item_name
        price_text = f"{item_price}Coin"

        with cols[idx]:
            st.markdown(
                f"""
                <div style="
                    background: white;
                    border: 3px solid {"#7dd87d" if is_bought else "#ffd1dc"};
                    border-radius: 20px;
                    padding: 1.2rem;
                    text-align: center;
                    margin-bottom: 1rem;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                ">
                    <div style="font-size: 1.3rem; font-weight: 800; color: #333; margin-bottom: 0.5rem;">{display_name}</div>
                    <div style="font-size: 1.1rem; font-weight: 700; color: #ff9900; margin-bottom: 0.8rem;">🪙 {price_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if is_bought:
                bought_label = to_hiragana("購入済み") if st.session_state.elementary_mode else "購入済み"
                st.button(bought_label, key=f"bought_{item_id}", disabled=True, use_container_width=True)
            else:
                buy_label = to_hiragana("購入") if st.session_state.elementary_mode else "購入"
                if st.button(buy_label, key=f"buy_{item_id}", use_container_width=True):
                    current_coin = player.get("coin", 0)
                    if current_coin < item_price:
                        st.warning("Coinが足りません")
                    else:
                        player["coin"] = current_coin - item_price
                        if "purchased_items" not in player:
                            player["purchased_items"] = []
                        player["purchased_items"].append(item_id)
                        save_player_data()
                        st.success(f"{item_name} をこうにゅうしたよ！" if st.session_state.elementary_mode else f"{item_name} を購入しました！")
                        st.rerun()


def check_badges():
    """バッジの獲得判定を行い、獲得したバッジがあればコインを付与し、セッション状態に保存して、プレイヤーデータをセーブする。"""
    player = st.session_state.player_data
    if "badges" not in player:
        player["badges"] = []
    
    newly_unlocked = []
    
    # 1. 🥉 はじめての正解
    if "🥉 はじめての正解" not in player["badges"]:
        if st.session_state.get("quiz_correct", 0) >= 1:
            player["badges"].append("🥉 はじめての正解")
            newly_unlocked.append("🥉 はじめての正解")
            player["coin"] = player.get("coin", 0) + 30
            
    # 2. 🥈 がんばりやさん
    if "🥈 がんばりやさん" not in player["badges"]:
        if st.session_state.get("quiz_correct", 0) >= 10:
            player["badges"].append("🥈 がんばりやさん")
            newly_unlocked.append("🥈 がんばりやさん")
            player["coin"] = player.get("coin", 0) + 30

    # 3. 🥇 英語マスター
    if "🥇 英語マスター" not in player["badges"]:
        if st.session_state.get("quiz_correct", 0) >= 100:
            player["badges"].append("🥇 英語マスター")
            newly_unlocked.append("🥇 英語マスター")
            player["coin"] = player.get("coin", 0) + 30

    # 4. 🔥 3日連続
    if "🔥 3日連続" not in player["badges"]:
        record = get_learning_record_summary()
        if record.get("consecutive_study_days", 0) >= 3:
            player["badges"].append("🔥 3日連続")
            newly_unlocked.append("🔥 3日連続")
            player["coin"] = player.get("coin", 0) + 30

    # 5. 💎 PERFECT
    if "💎 PERFECT" not in player["badges"]:
        # 10問クイズを全問正解
        if st.session_state.get("quiz_game_finished") and st.session_state.get("quiz_result_summary"):
            summary = st.session_state.quiz_result_summary
            if summary.get("correct_count", 0) == 10 and summary.get("total_questions", 0) == 10:
                player["badges"].append("💎 PERFECT")
                newly_unlocked.append("💎 PERFECT")
                player["coin"] = player.get("coin", 0) + 30

    # 6. ⭐ レベル5達成
    if "⭐ レベル5達成" not in player["badges"]:
        if player.get("level", 1) >= 5:
            player["badges"].append("⭐ レベル5達成")
            newly_unlocked.append("⭐ レベル5達成")
            player["coin"] = player.get("coin", 0) + 30

    if newly_unlocked:
        if "new_badge_unlocked" not in st.session_state:
            st.session_state.new_badge_unlocked = []
        st.session_state.new_badge_unlocked.extend(newly_unlocked)
        save_player_data()


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
    if not word:
        return
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


def get_base64_audio(file_path: Path):
    """音声ファイルをBase64エンコードして返す。"""
    if not file_path.exists():
        return ""
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


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
    
    # デイリーミッションの更新
    update_daily_mission(is_correct)

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

    check_badges()
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
        check_badges()
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
# 初期化のタイミング（1414行目以降）で実際のラジオボタンの値が同期された後にのみ検知するよう、
# ここではなくラジオボタン定義の直後でチェックを行います。

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
    pending = st.session_state.level_up_pending
    old_lv = pending.get("old", 1)
    new_lv = pending.get("new", 2)
    
    # 演出
    st.balloons()
    st.snow()
    
    # 褒め言葉ランダム
    praise_list = [
        "やったね！！",
        "すごい！！",
        "Excellent!!",
        "Great!!",
        "Amazing!!",
        "よくできました！！"
    ]
    praise_word = random.choice(praise_list)
    
    # レベルアップカード表示
    st.markdown(
        f"""
        <div style="
            background: white;
            border: 4px solid #ff6b9d;
            border-radius: 28px;
            padding: 2rem;
            text-align: center;
            box-shadow: 0 8px 32px rgba(255, 107, 157, 0.2);
            margin: 1.5rem 0;
        ">
            <div style="font-size: 2.5rem; font-weight: 800; color: #ff6b9d; margin-bottom: 1rem;">🎉 LEVEL UP!!</div>
            <div style="font-size: 1.8rem; font-weight: 700; color: #555; margin-bottom: 1rem;">Lv{old_lv} → <span style="color: #ff6b9d; font-size: 2.2rem;">Lv{new_lv}</span></div>
            <div style="font-size: 1.5rem; font-weight: 700; color: #4a90d9; margin-bottom: 1.5rem;">✨ {praise_word}</div>
            <div style="
                background: #fff8e7;
                border: 2px dashed #ffc966;
                border-radius: 15px;
                padding: 0.8rem;
                display: inline-block;
                color: #b8860b;
                font-size: 1.4rem;
                font-weight: 800;
            ">🪙 Coin +50</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================
# 新しいバッジ獲得演出
# ============================================================
if "new_badge_unlocked" in st.session_state and st.session_state.new_badge_unlocked:
    for badge_name in st.session_state.new_badge_unlocked:
        st.balloons()
        st.snow()
        st.toast(f"🏅 新しいバッジ獲得！ {badge_name} 🪙+30 Coin!", icon="🎉")
        
        st.markdown(
            f"""
            <div style="
                background: white;
                border: 4px solid #ffd700;
                border-radius: 28px;
                padding: 2rem;
                text-align: center;
                box-shadow: 0 8px 32px rgba(255, 215, 0, 0.2);
                margin: 1.5rem 0;
            ">
                <div style="font-size: 2.2rem; font-weight: 800; color: #ff9900; margin-bottom: 1rem;">🏅 新しいバッジ獲得！</div>
                <div style="font-size: 2.5rem; font-weight: 800; color: #ff4d4d; margin-bottom: 1.2rem;">{badge_name}</div>
                <div style="
                    background: #fff8e7;
                    border: 2px dashed #ffc966;
                    border-radius: 15px;
                    padding: 0.8rem;
                    display: inline-block;
                    color: #b8860b;
                    font-size: 1.4rem;
                    font-weight: 800;
                ">🪙 Coin +30</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    st.session_state.new_badge_unlocked = []

if st.session_state.get("daily_mission_claimed"):
    st.toast(st.session_state.daily_mission_claimed, icon="🎉")
    st.session_state.daily_mission_claimed = None

# ============================================================
# 今日のミッション
# ============================================================
player = st.session_state.player_data
check_daily_reset() # 表示前に最新の状態に

d_correct = player.get("daily_correct", 0)
d_clear = player.get("daily_clear", 0)
d_claimed = player.get("daily_claimed", [False, False, False])

# ミッション表示用のラベル
m1_label = "5問正解する"
m2_label = "10問クリアする"
m3_label = "20問クリアする"

if st.session_state.elementary_mode:
    m1_label = to_hiragana(m1_label)
    m2_label = to_hiragana(m2_label)
    m3_label = to_hiragana(m3_label)

m1_check = "☑" if d_claimed[0] else "□"
m2_check = "☑" if d_claimed[1] else "□"
m3_check = "☑" if d_claimed[2] else "□"

m1_status = f"{d_correct} / 5" if not d_claimed[0] else "達成！"
m2_status = f"{d_clear} / 10" if not d_claimed[1] else "達成！"
m3_status = f"{d_clear} / 20" if not d_claimed[2] else "達成！"

if st.session_state.elementary_mode:
    m1_status = to_hiragana(m1_status)
    m2_status = to_hiragana(m2_status)
    m3_status = to_hiragana(m3_status)

st.markdown(
    f"""
    <div style="
        background: #fff9e6;
        border: 3px solid #ffcc00;
        border-radius: 24px;
        padding: 1.2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 6px 18px rgba(255, 204, 0, 0.2);
    ">
        <div style="font-size: 1.3rem; font-weight: 800; color: #e6b800; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem;">
            🎯 今日のミッション
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0; border-bottom: 1px dashed #ffcc00; color: #555; font-weight: 700;">
            <div>{m1_check} {m1_label}</div>
            <div style="color: #ff9900;">+20Coin <span style="margin-left: 0.5rem; color: #888; font-size: 0.9rem;">({m1_status})</span></div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0; border-bottom: 1px dashed #ffcc00; color: #555; font-weight: 700;">
            <div>{m2_check} {m2_label}</div>
            <div style="color: #ff9900;">+30Coin <span style="margin-left: 0.5rem; color: #888; font-size: 0.9rem;">({m2_status})</span></div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0; color: #555; font-weight: 700;">
            <div>{m3_check} {m3_label}</div>
            <div style="color: #ff9900;">+50Coin <span style="margin-left: 0.5rem; color: #888; font-size: 0.9rem;">({m3_status})</span></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Player Status & ユーザー情報
# ============================================================
check_badges()
player = st.session_state.player_data

# ユーザー情報カード & 切替ボタン
curr_user_id = st.session_state.get("current_user_id")
user_display_name = get_display_name(curr_user_id) if curr_user_id else "デフォルト"
summary_data = get_learning_record_summary()
learned_count = len(st.session_state.learned_words)
not_learned_count = len(st.session_state.not_learned_words)
total_q = summary_data["total_questions"]
accuracy_pct = summary_data["accuracy"]

st.markdown(
    f"""
    <div style="
        background: #f0f8ff;
        border: 3px solid #4a90d9;
        border-radius: 20px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px rgba(74, 144, 217, 0.15);
    ">
        <div style="font-size: 1.3rem; font-weight: 800; color: #2c3e50; margin-bottom: 0.5rem;">👤 {user_display_name}</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #e6b800; margin-bottom: 0.3rem;">⭐ Lv.{player.get('level', 1)}</div>
        <div style="font-size: 1rem; font-weight: 600; color: #555;">📚 覚えた単語：{learned_count}語</div>
        <div style="font-size: 1rem; font-weight: 600; color: #555;">😅 苦手単語：{not_learned_count}語</div>
        <div style="font-size: 1rem; font-weight: 600; color: #555;">📝 学習数：{total_q}問</div>
        <div style="font-size: 1rem; font-weight: 600; color: #555;">🎯 正答率：{accuracy_pct}%</div>
    </div>
    """,
    unsafe_allow_html=True
)

if st.button("🔄 ユーザー切替 / 変更", key="btn_switch_user_main", use_container_width=True):
    save_last_user_id(None)
    set_active_user(None)
    st.rerun()

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

# ============================================================
# バッジ一覧の表示
# ============================================================
st.subheader(to_hiragana("🏅 バッジ") if st.session_state.elementary_mode else "🏅 バッジ")

badges_def = [
    {"name": "🥉 はじめての正解", "desc": "1問正解"},
    {"name": "🥈 がんばりやさん", "desc": "10問正解"},
    {"name": "🥇 英語マスター", "desc": "100問正解"},
    {"name": "🔥 3日連続", "desc": "3日連続で学習"},
    {"name": "💎 PERFECT", "desc": "10問クイズを全問正解"},
    {"name": "⭐ レベル5達成", "desc": "レベル5到達"}
]

obtained_badges = player.get("badges", [])

badge_cols = st.columns(2)
for idx, b in enumerate(badges_def):
    has_badge = b["name"] in obtained_badges
    status_icon = "✅" if has_badge else "⬜"
    
    desc_text = to_hiragana(b["desc"]) if st.session_state.elementary_mode else b["desc"]
    badge_name_text = to_hiragana(b["name"]) if st.session_state.elementary_mode else b["name"]
    
    bg_style = "linear-gradient(135deg, #fffcf0 0%, #fff8e7 100%)" if has_badge else "#f0f0f0"
    border_color = "#ffd700" if has_badge else "#d3d3d3"
    text_color = "#555" if has_badge else "#888"
    icon_color = "#ff9900" if has_badge else "#aaaaaa"
    box_shadow = "0 6px 18px rgba(255, 215, 0, 0.2)" if has_badge else "none"
    
    with badge_cols[idx % 2]:
        st.markdown(
            f"""
            <div style="
                background: {bg_style};
                border: 3px solid {border_color};
                border-radius: 20px;
                padding: 1rem;
                margin-bottom: 0.8rem;
                box-shadow: {box_shadow};
                display: flex;
                align-items: center;
                justify-content: space-between;
            ">
                <div style="text-align: left;">
                    <div style="font-size: 1.15rem; font-weight: 800; color: {text_color};">{badge_name_text}</div>
                    <div style="font-size: 0.85rem; color: #888888; font-weight: 500;">{desc_text}</div>
                </div>
                <div style="font-size: 1.4rem; font-weight: 800; color: {icon_color};">{status_icon}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

st.markdown("---")

# モード選択
mode_col1, mode_col2 = st.columns(2)
app_modes = ["単語カード", "4択クイズ", "🛒 ショップ"]
study_modes = ["通常モード", "苦手復習モード"]
if st.session_state.elementary_mode:
    app_modes = [to_hiragana(m) for m in app_modes]
    study_modes = [to_hiragana(m) for m in study_modes]

with mode_col1:
    st.radio("アプリのモード", app_modes, horizontal=True, key="app_mode_radio", label_visibility="collapsed")
    # 選択値を内部用の英語/漢字キーに変換
    if st.session_state.app_mode_radio in app_modes:
        idx = app_modes.index(st.session_state.app_mode_radio)
        new_app_mode = ["単語カード", "4択クイズ", "🛒 ショップ"][idx]
        if st.session_state.app_mode != new_app_mode:
            st.session_state.app_mode = new_app_mode
            st.session_state.show_meaning = False
            reset_quiz_state()

with mode_col2:
    st.radio("出題モード", study_modes, horizontal=True, key="study_mode_radio", label_visibility="collapsed")
    if st.session_state.study_mode_radio in study_modes:
        idx = study_modes.index(st.session_state.study_mode_radio)
        new_study_mode = ["通常モード", "苦手復習モード"][idx]
        if st.session_state.study_mode != new_study_mode:
            st.session_state.study_mode = new_study_mode
            st.session_state.used_words = []
            st.session_state.current_word = None
            st.session_state.show_meaning = False
            reset_quiz_state()

# 共通出題関数から現在の単語を保証・取得する
# モードが確定した後に呼び出すことで、初回判定時の不整合を防ぐ
current_english = get_current_word()

def fmt_rec(text):
    return to_hiragana(text) if st.session_state.elementary_mode else text

# 小学生モードON/OFF追加
elem_label = "🎒 小学生モード（ひらがな表示）"
if st.session_state.elementary_mode:
    elem_label = to_hiragana(elem_label)
st.checkbox(elem_label, key="elementary_mode")

record_summary = get_learning_record_summary()

st.markdown(
    f"""
    <div class="record-card">
        <div class="record-title">📈 学習記録</div>
        <div class="record-grid">
            <div class="record-item">今日解いた問題数<strong>{record_summary['today_questions']}問</strong></div>
            <div class="record-item">総問題数<strong>{record_summary['total_questions']}問</strong></div>
            <div class="record-item">正解数<strong>{record_summary['correct']}問</strong></div>
            <div class="record-item">不正解数<strong>{record_summary['wrong']}問</strong></div>
            <div class="record-item">正解率<strong>{record_summary['accuracy']}%</strong></div>
            <div class="record-item">最高コンボ<strong>{record_summary['best_combo']}連続</strong></div>
            <div class="record-item">総学習日数<strong>{record_summary['total_study_days']}日</strong></div>
            <div class="record-item">連続学習日数<strong>{record_summary['consecutive_study_days']}日</strong></div>
            <div class="record-item">総プレイ回数<strong>{record_summary['play_count']}回</strong></div>
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

    if st.session_state.app_mode == "🛒 ショップ":
        show_shop()
    elif current_english is None:
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
                # 単語カードを「クリア」したとみなしてミッション更新（正解ではないが回答扱い）
                update_daily_mission(is_correct=False)
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

            if not st.session_state.quiz_answered:
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
                            btn_key = f"real_btn_{current_english}_{index}_{choice}"

                            # 本物のStreamlitボタンのみを表示する（トリッキーなHTML/JSボタンハックは完全撤廃）
                            if st.button(
                                display_choice,
                                key=btn_key,
                                use_container_width=True,
                                disabled=st.session_state.quiz_answered,
                            ):
                                record_quiz_answer(choice)
                                st.rerun()

            if st.session_state.quiz_answered:
                # 効果音の再生
                if st.session_state.get("pending_audio"):
                    audio_type = st.session_state.pending_audio
                    
                    # 音声ファイルのBase64取得
                    audio_file = APP_DIR / "assets" / ("correct.mp3" if audio_type == "correct" else "wrong.mp3")
                    audio_base64 = get_base64_audio(audio_file)
                    
                    if audio_base64:
                        sound_html = f"""
                        <script>
                        (() => {{
                            const currentWord = "{current_english}";
                            const sessionKey = "sound_played_" + currentWord;
                            
                            if (!sessionStorage.getItem(sessionKey)) {{
                                sessionStorage.setItem(sessionKey, "true");
                                
                                const audio = new Audio("data:audio/mp3;base64,{audio_base64}");
                                audio.play().catch(e => console.error("Audio play failed:", e));
                            }}
                        }})();
                        </script>
                        """
                        st.components.v1.html(sound_html, height=0, width=0)

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
