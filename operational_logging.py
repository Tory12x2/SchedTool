import logging
import os
import time
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler

import config


DATABASE_PATH = getattr(config, "DATABASE_PATH", "schedule.db")
SCHEDTOOL_LOG_DIR = os.getenv(
    "SCHEDTOOL_LOG_DIR",
    getattr(
        config,
        "SCHEDTOOL_LOG_DIR",
        "/data/logs" if DATABASE_PATH.startswith("/data/") else "logs",
    ),
)
LOG_RETENTION_DAYS = int(
    os.getenv(
        "SCHEDTOOL_LOG_RETENTION_DAYS",
        getattr(config, "LOG_RETENTION_DAYS", 30),
    )
)


LOGGER_NAME = "schedtool"
_health_logged_dates = set()


def setup_logging():
    os.makedirs(SCHEDTOOL_LOG_DIR, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = TimedRotatingFileHandler(
        os.path.join(SCHEDTOOL_LOG_DIR, "schedtool.log"),
        when="midnight",
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.INFO)
    discord_logger.addHandler(file_handler)

    return logger


def get_logger():
    return logging.getLogger(LOGGER_NAME)


def log_info(event, **fields):
    get_logger().info("%s %s", event, format_fields(fields))


def log_warning(event, **fields):
    get_logger().warning("%s %s", event, format_fields(fields))


def log_error(event, error=None, **fields):
    if error is not None:
        fields["error_type"] = error.__class__.__name__
        fields["error"] = str(error)[:300]
    get_logger().error("%s %s", event, format_fields(fields), exc_info=error)


@contextmanager
def timed_log(event, **fields):
    started = time.monotonic()
    try:
        yield
    except Exception as error:
        fields["elapsed_ms"] = elapsed_ms(started)
        log_error(f"{event}.failed", error, **fields)
        raise
    fields["elapsed_ms"] = elapsed_ms(started)
    log_info(f"{event}.completed", **fields)


def maybe_log_daily_health(client, today):
    key = today.isoformat()
    if key in _health_logged_dates:
        return
    _health_logged_dates.add(key)
    log_health_snapshot(client, key)


def log_health_snapshot(client, date_label):
    import sqlite3

    db_size_bytes = os.path.getsize(DATABASE_PATH) if os.path.exists(DATABASE_PATH) else 0
    metrics = {
        "date": date_label,
        "guilds": len(client.guilds),
        "cached_members": sum(
            1 for guild in client.guilds for member in guild.members if not member.bot
        ),
        "db_size_kb": round(db_size_bytes / 1024, 1),
    }

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        for table, label in (
            ("schedules", "events"),
            ("event_dates", "event_dates"),
            ("availability", "answers"),
            ("member_icons", "icons"),
            ("event_participants", "participant_rows"),
        ):
            metrics[label] = count_rows(cursor, table)
        metrics["answer_users"] = count_distinct(cursor, "availability", "user_id")
    finally:
        conn.close()

    log_info("health.daily", **metrics)


def count_rows(cursor, table):
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except Exception:
        return 0


def count_distinct(cursor, table, column):
    try:
        cursor.execute(f"SELECT COUNT(DISTINCT {column}) FROM {table}")
        return cursor.fetchone()[0]
    except Exception:
        return 0


def elapsed_ms(started):
    return round((time.monotonic() - started) * 1000, 1)


def format_fields(fields):
    safe_fields = {
        key: value
        for key, value in fields.items()
        if value is not None and "token" not in key.lower()
    }
    return " ".join(f"{key}={format_value(value)}" for key, value in safe_fields.items())


def format_value(value):
    text = str(value).replace("\n", " ")[:300]
    if " " in text:
        return repr(text)
    return text
