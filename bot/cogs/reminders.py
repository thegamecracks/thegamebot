#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import functools
import logging
from typing import TypedDict, cast, Literal

import asqlite
from dateutil.relativedelta import relativedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import converters, utils
from main import TheGameBot

logger = logging.getLogger('discord')


class ReminderContentTransformer(app_commands.Transformer):
    """Ensures the content is within the maximum length allowed."""
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str):
        max_length = Reminders.MAXIMUM_REMINDER_CONTENT
        over_size = len(value) - max_length

        if over_size > 0:
            raise app_commands.AppCommandError(
                f'The content cannot exceed {max_length} characters in length. '
                f'(+{over_size})'
            )

        return value


class ReminderIndexTransformer(app_commands.Transformer):
    """Verifies the index given for a reminder."""
    @classmethod
    def type(cls):
        return discord.AppCommandOptionType.integer

    @classmethod
    def min_value(cls):
        return 1

    @classmethod
    async def get_max_value(cls, bot: TheGameBot, user_id: int):
        async with bot.db.connect() as conn:
            return await query_reminder_count(conn, user_id)

    @classmethod
    async def autocomplete(cls, interaction: discord.Interaction, value: int):
        bot = cast(TheGameBot, interaction.client)
        max_value = await cls.get_max_value(bot, interaction.user.id)

        choices = [
            app_commands.Choice(name=str(n), value=n)
            for n in range(1, min(max_value, 25) + 1)
            # Maximum number of choices allowed is 25
        ]

        if not choices:
            choices.append(app_commands.Choice(
                name='You have no reminders to choose from.',
                value=1
            ))

        return choices

    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: int):
        bot = cast(TheGameBot, interaction.client)
        max_value = await cls.get_max_value(bot, interaction.user.id)

        if max_value == 0:
            raise app_commands.AppCommandError(
                'You have no reminders to choose from.'
            )
        elif not 1 <= value <= max_value:
            raise app_commands.AppCommandError(
                f'You must choose a reminder between 1 and {max_value}.'
            )

        return value - 1


class PartialReminderEntry(TypedDict):
    user_id: int
    channel_id: int
    due: datetime.datetime
    content: str


class ReminderEntry(PartialReminderEntry):
    reminder_id: int


def has_pending_reminder():
    """An application command check to ensure the user has one reminder."""
    async def predicate(interaction: discord.Interaction):
        client = cast(TheGameBot, interaction.client)

        async with client.db.connect() as conn:
            count = await query_reminder_count(conn, interaction.user.id)

            if not count:
                raise app_commands.AppCommandError(
                    'You currently have no pending reminders.'
                )

        return True

    return app_commands.check(predicate)


async def query_reminder_count(conn: asqlite.Connection, user_id: int) -> int:
    # NOTE: because guild_id can be None, the query has
    # to use "IS" to correctly match nulls
    query = 'SELECT COUNT(*) AS length FROM reminder WHERE user_id = ?'
    async with conn.execute(query, user_id) as c:
        row = await c.fetchone()
        return row['length']


