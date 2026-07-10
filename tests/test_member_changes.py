import asyncio
import unittest
from datetime import datetime

import discord

from auto_scheduler import (
    build_available_day_reminder_messages,
    run_participant_growth_once,
)
from database import (
    clear_participant_role_id,
    delete_event,
    initialize_event_participants,
    save_event_dates,
    save_event_settings,
    save_deadline_settings,
    save_participant_role_id,
    save_reminder_settings,
    save_schedule_message,
    set_user_status,
    sync_event_participants,
    get_deadline_settings,
)
from embeds import (
    add_chunked_field,
    create_monthly_table_embed,
    get_monthly_table_page_count,
)
from participants import can_member_answer, get_participant_members
from schedule_service import build_deadline_at, build_deadline_text


class FakePermissions:
    def __init__(self, administrator=False):
        self.administrator = administrator


class FakeMember:
    def __init__(self, user_id, roles=None, administrator=False, bot=False):
        self.id = user_id
        self.roles = roles or []
        self.guild_permissions = FakePermissions(administrator)
        self.bot = bot
        self.display_name = f"member-{user_id}"


class FakeRole:
    def __init__(self, role_id, members=None):
        self.id = role_id
        self.members = members or []


class FakeGuild:
    def __init__(self, guild_id, members, roles=None):
        self.id = guild_id
        self.members = members
        self.roles = {role.id: role for role in roles or []}

    def get_role(self, role_id):
        return self.roles.get(role_id)

    def get_member(self, user_id):
        return next((member for member in self.members if member.id == user_id), None)


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.messages = []

    async def send(self, content, **kwargs):
        self.messages.append(content)


class FakeClient:
    def __init__(self, guild, channel):
        self.guilds = [guild]
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel if self.channel.id == channel_id else None


class MemberChangeTests(unittest.TestCase):
    def test_participant_growth_detects_add_and_readd(self):
        guild_id = 91001
        event_id = "member_test_20300101"
        delete_event(event_id, guild_id)

        self.assertEqual(sync_event_participants(event_id, {1, 2}, guild_id), set())
        self.assertEqual(sync_event_participants(event_id, {1, 2, 3}, guild_id), {3})
        self.assertEqual(sync_event_participants(event_id, {1, 2}, guild_id), set())
        self.assertEqual(sync_event_participants(event_id, {1, 2, 3}, guild_id), {3})

        delete_event(event_id, guild_id)

    def test_role_limits_answers_but_allows_administrator(self):
        guild_id = 91002
        role = FakeRole(700)
        included = FakeMember(1, roles=[role])
        excluded = FakeMember(2)
        administrator = FakeMember(3, administrator=True)
        role.members = [included]
        guild = FakeGuild(guild_id, [included, excluded, administrator], [role])
        save_participant_role_id(role.id, guild_id)

        self.assertEqual(get_participant_members(guild), [included])
        self.assertTrue(can_member_answer(guild, included))
        self.assertFalse(can_member_answer(guild, excluded))
        self.assertTrue(can_member_answer(guild, administrator))

    def test_role_notification_uses_one_role_mention(self):
        messages = build_available_day_reminder_messages(
            "event",
            datetime(2030, 1, 1),
            {1, 2},
            {3},
            "",
            mention_enabled=True,
            participant_role_id=700,
        )

        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("<@&700>"))
        self.assertIn("参加可能: 2人", messages[0])
        self.assertIn("保留: 1人", messages[0])
        self.assertNotIn("<@1>", messages[0])

    def test_large_notification_is_split_below_discord_limit(self):
        messages = build_available_day_reminder_messages(
            "event",
            datetime(2030, 1, 1),
            set(range(1, 31)),
            set(range(31, 41)),
            "comment",
            mention_enabled=True,
        )

        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= 2000 for message in messages))

    def test_embed_fields_are_split_below_field_limit(self):
        embed = discord.Embed(title="test")
        add_chunked_field(embed, "members", ["x" * 200 for _ in range(12)])

        self.assertGreater(len(embed.fields), 1)
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))

    def test_monthly_table_paginates_large_member_list(self):
        guild_id = 91003
        event_id = "monthly_test_20300101"
        members = [FakeMember(user_id) for user_id in range(1, 51)]
        guild = FakeGuild(guild_id, members)
        dates = [
            {"label": f"01/{day:02d}", "value": f"203001{day:02d}"}
            for day in range(1, 11)
        ]
        clear_participant_role_id(guild_id)
        delete_event(event_id, guild_id)

        for date in dates:
            for member in members[:24]:
                set_user_status(event_id, date["value"], member.id, "available", guild_id)

        embed = create_monthly_table_embed(guild, event_id, dates, page=0)
        self.assertEqual(get_monthly_table_page_count(guild), 3)
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))
        self.assertLessEqual(len(embed), 6000)

        delete_event(event_id, guild_id)

    def test_daily_scan_mentions_only_added_members(self):
        guild_id = 91004
        event_id = "growth_test_20300101"
        channel = FakeChannel(81004)
        initial_member = FakeMember(1)
        added_member = FakeMember(2)
        guild = FakeGuild(guild_id, [initial_member, added_member])
        client = FakeClient(guild, channel)

        clear_participant_role_id(guild_id)
        delete_event(event_id, guild_id)
        save_reminder_settings(1, 0, "", guild_id)
        save_event_dates(
            event_id,
            [{"label": "01/01", "value": "20300101"}],
            guild_id,
        )
        save_event_settings(event_id, "2030-01-01 23:59", False, guild_id)
        save_schedule_message(event_id, channel.id, 9100401, guild_id)
        initialize_event_participants(event_id, {initial_member.id}, guild_id)

        asyncio.run(run_participant_growth_once(client))

        self.assertEqual(len(channel.messages), 1)
        self.assertIn(f"<@{added_member.id}>", channel.messages[0])
        self.assertNotIn(f"<@{initial_member.id}>", channel.messages[0])

        delete_event(event_id, guild_id)

    def test_deadline_settings_are_saved_per_guild(self):
        guild_id = 91005

        save_deadline_settings(3, 22, guild_id)

        self.assertEqual(
            get_deadline_settings(guild_id),
            {"days_before": 3, "hour": 22},
        )
        self.assertEqual(build_deadline_text(3, 22), "各日程の3日前22時（開始日が当日の場合は当日23:59）")

    def test_current_deadline_default_stays_compatible(self):
        deadline = build_deadline_at("20300110", 2, 24)

        self.assertEqual(deadline.strftime("%Y-%m-%d %H:%M"), "2030-01-09 00:00")
        self.assertEqual(build_deadline_text(2, 24), "各日程の2日前24時（開始日が当日の場合は当日23:59）")


if __name__ == "__main__":
    unittest.main()
