from database import (
    are_all_event_groups_closed,
    get_dates,
    get_result_message,
    get_schedule_message,
    mark_event_closed,
    mark_event_group_closed,
)
from embeds import create_result_embed
from views import OpenScheduleView


# =========================
# 募集終了処理
# =========================
# 手動 /close と自動締切の両方で使います。


async def close_schedule(client, guild, event_id):
    guild_id = guild.id
    dates = get_dates(event_id, guild_id)
    schedule_data = get_schedule_message(event_id, guild_id)
    result_data = get_result_message(event_id, guild_id)

    if not schedule_data and not result_data:
        return False

    if schedule_data:
        channel_id, message_id = schedule_data
        channel = client.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.edit(
                content=f"日程調整: {event_id}\n募集は終了しました。",
                view=OpenScheduleView(event_id, guild_id, dates, closed=True),
            )

    if result_data:
        channel_id, message_id = result_data
        channel = client.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.edit(
                embed=create_result_embed(guild, event_id, dates),
                view=None,
            )

    mark_event_closed(event_id, guild_id)
    return True


async def close_schedule_group(client, guild, event_id, group_index):
    guild_id = guild.id
    dates = get_dates(event_id, guild_id)
    schedule_data = get_schedule_message(event_id, guild_id)
    result_data = get_result_message(event_id, guild_id)

    if not schedule_data and not result_data:
        return False

    mark_event_group_closed(event_id, group_index, guild_id)
    all_closed = are_all_event_groups_closed(event_id, guild_id)

    if all_closed:
        mark_event_closed(event_id, guild_id)

    if schedule_data:
        channel_id, message_id = schedule_data
        channel = client.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            content = (
                f"日程調整: {event_id}\n募集は終了しました。"
                if all_closed
                else f"日程調整: {event_id}\n締切済みの日程範囲があります。"
            )
            await message.edit(
                content=content,
                view=OpenScheduleView(event_id, guild_id, dates, closed=all_closed),
            )

    if result_data:
        channel_id, message_id = result_data
        channel = client.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.edit(
                embed=create_result_embed(guild, event_id, dates),
                view=None,
            )

    return True