class Reminders(commands.Cog, app_commands.Group):
    """Manage your reminders sent out by thegamebot."""

    MAXIMUM_REMINDERS = 10
    MAXIMUM_REMINDER_CONTENT = 250
    MINIMUM_REMINDER_TIME = 30

    NEAR_DUE = datetime.timedelta(minutes=11)
    # NOTE: should be just a bit longer than task loop

    def __init__(self, bot: TheGameBot):
        super().__init__(name='reminder')
        self.bot = bot
        self.reminder_tasks = {}  # reminder_id: Task
        self.send_reminders.start()

    def cog_unload(self):
        self.send_reminders.cancel()
        for task in self.reminder_tasks.values():
            task.cancel()

    async def add_reminder(self, entry: PartialReminderEntry):
        row = entry.copy()
        # NOTE: due to a bug with sqlite3.dbapi2.convert_timestamp,
        # timezones cannot be included when the microsecond
        # is omitted by isoformat()
        row['due'] = row['due'].astimezone(datetime.timezone.utc).replace(tzinfo=None)

        # SQLite rowid is aliased as reminder_id, so we don't need an extra query
        reminder_id = await self.bot.db.add_row('reminder', row)

        entry = cast(ReminderEntry, entry)
        entry['reminder_id'] = reminder_id

        return self.check_reminder(entry)

    @app_commands.command(name='list')
    @has_pending_reminder()
    async def _list(self, interaction: discord.Interaction):
        """View a list of your currently active reminders."""
        lines = []
        async with self.bot.db.connect() as conn:
            query = 'SELECT * FROM reminder WHERE user_id = ?'
            async with conn.execute(query, interaction.user.id) as c:
                i = 1
                while row := await c.fetchone():
                    due = row['due'].replace(tzinfo=datetime.timezone.utc)
                    lines.append('{}. <#{}> {}: {}'.format(
                        i, row['channel_id'],
                        discord.utils.format_dt(due, 'R'),
                        utils.truncate_message(row['content'], 40, max_lines=1)
                    ))
                    i += 1

        embed = discord.Embed(
            color=self.bot.get_user_color(interaction.user),
            description='\n'.join(lines)
        ).set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command()
    @app_commands.describe(
        index='The index of the reminder you want to show.'
    )
    async def show(
        self, interaction: discord.Interaction,
        index: app_commands.Transform[int, ReminderIndexTransformer]
    ):
        """Show the content and due date of a specific reminder."""
        async with self.bot.db.connect() as conn:
            query = 'SELECT * FROM reminder WHERE user_id = ? LIMIT 1 OFFSET ?'
            async with conn.execute(query, interaction.user.id, index) as c:
                row = await c.fetchone()

        due = row['due'].replace(tzinfo=datetime.timezone.utc)
        embed = discord.Embed(
            title=f'Reminder #{index + 1:,d}',
            description=row['content'],
            color=self.bot.get_user_color(interaction.user)
        ).add_field(
            name='Sends to',
            value='<#{}>'.format(row['channel_id'])
        ).add_field(
            name='Due in',
            value='{}\n({})'.format(
                utils.timedelta_string(
                    relativedelta(due, interaction.created_at),
                    inflector=self.bot.inflector
                ),
                discord.utils.format_dt(due, style='F')
            )
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command()
    @app_commands.describe(
        index='The index of the reminder you want to remove.'
    )
    async def remove(
        self, interaction: discord.Interaction,
        index: app_commands.Transform[int, ReminderIndexTransformer]
    ):
        """Remove one of your pending reminders."""
        async with self.bot.db.connect() as conn:
            query = 'SELECT reminder_id FROM reminder WHERE user_id = ? LIMIT 1 OFFSET ?'
            async with conn.execute(query, interaction.user.id, index) as c:
                reminder_id: int = (await c.fetchone())['reminder_id']

        await self.bot.db.delete_rows(
            'reminder', where={'reminder_id': reminder_id}
        )

        content = 'Successfully deleted your {} reminder!'.format(
            self.bot.inflector.ordinal(index + 1)
        )

        await interaction.response.send_message(content, ephemeral=True)

    @app_commands.command()
    @app_commands.checks.bot_has_permissions(send_messages=True)
    @app_commands.describe(
        when='The time at which this reminder should be sent.',
        content='The message to send with your reminder.'
    )
    async def add(
        self, interaction: discord.Interaction,
        when: converters.FutureDatetimeTransform,
        content: app_commands.Transform[str, ReminderContentTransformer]
    ):
        """Create a reminder in the current channel."""
        async with self.bot.db.connect() as conn:
            count = await query_reminder_count(conn, interaction.user.id)

        if count >= self.MAXIMUM_REMINDERS:
            return await interaction.response.send_message(
                'You have reached the maximum limit of '
                f'{self.MAXIMUM_REMINDERS} reminders.',
                ephemeral=True
            )

        td = when - interaction.created_at
        if td.total_seconds() < 0:
            return await interaction.response.send_message(
                'You cannot create a reminder for the past.',
                ephemeral=True
            )
        elif td.total_seconds() < self.MINIMUM_REMINDER_TIME:
            return await interaction.response.send_message(
                'You must set a reminder lasting for at '
                f'least {self.MINIMUM_REMINDER_TIME} seconds.',
                ephemeral=True
            )

        await self.add_reminder({
            'user_id': interaction.user.id,
            'channel_id': cast(int, interaction.channel_id),
            'due': when,
            'content': content
        })

        await interaction.response.send_message(
            'Added your {} reminder for {} in this channel!'.format(
                self.bot.inflector.ordinal(count + 1),
                discord.utils.format_dt(when, style='F')
            ),
            ephemeral=True
        )

    @app_commands.command()
    @app_commands.describe(
        mode='Moderators can set this to global to remove reminders from other members.',
        channel='The channel to clear reminders from. Defaults to the current channel.'
    )
    async def clear(
        self, interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        mode: Literal['personal', 'global'] = 'personal'
    ):
        """Clear your reminders in the given channel."""
        channel = channel or interaction.channel
        channel_reference = 'this channel'
        if channel != interaction.channel:
            channel_reference = channel.mention

        user_only = mode == 'personal'
        if not user_only and not interaction.permissions.manage_messages:
            await interaction.response.send_message(
                'You must have the Manage Messages permission to clear '
                'reminders from other members!',
                ephemeral=True
            )

        # Determine the SQL queries to use
        if user_only:
            where_conditions = 'WHERE user_id = ? AND channel_id = ?'
            params = (interaction.user.id, channel.id)
        else:
            where_conditions = 'WHERE channel_id = ?'
            params = (channel.id,)

        # Check that there are any reminders in the channel to delete
        async with self.bot.db.connect() as conn:
            query = f'SELECT COUNT(*) FROM reminder {where_conditions}'
            async with conn.execute(query, params) as c:
                count: int = (await c.fetchone())[0]

        if count == 0:
            subject = 'You have' if user_only else 'There are'
            return await interaction.response.send_message(
                f'{subject} no reminders to delete in {channel_reference}!',
                ephemeral=True
            )

        # Actually delete the reminders
        async with self.bot.db.connect(writing=True) as conn:
            query = f'DELETE FROM reminder {where_conditions}'
            await conn.execute(query, params)

        content = 'Successfully cleared{your} {n} {reminders} from {ref}!'.format(
            your=' your' * user_only,
            n=count,
            reminders=self.bot.inflector.plural('reminder', count),
            ref=channel_reference
        )

        await interaction.response.send_message(content, ephemeral=True)

    def check_reminder(self, entry: ReminderEntry, *, now=None):
        """Starts an :class:`asyncio.Task` to handle sending a reminder
        if the given reminder is nearing due.

        :returns bool: Indicates whether the task was created or not.

        """
        if entry['reminder_id'] in self.reminder_tasks:
            # Task already exists; skip
            return False
        elif now is None:
            now = discord.utils.utcnow()

        td = entry['due'] - now
        is_soon = td < self.NEAR_DUE
        if is_soon:
            self.create_reminder_task(td, entry)

        return is_soon

    def create_reminder_task(self, td, entry: ReminderEntry):
        """Adds a reminder task to the bot loop and logs it."""
        reminder_id = entry['reminder_id']
        task = self.bot.loop.create_task(self.reminder_coro(entry))
        self.reminder_tasks[reminder_id] = task
        task.add_done_callback(functools.partial(
            self.reminder_coro_remove_task, reminder_id
        ))

        logger.debug(
            'Reminders: created reminder task {} '
            'for {}, due in {}'.format(
                reminder_id, entry['user_id'], td
            )
        )

        return task

    def reminder_coro_remove_task(self, reminder_id: int, task: asyncio.Task):
        self.reminder_tasks.pop(reminder_id, None)

    async def reminder_coro(self, entry: ReminderEntry):
        """Schedules a reminder to be sent to the user."""
        async def remove_entry(log: str):
            logger.debug(log)
            await self.bot.db.delete_rows(
                'reminder',
                where={'reminder_id': reminder_id}
            )

        # Wait until the reminder is due
        reminder_id = entry['reminder_id']
        seconds = (entry['due'] - discord.utils.utcnow()).total_seconds()
        await asyncio.sleep(seconds)

        # Do some last-second checks before sending reminder
        row = await self.bot.db.get_one(
            'reminder', 'reminder_id',
            where={'reminder_id': reminder_id}
        )

        if row is None:
            return await remove_entry(
                f'Reminders: canceled reminder {reminder_id}: '
                'reminder was deleted during wait'
            )

        channel = self.bot.get_channel(entry['channel_id'])
        if channel is None:
            # Might be a deleted channel but could also be a DM channel,
            # the latter being resolvable with fetch_channel()
            try:
                channel = await self.bot.fetch_channel(entry['channel_id'])
            except (discord.NotFound, discord.Forbidden):
                return await remove_entry(
                    f'Reminders: canceled reminder {reminder_id}: '
                    'channel no longer exists'
                )

        if getattr(channel, 'guild', None) is not None:
            # Check if member is still in the guild
            member = await utils.getch_member(channel.guild, entry['user_id'])
            if member is None:
                return await remove_entry(
                    f'Reminders: canceled reminder {reminder_id}: '
                    'member is no longer in the guild'
                )

        # NOTE: multiple API calls could be made above if
        # member/user left several reminders

        description = '<@{mention}> **{due}{is_overdue}**\n{content}'.format(
            mention=entry['user_id'],
            due=discord.utils.format_dt(entry['due'], style='F'),
            is_overdue=' (overdue)' * (seconds < 0),
            content=entry['content']
        )

        # Now we can try to send the reminder
        try:
            await channel.send(description)
        except discord.Forbidden as e:
            await remove_entry(
                f'Reminders: failed to send reminder {reminder_id}: '
                f'was forbidden from sending: {e}'
            )
        except discord.HTTPException as e:
            # This may be a fault on server end, log this with higher
            # severity and allow the send_reminders loop to retry
            logger.warning(
                f'Reminders: failed to send reminder {reminder_id}: '
                f'HTTPException occurred: {e}'
            )
        else:
            await remove_entry(f'Reminders: successfully sent reminder {reminder_id}')

    @tasks.loop(minutes=10)
    async def send_reminders(self):
        """Periodically queries the database for reminders and
        spins up reminder tasks as needed.
        """
        now = discord.utils.utcnow()

        async for entry in self.bot.db.yield_rows('reminder'):
            entry = cast(ReminderEntry, dict(entry))
            entry['due'] = entry['due'].replace(tzinfo=datetime.timezone.utc)
            self.check_reminder(entry, now=now)

    @send_reminders.before_loop
    async def before_send_reminders(self):
        await self.bot.wait_until_ready()


async def setup(bot: TheGameBot):
    await bot.add_cog(Reminders(bot))
