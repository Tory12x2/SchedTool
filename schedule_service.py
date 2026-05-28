from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import RESULT_CHANNEL_ID, WEEKDAYS
from database import (
    save_event_dates,
    save_event_settings,
    save_result_message,
    save_schedule_message,
)
from embeds import create_result_embed
from views import OpenScheduleView


# =========================
# 日程調整の作成処理
# =========================
# 手動コマンドと自動投稿の両方から使う共通処理です。


TIMEZONE = ZoneInfo("Asia/Tokyo")


def build_dates(start_date, days):
    dates = []
    current = start_date

    for _ in range(days):
        weekday = WEEKDAYS[current.weekday()]
        dates.append(
            {
                "label": current.strftime("%m/%d") + f"({weekday})",
                "value": current.strftime("%Y%m%d"),
            }
        )
        current += timedelta(days=1)

    return dates


async def create_schedule(client, guild, schedule_channel, event_name, start_date, days):
    event_id = f"{event_name}_{start_date.strftime('%Y%m%d')}"
    dates = build_dates(start_date, days)
    now = datetime.now(TIMEZONE).replace(tzinfo=None)
    deadline_at = start_date - timedelta(days=1)

    if deadline_at <= now:
        deadline_at = now + timedelta(days=1)

    save_event_dates(event_id, dates)
    save_event_settings(event_id, deadline_at.strftime("%Y-%m-%d %H:%M"), closed=False)

    result_channel = client.get_channel(RESULT_CHANNEL_ID)
    if not result_channel:
        raise RuntimeError(
            "通知チャンネルが見つかりません。config.py の RESULT_CHANNEL_ID を確認してください。"
        )

    schedule_message = await schedule_channel.send(
        f"日程調整: {event_id}\n"
        f"締切: {deadline_at.strftime('%Y-%m-%d %H:%M')}\n"
        "参加可否を回答するには、対象の日程ボタンを押してください。",
        view=OpenScheduleView(event_id, dates),
    )
    save_schedule_message(event_id, schedule_channel.id, schedule_message.id)

    result_message = await result_channel.send(
        embed=create_result_embed(guild, event_id, dates),
    )
    save_result_message(event_id, result_channel.id, result_message.id)

    return event_id, dates
