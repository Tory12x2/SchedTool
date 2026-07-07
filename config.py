import os

from dotenv import load_dotenv


load_dotenv()


def get_int_env(name, default=0):
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return int(value)


# =========================
# 環境変数
# =========================
# Botトークンは直接コードに書かず、.env または環境変数から読み込みます。
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")


# =========================
# Discordサーバー / 通知先
# =========================
# RESULT_CHANNEL_ID:
#   初期状態の通知先チャンネルIDです。未設定の場合はDiscord内の
#   /notification_channel_setting で設定してください。

GUILD_ID = get_int_env("GUILD_ID")
RESULT_CHANNEL_ID = get_int_env("RESULT_CHANNEL_ID")


# =========================
# データ保存
# =========================
# SQLiteの保存先です。

DATABASE_PATH = os.getenv("DATABASE_PATH", "schedule.db")
SCHEDTOOL_LOG_DIR = os.getenv(
    "SCHEDTOOL_LOG_DIR",
    "/data/logs" if DATABASE_PATH.startswith("/data/") else "logs",
)
LOG_RETENTION_DAYS = get_int_env("SCHEDTOOL_LOG_RETENTION_DAYS", 30)


# =========================
# 日程 / UI設定
# =========================
# 回答UIは5日ずつ表示します。
# Discordのボタンは1メッセージ最大5行なので、10日分は5日ずつ2つの入口に分けます。

MAX_DAYS = 10
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


# =========================
# 回答ラベル
# =========================
# ボタンや結果表示の文言を変えたい場合はここを調整します。

STATUS_ORDER = ("available", "maybe", "no")

STATUS_LABELS = {
    "available": "◎",
    "maybe": "△",
    "no": "×",
}

STATUS_NAMES = {
    "available": "参加可能",
    "maybe": "保留",
    "no": "不参加",
}


# =========================
# 月間日程表のメンバーアイコン
# =========================
# 月間日程表では名前の代わりに、この中からメンバーごとに固定アイコンを割り当てます。

MEMBER_ICONS = [
    "🍎", "🍊", "🍋", "🍇", "🍓",
    "🍒", "🍑", "🥝", "🍍", "🥥",
    "🥐", "🍞", "🧀", "🍙", "🍜",
    "🍣", "🍤", "🍰", "🍩", "☕",
    "⚽", "🏀", "🎾", "🎲", "🎧",
    "🎮", "🎹", "🚗", "🚲", "✈️",
]
