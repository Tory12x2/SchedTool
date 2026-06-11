import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from close_service import close_schedule_group
from config import WEEKDAYS
from database import (
    get_active_auto_schedule_settings,
    get_notification_mention_enabled,
    get_open_event_groups_with_deadlines,
    get_participant_role_id,
    get_reminder_settings,
    get_result_channel_id,
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
    for auto_settings in get_active_auto_schedule_settings():
        schedule_settings = get_schedule_settings(auto_settings["guild_id"])

        if not auto_settings or not auto_settings["active"] or not schedule_settings:
            continue

        today = datetime.now(TIMEZONE).date()
        next_start_date = datetime.strptime(
            auto_settings["next_start_date"],
            "%Y-%m-%d",
        ).date()
        post_date = next_start_date - timedelta(days=auto_settings["lead_days"])

        if today < post_date:
            continue

        guild = client.get_guild(auto_settings["guild_id"])
        channel = client.get_channel(auto_settings["channel_id"])
        if not guild or not channel:
            continue

        await create_schedule(
            client,
            guild,
            channel,
            schedule_settings["event_name"],
            datetime.combine(next_start_date, datetime.min.time()),
            schedule_settings["days"],
        )

        following_start_date = next_start_date + timedelta(days=schedule_settings["days"])
        update_auto_schedule_next_start(
            following_start_date.strftime("%Y-%m-%d"),
            auto_settings["guild_id"],
        )


async def run_deadline_close_once(client):
    now = datetime.now(TIMEZONE)

    for event in get_open_event_groups_with_deadlines():
        guild = client.get_guild(event["guild_id"])
        if not guild:
            continue

        deadline_at = datetime.strptime(event["deadline_at"], "%Y-%m-%d %H:%M")
        deadline_at = deadline_at.replace(tzinfo=TIMEZONE)

        if now >= deadline_at:
            await close_schedule_group(
                client,
                guild,
                event["event_id"],
                event["group_index"],
            )


async def run_available_day_reminder_once(client):
    now = datetime.now(TIMEZONE)

    for guild in client.guilds:
        reminder_settings = get_reminder_settings(guild.id)

        if now.hour < reminder_settings["hour"]:
            continue

        target_date = now.date() + timedelta(days=reminder_settings["days_before"])
        target_value = target_date.strftime("%Y%m%d")

        channel = client.get_channel(get_result_channel_id(guild.id))
        if not channel:
            continue

        member_ids = get_non_bot_member_ids(guild)
        if not member_ids:
            continue

        for event in get_unnotified_event_dates(target_value, guild.id):
            available_users = get_users(
                event["event_id"],
                event["date"],
                "available",
                guild.id,
            )
            unavailable_users = get_users(
                event["event_id"],
                event["date"],
                "no",
                guild.id,
            )
            maybe_users = get_users(
                event["event_id"],
                event["date"],
                "maybe",
                guild.id,
            )
            available_users &= member_ids
            unavailable_users &= member_ids
            maybe_users &= member_ids
            answered_users = available_users | maybe_users | unavailable_users
 
            if member_ids.issubset(answered_users) and not unavailable_users:
                await channel.send(
                    build_available_day_reminder_text(
                        event["event_id"],
                        target_date,
                        available_users,
                        maybe_users,
                        reminder_settings["comment"],
                        get_notification_mention_enabled(guild.id),
                    )
                )
                mark_reminder_sent(event["event_id"], event["date"], guild.id)


def get_participant_members(guild):
    role_id = get_participant_role_id(guild.id)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return [member for member in role.members if not member.bot]

    return [member for member in guild.members if not member.bot]


def get_participant_member_ids(guild):
    return {member.id for member in get_participant_members(guild)}


def get_non_bot_member_ids(guild):
    return get_participant_member_ids(guild)


def build_available_day_reminder_text(
    event_id,
    target_date,
    available_users,
    maybe_users,
    comment,
    mention_enabled=True,
):
    weekday = WEEKDAYS[target_date.weekday()]
    label = target_date.strftime("%m/%d") + f"({weekday})"
    if mention_enabled:
        available_text = " ".join(f"<@{user_id}>" for user_id in sorted(available_users))
        available_text = available_text or "なし"
    else:
        available_text = f"{len(available_users)}人" if available_users else "なし"

    maybe_count = len(maybe_users)
    probability = 100 * (0.5 ** maybe_count)
    comment_line = f"\n{comment}" if comment else ""

    return (
        f"参加可能日のお知らせ\n"
        f"イベント: {event_id}\n"
        f"日程: {label}\n"
        f"参加可能: {available_text}\n"
        f"保留: {maybe_count}人\n"
        f"決行確率: {probability:g}%"
        f"{comment_line}"
    )
