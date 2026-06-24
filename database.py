import os
import sqlite3
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from config import GUILD_ID, DATABASE_PATH, MEMBER_ICONS, RESULT_CHANNEL_ID, WEEKDAYS


# =========================
# SQLite接続
# =========================
# このファイルは「保存・取得・削除」だけを担当します。

database_dir = os.path.dirname(DATABASE_PATH)
if database_dir:
    os.makedirs(database_dir, exist_ok=True)

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")

TIMEZONE = ZoneInfo("Asia/Tokyo")
DATE_GROUP_SIZE = 5


def to_storage_event_id(guild_id, event_id):
    prefix = f"{guild_id}:"
    if str(event_id).startswith(prefix):
        return event_id
    return f"{guild_id}:{event_id}"


def display_event_id(event_id):
    text = str(event_id)
    if ":" not in text:
        return text
    return text.split(":", 1)[1]


def initialize_database():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            event_id TEXT PRIMARY KEY,
            channel_id INTEGER,
            message_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS result_messages (
            event_id TEXT PRIMARY KEY,
            channel_id INTEGER,
            message_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS availability (
            event_id TEXT,
            date TEXT,
            user_id INTEGER,
            status TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_dates (
            event_id TEXT,
            date TEXT,
            PRIMARY KEY (event_id, date)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_settings (
            event_id TEXT PRIMARY KEY,
            deadline_at TEXT,
            closed INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_group_settings (
            event_id TEXT,
            group_index INTEGER,
            deadline_at TEXT,
            closed INTEGER,
            PRIMARY KEY (event_id, group_index)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            event_name TEXT,
            days INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_schedule_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            active INTEGER,
            channel_id INTEGER,
            next_start_date TEXT,
            lead_days INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS member_icons (
            user_id INTEGER PRIMARY KEY,
            icon TEXT UNIQUE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            days_before INTEGER,
            hour INTEGER,
            comment TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            result_channel_id INTEGER,
            mention_enabled INTEGER,
            participant_role_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            result_channel_id INTEGER,
            mention_enabled INTEGER,
            participant_role_id INTEGER,
            event_name TEXT,
            days INTEGER,
            auto_active INTEGER,
            auto_channel_id INTEGER,
            auto_next_start_date TEXT,
            auto_lead_days INTEGER,
            reminder_days_before INTEGER,
            reminder_hour INTEGER,
            reminder_comment TEXT
        )
        """
    )

    cursor.execute("PRAGMA table_info(bot_settings)")
    bot_setting_columns = {row[1] for row in cursor.fetchall()}
    if "mention_enabled" not in bot_setting_columns:
        cursor.execute(
            """
            ALTER TABLE bot_settings
            ADD COLUMN mention_enabled INTEGER DEFAULT 1
            """
        )
    if "participant_role_id" not in bot_setting_columns:
        cursor.execute(
            """
            ALTER TABLE bot_settings
            ADD COLUMN participant_role_id INTEGER
            """
        )

    cursor.execute(
        """
        INSERT OR IGNORE INTO bot_settings (
            id,
            result_channel_id,
            mention_enabled,
            participant_role_id
        )
        VALUES (1, ?, 1, NULL)
        """,
        (RESULT_CHANNEL_ID,),
    )

    cursor.execute("PRAGMA table_info(reminder_settings)")
    reminder_columns = {row[1] for row in cursor.fetchall()}
    if "comment" not in reminder_columns:
        cursor.execute(
            """
            ALTER TABLE reminder_settings
            ADD COLUMN comment TEXT DEFAULT ''
            """
        )

    cursor.execute(
        """
        INSERT OR IGNORE INTO reminder_settings
        VALUES (1, 1, 21, '')
        """
    )

    migrate_legacy_data_to_default_guild()
    initialize_default_guild_settings()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_logs (
            event_id TEXT,
            date TEXT,
            PRIMARY KEY (event_id, date)
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_availability_event_date_status
        ON availability (event_id, date, status)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_availability_event_date_user
        ON availability (event_id, date, user_id)
        """
    )

    # 以前の availability だけのデータが残っていても、日付一覧に移せるようにします。
    cursor.execute(
        """
        INSERT OR IGNORE INTO event_dates
        SELECT DISTINCT event_id, date
        FROM availability
        """
    )

    initialize_event_group_settings()
    refresh_open_event_group_deadlines()

    conn.commit()


def build_group_deadline(date_value):
    date_obj = datetime.strptime(date_value, "%Y%m%d")
    today = datetime.now(TIMEZONE).date()

    if date_obj.date() <= today:
        deadline_at = datetime.combine(today, datetime.max.time()).replace(
            microsecond=0,
            second=0,
        )
    else:
        deadline_at = date_obj - timedelta(days=1)

    return deadline_at.strftime("%Y-%m-%d %H:%M")


def migrate_legacy_data_to_default_guild():
    for table in (
        "schedules",
        "result_messages",
        "availability",
        "event_dates",
        "event_settings",
        "event_group_settings",
        "reminder_logs",
    ):
        cursor.execute(
            f"""
            UPDATE {table}
            SET event_id = ? || ':' || event_id
            WHERE instr(event_id, ':') = 0
            """,
            (GUILD_ID,),
        )


def initialize_default_guild_settings():
    cursor.execute(
        """
        SELECT result_channel_id, mention_enabled, participant_role_id
        FROM bot_settings
        WHERE id = 1
        """
    )
    bot_row = cursor.fetchone()
    result_channel_id = bot_row[0] if bot_row else RESULT_CHANNEL_ID
    mention_enabled = bot_row[1] if bot_row else 1
    participant_role_id = bot_row[2] if bot_row else None

    cursor.execute(
        """
        SELECT event_name, days
        FROM schedule_settings
        WHERE id = 1
        """
    )
    schedule_row = cursor.fetchone()
    event_name = schedule_row[0] if schedule_row else None
    days = schedule_row[1] if schedule_row else None

    cursor.execute(
        """
        SELECT active, channel_id, next_start_date, lead_days
        FROM auto_schedule_settings
        WHERE id = 1
        """
    )
    auto_row = cursor.fetchone()
    auto_active = auto_row[0] if auto_row else 0
    auto_channel_id = auto_row[1] if auto_row else None
    auto_next_start_date = auto_row[2] if auto_row else None
    auto_lead_days = auto_row[3] if auto_row else None

    cursor.execute(
        """
        SELECT days_before, hour, comment
        FROM reminder_settings
        WHERE id = 1
        """
    )
    reminder_row = cursor.fetchone()
    reminder_days_before = reminder_row[0] if reminder_row else 1
    reminder_hour = reminder_row[1] if reminder_row else 21
    reminder_comment = reminder_row[2] if reminder_row else ""

    cursor.execute(
        """
        INSERT OR IGNORE INTO guild_settings
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            GUILD_ID,
            result_channel_id,
            mention_enabled,
            participant_role_id,
            event_name,
            days,
            auto_active,
            auto_channel_id,
            auto_next_start_date,
            auto_lead_days,
            reminder_days_before,
            reminder_hour,
            reminder_comment,
        ),
    )


def ensure_guild_settings(guild_id):
    cursor.execute(
        """
        INSERT OR IGNORE INTO guild_settings
        VALUES (?, ?, 1, NULL, NULL, NULL, 0, NULL, NULL, NULL, 1, 21, '')
        """,
        (guild_id, RESULT_CHANNEL_ID),
    )
    conn.commit()


def initialize_event_group_settings():
    cursor.execute(
        """
        SELECT DISTINCT event_id
        FROM event_dates
        """
    )
    event_ids = [row[0] for row in cursor.fetchall()]

    for event_id in event_ids:
        cursor.execute(
            """
            SELECT 1
            FROM event_group_settings
            WHERE event_id = ?
            LIMIT 1
            """,
            (event_id,),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            SELECT date
            FROM event_dates
            WHERE event_id = ?
            ORDER BY date
            """,
            (event_id,),
        )
        dates = [row[0] for row in cursor.fetchall()]

        for group_index, start in enumerate(range(0, len(dates), DATE_GROUP_SIZE)):
            deadline_at = build_group_deadline(dates[start])
            cursor.execute(
                """
                INSERT OR IGNORE INTO event_group_settings
                VALUES (?, ?, ?, 0)
                """,
                (event_id, group_index, deadline_at),
            )


def refresh_open_event_group_deadlines():
    cursor.execute(
        """
        SELECT DISTINCT event_id
        FROM event_group_settings
        """
    )
    event_ids = [row[0] for row in cursor.fetchall()]

    for event_id in event_ids:
        cursor.execute(
            """
            SELECT date
            FROM event_dates
            WHERE event_id = ?
            ORDER BY date
            """,
            (event_id,),
        )
        dates = [row[0] for row in cursor.fetchall()]

        for group_index, start in enumerate(range(0, len(dates), DATE_GROUP_SIZE)):
            deadline_at = build_group_deadline(dates[start])
            cursor.execute(
                """
                UPDATE event_group_settings
                SET deadline_at = ?
                WHERE event_id = ?
                AND group_index = ?
                AND closed = 0
                """,
                (deadline_at, event_id, group_index),
            )

        cursor.execute(
            """
            SELECT MAX(deadline_at)
            FROM event_group_settings
            WHERE event_id = ?
            """,
            (event_id,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            cursor.execute(
                """
                UPDATE event_settings
                SET deadline_at = ?
                WHERE event_id = ?
                AND closed = 0
                """,
                (row[0], event_id),
            )


def save_schedule_message(event_id, channel_id, message_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        INSERT OR REPLACE INTO schedules
        VALUES (?, ?, ?)
        """,
        (event_id, channel_id, message_id),
    )
    conn.commit()


def get_schedule_message(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        SELECT channel_id, message_id
        FROM schedules
        WHERE event_id = ?
        """,
        (event_id,),
    )
    return cursor.fetchone()


def get_schedule_messages():
    cursor.execute(
        """
        SELECT event_id, channel_id, message_id
        FROM schedules
        ORDER BY event_id
        """
    )
    return [
        {
            "guild_id": int(str(row[0]).split(":", 1)[0]) if ":" in str(row[0]) else GUILD_ID,
            "event_id": display_event_id(row[0]),
            "channel_id": row[1],
            "message_id": row[2],
        }
        for row in cursor.fetchall()
    ]


def save_result_message(event_id, channel_id, message_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        INSERT OR REPLACE INTO result_messages
        VALUES (?, ?, ?)
        """,
        (event_id, channel_id, message_id),
    )
    conn.commit()


def get_result_message(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        SELECT channel_id, message_id
        FROM result_messages
        WHERE event_id = ?
        """,
        (event_id,),
    )
    return cursor.fetchone()


def save_schedule_settings(event_name, days, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET event_name = ?, days = ?
        WHERE guild_id = ?
        """,
        (event_name, days, guild_id),
    )
    conn.commit()


def get_schedule_settings(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        SELECT event_name, days
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    if not row or not row[0] or not row[1]:
        return None

    return {
        "event_name": row[0],
        "days": row[1],
    }


def save_auto_schedule_settings(channel_id, next_start_date, lead_days, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET auto_active = 1,
            auto_channel_id = ?,
            auto_next_start_date = ?,
            auto_lead_days = ?
        WHERE guild_id = ?
        """,
        (channel_id, next_start_date, lead_days, guild_id),
    )
    conn.commit()


def get_auto_schedule_settings(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        SELECT auto_active, auto_channel_id, auto_next_start_date, auto_lead_days
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        "active": bool(row[0]),
        "channel_id": row[1],
        "next_start_date": row[2],
        "lead_days": row[3],
    }


def get_active_auto_schedule_settings():
    cursor.execute(
        """
        SELECT guild_id, auto_active, auto_channel_id, auto_next_start_date, auto_lead_days
        FROM guild_settings
        WHERE auto_active = 1
        """
    )
    return [
        {
            "guild_id": row[0],
            "active": bool(row[1]),
            "channel_id": row[2],
            "next_start_date": row[3],
            "lead_days": row[4],
        }
        for row in cursor.fetchall()
    ]


def stop_auto_schedule(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET auto_active = 0
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    conn.commit()


def update_auto_schedule_next_start(next_start_date, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET auto_next_start_date = ?
        WHERE guild_id = ?
        """,
        (next_start_date, guild_id),
    )
    conn.commit()


def save_event_settings(event_id, deadline_at, closed=False, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        INSERT OR REPLACE INTO event_settings
        VALUES (?, ?, ?)
        """,
        (event_id, deadline_at, int(closed)),
    )
    conn.commit()


def save_event_group_settings(event_id, group_index, deadline_at, closed=False, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        INSERT OR REPLACE INTO event_group_settings
        VALUES (?, ?, ?, ?)
        """,
        (event_id, group_index, deadline_at, int(closed)),
    )
    conn.commit()


def get_event_settings(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        SELECT deadline_at, closed
        FROM event_settings
        WHERE event_id = ?
        """,
        (event_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        "deadline_at": row[0],
        "closed": bool(row[1]),
    }


def get_event_group_settings(event_id, group_index, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        SELECT deadline_at, closed
        FROM event_group_settings
        WHERE event_id = ?
        AND group_index = ?
        """,
        (event_id, group_index),
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        "deadline_at": row[0],
        "closed": bool(row[1]),
    }


def mark_event_closed(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        UPDATE event_settings
        SET closed = 1
        WHERE event_id = ?
        """,
        (event_id,),
    )
    conn.commit()


def mark_event_group_closed(event_id, group_index, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        UPDATE event_group_settings
        SET closed = 1
        WHERE event_id = ?
        AND group_index = ?
        """,
        (event_id, group_index),
    )
    conn.commit()


def are_all_event_groups_closed(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM event_group_settings
        WHERE event_id = ?
        AND closed = 0
        """,
        (event_id,),
    )
    return cursor.fetchone()[0] == 0


def get_open_events_with_deadlines():
    cursor.execute(
        """
        SELECT event_id, deadline_at
        FROM event_settings
        WHERE closed = 0
        ORDER BY deadline_at
        """
    )
    return [
        {
            "guild_id": int(str(row[0]).split(":", 1)[0]) if ":" in str(row[0]) else GUILD_ID,
            "event_id": display_event_id(row[0]),
            "deadline_at": row[1],
        }
        for row in cursor.fetchall()
    ]


def get_open_event_groups_with_deadlines():
    cursor.execute(
        """
        SELECT event_id, group_index, deadline_at
        FROM event_group_settings
        WHERE closed = 0
        ORDER BY deadline_at
        """
    )
    return [
        {
            "guild_id": int(str(row[0]).split(":", 1)[0]) if ":" in str(row[0]) else GUILD_ID,
            "event_id": display_event_id(row[0]),
            "group_index": row[1],
            "deadline_at": row[2],
        }
        for row in cursor.fetchall()
    ]


def get_member_icon(user_id):
    cursor.execute(
        """
        SELECT icon
        FROM member_icons
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        """
        SELECT icon
        FROM member_icons
        """
    )
    used_icons = {row[0] for row in cursor.fetchall()}

    icon = None
    for candidate in MEMBER_ICONS:
        if candidate not in used_icons:
            icon = candidate
            break

    if icon is None:
        icon = f"#{len(used_icons) + 1}"

    cursor.execute(
        """
        INSERT INTO member_icons
        VALUES (?, ?)
        """,
        (user_id, icon),
    )
    conn.commit()
    return icon


def set_member_icon(user_id, icon):
    cursor.execute(
        """
        SELECT user_id
        FROM member_icons
        WHERE icon = ?
        AND user_id != ?
        """,
        (icon, user_id),
    )
    row = cursor.fetchone()
    if row:
        return False

    cursor.execute(
        """
        INSERT OR REPLACE INTO member_icons
        VALUES (?, ?)
        """,
        (user_id, icon),
    )
    conn.commit()
    return True


def save_reminder_settings(days_before, hour, comment, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET reminder_days_before = ?,
            reminder_hour = ?,
            reminder_comment = ?
        WHERE guild_id = ?
        """,
        (days_before, hour, comment, guild_id),
    )
    conn.commit()


def save_result_channel_id(channel_id, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET result_channel_id = ?
        WHERE guild_id = ?
        """,
        (channel_id, guild_id),
    )
    conn.commit()


def get_result_channel_id(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        SELECT result_channel_id
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    if not row:
        return RESULT_CHANNEL_ID
    return row[0]


def save_notification_mention_enabled(enabled, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET mention_enabled = ?
        WHERE guild_id = ?
        """,
        (int(enabled), guild_id),
    )
    conn.commit()


def save_participant_role_id(role_id, guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        UPDATE guild_settings
        SET participant_role_id = ?
        WHERE guild_id = ?
        """,
        (role_id, guild_id),
    )
    conn.commit()


def get_participant_role_id(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        SELECT participant_role_id
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return row[0]


def get_notification_mention_enabled(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        SELECT mention_enabled
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    if not row:
        return True
    return bool(row[0])


def get_reminder_settings(guild_id=GUILD_ID):
    ensure_guild_settings(guild_id)
    cursor.execute(
        """
        SELECT reminder_days_before, reminder_hour, reminder_comment
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    if not row:
        return {
            "days_before": 1,
            "hour": 21,
            "comment": "",
        }

    return {
        "days_before": row[0],
        "hour": row[1],
        "comment": row[2] or "",
    }


def get_unnotified_event_dates(date, guild_id=None):
    prefix_filter = f"{guild_id}:%" if guild_id is not None else "%"
    cursor.execute(
        """
        SELECT event_id, date
        FROM event_dates
        WHERE date = ?
        AND event_id LIKE ?
        AND NOT EXISTS (
            SELECT 1
            FROM reminder_logs
            WHERE reminder_logs.event_id = event_dates.event_id
            AND reminder_logs.date = event_dates.date
        )
        ORDER BY event_id
        """,
        (date, prefix_filter),
    )
    return [
        {
            "guild_id": int(str(row[0]).split(":", 1)[0]) if ":" in str(row[0]) else GUILD_ID,
            "event_id": display_event_id(row[0]),
            "date": row[1],
        }
        for row in cursor.fetchall()
    ]


def mark_reminder_sent(event_id, date, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        INSERT OR IGNORE INTO reminder_logs
        VALUES (?, ?)
        """,
        (event_id, date),
    )
    conn.commit()


def save_event_dates(event_id, dates, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute("DELETE FROM availability WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM event_dates WHERE event_id = ?", (event_id,))

    for date in dates:
        cursor.execute(
            """
            INSERT OR REPLACE INTO event_dates
            VALUES (?, ?)
            """,
            (event_id, date["value"]),
        )

    conn.commit()


def get_event_list(guild_id=GUILD_ID):
    prefix_filter = f"{guild_id}:%"
    cursor.execute(
        """
        SELECT DISTINCT event_id
        FROM event_dates
        WHERE event_id LIKE ?
        ORDER BY event_id
        """,
        (prefix_filter,),
    )
    return [display_event_id(row[0]) for row in cursor.fetchall()]


def get_latest_event_period(event_name, guild_id=GUILD_ID):
    guild_prefix = f"{guild_id}:"
    event_prefix = f"{event_name}_"
    cursor.execute(
        """
        SELECT event_id, date
        FROM event_dates
        WHERE event_id LIKE ?
        ORDER BY event_id, date
        """,
        (f"{guild_prefix}%",),
    )

    periods = {}
    for stored_event_id, date_value in cursor.fetchall():
        event_id = display_event_id(stored_event_id)
        if not event_id.startswith(event_prefix):
            continue

        start_text = event_id[len(event_prefix):]
        if len(start_text) != 8 or not start_text.isdigit():
            continue

        periods.setdefault(event_id, []).append(date_value)

    if not periods:
        return None

    latest_event_id, latest_dates = max(
        periods.items(),
        key=lambda item: max(item[1]),
    )
    latest_dates = sorted(set(latest_dates))
    last_date = datetime.strptime(latest_dates[-1], "%Y%m%d")
    next_start_date = last_date + timedelta(days=1)

    return {
        "event_id": latest_event_id,
        "days": len(latest_dates),
        "start_date": latest_dates[0],
        "end_date": latest_dates[-1],
        "next_start_date": next_start_date.strftime("%Y-%m-%d"),
    }


def get_dates(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        SELECT DISTINCT date
        FROM event_dates
        WHERE event_id = ?
        ORDER BY date
        """,
        (event_id,),
    )

    dates = []
    for (value,) in cursor.fetchall():
        date_obj = datetime.strptime(value, "%Y%m%d")
        weekday = WEEKDAYS[date_obj.weekday()]
        dates.append(
            {
                "label": date_obj.strftime("%m/%d") + f"({weekday})",
                "value": value,
            }
        )

    return dates


def delete_event(event_id, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    for table in (
        "availability",
        "schedules",
        "result_messages",
        "event_dates",
        "event_settings",
        "event_group_settings",
        "reminder_logs",
    ):
        cursor.execute(
            f"""
            DELETE FROM {table}
            WHERE event_id = ?
            """,
            (event_id,),
        )

    conn.commit()


def get_users(event_id, date, status=None, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    if status is None:
        cursor.execute(
            """
            SELECT user_id
            FROM availability
            WHERE event_id = ?
            AND date = ?
            """,
            (event_id, date),
        )
    else:
        cursor.execute(
            """
            SELECT user_id
            FROM availability
            WHERE event_id = ?
            AND date = ?
            AND status = ?
            """,
            (event_id, date, status),
        )

    return {row[0] for row in cursor.fetchall()}


def set_user_status(event_id, date, user_id, status, guild_id=GUILD_ID):
    event_id = to_storage_event_id(guild_id, event_id)
    cursor.execute(
        """
        DELETE FROM availability
        WHERE event_id = ?
        AND date = ?
        AND user_id = ?
        """,
        (event_id, date, user_id),
    )

    cursor.execute(
        """
        INSERT INTO availability
        VALUES (?, ?, ?, ?)
        """,
        (event_id, date, user_id, status),
    )

    conn.commit()


initialize_database()
