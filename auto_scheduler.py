import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord

from close_service import close_schedule_group
from config import WEEKDAYS
from database import (
    get_active_auto_schedule_settings,
    get_notification_mention_enabled,
    get_open_events_with_deadlines,
    get_open_event_groups_with_deadlines,
    get_participant_role_id,
    get_reminder_settings,
    get_result_channel_id,
    get_schedule_message,
    get_schedule_settings,
    get_unnotified_event_dates,
    get_users,
    has_missing_role_alert,
    has_participant_scan_run,
    mark_missing_role_alert,
    mark_event_participants_inactive,
    mark_participant_scan_run,
    mark_reminder_sent,
    sync_event_participants,
    update_auto_schedule_next_start,
)
from participants import (
    PARTICIPANT_PAGE_SIZE,
    get_participant_member_ids,
    is_participant_role_missing,
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
            await run_participant_growth_once(client)
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

        try:
            await create_schedule(
                client,
                guild,
                channel,
                schedule_settings["event_name"],
                datetime.combine(next_start_date, datetime.min.time()),
                schedule_settings["days"],
            )
        except RuntimeError as error:
            print(f"{guild.name}: 自動作成を保留しました / {error}")
            continue

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

        if is_participant_role_missing(guild):
            await send_missing_role_alert_once(client, guild)
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
                messages = build_available_day_reminder_messages(
                    event["event_id"],
                    target_date,
                    available_users,
                    maybe_users,
                    reminder_settings["comment"],
                    get_notification_mention_enabled(guild.id),
                    get_participant_role_id(guild.id),
                )
                for message in messages:
                    await channel.send(
                        message,
                        allowed_mentions=discord.AllowedMentions(
                            everyone=False,
                            users=True,
                            roles=True,
                        ),
                    )
                mark_reminder_sent(event["event_id"], event["date"], guild.id)


async def run_participant_growth_once(client):
    now = datetime.now(TIMEZONE)
    scan_date = now.date().isoformat()

    for guild in client.guilds:
        reminder_settings = get_reminder_settings(guild.id)
        if now.hour < reminder_settings["hour"]:
            continue
        if has_participant_scan_run(guild.id, scan_date):
            continue

        if is_participant_role_missing(guild):
            await send_missing_role_alert_once(client, guild)
            mark_participant_scan_run(guild.id, scan_date)
            continue

        current_user_ids = get_participant_member_ids(guild)
        guild_events = [
            event
            for event in get_open_events_with_deadlines()
            if event["guild_id"] == guild.id
        ]

        for event in guild_events:
            schedule_message = get_schedule_message(event["event_id"], guild.id)
            if not schedule_message:
                continue

            channel_id, message_id = schedule_message
            channel = client.get_channel(channel_id)
            if not channel:
                continue

            added_user_ids = sync_event_participants(
                event["event_id"],
                current_user_ids,
                guild.id,
            )
            if not added_user_ids:
                continue

            link = f"https://discord.com/channels/{guild.id}/{channel_id}/{message_id}"
            for user_ids in chunk_user_ids(added_user_ids):
                mentions = " ".join(f"<@{user_id}>" for user_id in user_ids)
                try:
                    await channel.send(
                        "日程回答のお願い\n\n"
                        f"{mentions}\n"
                        f"「{event['event_id']}」の回答を受け付けています。\n"
                        f"日程調整メッセージから参加可否を回答してください。\n{link}",
                        allowed_mentions=discord.AllowedMentions(
                            everyone=False,
                            users=True,
                            roles=False,
                        ),
                    )
                except discord.DiscordException:
                    mark_event_participants_inactive(
                        event["event_id"],
                        added_user_ids,
                        guild.id,
                    )
                    raise

        mark_participant_scan_run(guild.id, scan_date)


async def send_missing_role_alert_once(client, guild, deleted_role_id=None):
    role_id = deleted_role_id or get_participant_role_id(guild.id)
    if not role_id or has_missing_role_alert(guild.id, role_id):
        return

    channel = client.get_channel(get_result_channel_id(guild.id))
    if not channel:
        return

    await channel.send(
        "SchedToolで設定されていた参加予定者ロールが見つかりません。\n"
        "/participant_role_setting で再設定するか、"
        "/participant_role_clear で全メンバー対象に戻してください。\n"
        "再設定されるまで日程の自動作成と通知を停止します。"
    )
    mark_missing_role_alert(guild.id, role_id)


def chunk_user_ids(user_ids, size=PARTICIPANT_PAGE_SIZE):
    ordered = sorted(user_ids)
    return [ordered[index : index + size] for index in range(0, len(ordered), size)]


def get_non_bot_member_ids(guild):
    return get_participant_member_ids(guild)


def build_available_day_reminder_messages(
    event_id,
    target_date,
    available_users,
    maybe_users,
    comment,
    mention_enabled=True,
    participant_role_id=None,
):
    if participant_role_id and mention_enabled:
        return [
            build_available_day_reminder_text(
                event_id,
                target_date,
                available_users,
                maybe_users,
                comment,
                mention_enabled=False,
                prefix=f"<@&{participant_role_id}>\n\n",
            )
        ]

    participant_count = len(available_users | maybe_users)
    if not mention_enabled or participant_count <= PARTICIPANT_PAGE_SIZE:
        return [
            build_available_day_reminder_text(
                event_id,
                target_date,
                available_users,
                maybe_users,
                comment,
                mention_enabled=mention_enabled,
            )
        ]

    messages = [
        build_available_day_reminder_text(
            event_id,
            target_date,
            available_users,
            maybe_users,
            comment,
            mention_enabled=False,
        )
    ]
    for label, user_ids in (("参加可能", available_users), ("保留", maybe_users)):
        for user_id_chunk in chunk_user_ids(user_ids):
            mentions = " ".join(f"<@{user_id}>" for user_id in user_id_chunk)
            messages.append(f"{label}: {mentions}")
    return messages


def build_available_day_reminder_text(
    event_id,
    target_date,
    available_users,
    maybe_users,
    comment,
    mention_enabled=True,
    prefix="",
):
    weekday = WEEKDAYS[target_date.weekday()]
    label = target_date.strftime("%m/%d") + f"({weekday})"
    if mention_enabled:
        available_text = " ".join(f"<@{user_id}>" for user_id in sorted(available_users))
        available_text = available_text or "なし"
        maybe_text = " ".join(f"<@{user_id}>" for user_id in sorted(maybe_users))
        maybe_text = maybe_text or "なし"
    else:
        available_text = f"{len(available_users)}人" if available_users else "なし"
        maybe_text = f"{len(maybe_users)}人" if maybe_users else "なし"

    maybe_count = len(maybe_users)
    probability = 100 * (0.5 ** maybe_count)
    comment_line = f"\n{comment[:500]}" if comment else ""

    return (
        f"{prefix}開催日のお知らせ\n"
        f"イベント: {event_id}\n"
        f"日程: {label}\n"
        f"参加可能: {available_text}\n"
        f"保留: {maybe_text}\n"
        f"開催確率: {probability:g}%…保留の方は確定次第コメントください"
        f"{comment_line}"
    )
