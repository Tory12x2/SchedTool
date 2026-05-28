import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from close_service import close_schedule
from config import GUILD_ID, RESULT_CHANNEL_ID, WEEKDAYS
from database import (
    get_auto_schedule_settings,
    get_open_events_with_deadlines,
    get_reminder_settings,
    get_schedule_settings,
    get_unnotified_event_dates,
    get_users,
    mark_reminder_sent,
    update_auto_schedule_next_start,
)
from schedule_service import create_schedule


# =========================
# 自動日程調整
# =========================
# /auto_schedule_start で保存した設定を見て、開始日の指定日前に自動投稿します。


TIMEZONE = ZoneInfo("Asia/Tokyo")
CHECK_INTERVAL_SECONDS = 60 * 60


async def auto_schedule_loop(client):
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            await run_auto_schedule_once(client)
            await run_deadline_close_once(client)
            await run_available_day_reminder_once(client)
        except Exception as error:
            print(f"自動日程調整エラー: {error}")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def run_auto_schedule_once(client):
    auto_settings = get_auto_schedule_settings()
    schedule_settings = get_schedule_settings()

    if not auto_settings or not auto_settings["active"] or not schedule_settings:
        return

    today = datetime.now(TIMEZONE).date()
    next_start_date = datetime.strptime(
        auto_settings["next_start_date"],
        "%Y-%m-%d",
    ).date()
    post_date = next_start_date - timedelta(days=auto_settings["lead_days"])

    if today < post_date:
        return

    guild = client.get_guild(GUILD_ID)
    channel = client.get_channel(auto_settings["channel_id"])
    if not guild or not channel:
        return

    await create_schedule(
        client,
        guild,
        channel,
        schedule_settings["event_name"],
        datetime.combine(next_start_date, datetime.min.time()),
        schedule_settings["days"],
    )

    following_start_date = next_start_date + timedelta(days=schedule_settings["days"])
    update_auto_schedule_next_start(following_start_date.strftime("%Y-%m-%d"))


async def run_deadline_close_once(client):
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    now = datetime.now(TIMEZONE)

    for event in get_open_events_with_deadlines():
        deadline_at = datetime.strptime(event["deadline_at"], "%Y-%m-%d %H:%M")
        deadline_at = deadline_at.replace(tzinfo=TIMEZONE)

        if now >= deadline_at:
            await close_schedule(client, guild, event["event_id"])


async def run_available_day_reminder_once(client):
    reminder_settings = get_reminder_settings()
    now = datetime.now(TIMEZONE)

    if now.hour < reminder_settings["hour"]:
        return

    target_date = now.date() + timedelta(days=reminder_settings["days_before"])
    target_value = target_date.strftime("%Y%m%d")

    channel = client.get_channel(RESULT_CHANNEL_ID)
    if not channel:
        return

    for event in get_unnotified_event_dates(target_value):
        available_users = get_users(
            event["event_id"],
            event["date"],
            "available",
        )

        if available_users:
            weekday = WEEKDAYS[target_date.weekday()]
            label = target_date.strftime("%m/%d") + f"({weekday})"
            mentions = " ".join(f"<@{user_id}>" for user_id in sorted(available_users))
            comment = reminder_settings["comment"]
            comment_line = f"\n{comment}" if comment else ""

            await channel.send(
                f"参加可能日のお知らせ\n"
                f"イベント: {event['event_id']}\n"
                f"日程: {label}\n"
                f"参加可能: {mentions}"
                f"{comment_line}"
            )

        mark_reminder_sent(event["event_id"], event["date"])
