from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import WEEKDAYS
from database import (
    get_result_channel_id,
    initialize_event_participants,
    save_result_channel_id,
    save_event_dates,
    save_event_group_settings,
    save_event_settings,
    save_result_message,
    save_schedule_message,
)
from embeds import create_result_embed
from participants import get_participant_member_ids, is_participant_role_missing
from views import OpenScheduleView


# =========================
# 日程調整の作成処理
# =========================
# 手動コマンドと自動投稿の両方から使う共通処理です。


TIMEZONE = ZoneInfo("Asia/Tokyo")
DATE_GROUP_SIZE = 5


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


def split_dates(dates, size=DATE_GROUP_SIZE):
    return [dates[index : index + size] for index in range(0, len(dates), size)]


def build_deadline_at(first_date_value):
    first_date = datetime.strptime(first_date_value, "%Y%m%d")
    today = datetime.now(TIMEZONE).date()

    if first_date.date() <= today:
        return datetime.combine(today, datetime.max.time()).replace(
            microsecond=0,
            second=0,
        )

    return first_date - timedelta(days=1)


def build_deadline_text():
    return "各日程の2日前24時（開始日が当日の場合は当日23:59）"


async def create_schedule(client, guild, schedule_channel, event_name, start_date, days):
    if is_participant_role_missing(guild):
        raise RuntimeError(
            "設定されている参加予定者ロールが見つかりません。"
            "/participant_role_setting で再設定するか、"
            "/participant_role_clear で全メンバー対象に戻してください。"
        )

    guild_id = guild.id
    event_id = f"{event_name}_{start_date.strftime('%Y%m%d')}"
    dates = build_dates(start_date, days)
    date_groups = split_dates(dates)
    deadlines = [
        build_deadline_at(date_group[0]["value"])
        for date_group in date_groups
        if date_group
    ]
    final_deadline_at = max(deadlines)

    save_event_dates(event_id, dates, guild_id)
    initialize_event_participants(
        event_id,
        get_participant_member_ids(guild),
        guild_id,
    )
    save_event_settings(
        event_id,
        final_deadline_at.strftime("%Y-%m-%d %H:%M"),
        closed=False,
        guild_id=guild_id,
    )

    for group_index, deadline_at in enumerate(deadlines):
        save_event_group_settings(
            event_id,
            group_index,
            deadline_at.strftime("%Y-%m-%d %H:%M"),
            closed=False,
            guild_id=guild_id,
        )

    result_channel_id = get_result_channel_id(guild_id)
    result_channel = client.get_channel(result_channel_id) if result_channel_id else None
    if not result_channel:
        if result_channel_id:
            raise RuntimeError(
                "通知チャンネルが見つかりません。/notification_channel_setting で通知先を設定してください。"
            )

        save_result_channel_id(schedule_channel.id, guild_id)
        result_channel = schedule_channel

    if not result_channel:
        raise RuntimeError(
            "通知チャンネルが見つかりません。/notification_channel_setting で通知先を設定してください。"
        )

    schedule_message = await schedule_channel.send(
        f"日程調整: {event_id}\n"
        f"締切: {build_deadline_text()}\n"
        "参加可否を回答するには、対象の日程ボタンを押してください。",
        view=OpenScheduleView(event_id, guild_id, dates),
    )
    save_schedule_message(event_id, schedule_channel.id, schedule_message.id, guild_id)

    result_message = await result_channel.send(
        embed=create_result_embed(guild, event_id, dates),
    )
    save_result_message(event_id, result_channel.id, result_message.id, guild_id)

    return event_id, dates
