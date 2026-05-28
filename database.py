import sqlite3
from datetime import datetime

from config import DATABASE_PATH, MEMBER_ICONS, WEEKDAYS


# =========================
# SQLite接続
# =========================
# このファイルは「保存・取得・削除」だけを担当します。

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()


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
        CREATE TABLE IF NOT EXISTS reminder_logs (
            event_id TEXT,
            date TEXT,
            PRIMARY KEY (event_id, date)
        )
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

    conn.commit()


def save_schedule_message(event_id, channel_id, message_id):
    cursor.execute(
        """
        INSERT OR REPLACE INTO schedules
        VALUES (?, ?, ?)
        """,
        (event_id, channel_id, message_id),
    )
    conn.commit()


def get_schedule_message(event_id):
    cursor.execute(
        """
        SELECT channel_id, message_id
        FROM schedules
        WHERE event_id = ?
        """,
        (event_id,),
    )
    return cursor.fetchone()


def save_result_message(event_id, channel_id, message_id):
    cursor.execute(
        """
        INSERT OR REPLACE INTO result_messages
        VALUES (?, ?, ?)
        """,
        (event_id, channel_id, message_id),
    )
    conn.commit()


def get_result_message(event_id):
    cursor.execute(
        """
        SELECT channel_id, message_id
        FROM result_messages
        WHERE event_id = ?
        """,
        (event_id,),
    )
    return cursor.fetchone()


def save_schedule_settings(event_name, days):
    cursor.execute(
        """
        INSERT OR REPLACE INTO schedule_settings
        VALUES (1, ?, ?)
        """,
        (event_name, days),
    )
    conn.commit()


def get_schedule_settings():
    cursor.execute(
        """
        SELECT event_name, days
        FROM schedule_settings
        WHERE id = 1
        """
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        "event_name": row[0],
        "days": row[1],
    }


def save_auto_schedule_settings(channel_id, next_start_date, lead_days):
    cursor.execute(
        """
        INSERT OR REPLACE INTO auto_schedule_settings
        VALUES (1, 1, ?, ?, ?)
        """,
        (channel_id, next_start_date, lead_days),
    )
    conn.commit()


def get_auto_schedule_settings():
    cursor.execute(
        """
        SELECT active, channel_id, next_start_date, lead_days
        FROM auto_schedule_settings
        WHERE id = 1
        """
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


def stop_auto_schedule():
    cursor.execute(
        """
        UPDATE auto_schedule_settings
        SET active = 0
        WHERE id = 1
        """
    )
    conn.commit()


def update_auto_schedule_next_start(next_start_date):
    cursor.execute(
        """
        UPDATE auto_schedule_settings
        SET next_start_date = ?
        WHERE id = 1
        """,
        (next_start_date,),
    )
    conn.commit()


def save_event_settings(event_id, deadline_at, closed=False):
    cursor.execute(
        """
        INSERT OR REPLACE INTO event_settings
        VALUES (?, ?, ?)
        """,
        (event_id, deadline_at, int(closed)),
    )
    conn.commit()


def get_event_settings(event_id):
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


def mark_event_closed(event_id):
    cursor.execute(
        """
        UPDATE event_settings
        SET closed = 1
        WHERE event_id = ?
        """,
        (event_id,),
    )
    conn.commit()


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
            "event_id": row[0],
            "deadline_at": row[1],
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


def save_reminder_settings(days_before, hour, comment):
    cursor.execute(
        """
        INSERT OR REPLACE INTO reminder_settings
        VALUES (1, ?, ?, ?)
        """,
        (days_before, hour, comment),
    )
    conn.commit()


def get_reminder_settings():
    cursor.execute(
        """
        SELECT days_before, hour, comment
        FROM reminder_settings
        WHERE id = 1
        """
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


def get_unnotified_event_dates(date):
    cursor.execute(
        """
        SELECT event_id, date
        FROM event_dates
        WHERE date = ?
        AND NOT EXISTS (
            SELECT 1
            FROM reminder_logs
            WHERE reminder_logs.event_id = event_dates.event_id
            AND reminder_logs.date = event_dates.date
        )
        ORDER BY event_id
        """,
        (date,),
    )
    return [
        {
            "event_id": row[0],
            "date": row[1],
        }
        for row in cursor.fetchall()
    ]


def mark_reminder_sent(event_id, date):
    cursor.execute(
        """
        INSERT OR IGNORE INTO reminder_logs
        VALUES (?, ?)
        """,
        (event_id, date),
    )
    conn.commit()


def save_event_dates(event_id, dates):
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


def get_event_list():
    cursor.execute(
        """
        SELECT DISTINCT event_id
        FROM event_dates
        ORDER BY event_id
        """
    )
    return [row[0] for row in cursor.fetchall()]


def get_dates(event_id):
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


def delete_event(event_id):
    for table in (
        "availability",
        "schedules",
        "result_messages",
        "event_dates",
        "event_settings",
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


def get_users(event_id, date, status=None):
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


def set_user_status(event_id, date, user_id, status):
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
