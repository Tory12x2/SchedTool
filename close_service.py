from database import (
    get_dates,
    get_result_message,
    get_schedule_message,
    mark_event_closed,
)
from embeds import create_result_embed
from views import OpenScheduleView


# =========================
# 募集終了処理
# =========================
# 手動 /close と自動締切の両方で使います。


async def close_schedule(client, guild, event_id):
    dates = get_dates(event_id)
    schedule_data = get_schedule_message(event_id)
    result_data = get_result_message(event_id)

    if not schedule_data and not result_data:
        return False

    if schedule_data:
        channel_id, message_id = schedule_data
        channel = client.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.edit(
                content=f"日程調整: {event_id}\n募集は終了しました。",
                view=OpenScheduleView(event_id, dates, closed=True),
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

    mark_event_closed(event_id)
    return True
